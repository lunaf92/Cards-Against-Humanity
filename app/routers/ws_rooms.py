"""Room WebSocket router for real-time lobby and game events."""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime, timedelta
from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import database
from app.core.config import settings
from app.core.security import decode_token
from app.models import GameRound, Room, Submission, User
from app.schemas.ws import WSEvent
from app.services.auth import AuthService
from app.services.rooms import RECONNECT_WINDOW_TTL, RoomGameError, RoomService
from app.services.ws_connection_manager import connection_manager

router = APIRouter(tags=["ws"])

# NOTE: these task registries are process-local. Timers and reconnect windows only
# work while the app runs as a single process (see docs/FUTURE_WORK.md).
_reconnect_timeout_tasks: dict[tuple[UUID, UUID], asyncio.Task] = {}
_round_timer_tasks: dict[tuple[UUID, UUID], asyncio.Task] = {}
_judging_timer_tasks: dict[tuple[UUID, UUID], asyncio.Task] = {}


def _cancel_round_timer_task(room_id: UUID, round_id: UUID) -> None:
    """Cancel scheduled round timer task if present."""
    task = _round_timer_tasks.pop((room_id, round_id), None)
    if task is not None and not task.done():
        task.cancel()


def _schedule_round_timer_task(room_id: UUID, round_id: UUID, duration_seconds: int) -> None:
    """Cancel any existing round timer and schedule a fresh one."""
    _cancel_round_timer_task(room_id, round_id)
    _round_timer_tasks[(room_id, round_id)] = asyncio.create_task(
        _run_round_timer(room_id, round_id, duration_seconds)
    )


def _cancel_judging_timer_task(room_id: UUID, round_id: UUID) -> None:
    """Cancel scheduled judging timer task if present."""
    task = _judging_timer_tasks.pop((room_id, round_id), None)
    if task is not None and not task.done():
        task.cancel()


def _schedule_judging_timer_task(room_id: UUID, round_id: UUID, duration_seconds: int) -> None:
    """Cancel any existing judging timer and schedule a fresh one."""
    _cancel_judging_timer_task(room_id, round_id)
    _judging_timer_tasks[(room_id, round_id)] = asyncio.create_task(
        _run_judging_timer(room_id, round_id, duration_seconds)
    )


def _cancel_reconnect_timeout_task(room_id: UUID, player_id: UUID) -> None:
    """Cancel scheduled reconnect timeout task for a player if present."""
    task = _reconnect_timeout_tasks.pop((room_id, player_id), None)
    if task is not None and not task.done():
        task.cancel()


def _schedule_reconnect_timeout_task(room_id: UUID, player_id: UUID) -> None:
    """Schedule reconnect timeout handling for a disconnected player."""
    _cancel_reconnect_timeout_task(room_id, player_id)
    _reconnect_timeout_tasks[(room_id, player_id)] = asyncio.create_task(
        _run_reconnect_timeout(room_id, player_id)
    )


async def _get_room_for_update(db: AsyncSession, room_id: UUID) -> Room | None:
    """Load room row with a row lock so concurrent commands serialize per room."""
    result = await db.execute(select(Room).where(Room.id == room_id).with_for_update())
    return result.scalar_one_or_none()


async def _broadcast_round_started(
    room_id: UUID,
    round_obj: GameRound,
    black_card,
    round_timer_seconds: int,
) -> None:
    """Broadcast round.started for a new round and schedule its submission timer."""
    round_expires_at = datetime.now(UTC) + timedelta(seconds=round_timer_seconds)
    await connection_manager.broadcast_event(
        room_id,
        WSEvent(
            event="round.started",
            room_id=room_id,
            payload={
                "round_id": str(round_obj.id),
                "round_number": round_obj.round_number,
                "czar_id": str(round_obj.czar_id),
                "black_card": {
                    "id": str(black_card.id),
                    "text": black_card.text,
                    "pick": black_card.pick,
                },
                "round_expires_at": round_expires_at,
            },
        ).model_dump(mode="json"),
    )
    _schedule_round_timer_task(room_id, round_obj.id, round_timer_seconds)


async def _broadcast_pick_winner_outcome(
    room_id: UUID,
    round_id: UUID,
    outcome: dict,
    correlation_id: UUID | None,
    round_timer_seconds: int,
) -> None:
    """Broadcast round result, then either game over or the next round start."""
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

    await _broadcast_round_started(
        room_id,
        outcome["next_round"],
        outcome["next_black_card"],
        round_timer_seconds,
    )


async def _run_round_timer(room_id: UUID, round_id: UUID, duration_seconds: int) -> None:
    """Auto-submit for non-submitting players when the round timer expires.

    If nobody managed to submit, the round is skipped instead of leaving the
    game stuck in a waiting state without a timer.
    """
    try:
        await asyncio.sleep(duration_seconds)
        redis_client = redis.from_url(settings.REDIS_URL)
        try:
            judging_submissions = None
            next_round_started = None
            round_timer_seconds = duration_seconds
            async with database.async_session() as db:
                round_result = await db.execute(
                    select(GameRound).where(GameRound.id == round_id, GameRound.room_id == room_id)
                )
                round_obj = round_result.scalar_one_or_none()
                if round_obj is None or round_obj.status != "waiting":
                    return

                room = await _get_room_for_update(db, room_id)
                if room is None or room.status != "in_progress":
                    return
                round_timer_seconds = room.round_timer_seconds

                # Find players who haven't submitted yet (excluding czar)
                submitted_ids_result = await db.execute(
                    select(Submission.player_id).where(Submission.round_id == round_id)
                )
                submitted_ids = {row[0] for row in submitted_ids_result.all()}

                pending_player_ids = [
                    player.player_id
                    for player in await RoomService._ordered_room_player_rows(db, room_id)
                    if player.player_id != round_obj.czar_id and player.player_id not in submitted_ids
                ]

                for player_id in pending_player_ids:
                    hand = await RoomService.get_player_hand(redis_client, room_id, player_id)
                    if not hand:
                        continue
                    try:
                        await RoomService.submit_cards(
                            db,
                            room,
                            player_id,
                            round_id,
                            hand[:1],
                            redis_client,
                        )
                    except RoomGameError:
                        continue

                if round_obj.status == "waiting":
                    # Auto-submits didn't complete the round; force a transition.
                    submission_count_result = await db.execute(
                        select(Submission.id).where(Submission.round_id == round_id).limit(1)
                    )
                    if submission_count_result.scalar_one_or_none() is not None:
                        round_obj.status = "judging"
                    else:
                        # No submissions at all: skip the round entirely.
                        round_obj.status = "complete"
                        try:
                            next_czar_id = await RoomService._next_czar_id(
                                db, room_id, round_obj.czar_id
                            )
                            next_round_started = await RoomService._create_round(
                                db,
                                redis_client,
                                room,
                                round_obj.round_number + 1,
                                next_czar_id,
                            )
                        except RoomGameError:
                            room.status = "finished"

                if round_obj.status == "judging":
                    judging_submissions = await RoomService._round_submission_payload(db, round_id)

                await db.commit()

            await connection_manager.broadcast_event(
                room_id,
                WSEvent(
                    event="round.timer_expired",
                    room_id=room_id,
                    payload={"round_id": str(round_id)},
                ).model_dump(mode="json"),
            )

            if judging_submissions is not None:
                await connection_manager.broadcast_event(
                    room_id,
                    WSEvent(
                        event="round.judging",
                        room_id=room_id,
                        payload={
                            "round_id": str(round_id),
                            "submissions": judging_submissions,
                        },
                    ).model_dump(mode="json"),
                )
                _schedule_judging_timer_task(room_id, round_id, round_timer_seconds)
            elif next_round_started is not None:
                next_round, next_black_card = next_round_started
                await _broadcast_round_started(
                    room_id, next_round, next_black_card, round_timer_seconds
                )
        finally:
            await redis_client.aclose()
    except asyncio.CancelledError:
        return
    finally:
        _round_timer_tasks.pop((room_id, round_id), None)


async def _run_judging_timer(room_id: UUID, round_id: UUID, duration_seconds: int) -> None:
    """Pick a random winner when the czar fails to judge before the timer expires."""
    try:
        await asyncio.sleep(duration_seconds)
        redis_client = redis.from_url(settings.REDIS_URL)
        try:
            outcome = None
            round_timer_seconds = duration_seconds
            async with database.async_session() as db:
                round_result = await db.execute(
                    select(GameRound).where(GameRound.id == round_id, GameRound.room_id == room_id)
                )
                round_obj = round_result.scalar_one_or_none()
                if round_obj is None or round_obj.status != "judging":
                    return

                room = await _get_room_for_update(db, room_id)
                if room is None or room.status != "in_progress":
                    return
                round_timer_seconds = room.round_timer_seconds

                submissions_result = await db.execute(
                    select(Submission).where(Submission.round_id == round_id)
                )
                submissions = submissions_result.scalars().all()
                if not submissions:
                    return

                try:
                    outcome = await RoomService.pick_winner(
                        db,
                        room,
                        round_obj.czar_id,
                        round_id,
                        random.choice(submissions).id,
                        redis_client,
                    )
                except RoomGameError:
                    await db.rollback()
                    return
                await db.commit()

            await connection_manager.broadcast_event(
                room_id,
                WSEvent(
                    event="round.judging_expired",
                    room_id=room_id,
                    payload={"round_id": str(round_id), "reason": "czar_timeout"},
                ).model_dump(mode="json"),
            )
            await _broadcast_pick_winner_outcome(
                room_id, round_id, outcome, None, round_timer_seconds
            )
        finally:
            await redis_client.aclose()
    except asyncio.CancelledError:
        return
    finally:
        _judging_timer_tasks.pop((room_id, round_id), None)


async def _run_reconnect_timeout(room_id: UUID, player_id: UUID) -> None:
    """Emit timeout removal event when reconnect window expires."""
    try:
        await asyncio.sleep(RECONNECT_WINDOW_TTL)
        redis_client = redis.from_url(settings.REDIS_URL)
        try:
            still_disconnected = await RoomService.is_player_in_reconnect_window(
                redis_client,
                room_id,
                player_id,
            )
            if not still_disconnected:
                return

            await RoomService.clear_reconnect_window(redis_client, room_id, player_id)

            async with database.async_session() as db:
                timeout_outcome = await RoomService.handle_player_timeout(
                    db,
                    redis_client,
                    room_id,
                    player_id,
                )
                await db.commit()

            await connection_manager.broadcast_event(
                room_id,
                WSEvent(
                    event="player.removed_timeout",
                    room_id=room_id,
                    payload={
                        "player_id": str(player_id),
                        "reason": "reconnect_timeout",
                    },
                ).model_dump(mode="json"),
            )

            if timeout_outcome["czar_timed_out"] and timeout_outcome["next_round"] is not None:
                next_round = timeout_outcome["next_round"]
                next_black_card = timeout_outcome["next_black_card"]
                skipped_round_id = timeout_outcome.get("skipped_round_id")
                round_timer_seconds = int(timeout_outcome.get("round_timer_seconds") or RECONNECT_WINDOW_TTL)
                if skipped_round_id is not None:
                    _cancel_round_timer_task(room_id, skipped_round_id)
                    _cancel_judging_timer_task(room_id, skipped_round_id)

                await _broadcast_round_started(
                    room_id, next_round, next_black_card, round_timer_seconds
                )
        finally:
            await redis_client.aclose()
    except asyncio.CancelledError:
        return
    finally:
        _reconnect_timeout_tasks.pop((room_id, player_id), None)


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

    if payload.get("type") != "access":
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
    redis_client,
    room_id: UUID,
    current_user_id: UUID,
    correlation_id: UUID | None,
) -> None:
    """Handle host command to start a game from lobby state."""
    async with database.async_session() as db:
        room = await _get_room_for_update(db, room_id)
        if room is None:
            await _send_protocol_error(
                websocket, room_id, "ROOM_NOT_FOUND", "Room not found", correlation_id
            )
            return

        should_broadcast_locked = room.room_kind == "random" and room.status == "matchmaking_lobby"
        try:
            outcome = await RoomService.start_game(db, room, current_user_id, redis_client)
        except RoomGameError as exc:
            await db.rollback()
            await _send_protocol_error(
                websocket,
                room_id,
                exc.code,
                exc.message,
                correlation_id,
                exc.details,
            )
            return

        await db.commit()
        round_timer_seconds = room.round_timer_seconds

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

    if should_broadcast_locked:
        await connection_manager.broadcast_event(
            room_id,
            WSEvent(
                event="matchmaking.locked",
                room_id=room_id,
                payload={
                    "reason": "host_started",
                    "player_count": len(outcome["players"]),
                },
            ).model_dump(mode="json"),
        )

    await _broadcast_round_started(
        room_id, outcome["round"], outcome["black_card"], round_timer_seconds
    )


async def _handle_submit_cards(
    websocket: WebSocket,
    redis_client,
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

    async with database.async_session() as db:
        room = await _get_room_for_update(db, room_id)
        if room is None:
            await _send_protocol_error(
                websocket, room_id, "ROOM_NOT_FOUND", "Room not found", correlation_id
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
            await db.rollback()
            await _send_protocol_error(
                websocket,
                room_id,
                exc.code,
                exc.message,
                correlation_id,
                exc.details,
            )
            return

        await db.commit()
        round_timer_seconds = room.round_timer_seconds

    if outcome["transition"] == "judging":
        _cancel_round_timer_task(room_id, outcome["round"].id)
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
        _schedule_judging_timer_task(room_id, outcome["round"].id, round_timer_seconds)
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
    redis_client,
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

    async with database.async_session() as db:
        room = await _get_room_for_update(db, room_id)
        if room is None:
            await _send_protocol_error(
                websocket, room_id, "ROOM_NOT_FOUND", "Room not found", correlation_id
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
            await db.rollback()
            await _send_protocol_error(
                websocket,
                room_id,
                exc.code,
                exc.message,
                correlation_id,
                exc.details,
            )
            return

        await db.commit()
        round_timer_seconds = room.round_timer_seconds

    _cancel_judging_timer_task(room_id, round_id)
    await _broadcast_pick_winner_outcome(
        room_id, round_id, outcome, correlation_id, round_timer_seconds
    )


@router.websocket("/ws/rooms/{room_id}")
async def ws_room_channel(websocket: WebSocket, room_id: UUID):
    """Handle authenticated room channel session and baseline protocol commands.

    Database sessions are opened per operation instead of per connection so idle
    sockets do not pin connection-pool slots or hold transactions open.
    """
    connected_user_id: UUID | None = None
    redis_client = redis.from_url(settings.REDIS_URL)

    try:
        token = websocket.query_params.get("token")
        async with database.async_session() as db:
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

            room_kind = room.room_kind
            room_status = room.status

        had_existing_socket = connection_manager.has_user_connections(room_id, authenticated_user_id)
        await connection_manager.connect(room_id, authenticated_user_id, websocket)
        connected_user_id = authenticated_user_id

        player_joined_payload: dict | None = None
        if not had_existing_socket:
            async with database.async_session() as db:
                player_joined_payload = await RoomService.mark_player_connection_state(
                    db,
                    room_id,
                    authenticated_user_id,
                    is_connected=True,
                )
                await db.commit()

            was_in_reconnect_window = await RoomService.is_player_in_reconnect_window(
                redis_client,
                room_id,
                authenticated_user_id,
            )
            if was_in_reconnect_window:
                _cancel_reconnect_timeout_task(room_id, authenticated_user_id)
                await RoomService.clear_reconnect_window(redis_client, room_id, authenticated_user_id)
                await connection_manager.broadcast_event(
                    room_id,
                    WSEvent(
                        event="player.reconnected",
                        room_id=room_id,
                        payload={"player_id": str(authenticated_user_id)},
                    ).model_dump(mode="json"),
                )

        connected_event = WSEvent(
            event="room.connected",
            room_id=room_id,
            payload={
                "user_id": str(authenticated_user_id),
                "room_status": room_status,
            },
        )
        await websocket.send_json(connected_event.model_dump(mode="json"))

        async with database.async_session() as db:
            sync_payload = await _build_room_state_payload(
                db,
                room_id,
                redis_client,
                authenticated_user_id,
            )
        sync_event = WSEvent(event="room.state_sync", room_id=room_id, payload=sync_payload)
        await websocket.send_json(sync_event.model_dump(mode="json"))

        if player_joined_payload is not None and connection_manager.has_other_connected_users(room_id, authenticated_user_id):
            await connection_manager.broadcast_event(
                room_id,
                WSEvent(
                    event="room.player_joined",
                    room_id=room_id,
                    payload={"player": player_joined_payload},
                ).model_dump(mode="json"),
            )

        if room_kind == "random" and room_status == "matchmaking_lobby":
            async with database.async_session() as db:
                player_count = await RoomService._room_player_count(db, room_id)
                countdown_state = await RoomService.get_matchmaking_state(db, room_id)

            await connection_manager.broadcast_event(
                room_id,
                WSEvent(
                    event="matchmaking.match_found",
                    room_id=room_id,
                    payload={
                        "room_id": str(room_id),
                        "player_count": player_count,
                    },
                ).model_dump(mode="json"),
            )

            if countdown_state and countdown_state["fill_expires_at"] is not None:
                await connection_manager.broadcast_event(
                    room_id,
                    WSEvent(
                        event="matchmaking.countdown_started",
                        room_id=room_id,
                        payload={
                            "expires_at": countdown_state["fill_expires_at"],
                            "seconds_remaining": max(0, countdown_state["seconds_remaining"] or 0),
                            "player_count": countdown_state["player_count"],
                        },
                    ).model_dump(mode="json"),
                )

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
                async with database.async_session() as db:
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
                await _handle_start_game(
                    websocket=websocket,
                    redis_client=redis_client,
                    room_id=room_id,
                    current_user_id=authenticated_user_id,
                    correlation_id=correlation_id,
                )
                continue

            if event_name == "game.submit_cards":
                await _handle_submit_cards(
                    websocket=websocket,
                    redis_client=redis_client,
                    room_id=room_id,
                    current_user_id=authenticated_user_id,
                    correlation_id=correlation_id,
                    payload=incoming.get("payload", {}),
                )
                continue

            if event_name == "game.pick_winner":
                await _handle_pick_winner(
                    websocket=websocket,
                    redis_client=redis_client,
                    room_id=room_id,
                    current_user_id=authenticated_user_id,
                    correlation_id=correlation_id,
                    payload=incoming.get("payload", {}),
                )
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
            disconnected_user = connection_manager.disconnect(room_id, connected_user_id, websocket)
            if disconnected_user:
                async with database.async_session() as db:
                    disconnect_outcome = await RoomService.handle_lobby_disconnect(
                        db,
                        room_id,
                        connected_user_id,
                    )
                    await db.commit()

                room_status = disconnect_outcome.get("room_status")

                # No reconnect window once a game is over (or the room is gone).
                if room_status in ("lobby", "matchmaking_lobby", "in_progress"):
                    reconnect_payload = await RoomService.start_reconnect_window(
                        redis_client, room_id, connected_user_id
                    )
                    _schedule_reconnect_timeout_task(room_id, connected_user_id)
                    await connection_manager.broadcast_event(
                        room_id,
                        WSEvent(
                            event="player.reconnect_window_started",
                            room_id=room_id,
                            payload=reconnect_payload,
                        ).model_dump(mode="json"),
                    )

                if room_status in ("lobby", "matchmaking_lobby"):
                    await connection_manager.broadcast_event(
                        room_id,
                        WSEvent(
                            event="room.player_left",
                            room_id=room_id,
                            payload={
                                "player_id": str(connected_user_id),
                                "reason": "disconnect",
                            },
                        ).model_dump(mode="json"),
                    )

                    host_changed = disconnect_outcome.get("host_changed")
                    if host_changed is not None:
                        await connection_manager.broadcast_event(
                            room_id,
                            WSEvent(
                                event="room.host_changed",
                                room_id=room_id,
                                payload={
                                    "previous_host_id": str(host_changed["previous_host_id"]),
                                    "new_host_id": str(host_changed["new_host_id"]),
                                },
                            ).model_dump(mode="json"),
                        )

        await redis_client.aclose()
