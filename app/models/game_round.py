"""GameRound model for tracking game rounds."""
from sqlalchemy import Column, Integer, Enum, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from datetime import datetime
import uuid

from app.models.base import Base


class GameRound(Base):
    """Track a single game round."""
    __tablename__ = "game_rounds"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(PG_UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    czar_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    black_card_id = Column(PG_UUID(as_uuid=True), ForeignKey("cards.id"), nullable=False)
    status = Column(
        Enum("waiting", "judging", "complete", name="round_status"),
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
