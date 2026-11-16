"""Room endpoints for private rooms and random matchmaking queue."""
from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User
from app.schemas.room import (
    ActiveRoomResponse,
    QueueLeaveResponse,
    QueueResponse,
    RoomConfigUpdateRequest,
    RoomCreateRequest,
    RoomDetailsResponse,
    RoomJoinRequest,
    RoomResponse,
)
from app.services.rooms import RoomService
from app.schemas.ws import WSEvent
from app.services.ws_connection_manager import connection_manager

router = APIRouter(prefix="/rooms", tags=["rooms"])


async def _build_room_details(db: AsyncSession, room) -> RoomDetailsResponse:
    """Shape room plus player list into API response model."""
    players = await RoomService.list_room_players(db, room.id)
    room_data = RoomResponse.model_validate(room).model_dump()
    return RoomDetailsResponse(**room_data, players=players)


@router.post("", response_model=RoomDetailsResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: RoomCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create private room, generate code, and insert host as first player."""
    room = await RoomService.create_private_room(db, current_user, payload)
    await db.commit()
    await db.refresh(room)
    return await _build_room_details(db, room)


@router.post("/join", response_model=RoomDetailsResponse)
async def join_room(
    payload: RoomJoinRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Join a private room by code and password with capacity validation."""
    room = await RoomService.join_private_room(db, current_user, payload)
    await db.commit()
    await db.refresh(room)
    return await _build_room_details(db, room)


@router.post("/queue", response_model=QueueResponse)
async def join_matchmaking_queue(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enter random matchmaking queue and promote first 3 players into lobby."""
    redis_client = redis.from_url(settings.REDIS_URL)
    try:
        queue_size, matched_room_id, is_new_room = await RoomService.enqueue_for_matchmaking(
            db=db,
            redis_client=redis_client,
            user=current_user,
        )
        await db.commit()

        if matched_room_id is not None and not is_new_room:
            matchmaking_state = await RoomService.get_matchmaking_state(db, matched_room_id)
            if matchmaking_state and matchmaking_state["fill_expires_at"] is not None:
                await connection_manager.broadcast_event(
                    matched_room_id,
                    WSEvent(
                        event="matchmaking.countdown_reset",
                        room_id=matched_room_id,
                        payload={
                            "expires_at": matchmaking_state["fill_expires_at"],
                            "seconds_remaining": max(
                                0,
                                matchmaking_state["seconds_remaining"] or 0,
                            ),
                            "player_count": matchmaking_state["player_count"],
                        },
                    ).model_dump(mode="json"),
                )

        return QueueResponse(
            queued=True,
            queue_size=queue_size,
            matched_room_id=matched_room_id,
        )
    finally:
        await redis_client.close()


@router.delete("/queue", response_model=QueueLeaveResponse)
async def leave_matchmaking_queue(current_user: User = Depends(get_current_user)):
    """Leave the random matchmaking queue."""
    redis_client = redis.from_url(settings.REDIS_URL)
    try:
        removed = await RoomService.leave_matchmaking_queue(redis_client, current_user.id)
        return QueueLeaveResponse(removed=removed)
    finally:
        await redis_client.close()


@router.get("/active", response_model=ActiveRoomResponse)
async def get_active_room(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the caller's newest unfinished room so clients can resume or detect a match."""
    room = await RoomService.get_active_room_for_user(db, current_user.id)
    if room is None:
        return ActiveRoomResponse(room=None)
    return ActiveRoomResponse(room=await _build_room_details(db, room))


@router.get("/{room_id}", response_model=RoomDetailsResponse)
async def get_room_details(
    room_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return room details and player list for room members (reconnect support)."""
    room = await RoomService.get_room_for_member(db, room_id, current_user.id)
    return await _build_room_details(db, room)


@router.patch("/{room_id}/config", response_model=RoomDetailsResponse)
async def update_room_config(
    room_id: UUID,
    payload: RoomConfigUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Host-only room configuration update while room status is lobby."""
    room = await RoomService.update_room_config(
        db=db,
        room_id=room_id,
        host_user_id=current_user.id,
        payload=payload,
    )
    await db.commit()
    await db.refresh(room)
    details = await _build_room_details(db, room)
    # Non-host clients only learn about setting changes through the room socket.
    await connection_manager.broadcast_event(
        room.id,
        WSEvent(
            event="room.config_updated",
            room_id=room.id,
            payload={"room": RoomResponse.model_validate(room).model_dump(mode="json")},
        ).model_dump(mode="json"),
    )
    return details
