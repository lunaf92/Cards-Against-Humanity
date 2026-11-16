"""Rooms endpoint tests."""
import asyncio
from datetime import datetime
from uuid import UUID

from fastapi import status
from sqlalchemy import select

from app.models import Room, RoomPlayer, User
from app.routers import rooms as rooms_router
from app.services.rooms import RoomService


def _register_and_get_access_token(client, username: str, email: str | None = None) -> str:
    """Create a user through public API and return access token."""
    payload = {
        "username": username,
        "password": "securepass123",
    }
    if email:
        payload["email"] = email

    response = client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    """Build bearer auth headers for protected endpoints."""
    return {"Authorization": f"Bearer {token}"}


class _FakeRedisClient:
    """Minimal async fake Redis client supporting sorted-set queue operations."""

    def __init__(self):
        self._queue: dict[str, float] = {}

    async def zadd(self, key: str, mapping: dict[str, float]):
        assert key == "matchmaking:queue"
        self._queue.update(mapping)

    async def zcard(self, key: str):
        assert key == "matchmaking:queue"
        return len(self._queue)

    async def zrange(self, key: str, start: int, end: int):
        assert key == "matchmaking:queue"
        ordered = sorted(self._queue.items(), key=lambda item: (item[1], item[0]))
        if end == -1:
            items = ordered[start:]
        else:
            items = ordered[start : end + 1]
        return [member for member, _ in items]

    async def zrem(self, key: str, member: str):
        assert key == "matchmaking:queue"
        if member in self._queue:
            self._queue.pop(member)
            return 1
        return 0

    async def close(self):
        return None


def test_create_room_and_get_room_details(client):
    """Host can create a private room and fetch details with player list."""
    token = _register_and_get_access_token(client, "room_host_user")

    create_response = client.post(
        "/rooms",
        headers=_auth_headers(token),
        json={
            "password": "roompass",
            "max_players": 6,
            "winning_score": 7,
            "round_timer_seconds": 75,
            "card_pool_mode": "default_only",
        },
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    created = create_response.json()

    assert len(created["code"]) == 6
    assert created["room_kind"] == "private"
    assert created["status"] == "lobby"
    assert len(created["players"]) == 1
    assert created["players"][0]["username"] == "room_host_user"

    room_id = created["id"]
    details_response = client.get(f"/rooms/{room_id}", headers=_auth_headers(token))
    assert details_response.status_code == status.HTTP_200_OK
    details = details_response.json()
    assert details["id"] == room_id
    assert len(details["players"]) == 1


def test_join_room_with_password_and_capacity_guard(client):
    """Players can join by code/password and room capacity is enforced."""
    host_token = _register_and_get_access_token(client, "room_host_cap")
    create_response = client.post(
        "/rooms",
        headers=_auth_headers(host_token),
        json={
            "password": "joinpass",
            "max_players": 2,
            "winning_score": 8,
            "round_timer_seconds": 90,
            "card_pool_mode": "default_only",
        },
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    room_code = create_response.json()["code"]

    guest_token = _register_and_get_access_token(client, "room_guest_cap")
    join_response = client.post(
        "/rooms/join",
        headers=_auth_headers(guest_token),
        json={"code": room_code, "password": "joinpass"},
    )
    assert join_response.status_code == status.HTTP_200_OK
    assert len(join_response.json()["players"]) == 2

    another_token = _register_and_get_access_token(client, "room_third_cap")
    full_response = client.post(
        "/rooms/join",
        headers=_auth_headers(another_token),
        json={"code": room_code, "password": "joinpass"},
    )
    assert full_response.status_code == status.HTTP_409_CONFLICT


def test_update_room_config_is_host_only_and_lobby_only(client, test_db):
    """Only host can update config and only while room is in lobby."""
    host_token = _register_and_get_access_token(client, "room_host_cfg")
    guest_token = _register_and_get_access_token(client, "room_guest_cfg")

    create_response = client.post(
        "/rooms",
        headers=_auth_headers(host_token),
        json={
            "password": "cfgpass",
            "max_players": 6,
            "winning_score": 7,
            "round_timer_seconds": 70,
            "card_pool_mode": "default_only",
        },
    )
    room_id = create_response.json()["id"]
    room_code = create_response.json()["code"]

    join_response = client.post(
        "/rooms/join",
        headers=_auth_headers(guest_token),
        json={"code": room_code, "password": "cfgpass"},
    )
    assert join_response.status_code == status.HTTP_200_OK

    guest_patch = client.patch(
        f"/rooms/{room_id}/config",
        headers=_auth_headers(guest_token),
        json={"winning_score": 9},
    )
    assert guest_patch.status_code == status.HTTP_403_FORBIDDEN

    host_patch = client.patch(
        f"/rooms/{room_id}/config",
        headers=_auth_headers(host_token),
        json={"winning_score": 9, "round_timer_seconds": 95},
    )
    assert host_patch.status_code == status.HTTP_200_OK
    assert host_patch.json()["winning_score"] == 9
    assert host_patch.json()["round_timer_seconds"] == 95

    async def _mark_room_in_progress():
        async with test_db() as session:
            result = await session.get(Room, UUID(room_id))
            result.status = "in_progress"
            await session.commit()

    asyncio.run(_mark_room_in_progress())

    not_lobby_patch = client.patch(
        f"/rooms/{room_id}/config",
        headers=_auth_headers(host_token),
        json={"winning_score": 10},
    )
    assert not_lobby_patch.status_code == status.HTTP_409_CONFLICT


def test_matchmaking_queue_promotes_first_three_players(client, monkeypatch):
    """Queue endpoint promotes first three queued users into random matchmaking room."""
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr(rooms_router.redis, "from_url", lambda *_args, **_kwargs: fake_redis)

    broadcasted_events: list[tuple[UUID, dict]] = []

    async def _capture_broadcast(room_id: UUID, payload: dict) -> None:
        broadcasted_events.append((room_id, payload))

    monkeypatch.setattr(rooms_router.connection_manager, "broadcast_event", _capture_broadcast)

    t1 = _register_and_get_access_token(client, "queue_user_1")
    t2 = _register_and_get_access_token(client, "queue_user_2")
    t3 = _register_and_get_access_token(client, "queue_user_3")

    r1 = client.post("/rooms/queue", headers=_auth_headers(t1))
    assert r1.status_code == status.HTTP_200_OK
    assert r1.json()["matched_room_id"] is None
    assert r1.json()["queue_size"] == 1

    r2 = client.post("/rooms/queue", headers=_auth_headers(t2))
    assert r2.status_code == status.HTTP_200_OK
    assert r2.json()["matched_room_id"] is None
    assert r2.json()["queue_size"] == 2

    r3 = client.post("/rooms/queue", headers=_auth_headers(t3))
    assert r3.status_code == status.HTTP_200_OK
    assert r3.json()["matched_room_id"] is not None
    assert r3.json()["queue_size"] == 0

    room_id = r3.json()["matched_room_id"]
    room_details = client.get(f"/rooms/{room_id}", headers=_auth_headers(t1))
    assert room_details.status_code == status.HTTP_200_OK
    assert room_details.json()["room_kind"] == "random"
    assert room_details.json()["status"] == "matchmaking_lobby"
    assert len(room_details.json()["players"]) == 3

    expiry_before = datetime.fromisoformat(room_details.json()["matchmaking_fill_expires_at"])

    t4 = _register_and_get_access_token(client, "queue_user_4")
    r4 = client.post("/rooms/queue", headers=_auth_headers(t4))
    assert r4.status_code == status.HTTP_200_OK
    assert r4.json()["matched_room_id"] == room_id

    reset_events = [payload for evt_room_id, payload in broadcasted_events if str(evt_room_id) == room_id and payload.get("event") == "matchmaking.countdown_reset"]
    assert len(reset_events) == 1
    assert reset_events[0]["payload"]["player_count"] == 4
    assert reset_events[0]["payload"]["seconds_remaining"] >= 0

    room_details_after = client.get(f"/rooms/{room_id}", headers=_auth_headers(t1))
    assert room_details_after.status_code == status.HTTP_200_OK
    assert len(room_details_after.json()["players"]) == 4
    expiry_after = datetime.fromisoformat(room_details_after.json()["matchmaking_fill_expires_at"])
    assert expiry_after >= expiry_before


def test_leave_matchmaking_queue(client, monkeypatch):
    """Queue leave endpoint removes user membership idempotently."""
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr(rooms_router.redis, "from_url", lambda *_args, **_kwargs: fake_redis)

    token = _register_and_get_access_token(client, "queue_leaver")
    enqueue = client.post("/rooms/queue", headers=_auth_headers(token))
    assert enqueue.status_code == status.HTTP_200_OK

    leave_once = client.delete("/rooms/queue", headers=_auth_headers(token))
    assert leave_once.status_code == status.HTTP_200_OK
    assert leave_once.json()["removed"] is True

    leave_twice = client.delete("/rooms/queue", headers=_auth_headers(token))
    assert leave_twice.status_code == status.HTTP_200_OK
    assert leave_twice.json()["removed"] is False


def test_matchmaking_worker_tick_starts_and_cancels_countdown(test_db):
    """Worker tick starts countdown at 3+ players and cancels below 3 players."""

    async def _assert_tick_behavior():
        async with test_db() as session:
            users = [
                User(username="tick_user_1", email="tick1@example.com", password_hash="hash"),
                User(username="tick_user_2", email="tick2@example.com", password_hash="hash"),
                User(username="tick_user_3", email="tick3@example.com", password_hash="hash"),
            ]
            session.add_all(users)
            await session.flush()

            room = Room(
                code="TICK01",
                host_id=users[0].id,
                room_kind="random",
                status="matchmaking_lobby",
                max_players=10,
                winning_score=8,
                round_timer_seconds=90,
                card_pool_mode="default_only",
                matchmaking_fill_expires_at=None,
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

            updated = await RoomService.process_matchmaking_tick(session)
            assert len(updated) == 1
            assert updated[0]["event"] == "matchmaking.countdown_started"
            assert room.matchmaking_fill_expires_at is not None

            # Drop to 2 players and ensure countdown is canceled.
            room_player_obj = (
                await session.execute(
                    select(RoomPlayer)
                    .where(RoomPlayer.room_id == room.id)
                    .limit(1)
                )
            ).scalar_one()
            await session.delete(room_player_obj)
            await session.flush()

            updated = await RoomService.process_matchmaking_tick(session)
            assert len(updated) == 1
            assert updated[0]["event"] == "matchmaking.countdown_canceled"
            assert room.matchmaking_fill_expires_at is None

    asyncio.run(_assert_tick_behavior())


def test_active_room_lets_queued_players_find_their_match(client, monkeypatch):
    """Players queued before the match was made discover the room via GET /rooms/active."""
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr(rooms_router.redis, "from_url", lambda *_args, **_kwargs: fake_redis)

    async def _ignore_broadcast(room_id: UUID, payload: dict) -> None:
        return None

    monkeypatch.setattr(rooms_router.connection_manager, "broadcast_event", _ignore_broadcast)

    tokens = [_register_and_get_access_token(client, f"active_user_{i}") for i in range(3)]

    none_yet = client.get("/rooms/active", headers=_auth_headers(tokens[0]))
    assert none_yet.status_code == status.HTTP_200_OK
    assert none_yet.json() == {"room": None}

    for token in tokens:
        client.post("/rooms/queue", headers=_auth_headers(token))

    active = client.get("/rooms/active", headers=_auth_headers(tokens[0]))
    assert active.status_code == status.HTTP_200_OK
    assert active.json()["room"]["room_kind"] == "random"
    assert len(active.json()["room"]["players"]) == 3


def test_active_room_ignores_finished_rooms(client, test_db):
    """A finished room is not reported as active."""
    token = _register_and_get_access_token(client, "active_finished")
    created = client.post("/rooms", json={"password": "pass1234"}, headers=_auth_headers(token))
    room_id = created.json()["id"]
    assert client.get("/rooms/active", headers=_auth_headers(token)).json()["room"]["id"] == room_id

    async def _finish() -> None:
        async with test_db() as session:
            room = (await session.execute(select(Room).where(Room.id == UUID(room_id)))).scalar_one()
            room.status = "finished"
            await session.commit()

    asyncio.run(_finish())
    assert client.get("/rooms/active", headers=_auth_headers(token)).json() == {"room": None}
