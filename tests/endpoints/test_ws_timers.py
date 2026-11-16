"""Timer and reconnect-timeout tests for the room WebSocket layer.

These drive the timer coroutines directly (zero-length sleeps, captured
broadcasts) instead of going through sockets, which keeps them deterministic.
"""

import asyncio
from uuid import uuid4

from app.models import Card, Room, RoomPlayer, User
from app.routers import ws_rooms as ws_rooms_router
from app.services.rooms import RoomService
from tests.endpoints.test_ws_rooms import _FakeRedisClient


async def _setup_started_game(test_db, redis, *, players: int, pick: int = 1):
    """Create a room with a started game and return (room_id, round, user_ids)."""
    async with test_db() as session:
        users = [
            User(username=f"timer_{uuid4().hex[:8]}_{index}", password_hash="hash")
            for index in range(players)
        ]
        session.add_all(users)
        await session.flush()

        room = Room(
            code=uuid4().hex[:6].upper(),
            host_id=users[0].id,
            room_kind="private",
            status="lobby",
            max_players=6,
            winning_score=3,
            round_timer_seconds=90,
            card_pool_mode="default_only",
        )
        session.add(room)
        await session.flush()
        for index, user in enumerate(users, start=1):
            session.add(RoomPlayer(room_id=room.id, player_id=user.id, join_order=index, score=0))

        session.add_all(
            [Card(type="black", text=f"Prompt {index}", pick=pick, is_default=True) for index in range(3)]
        )
        session.add_all(
            [Card(type="white", text=f"White {index}", is_default=True) for index in range(60)]
        )
        await session.flush()

        outcome = await RoomService.start_game(session, room, users[0].id, redis)
        await session.commit()
        return room.id, outcome["round"], [user.id for user in users]


def _patch_runtime(monkeypatch, redis) -> list[dict]:
    """Route the router's Redis and broadcasts to in-memory doubles; return captured events."""
    captured: list[dict] = []

    async def _capture_broadcast(_room_id, payload):
        captured.append(payload)

    monkeypatch.setattr(ws_rooms_router.redis, "from_url", lambda *_a, **_k: redis)
    monkeypatch.setattr(ws_rooms_router.connection_manager, "broadcast_event", _capture_broadcast)
    monkeypatch.setattr(ws_rooms_router, "_schedule_round_timer_task", lambda *a, **k: None)
    monkeypatch.setattr(ws_rooms_router, "_schedule_judging_timer_task", lambda *a, **k: None)
    return captured


def test_round_timer_auto_submits_full_pick_count(test_db, monkeypatch):
    """Timer expiry on a pick-2 black card auto-submits two cards per idle player."""
    redis = _FakeRedisClient()
    captured = _patch_runtime(monkeypatch, redis)

    async def _run():
        room_id, round_obj, _user_ids = await _setup_started_game(
            test_db, redis, players=3, pick=2
        )
        await ws_rooms_router._run_round_timer(room_id, round_obj.id, 0)

    asyncio.run(_run())

    assert [event["event"] for event in captured] == ["round.timer_expired", "round.judging"]
    submissions = captured[1]["payload"]["submissions"]
    assert len(submissions) == 2
    assert all(len(item["white_card_texts"]) == 2 for item in submissions)
    assert captured[1]["payload"]["judging_expires_at"] is not None


def test_judging_timer_auto_picks_and_starts_next_round(test_db, monkeypatch):
    """Czar timeout picks a winner and the game continues with a new round."""
    redis = _FakeRedisClient()
    captured = _patch_runtime(monkeypatch, redis)

    async def _run():
        room_id, round_obj, _user_ids = await _setup_started_game(test_db, redis, players=3)
        await ws_rooms_router._run_round_timer(room_id, round_obj.id, 0)
        await ws_rooms_router._run_judging_timer(room_id, round_obj.id, 0)

    asyncio.run(_run())

    assert [event["event"] for event in captured] == [
        "round.timer_expired",
        "round.judging",
        "round.judging_expired",
        "round.result",
        "round.started",
    ]
    assert captured[4]["payload"]["round_number"] == 2


def test_reconnect_timeout_ends_game_with_game_over_event(test_db, monkeypatch):
    """Losing a player in a three-player game broadcasts game.over, not just a removal."""
    redis = _FakeRedisClient()
    captured = _patch_runtime(monkeypatch, redis)

    async def _immediate_sleep(_seconds):
        return

    monkeypatch.setattr(ws_rooms_router.asyncio, "sleep", _immediate_sleep)

    async def _run():
        room_id, _round_obj, user_ids = await _setup_started_game(test_db, redis, players=3)
        await RoomService.start_reconnect_window(redis, room_id, user_ids[2])
        await ws_rooms_router._run_reconnect_timeout(room_id, user_ids[2])
        return user_ids

    user_ids = asyncio.run(_run())

    assert [event["event"] for event in captured] == ["player.removed_timeout", "game.over"]
    game_over = captured[1]["payload"]
    assert game_over["reason"] == "not_enough_players"
    assert game_over["winner_player_id"] is None
    assert {row["player_id"] for row in game_over["scoreboard"]} == {
        str(user_ids[0]),
        str(user_ids[1]),
    }


def test_reconnect_timeout_never_removes_a_connected_player(monkeypatch):
    """A player with a live socket is kept even if a stale window marker exists."""
    redis = _FakeRedisClient()
    captured = _patch_runtime(monkeypatch, redis)
    room_id, player_id = uuid4(), uuid4()

    async def _immediate_sleep(_seconds):
        return

    monkeypatch.setattr(ws_rooms_router.asyncio, "sleep", _immediate_sleep)
    monkeypatch.setattr(
        ws_rooms_router.connection_manager, "has_user_connections", lambda *_a: True
    )

    async def _run():
        await RoomService.start_reconnect_window(redis, room_id, player_id)
        await ws_rooms_router._run_reconnect_timeout(room_id, player_id)

    asyncio.run(_run())
    assert captured == []


def test_restore_game_timers_rearms_active_rounds(test_db, monkeypatch):
    """After a restart, rounds that were in flight get a fresh timer."""
    redis = _FakeRedisClient()
    scheduled: list[tuple] = []
    monkeypatch.setattr(
        ws_rooms_router, "_schedule_round_timer_task", lambda *args: scheduled.append(args)
    )

    async def _run():
        room_id, round_obj, _user_ids = await _setup_started_game(test_db, redis, players=3)
        restored = await ws_rooms_router.restore_game_timers()
        return room_id, round_obj.id, restored

    room_id, round_id, restored = asyncio.run(_run())
    assert restored == 1
    assert scheduled == [(room_id, round_id, 90)]
