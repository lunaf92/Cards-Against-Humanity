"""WebSocket message schemas for room protocol v1."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class WSEvent(BaseModel):
    """Generic WebSocket envelope used for inbound and outbound events."""

    version: str = "v1"
    event: str
    room_id: UUID
    message_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None
    payload: dict = Field(default_factory=dict)


class WSErrorPayload(BaseModel):
    """Structured error payload for protocol-level command failures."""

    code: str
    message: str
    details: dict = Field(default_factory=dict)
