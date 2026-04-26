"""Unit tests for gameplay state persisted outside the relational schema."""

import asyncio
import json

from app.models import Card, Room, RoomPlayer, User
from app.services.rooms import RoomGameError, RoomService


class _FakeRedisClient:
    """Minimal async Redis double for JSON gameplay state keys."""

    def __init__(self):
        self._values: dict[str, str] = {}

    async def get(self, key: str):
        return self._values.get(key)

    async def set(self, key: str, value: str):
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