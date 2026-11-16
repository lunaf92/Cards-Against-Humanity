"""Room schemas for private rooms and matchmaking flow."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


RoomKind = Literal["private", "random"]
RoomStatus = Literal["lobby", "matchmaking_lobby", "in_progress", "finished"]


class RoomCreateRequest(BaseModel):
    """Request payload for creating a private room."""

    password: str = Field(min_length=4, max_length=64)
    max_players: int = Field(default=10, ge=2, le=10)
    winning_score: int = Field(default=8, ge=3, le=20)
    round_timer_seconds: int = Field(default=90, ge=30, le=300)
    # Decks to deal from; omitted means the default built-in packs.
    deck_ids: list[UUID] | None = Field(default=None, min_length=1)


class RoomJoinRequest(BaseModel):
    """Request payload for joining a private room by code/password."""

    code: str = Field(min_length=6, max_length=6)
    password: str = Field(min_length=1, max_length=64)


class RoomConfigUpdateRequest(BaseModel):
    """Host-only room configuration changes while lobby is open."""

    max_players: int | None = Field(default=None, ge=2, le=10)
    winning_score: int | None = Field(default=None, ge=3, le=20)
    round_timer_seconds: int | None = Field(default=None, ge=30, le=300)
    deck_ids: list[UUID] | None = Field(default=None, min_length=1)


class RoomDeckSummary(BaseModel):
    """A deck a room deals from."""

    id: UUID
    name: str
    is_builtin: bool
    is_public: bool
    black_count: int
    white_count: int


class RoomPlayerResponse(BaseModel):
    """Player entry in room details."""

    player_id: UUID
    username: str
    join_order: int
    score: int
    is_connected: bool


class RoomResponse(BaseModel):
    """Room response payload."""

    id: UUID
    code: str
    host_id: UUID | None
    room_kind: RoomKind
    status: RoomStatus
    max_players: int
    winning_score: int
    round_timer_seconds: int
    decks: list[RoomDeckSummary] = []
    matchmaking_fill_expires_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class RoomDetailsResponse(RoomResponse):
    """Room details with current player list."""

    players: list[RoomPlayerResponse]


class QueueResponse(BaseModel):
    """Queue operation response payload."""

    queued: bool
    queue_size: int
    matched_room_id: UUID | None = None


class QueueLeaveResponse(BaseModel):
    """Leave queue response payload."""

    removed: bool


class ActiveRoomResponse(BaseModel):
    """The caller's current unfinished room, or null when they are in none."""

    room: RoomDetailsResponse | None
