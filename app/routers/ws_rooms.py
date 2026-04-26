"""Room WebSocket router for real-time lobby and game events."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models import Room, User
from app.schemas.ws import WSEvent
from app.services.auth import AuthService
from app.services.rooms import RoomGameError, RoomService
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


def _safe_uuid_list(values: list[str] | None) -> list[UUID] | None:
    """Parse list of UUID strings safely for command payload validation."""
    if values is None:
        return None

    parsed: list[UUID] = []
    for raw in values:
        item = _safe_uuid(raw)
        if item is None:
            return None
        parsed.append(item)

    return parsed


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


async def _build_room_state_payload(
    db: AsyncSession,
    room_id: UUID,
    redis_client,
    current_user_id: UUID,
) -> dict:
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
        "game": await RoomService.build_game_state(db, room_id, redis_client, current_user_id),
    }


async def _send_protocol_error(
    websocket: WebSocket,
    room_id: UUID,
    code: str,
    message: str,
    correlation_id: UUID | None,
    details: dict | None = None,
) -> None:
    """Send protocol error event on an already-open websocket channel."""
    error_event = WSEvent(
        event="error",
        room_id=room_id,
        correlation_id=correlation_id,
        payload={
            "code": code,
            "message": message,
            "details": details or {},
        },
    )
    await websocket.send_json(error_event.model_dump(mode="json"))


async def _handle_start_game(
    websocket: WebSocket,
    db: AsyncSession,
    redis_client,
    room: Room,
    room_id: UUID,
    current_user_id: UUID,
    correlation_id: UUID | None,
) -> None:
    """Handle host command to start a game from lobby state."""
    try:
        outcome = await RoomService.start_game(db, room, current_user_id, redis_client)
    except RoomGameError as exc:
        await _send_protocol_error(
            websocket,
            room_id,
            exc.code,
            exc.message,
            correlation_id,
            exc.details,
        )
        await db.rollback()
        return

    await db.commit()

    await connection_manager.broadcast_event(
        room_id,
        WSEvent(
            event="game.started",
            room_id=room_id,
            correlation_id=correlation_id,
            payload={
                "started_at": datetime.now(UTC),
                "round_number": outcome["round_number"],
                "players": [
                    {"player_id": str(player["player_id"]), "score": player["score"]}
                    for player in outcome["players"]
                ],
            },
        ).model_dump(mode="json"),
    )

    await connection_manager.broadcast_event(
        room_id,
        WSEvent(
            event="round.started",
            room_id=room_id,
            payload={
                "round_id": str(outcome["round"].id),
                "round_number": outcome["round_number"],
                "czar_id": str(outcome["round"].czar_id),
                "black_card": {
                    "id": str(outcome["black_card"].id),
                    "text": outcome["black_card"].text,
                    "pick": outcome["black_card"].pick,
                },
                "round_expires_at": None,
            },
        ).model_dump(mode="json"),
    )


async def _handle_submit_cards(
    websocket: WebSocket,
    db: AsyncSession,
    redis_client,
    room: Room,
    room_id: UUID,
    current_user_id: UUID,
    correlation_id: UUID | None,
    payload: dict,
) -> None:
    """Handle player white-card submission command for active round."""
    round_id = _safe_uuid(payload.get("round_id"))
    white_card_ids = _safe_uuid_list(payload.get("white_card_ids"))
    if round_id is None or white_card_ids is None or not white_card_ids:
        await _send_protocol_error(
            websocket,
            room_id,
            "INVALID_PAYLOAD",
            "round_id and white_card_ids are required",
            correlation_id,
        )
        return

    try:
        outcome = await RoomService.submit_cards(
            db,
            room,
            current_user_id,
            round_id,
            white_card_ids,
            redis_client,
        )
    except RoomGameError as exc:
        await _send_protocol_error(
            websocket,
            room_id,
            exc.code,
            exc.message,
            correlation_id,
            exc.details,
        )
        await db.rollback()
        return

    await db.commit()
    if outcome["transition"] == "judging":
        await connection_manager.broadcast_event(
            room_id,
            WSEvent(
                event="round.judging",
                room_id=room_id,
                payload={
                    "round_id": str(outcome["round"].id),
                    "submissions": outcome["submissions"],
                },
            ).model_dump(mode="json"),
        )
        return

    await connection_manager.broadcast_event(
        room_id,
        WSEvent(
            event="round.submission_accepted",
            room_id=room_id,
            correlation_id=correlation_id,
            payload={
                "round_id": str(outcome["round"].id),
                "player_id": str(current_user_id),
                "submitted_count": outcome["submitted_count"],
                "required_count": outcome["required_count"],
            },
        ).model_dump(mode="json"),
    )


async def _handle_pick_winner(
    websocket: WebSocket,
    db: AsyncSession,
    redis_client,
    room: Room,
    room_id: UUID,
    current_user_id: UUID,
    correlation_id: UUID | None,
    payload: dict,
) -> None:
    """Handle czar winner selection for judging round."""
    round_id = _safe_uuid(payload.get("round_id"))
    submission_id = _safe_uuid(payload.get("submission_id"))
    if round_id is None or submission_id is None:
        await _send_protocol_error(
            websocket,
            room_id,
            "INVALID_PAYLOAD",
            "round_id and submission_id are required",
            correlation_id,
        )
        return

    try:
        outcome = await RoomService.pick_winner(
            db,
            room,
            current_user_id,
            round_id,
            submission_id,
            redis_client,
        )
    except RoomGameError as exc:
        await _send_protocol_error(
            websocket,
            room_id,
            exc.code,
            exc.message,
            correlation_id,
            exc.details,
        )
        await db.rollback()
        return

    await db.commit()

    await connection_manager.broadcast_event(
        room_id,
        WSEvent(
            event="round.result",
            room_id=room_id,
            correlation_id=correlation_id,
            payload={
                "round_id": str(round_id),
                "winner_player_id": str(outcome["winner_submission"].player_id),
                "winning_submission_id": str(outcome["winner_submission"].id),
                "scores": [
                    {
                        "player_id": str(item.player_id),
                        "score": item.score,
                    }
                    for item in outcome["scoreboard"]
                ],
            },
        ).model_dump(mode="json"),
    )

    if outcome["game_winner"] is not None:
        await connection_manager.broadcast_event(
            room_id,
            WSEvent(
                event="game.over",
                room_id=room_id,
                payload={
                    "winner_player_id": str(outcome["game_winner"].player_id),
                    "scoreboard": [
                        {
                            "player_id": str(item.player_id),
                            "score": item.score,
                        }
                        for item in outcome["scoreboard"]
                    ],
                },
            ).model_dump(mode="json"),
        )
        return

    await connection_manager.broadcast_event(
        room_id,
        WSEvent(
            event="round.started",
            room_id=room_id,
            payload={
                "round_id": str(outcome["next_round"].id),
                "round_number": outcome["next_round"].round_number,
                "czar_id": str(outcome["next_round"].czar_id),
                "black_card": {
                    "id": str(outcome["next_black_card"].id),
                    "text": outcome["next_black_card"].text,
                    "pick": outcome["next_black_card"].pick,
                },
                "round_expires_at": None,
            },
        ).model_dump(mode="json"),
    )


@router.websocket("/ws/rooms/{room_id}")
async def ws_room_channel(
    websocket: WebSocket,
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Handle authenticated room channel session and baseline protocol commands."""
    connected_user_id: UUID | None = None
    authenticated_user_id: UUID | None = None
    redis_client = redis.from_url(settings.REDIS_URL)

    try:
        token = websocket.query_params.get("token")
        user = await _resolve_current_user(db, token)
        if user is None:
            await _send_error(websocket, room_id, "UNAUTHORIZED", "Invalid or expired token")
            await websocket.close(code=4401)
            return
        authenticated_user_id = user.id

        try:
            room = await RoomService.get_room_for_member(db, room_id, authenticated_user_id)
        except HTTPException as exc:
            if exc.status_code == 404:
                await _send_error(websocket, room_id, "ROOM_NOT_FOUND", "Room not found")
                await websocket.close(code=4404)
                return

            await _send_error(websocket, room_id, "FORBIDDEN", "Not a room member")
            await websocket.close(code=4403)
            return

        await connection_manager.connect(room_id, authenticated_user_id, websocket)
        connected_user_id = authenticated_user_id

        connected_event = WSEvent(
            event="room.connected",
            room_id=room_id,
            payload={
                "user_id": str(authenticated_user_id),
                "room_status": room.status,
            },
        )
        await websocket.send_json(connected_event.model_dump(mode="json"))

        sync_payload = await _build_room_state_payload(
            db,
            room_id,
            redis_client,
            authenticated_user_id,
        )
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
                sync_payload = await _build_room_state_payload(
                    db,
                    room_id,
                    redis_client,
                    authenticated_user_id,
                )
                sync_event = WSEvent(
                    event="room.state_sync",
                    room_id=room_id,
                    correlation_id=correlation_id,
                    payload=sync_payload,
                )
                await websocket.send_json(sync_event.model_dump(mode="json"))
                continue

            if event_name == "lobby.start_game":
                await db.refresh(room)
                await _handle_start_game(
                    websocket=websocket,
                    db=db,
                    redis_client=redis_client,
                    room=room,
                    room_id=room_id,
                    current_user_id=authenticated_user_id,
                    correlation_id=correlation_id,
                )
                await db.refresh(room)
                continue

            if event_name == "game.submit_cards":
                await db.refresh(room)
                await _handle_submit_cards(
                    websocket=websocket,
                    db=db,
                    redis_client=redis_client,
                    room=room,
                    room_id=room_id,
                    current_user_id=authenticated_user_id,
                    correlation_id=correlation_id,
                    payload=incoming.get("payload", {}),
                )
                await db.refresh(room)
                continue

            if event_name == "game.pick_winner":
                await db.refresh(room)
                await _handle_pick_winner(
                    websocket=websocket,
                    db=db,
                    redis_client=redis_client,
                    room=room,
                    room_id=room_id,
                    current_user_id=authenticated_user_id,
                    correlation_id=correlation_id,
                    payload=incoming.get("payload", {}),
                )
                await db.refresh(room)
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
        await redis_client.aclose()
        if connected_user_id is not None:
            connection_manager.disconnect(room_id, connected_user_id, websocket)
