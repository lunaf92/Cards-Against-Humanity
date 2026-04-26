"""WebSocket room endpoint tests."""

from uuid import uuid4

from fastapi import status
from starlette.websockets import WebSocketDisconnect


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
    response = client.post(
        "/rooms",
        headers=_auth_headers(token),
        json={
            "password": "roompass",
            "max_players": 6,
            "winning_score": 8,
            "round_timer_seconds": 90,
            "card_pool_mode": "default_only",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()["id"]


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
