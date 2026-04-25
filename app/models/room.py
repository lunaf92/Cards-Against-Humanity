"""Room model."""
from sqlalchemy import Column, String, DateTime, Integer, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from datetime import datetime
import uuid

from app.models.base import Base


class Room(Base):
    """Room model for private/random matchmaking."""
    __tablename__ = "rooms"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(6), unique=True, nullable=False, index=True)
    host_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    room_kind = Column(Enum("private", "random", name="room_kind"), nullable=False)
    status = Column(
        Enum("lobby", "matchmaking_lobby", "in_progress", "finished", name="room_status"),
        default="lobby",
        nullable=False,
    )
    max_players = Column(Integer, default=10, nullable=False)
    winning_score = Column(Integer, default=8, nullable=False)
    round_timer_seconds = Column(Integer, default=90, nullable=False)
    card_pool_mode = Column(
        Enum(
            "default_only",
            "host_custom_only",
            "host_custom_mixed",
            "all_custom_only",
            "all_custom_mixed",
            name="card_pool_mode",
        ),
        default="default_only",
        nullable=False,
    )
    matchmaking_fill_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    host = relationship("User", back_populates="rooms")
