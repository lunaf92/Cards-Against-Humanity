"""Submission model for tracking card submissions."""
from sqlalchemy import Column, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY
from datetime import datetime
import uuid

from app.models.base import Base


class Submission(Base):
    """Track a player's submitted cards for a round."""
    __tablename__ = "submissions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    round_id = Column(PG_UUID(as_uuid=True), ForeignKey("game_rounds.id"), nullable=False)
    player_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    white_card_ids = Column(ARRAY(PG_UUID(as_uuid=True)), nullable=False)
    is_winner = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
