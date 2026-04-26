"""Room WebSocket router for real-time lobby and game events."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models import Room, User
from app.schemas.ws import WSEvent
from app.services.auth import AuthService
from app.services.rooms import RoomService
from app.services.ws_connection_manager import connection_manager

router = APIRouter(tags=["ws"])


async def _send_error(websocket: WebSocket, room_id: UUID, code: str, message: str, details: dict | None = None):
    """Emit protocol error event prior to close when possible."""
    event = WSEvent(
        event="error",
        room_id=room_id,
        payload={
            "code": code,
            "message": message,
            "details": details or {},
        },
    )
    await websocket.accept()
    await websocket.send_json(event.model_dump(mode="json"))


def _safe_uuid(value: str | None) -> UUID | None:
    """Parse UUID values safely for optional correlation IDs."""
    if value is None:
        return None

    try:
        return UUID(value)
    except (TypeError, ValueError):
        return None


async def _resolve_current_user(db: AsyncSession, token: str | None) -> User | None:
    """Resolve authenticated websocket user from JWT query token."""
    if not token:
        return None

    payload = decode_token(token)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    try:
        user_uuid = UUID(user_id)
    except (TypeError, ValueError):
        return None

    is_revoked = await AuthService.is_token_revoked(db, token)
    if is_revoked:
        return None

    result = await db.execute(select(User).where(User.id == user_uuid))
    return result.scalar_one_or_none()


async def _build_room_state_payload(db: AsyncSession, room_id: UUID) -> dict:
    """Build full room snapshot payload for initial sync and reconnect sync."""
    room_result = await db.execute(select(Room).where(Room.id == room_id))
    room_obj = room_result.scalar_one()

    players = await RoomService.list_room_players(db, room_id)
    return {
        "room": {
            "id": str(room_obj.id),
            "code": room_obj.code,
            "room_kind": room_obj.room_kind,
            "status": room_obj.status,
            "host_id": str(room_obj.host_id) if room_obj.host_id else None,
            "max_players": room_obj.max_players,
            "winning_score": room_obj.winning_score,
            "round_timer_seconds": room_obj.round_timer_seconds,
            "card_pool_mode": room_obj.card_pool_mode,
            "matchmaking_fill_expires_at": room_obj.matchmaking_fill_expires_at,
        },
        "players": players,
        "game": None,
    }


@router.websocket("/ws/rooms/{room_id}")
async def ws_room_channel(
    websocket: WebSocket,
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Handle authenticated room channel session and baseline protocol commands."""
    connected_user_id: UUID | None = None

    try:
        token = websocket.query_params.get("token")
        user = await _resolve_current_user(db, token)
        if user is None:
            await _send_error(websocket, room_id, "UNAUTHORIZED", "Invalid or expired token")
            await websocket.close(code=4401)
            return

        try:
            room = await RoomService.get_room_for_member(db, room_id, user.id)
        except HTTPException as exc:
            if exc.status_code == 404:
                await _send_error(websocket, room_id, "ROOM_NOT_FOUND", "Room not found")
                await websocket.close(code=4404)
                return

            await _send_error(websocket, room_id, "FORBIDDEN", "Not a room member")
            await websocket.close(code=4403)
            return

        await connection_manager.connect(room_id, user.id, websocket)
        connected_user_id = user.id

        connected_event = WSEvent(
            event="room.connected",
            room_id=room_id,
            payload={
                "user_id": str(user.id),
                "room_status": room.status,
            },
        )
        await websocket.send_json(connected_event.model_dump(mode="json"))

        sync_payload = await _build_room_state_payload(db, room_id)
        sync_event = WSEvent(event="room.state_sync", room_id=room_id, payload=sync_payload)
        await websocket.send_json(sync_event.model_dump(mode="json"))

        while True:
            incoming = await websocket.receive_json()
            event_name = incoming.get("event")
            correlation_id = _safe_uuid(incoming.get("correlation_id"))

            if event_name == "client.ping":
                pong_event = WSEvent(
                    event="server.pong",
                    room_id=room_id,
                    correlation_id=correlation_id,
                    payload={
                        "sent_at": incoming.get("payload", {}).get("sent_at"),
                        "received_at": datetime.now(UTC),
                    },
                )
                await websocket.send_json(pong_event.model_dump(mode="json"))
                continue

            if event_name == "room.state_sync.request":
                sync_payload = await _build_room_state_payload(db, room_id)
                sync_event = WSEvent(
                    event="room.state_sync",
                    room_id=room_id,
                    correlation_id=correlation_id,
                    payload=sync_payload,
                )
                await websocket.send_json(sync_event.model_dump(mode="json"))
                continue

            error_event = WSEvent(
                event="error",
                room_id=room_id,
                correlation_id=correlation_id,
                payload={
                    "code": "INVALID_EVENT",
                    "message": "Unsupported event",
                    "details": {"event": event_name},
                },
            )
            await websocket.send_json(error_event.model_dump(mode="json"))

    except WebSocketDisconnect:
        pass
    finally:
        if connected_user_id is not None:
            connection_manager.disconnect(room_id, connected_user_id)
