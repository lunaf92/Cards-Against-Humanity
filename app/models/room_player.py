"""RoomPlayer model for tracking players in rooms."""
from sqlalchemy import Column, Integer, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from datetime import datetime
import uuid

from app.models.base import Base


class RoomPlayer(Base):
    """Track players in a room and their state."""
    __tablename__ = "room_players"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(PG_UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=False)
    player_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    join_order = Column(Integer, nullable=False)
    score = Column(Integer, default=0, nullable=False)
    is_connected = Column(Boolean, default=True, nullable=False)
