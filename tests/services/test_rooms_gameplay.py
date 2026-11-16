"""Unit tests for gameplay state persisted outside the relational schema."""

import asyncio
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models import Card, Room, RoomPlayer, Submission, User
from app.schemas.room import RoomCreateRequest, RoomJoinRequest
from app.services.rooms import RECONNECT_WINDOW_TTL, RoomGameError, RoomService


class _FakeRedisClient:
    """Minimal async Redis double for JSON gameplay state keys."""

    def __init__(self):
        self._values: dict[str, str] = {}

    async def get(self, key: str):
        return self._values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self._values[key] = value

    async def delete(self, *keys: str):
        removed = 0
        for key in keys:
            if key in self._values:
                self._values.pop(key)
                removed += 1
        return removed


async def _create_users(session, total: int, prefix: str) -> list[User]:
    """Create and flush test users for gameplay flows."""
    users = [
        User(
            username=f"{prefix}_user_{idx}",
            email=f"{prefix}_{idx}@example.com",
            password_hash="hash",
        )
        for idx in range(1, total + 1)
    ]
    session.add_all(users)
    await session.flush()
    return users


async def _create_room_with_players(session, users: list[User]) -> Room:
    """Create in-progress-capable room with ordered players."""
    room = Room(
        code="GAME01",
        host_id=users[0].id,
        room_kind="private",
        status="lobby",
        max_players=6,
        winning_score=2,
        round_timer_seconds=90,
        card_pool_mode="default_only",
    )
    session.add(room)
    await session.flush()

    for index, user in enumerate(users, start=1):
        session.add(
            RoomPlayer(
                room_id=room.id,
                player_id=user.id,
                join_order=index,
                score=0,
                is_connected=True,
            )
        )

    await session.flush()
    return room


async def _seed_cards(session, *, black_cards: list[tuple[str, int]], white_total: int) -> None:
    """Seed deterministic black and white cards for gameplay tests."""
    session.add_all(
        [Card(type="black", text=text, pick=pick, is_default=True) for text, pick in black_cards]
    )
    session.add_all(
        [Card(type="white", text=f"White {idx}", is_default=True) for idx in range(1, white_total + 1)]
    )
    await session.flush()


def test_start_game_deals_ten_cards_per_player_into_redis(test_db):
    """Starting a game persists player hands and remaining white deck in Redis."""

    async def _run():
        async with test_db() as session:
            redis = _FakeRedisClient()
            users = await _create_users(session, 3, "deal")
            room = await _create_room_with_players(session, users)
            await _seed_cards(session, black_cards=[("Prompt _", 1)], white_total=35)

            outcome = await RoomService.start_game(session, room, users[0].id, redis)

            assert outcome["round_number"] == 1
            all_hand_cards: set[str] = set()
            for user in users:
                hand = await RoomService.get_player_hand(redis, room.id, user.id)
                assert len(hand) == 10
                all_hand_cards.update(str(card_id) for card_id in hand)

            assert len(all_hand_cards) == 30
            remaining_deck = await RoomService.get_white_deck(redis, room.id)
            assert len(remaining_deck) == 5

    asyncio.run(_run())


def test_submit_cards_rejects_card_not_in_players_hand(test_db):
    """Submission is rejected when requested white card is not owned by the player."""

    async def _run():
        async with test_db() as session:
            redis = _FakeRedisClient()
            users = await _create_users(session, 3, "ownership")
            room = await _create_room_with_players(session, users)
            await _seed_cards(session, black_cards=[("Prompt _", 1)], white_total=35)

            outcome = await RoomService.start_game(session, room, users[0].id, redis)
            await session.flush()

            invalid_card_id = (await RoomService.get_white_deck(redis, room.id))[0]

            try:
                await RoomService.submit_cards(
                    session,
                    room,
                    users[1].id,
                    outcome["round"].id,
                    [invalid_card_id],
                    redis,
                )
                assert False, "Expected RoomGameError for card not in player hand"
            except RoomGameError as exc:
                assert exc.code == "INVALID_CARD_SELECTION"
                assert exc.details == {"reason": "card_not_in_hand"}

    asyncio.run(_run())


def test_pick_winner_refills_hands_for_next_round(test_db):
    """Next round restores non-czar players to 10 cards after submissions."""

    async def _run():
        async with test_db() as session:
            redis = _FakeRedisClient()
            users = await _create_users(session, 3, "refill")
            room = await _create_room_with_players(session, users)
            await _seed_cards(
                session,
                black_cards=[("Prompt _", 1), ("Prompt again _", 1)],
                white_total=40,
            )

            start = await RoomService.start_game(session, room, users[0].id, redis)
            round_one = start["round"]
            hand_one = await RoomService.get_player_hand(redis, room.id, users[1].id)
            hand_two = await RoomService.get_player_hand(redis, room.id, users[2].id)

            await RoomService.submit_cards(session, room, users[1].id, round_one.id, [hand_one[0]], redis)
            judging = await RoomService.submit_cards(session, room, users[2].id, round_one.id, [hand_two[0]], redis)
            assert judging["transition"] == "judging"

            winning_submission_id = next(
                submission["submission_id"]
                for submission in judging["submissions"]
                if submission["white_card_texts"]
            )
            result = await RoomService.pick_winner(
                session,
                room,
                users[0].id,
                round_one.id,
                winning_submission_id,
                redis,
            )

            assert result["next_round"] is not None
            assert len(await RoomService.get_player_hand(redis, room.id, users[0].id)) == 10
            assert len(await RoomService.get_player_hand(redis, room.id, users[1].id)) == 10
            assert len(await RoomService.get_player_hand(redis, room.id, users[2].id)) == 10

    asyncio.run(_run())


def test_handle_player_timeout_skips_waiting_round_when_czar_times_out(test_db):
    """Timed-out active czar is removed and gameplay advances to the next round."""

    async def _run():
        async with test_db() as session:
            redis = _FakeRedisClient()
            users = await _create_users(session, 4, "timeout_czar")
            room = await _create_room_with_players(session, users)
            await _seed_cards(
                session,
                black_cards=[("Timeout prompt _", 1), ("Timeout next _", 1)],
                white_total=50,
            )

            started = await RoomService.start_game(session, room, users[0].id, redis)
            timeout_outcome = await RoomService.handle_player_timeout(
                session,
                redis,
                room.id,
                users[0].id,
            )

            assert timeout_outcome["czar_timed_out"] is True
            assert timeout_outcome["skipped_round_id"] == started["round"].id
            assert timeout_outcome["next_round"] is not None
            assert timeout_outcome["next_round"].round_number == started["round"].round_number + 1
            assert timeout_outcome["next_round"].czar_id != users[0].id

            players = await RoomService._ordered_room_player_rows(session, room.id)
            remaining_player_ids = {player.player_id for player in players}
            assert users[0].id not in remaining_player_ids

            timed_out_hand = await RoomService.get_player_hand(redis, room.id, users[0].id)
            assert timed_out_hand == []

    asyncio.run(_run())

async def _play_round_to_judging(session, redis, room, users, round_obj) -> dict:
    """Submit one card for every non-czar player and return the judging outcome."""
    outcome = None
    for user in users:
        if user.id == round_obj.czar_id:
            continue
        hand = await RoomService.get_player_hand(redis, room.id, user.id)
        outcome = await RoomService.submit_cards(
            session, room, user.id, round_obj.id, [hand[0]], redis
        )
    assert outcome["transition"] == "judging"
    return outcome


def test_refill_reshuffles_played_cards_when_white_deck_runs_out(test_db):
    """A short deck recycles discards instead of failing the czar's pick."""

    async def _run():
        async with test_db() as session:
            redis = _FakeRedisClient()
            users = await _create_users(session, 3, "recycle")
            room = await _create_room_with_players(session, users)
            # 30 cards are dealt, leaving 1 in the deck while 2 are needed next round.
            await _seed_cards(
                session,
                black_cards=[("Prompt _", 1), ("Prompt again _", 1)],
                white_total=31,
            )

            start = await RoomService.start_game(session, room, users[0].id, redis)
            judging = await _play_round_to_judging(session, redis, room, users, start["round"])

            result = await RoomService.pick_winner(
                session,
                room,
                users[0].id,
                start["round"].id,
                judging["submissions"][0]["submission_id"],
                redis,
            )

            assert result["next_round"] is not None
            hands = [await RoomService.get_player_hand(redis, room.id, user.id) for user in users]
            assert [len(hand) for hand in hands] == [10, 10, 10]
            # No card may be held twice after the reshuffle.
            assert len({card for hand in hands for card in hand}) == 30

    asyncio.run(_run())


def test_start_game_allowed_for_worker_locked_matchmaking_room(test_db):
    """A random lobby the worker flipped to in_progress (no rounds yet) can still be started."""

    async def _run():
        async with test_db() as session:
            redis = _FakeRedisClient()
            users = await _create_users(session, 3, "locked")
            room = await _create_room_with_players(session, users)
            room.room_kind = "random"
            room.status = "in_progress"
            await _seed_cards(session, black_cards=[("Prompt _", 1)], white_total=35)

            outcome = await RoomService.start_game(session, room, users[0].id, redis)
            assert outcome["round_number"] == 1

            # Once a round exists the room is a running game and cannot be restarted.
            try:
                await RoomService.start_game(session, room, users[0].id, redis)
                assert False, "Expected STATE_CONFLICT for a running game"
            except RoomGameError as exc:
                assert exc.code == "STATE_CONFLICT"

    asyncio.run(_run())


def test_pick_winner_resolves_round_when_winning_player_left(test_db):
    """Picking a submission whose author was removed completes the round without scoring."""

    async def _run():
        async with test_db() as session:
            redis = _FakeRedisClient()
            users = await _create_users(session, 4, "left_winner")
            room = await _create_room_with_players(session, users)
            await _seed_cards(
                session,
                black_cards=[("Prompt _", 1), ("Prompt again _", 1)],
                white_total=60,
            )

            start = await RoomService.start_game(session, room, users[0].id, redis)
            await _play_round_to_judging(session, redis, room, users, start["round"])

            await RoomService.handle_player_timeout(session, redis, room.id, users[1].id)
            departed_submission = (
                await session.execute(
                    select(Submission).where(Submission.player_id == users[1].id)
                )
            ).scalar_one()

            result = await RoomService.pick_winner(
                session, room, users[0].id, start["round"].id, departed_submission.id, redis
            )

            assert result["next_round"] is not None
            assert all(row.score == 0 for row in result["scoreboard"])

    asyncio.run(_run())


def test_player_timeout_moves_round_to_judging_when_remaining_players_submitted(test_db):
    """Removing the only player who had not submitted advances the round immediately."""

    async def _run():
        async with test_db() as session:
            redis = _FakeRedisClient()
            users = await _create_users(session, 4, "timeout_judging")
            room = await _create_room_with_players(session, users)
            await _seed_cards(session, black_cards=[("Prompt _", 1)], white_total=60)

            start = await RoomService.start_game(session, room, users[0].id, redis)
            for user in users[1:3]:
                hand = await RoomService.get_player_hand(redis, room.id, user.id)
                await RoomService.submit_cards(
                    session, room, user.id, start["round"].id, [hand[0]], redis
                )

            outcome = await RoomService.handle_player_timeout(
                session, redis, room.id, users[3].id
            )

            assert outcome["czar_timed_out"] is False
            assert outcome["judging_round_id"] == start["round"].id
            assert len(outcome["judging_submissions"]) == 2
            assert start["round"].status == "judging"

    asyncio.run(_run())


def test_player_timeout_ends_game_when_fewer_than_three_players_remain(test_db):
    """Dropping below three players finishes the game and reports a final scoreboard."""

    async def _run():
        async with test_db() as session:
            redis = _FakeRedisClient()
            users = await _create_users(session, 3, "timeout_over")
            room = await _create_room_with_players(session, users)
            await _seed_cards(session, black_cards=[("Prompt _", 1)], white_total=40)

            await RoomService.start_game(session, room, users[0].id, redis)
            outcome = await RoomService.handle_player_timeout(
                session, redis, room.id, users[2].id
            )

            assert outcome["game_over"] is True
            assert room.status == "finished"
            assert {row.player_id for row in outcome["scoreboard"]} == {users[0].id, users[1].id}
            # Redis game state is cleaned up with the game.
            assert await RoomService.get_white_deck(redis, room.id) == []

    asyncio.run(_run())


def test_lobby_disconnect_keeps_host_when_nobody_else_is_connected(test_db):
    """A lone host (e.g. refreshing the page) keeps the role instead of orphaning the room."""

    async def _run():
        async with test_db() as session:
            users = await _create_users(session, 2, "lone_host")
            room = await _create_room_with_players(session, users)
            await RoomService.mark_player_connection_state(
                session, room.id, users[1].id, is_connected=False
            )

            outcome = await RoomService.handle_lobby_disconnect(session, room.id, users[0].id)
            assert outcome["host_changed"] is None
            assert room.host_id == users[0].id

            # With a connected guest the role still moves, as before.
            await RoomService.mark_player_connection_state(
                session, room.id, users[1].id, is_connected=True
            )
            outcome = await RoomService.handle_lobby_disconnect(session, room.id, users[0].id)
            assert outcome["host_changed"]["new_host_id"] == users[1].id
            assert room.host_id == users[1].id

    asyncio.run(_run())


def test_game_state_snapshot_has_everything_a_client_needs_to_render(test_db):
    """State sync carries hand texts, own submission status, and a stable judging order."""

    async def _run():
        async with test_db() as session:
            redis = _FakeRedisClient()
            users = await _create_users(session, 3, "snapshot")
            room = await _create_room_with_players(session, users)
            await _seed_cards(session, black_cards=[("Prompt _", 1)], white_total=35)

            start = await RoomService.start_game(session, room, users[0].id, redis)
            hand = await RoomService.get_player_hand(redis, room.id, users[1].id)
            await RoomService.submit_cards(
                session, room, users[1].id, start["round"].id, [hand[0]], redis
            )

            state = await RoomService.build_game_state(session, room.id, redis, users[1].id)
            assert state["has_submitted"] is True
            assert state["submitted_player_ids"] == [str(users[1].id)]
            assert state["hand"] == [card["id"] for card in state["hand_cards"]]
            assert len(state["hand_cards"]) == 9
            assert all(card["text"].startswith("White ") for card in state["hand_cards"])

            other = await RoomService.build_game_state(session, room.id, redis, users[2].id)
            assert other["has_submitted"] is False

            hand = await RoomService.get_player_hand(redis, room.id, users[2].id)
            await RoomService.submit_cards(
                session, room, users[2].id, start["round"].id, [hand[0]], redis
            )
            first = await RoomService.build_game_state(session, room.id, redis, users[0].id)
            second = await RoomService.build_game_state(session, room.id, redis, users[0].id)
            assert first["status"] == "judging"
            assert first["submissions"] == second["submissions"]

    asyncio.run(_run())


def test_reconnect_window_marker_outlives_the_window():
    """The Redis marker must still exist when the in-process timeout task wakes up."""

    class _TtlRecordingRedis:
        def __init__(self):
            self.ttl = None

        async def setex(self, key, seconds, value):
            self.ttl = seconds

    async def _run():
        redis = _TtlRecordingRedis()
        payload = await RoomService.start_reconnect_window(redis, uuid4(), uuid4())
        assert payload["seconds_remaining"] == RECONNECT_WINDOW_TTL
        assert redis.ttl > RECONNECT_WINDOW_TTL

    asyncio.run(_run())


def test_join_private_room_rejects_finished_game(test_db):
    """New players cannot join a room whose game is over; existing members still can."""

    async def _run():
        async with test_db() as session:
            users = await _create_users(session, 2, "join_finished")
            room = await RoomService.create_private_room(
                session, users[0], RoomCreateRequest(password="roompass")
            )
            room.status = "finished"
            await session.flush()
            join = RoomJoinRequest(code=room.code, password="roompass")

            try:
                await RoomService.join_private_room(session, users[1], join)
                assert False, "Expected 409 for finished room"
            except HTTPException as exc:
                assert exc.status_code == 409

            assert (await RoomService.join_private_room(session, users[0], join)).id == room.id

    asyncio.run(_run())
