"""WebSocket room endpoint tests."""

import asyncio
from uuid import UUID, uuid4

import redis.asyncio as redis
from fastapi import status
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.models import Card
from app.services.rooms import RoomService


def _register_and_get_access_token(client, username: str, email: str | None = None) -> str:
    """Create a user through API and return access token."""
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


def _create_private_room(client, token: str) -> str:
    """Create a private room and return room ID."""
    room_id, _room_code = _create_private_room_with_code(client, token)
    return room_id


def _create_private_room_with_code(
    client,
    token: str,
    *,
    winning_score: int = 8,
) -> tuple[str, str]:
    """Create a private room and return room ID and join code."""
    response = client.post(
        "/rooms",
        headers=_auth_headers(token),
        json={
            "password": "roompass",
            "max_players": 6,
            "winning_score": winning_score,
            "round_timer_seconds": 90,
            "card_pool_mode": "default_only",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    return payload["id"], payload["code"]


def _join_room(client, token: str, code: str, password: str) -> None:
    """Join existing room by invite code."""
    response = client.post(
        "/rooms/join",
        headers=_auth_headers(token),
        json={"code": code, "password": password},
    )
    assert response.status_code == status.HTTP_200_OK


def _seed_cards(test_db, *, black_cards: list[tuple[str, int]], white_cards: list[str]) -> list[str]:
    """Seed cards needed by websocket tests and return white card ids."""

    async def _seed() -> list[str]:
        async with test_db() as session:
            cards = [
                Card(type="black", text=text, pick=pick, is_default=True)
                for text, pick in black_cards
            ]
            cards.extend(Card(type="white", text=text, is_default=True) for text in white_cards)
            session.add_all(cards)
            await session.flush()
            await session.commit()
            return {str(card.id): card.text for card in cards if card.type == "white"}

    return asyncio.run(_seed())


def _consume_bootstrap(websocket) -> dict:
    """Consume initial connect and sync events for a websocket client."""
    websocket.receive_json()
    return websocket.receive_json()


def _get_player_id(sync_event: dict, username: str) -> str:
    """Resolve a player's ID from the room state sync payload."""
    return next(
        player["player_id"]
        for player in sync_event["payload"]["players"]
        if player["username"] == username
    )


def _get_current_hand(room_id: str, user_id: str) -> list[str]:
    """Load the player's current dealt hand directly from Redis."""

    async def _load() -> list[str]:
        redis_client = redis.from_url(settings.REDIS_URL)
        try:
            hand = await RoomService.get_player_hand(
                redis_client,
                UUID(room_id),
                UUID(user_id),
            )
            return [str(card_id) for card_id in hand]
        finally:
            await redis_client.aclose()

    return asyncio.run(_load())


def _receive_broadcast(websockets, expected_event: str) -> list[dict]:
    """Receive the next broadcast event on all connected room websockets."""
    skipped_events = {"room.player_joined", "room.player_left", "room.host_changed"}
    events = []
    for websocket in websockets:
        for _ in range(6):
            event = websocket.receive_json()
            if event["event"] == expected_event:
                events.append(event)
                break
            assert event["event"] in skipped_events
        else:
            assert False, f"Expected {expected_event} event"

    return events


def test_ws_lobby_presence_events_and_host_transfer_on_disconnect(client):
    """Lobby sockets receive join/leave presence updates and host transfer on disconnect."""
    host_token = _register_and_get_access_token(client, "ws_presence_host")
    guest_token = _register_and_get_access_token(client, "ws_presence_guest")

    room_id, room_code = _create_private_room_with_code(client, host_token)
    _join_room(client, guest_token, room_code, "roompass")

    with client.websocket_connect(f"/ws/rooms/{room_id}?token={host_token}") as host_socket:
        host_sync = _consume_bootstrap(host_socket)
        host_player_id = _get_player_id(host_sync, "ws_presence_host")
        guest_player_id = _get_player_id(host_sync, "ws_presence_guest")

        with client.websocket_connect(f"/ws/rooms/{room_id}?token={guest_token}") as guest_socket:
            _consume_bootstrap(guest_socket)

            joined_event = host_socket.receive_json()
            assert joined_event["event"] == "room.player_joined"
            assert joined_event["payload"]["player"]["player_id"] == guest_player_id
            assert joined_event["payload"]["player"]["is_connected"] is True

        left_event = host_socket.receive_json()
        assert left_event["event"] == "room.player_left"
        assert left_event["payload"]["player_id"] == guest_player_id
        assert left_event["payload"]["reason"] == "disconnect"

    transfer_room_id, transfer_room_code = _create_private_room_with_code(client, host_token)
    _join_room(client, guest_token, transfer_room_code, "roompass")

    with client.websocket_connect(f"/ws/rooms/{transfer_room_id}?token={guest_token}") as guest_socket:
        guest_sync = _consume_bootstrap(guest_socket)
        transfer_host_player_id = _get_player_id(guest_sync, "ws_presence_host")
        transfer_guest_player_id = _get_player_id(guest_sync, "ws_presence_guest")

        with client.websocket_connect(f"/ws/rooms/{transfer_room_id}?token={host_token}") as host_socket:
            _consume_bootstrap(host_socket)

            joined_event = guest_socket.receive_json()
            assert joined_event["event"] == "room.player_joined"
            assert joined_event["payload"]["player"]["player_id"] == transfer_host_player_id

        left_event = guest_socket.receive_json()
        assert left_event["event"] == "room.player_left"
        assert left_event["payload"]["player_id"] == transfer_host_player_id

        host_changed = guest_socket.receive_json()
        assert host_changed["event"] == "room.host_changed"
        assert host_changed["payload"]["previous_host_id"] == transfer_host_player_id
        assert host_changed["payload"]["new_host_id"] == transfer_guest_player_id


def test_ws_room_rejects_missing_token(client):
    """WebSocket room channel rejects unauthenticated connections."""
    host_token = _register_and_get_access_token(client, "ws_missing_token_host")
    room_id = _create_private_room(client, host_token)

    with client.websocket_connect(f"/ws/rooms/{room_id}") as websocket:
        error_message = websocket.receive_json()
        assert error_message["event"] == "error"
        assert error_message["payload"]["code"] == "UNAUTHORIZED"

        try:
            websocket.receive_json()
            assert False, "Expected websocket close after unauthorized error"
        except WebSocketDisconnect as exc:
            assert exc.code == 4401


def test_ws_room_rejects_non_member(client):
    """WebSocket room channel rejects authenticated users not in room."""
    host_token = _register_and_get_access_token(client, "ws_non_member_host")
    outsider_token = _register_and_get_access_token(client, "ws_non_member_outsider")
    room_id = _create_private_room(client, host_token)

    with client.websocket_connect(f"/ws/rooms/{room_id}?token={outsider_token}") as websocket:
        error_message = websocket.receive_json()
        assert error_message["event"] == "error"
        assert error_message["payload"]["code"] == "FORBIDDEN"

        try:
            websocket.receive_json()
            assert False, "Expected websocket close after forbidden error"
        except WebSocketDisconnect as exc:
            assert exc.code == 4403


def test_ws_room_connect_sends_connected_and_state_sync(client):
    """Room members receive connection ack followed by room state snapshot."""
    host_token = _register_and_get_access_token(client, "ws_sync_host")
    room_id = _create_private_room(client, host_token)

    with client.websocket_connect(f"/ws/rooms/{room_id}?token={host_token}") as websocket:
        connected_event = websocket.receive_json()
        assert connected_event["event"] == "room.connected"
        assert connected_event["payload"]["room_status"] == "lobby"

        sync_event = websocket.receive_json()
        assert sync_event["event"] == "room.state_sync"
        assert sync_event["payload"]["room"]["id"] == room_id
        assert len(sync_event["payload"]["players"]) == 1
        assert sync_event["payload"]["game"] is None


def test_ws_room_ping_returns_pong_with_correlation_id(client):
    """Ping command returns pong event carrying correlation id and timestamps."""
    host_token = _register_and_get_access_token(client, "ws_ping_host")
    room_id = _create_private_room(client, host_token)
    correlation_id = str(uuid4())

    with client.websocket_connect(f"/ws/rooms/{room_id}?token={host_token}") as websocket:
        websocket.receive_json()  # room.connected
        websocket.receive_json()  # room.state_sync

        websocket.send_json(
            {
                "event": "client.ping",
                "correlation_id": correlation_id,
                "payload": {"sent_at": "2026-04-26T12:30:45.812Z"},
            }
        )

        pong_event = websocket.receive_json()
        assert pong_event["event"] == "server.pong"
        assert pong_event["correlation_id"] == correlation_id
        assert pong_event["payload"]["sent_at"] == "2026-04-26T12:30:45.812Z"
        assert pong_event["payload"]["received_at"] is not None


def test_ws_lobby_start_game_requires_host_and_emits_round_start(client, test_db):
    """Non-host start fails; host start emits game-start and round-start events."""
    _seed_cards(
        test_db,
        black_cards=[("Prompt _", 1)],
        white_cards=[f"Start filler {index}" for index in range(30)],
    )

    host_token = _register_and_get_access_token(client, "ws_start_host")
    guest_one_token = _register_and_get_access_token(client, "ws_start_guest_1")
    guest_two_token = _register_and_get_access_token(client, "ws_start_guest_2")

    room_id, room_code = _create_private_room_with_code(client, host_token)
    _join_room(client, guest_one_token, room_code, "roompass")
    _join_room(client, guest_two_token, room_code, "roompass")

    with client.websocket_connect(f"/ws/rooms/{room_id}?token={guest_one_token}") as guest_socket:
        guest_socket.receive_json()  # room.connected
        guest_socket.receive_json()  # room.state_sync

        guest_socket.send_json(
            {
                "event": "lobby.start_game",
                "correlation_id": str(uuid4()),
                "payload": {},
            }
        )

        not_host_error = guest_socket.receive_json()
        assert not_host_error["event"] == "error"
        assert not_host_error["payload"]["code"] == "NOT_HOST"

    correlation_id = str(uuid4())
    with client.websocket_connect(f"/ws/rooms/{room_id}?token={host_token}") as host_socket:
        host_socket.receive_json()  # room.connected
        host_socket.receive_json()  # room.state_sync

        host_socket.send_json(
            {
                "event": "lobby.start_game",
                "correlation_id": correlation_id,
                "payload": {},
            }
        )

        game_started = host_socket.receive_json()
        assert game_started["event"] == "game.started"
        assert game_started["correlation_id"] == correlation_id
        assert game_started["payload"]["round_number"] == 1

        round_started = host_socket.receive_json()
        assert round_started["event"] == "round.started"
        assert round_started["payload"]["round_number"] == 1
        assert round_started["payload"]["black_card"]["text"] == "Prompt _"


def test_ws_game_commands_reject_when_game_not_started(client):
    """Submit/pick commands return game-not-started while room remains lobby."""
    host_token = _register_and_get_access_token(client, "ws_game_not_started_host")
    room_id = _create_private_room(client, host_token)

    with client.websocket_connect(f"/ws/rooms/{room_id}?token={host_token}") as websocket:
        websocket.receive_json()  # room.connected
        websocket.receive_json()  # room.state_sync

        websocket.send_json(
            {
                "event": "game.submit_cards",
                "correlation_id": str(uuid4()),
                "payload": {
                    "round_id": str(uuid4()),
                    "white_card_ids": [str(uuid4())],
                },
            }
        )
        submit_error = websocket.receive_json()
        assert submit_error["event"] == "error"
        assert submit_error["payload"]["code"] == "GAME_NOT_STARTED"

        websocket.send_json(
            {
                "event": "game.pick_winner",
                "correlation_id": str(uuid4()),
                "payload": {
                    "round_id": str(uuid4()),
                    "submission_id": str(uuid4()),
                },
            }
        )
        pick_error = websocket.receive_json()
        assert pick_error["event"] == "error"
        assert pick_error["payload"]["code"] == "GAME_NOT_STARTED"


def test_ws_submit_cards_happy_path_transitions_room_to_judging(client, test_db):
    """Two player submissions move the room from waiting to judging."""
    white_cards = _seed_cards(
        test_db,
        black_cards=[("Prompt _", 1)],
        white_cards=["First answer", "Second answer"]
        + [f"Submit filler {index}" for index in range(30)],
    )

    host_token = _register_and_get_access_token(client, "ws_submit_host")
    guest_one_token = _register_and_get_access_token(client, "ws_submit_guest_1")
    guest_two_token = _register_and_get_access_token(client, "ws_submit_guest_2")

    room_id, room_code = _create_private_room_with_code(client, host_token)
    _join_room(client, guest_one_token, room_code, "roompass")
    _join_room(client, guest_two_token, room_code, "roompass")

    with (
        client.websocket_connect(f"/ws/rooms/{room_id}?token={host_token}") as host_socket,
        client.websocket_connect(f"/ws/rooms/{room_id}?token={guest_one_token}") as guest_one_socket,
        client.websocket_connect(f"/ws/rooms/{room_id}?token={guest_two_token}") as guest_two_socket,
    ):
        sockets = [host_socket, guest_one_socket, guest_two_socket]
        host_sync = _consume_bootstrap(host_socket)
        guest_one_sync = _consume_bootstrap(guest_one_socket)
        guest_two_sync = _consume_bootstrap(guest_two_socket)
        guest_one_user_id = _get_player_id(guest_one_sync, "ws_submit_guest_1")
        guest_two_user_id = _get_player_id(guest_two_sync, "ws_submit_guest_2")

        host_socket.send_json({"event": "lobby.start_game", "payload": {}})
        _receive_broadcast(sockets, "game.started")
        round_started_events = _receive_broadcast(sockets, "round.started")
        round_id = round_started_events[0]["payload"]["round_id"]
        guest_one_hand = _get_current_hand(room_id, guest_one_user_id)
        guest_two_hand = _get_current_hand(room_id, guest_two_user_id)

        guest_one_socket.send_json(
            {
                "event": "game.submit_cards",
                "payload": {
                    "round_id": round_id,
                    "white_card_ids": [guest_one_hand[0]],
                },
            }
        )
        accepted_events = _receive_broadcast(sockets, "round.submission_accepted")
        assert accepted_events[0]["payload"]["submitted_count"] == 1
        assert accepted_events[0]["payload"]["required_count"] == 2

        guest_two_socket.send_json(
            {
                "event": "game.submit_cards",
                "payload": {
                    "round_id": round_id,
                    "white_card_ids": [guest_two_hand[0]],
                },
            }
        )
        judging_events = _receive_broadcast(sockets, "round.judging")
        submissions = judging_events[0]["payload"]["submissions"]
        assert len(submissions) == 2
        flattened = {text for submission in submissions for text in submission["white_card_texts"]}
        assert flattened == {white_cards[guest_one_hand[0]], white_cards[guest_two_hand[0]]}


def test_ws_pick_winner_happy_path_starts_next_round(client, test_db):
    """Winner selection updates scores and automatically starts the next round."""
    white_cards = _seed_cards(
        test_db,
        black_cards=[("Prompt _", 1), ("Another prompt _", 1)],
        white_cards=["Winning answer", "Other answer"]
        + [f"Pick filler {index}" for index in range(32)],
    )

    host_token = _register_and_get_access_token(client, "ws_pick_host")
    guest_one_token = _register_and_get_access_token(client, "ws_pick_guest_1")
    guest_two_token = _register_and_get_access_token(client, "ws_pick_guest_2")

    room_id, room_code = _create_private_room_with_code(client, host_token, winning_score=3)
    _join_room(client, guest_one_token, room_code, "roompass")
    _join_room(client, guest_two_token, room_code, "roompass")

    with (
        client.websocket_connect(f"/ws/rooms/{room_id}?token={host_token}") as host_socket,
        client.websocket_connect(f"/ws/rooms/{room_id}?token={guest_one_token}") as guest_one_socket,
        client.websocket_connect(f"/ws/rooms/{room_id}?token={guest_two_token}") as guest_two_socket,
    ):
        sockets = [host_socket, guest_one_socket, guest_two_socket]
        host_sync = _consume_bootstrap(host_socket)
        guest_one_sync = _consume_bootstrap(guest_one_socket)
        guest_two_sync = _consume_bootstrap(guest_two_socket)
        guest_one_user_id = _get_player_id(guest_one_sync, "ws_pick_guest_1")
        guest_two_user_id = _get_player_id(guest_two_sync, "ws_pick_guest_2")

        host_socket.send_json({"event": "lobby.start_game", "payload": {}})
        _receive_broadcast(sockets, "game.started")
        round_started_events = _receive_broadcast(sockets, "round.started")
        first_round = round_started_events[0]["payload"]
        guest_one_hand = _get_current_hand(room_id, guest_one_user_id)
        guest_two_hand = _get_current_hand(room_id, guest_two_user_id)
        guest_one_card_id = guest_one_hand[0]
        guest_two_card_id = guest_two_hand[0]

        guest_one_socket.send_json(
            {
                "event": "game.submit_cards",
                "payload": {
                    "round_id": first_round["round_id"],
                    "white_card_ids": [guest_one_card_id],
                },
            }
        )
        _receive_broadcast(sockets, "round.submission_accepted")

        guest_two_socket.send_json(
            {
                "event": "game.submit_cards",
                "payload": {
                    "round_id": first_round["round_id"],
                    "white_card_ids": [guest_two_card_id],
                },
            }
        )
        judging_events = _receive_broadcast(sockets, "round.judging")
        winning_submission = next(
            submission
            for submission in judging_events[0]["payload"]["submissions"]
            if submission["white_card_texts"] == [white_cards[guest_one_card_id]]
        )

        host_socket.send_json(
            {
                "event": "game.pick_winner",
                "payload": {
                    "round_id": first_round["round_id"],
                    "submission_id": winning_submission["submission_id"],
                },
            }
        )
        result_events = _receive_broadcast(sockets, "round.result")
        scores = {row["player_id"]: row["score"] for row in result_events[0]["payload"]["scores"]}
        assert max(scores.values()) == 1

        next_round_events = _receive_broadcast(sockets, "round.started")
        next_round = next_round_events[0]["payload"]
        assert next_round["round_number"] == 2
        assert next_round["czar_id"] != first_round["czar_id"]
        assert next_round["black_card"]["text"] == "Another prompt _"
