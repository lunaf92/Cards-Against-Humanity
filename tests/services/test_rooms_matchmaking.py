"""Unit tests for matchmaking service behavior."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Room, RoomPlayer, User
from app.services.rooms import MATCHMAKING_QUEUE_KEY, RoomService


class _FakeRedisClient:
    """Minimal async Redis double for matchmaking queue operations."""

    def __init__(self):
        self._queue: dict[str, float] = {}

    async def zadd(self, key: str, mapping: dict[str, float]):
        assert key == MATCHMAKING_QUEUE_KEY
        self._queue.update(mapping)

    async def zcard(self, key: str):
        assert key == MATCHMAKING_QUEUE_KEY
        return len(self._queue)

    async def zrange(self, key: str, start: int, end: int):
        assert key == MATCHMAKING_QUEUE_KEY
        ordered = sorted(self._queue.items(), key=lambda item: (item[1], item[0]))
        if end == -1:
            items = ordered[start:]
        else:
            items = ordered[start : end + 1]
        return [member for member, _ in items]

    async def zrem(self, key: str, member: str):
        assert key == MATCHMAKING_QUEUE_KEY
        if member in self._queue:
            self._queue.pop(member)
            return 1
        return 0


async def _create_users(session, total: int, prefix: str) -> list[User]:
    """Create and flush test users for matchmaking flows."""
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


def test_enqueue_waits_until_third_player_before_matching(test_db):
    """First two users remain queued, third triggers room creation."""

    async def _run():
        async with test_db() as session:
            redis = _FakeRedisClient()
            users = await _create_users(session, 3, "queued")

            queue_size, matched_room_id, is_new_room = await RoomService.enqueue_for_matchmaking(
                session, redis, users[0]
            )
            assert queue_size == 1
            assert matched_room_id is None
            assert is_new_room is False

            queue_size, matched_room_id, is_new_room = await RoomService.enqueue_for_matchmaking(
                session, redis, users[1]
            )
            assert queue_size == 2
            assert matched_room_id is None
            assert is_new_room is False

            queue_size, matched_room_id, is_new_room = await RoomService.enqueue_for_matchmaking(
                session, redis, users[2]
            )
            assert queue_size == 0
            assert matched_room_id is not None
            assert is_new_room is True

            room = await session.get(Room, matched_room_id)
            assert room is not None
            assert room.room_kind == "random"
            assert room.status == "matchmaking_lobby"

            player_count = await RoomService._room_player_count(session, room.id)
            assert player_count == 3

    asyncio.run(_run())


def test_enqueue_fills_existing_open_lobby_and_resets_window(test_db):
    """Queued player joins open matchmaking lobby and refreshes 10-second fill window."""

    async def _run():
        async with test_db() as session:
            redis = _FakeRedisClient()
            users = await _create_users(session, 4, "fill")

            room = Room(
                code="FILL01",
                host_id=users[0].id,
                room_kind="random",
                status="matchmaking_lobby",
                max_players=10,
                winning_score=8,
                round_timer_seconds=90,
                card_pool_mode="default_only",
                matchmaking_fill_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=5),
            )
            session.add(room)
            await session.flush()

            for index, user in enumerate(users[:3], start=1):
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

            expires_before = room.matchmaking_fill_expires_at
            queue_size, matched_room_id, is_new_room = await RoomService.enqueue_for_matchmaking(
                session, redis, users[3]
            )

            assert queue_size == 0
            assert matched_room_id == room.id
            assert is_new_room is False
            assert room.matchmaking_fill_expires_at is not None
            assert room.matchmaking_fill_expires_at > expires_before

            player_count = await RoomService._room_player_count(session, room.id)
            assert player_count == 4

    asyncio.run(_run())


def test_process_matchmaking_tick_locks_room_when_countdown_expires(test_db):
    """Expired countdown locks matchmaking lobby and emits timer_expired event."""

    async def _run():
        async with test_db() as session:
            users = await _create_users(session, 3, "tick_reset")

            room = Room(
                code="TRES01",
                host_id=users[0].id,
                room_kind="random",
                status="matchmaking_lobby",
                max_players=10,
                winning_score=8,
                round_timer_seconds=90,
                card_pool_mode="default_only",
                matchmaking_fill_expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1),
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

            previous_expiry = room.matchmaking_fill_expires_at
            changes = await RoomService.process_matchmaking_tick(session)

            assert len(changes) == 1
            assert changes[0]["room_id"] == room.id
            assert changes[0]["event"] == "matchmaking.locked"
            assert changes[0]["reason"] == "timer_expired"
            assert room.status == "in_progress"
            assert room.matchmaking_fill_expires_at is None

    asyncio.run(_run())


def test_process_matchmaking_tick_does_not_reset_when_room_is_full(test_db):
    """Full rooms do not roll countdown forward after expiry."""

    async def _run():
        async with test_db() as session:
            users = await _create_users(session, 3, "tick_full")

            room = Room(
                code="FULL01",
                host_id=users[0].id,
                room_kind="random",
                status="matchmaking_lobby",
                max_players=3,
                winning_score=8,
                round_timer_seconds=90,
                card_pool_mode="default_only",
                matchmaking_fill_expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1),
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

            previous_expiry = room.matchmaking_fill_expires_at
            changes = await RoomService.process_matchmaking_tick(session)

            assert len(changes) == 1
            assert changes[0]["room_id"] == room.id
            assert changes[0]["event"] == "matchmaking.locked"
            assert changes[0]["reason"] == "max_players_reached"
            assert room.status == "in_progress"
            assert room.matchmaking_fill_expires_at is None

    asyncio.run(_run())


def test_find_open_matchmaking_room_skips_full_room(test_db):
    """Open-room lookup ignores lobbies that already reached max players."""

    async def _run():
        async with test_db() as session:
            users = await _create_users(session, 4, "open_room")

            full_room = Room(
                code="OPEN01",
                host_id=users[0].id,
                room_kind="random",
                status="matchmaking_lobby",
                max_players=3,
                winning_score=8,
                round_timer_seconds=90,
                card_pool_mode="default_only",
                matchmaking_fill_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=20),
            )
            candidate_room = Room(
                code="OPEN02",
                host_id=users[3].id,
                room_kind="random",
                status="matchmaking_lobby",
                max_players=10,
                winning_score=8,
                round_timer_seconds=90,
                card_pool_mode="default_only",
                matchmaking_fill_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=30),
            )
            session.add_all([full_room, candidate_room])
            await session.flush()

            for index, user in enumerate(users[:3], start=1):
                session.add(
                    RoomPlayer(
                        room_id=full_room.id,
                        player_id=user.id,
                        join_order=index,
                        score=0,
                        is_connected=True,
                    )
                )
            await session.flush()

            found = await RoomService._find_open_matchmaking_room(session)
            assert found is not None
            assert found.id == candidate_room.id

            found_room_players = (
                await session.execute(select(RoomPlayer).where(RoomPlayer.room_id == found.id))
            ).scalars().all()
            assert len(found_room_players) == 0

    asyncio.run(_run())
