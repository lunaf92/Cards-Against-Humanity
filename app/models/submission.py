"""Submission model for tracking card submissions."""
from datetime import UTC, datetime
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.types import TypeDecorator

from app.models.base import Base


class UUIDListType(TypeDecorator):
    """Store UUID lists as PostgreSQL ARRAY or generic JSON depending on dialect."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(PG_UUID(as_uuid=True)))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return [item if isinstance(item, uuid.UUID) else uuid.UUID(str(item)) for item in value]
        return [str(item) for item in value]

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return [item if isinstance(item, uuid.UUID) else uuid.UUID(str(item)) for item in value]


class Submission(Base):
    """Track a player's submitted cards for a round."""
    __tablename__ = "submissions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    round_id = Column(PG_UUID(as_uuid=True), ForeignKey("game_rounds.id"), nullable=False)
    player_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    white_card_ids = Column(UUIDListType(), nullable=False)
    is_winner = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )
