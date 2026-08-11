"""Card model."""
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from datetime import datetime, UTC
import uuid

from app.models.base import Base


class Card(Base):
    """Card model for black/white cards matching FR-CARD requirements."""
    __tablename__ = "cards"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(Enum("black", "white", name="card_type"), nullable=False)
    text = Column(String(500), nullable=False)
    # nullable=False matches migration 001's server_default='1' — the model was
    # missing this constraint despite the DB always having enforced it.
    pick = Column(Integer, default=1, nullable=False)
    owner_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)
    language = Column(String(10), default="en", nullable=False)  # Future: multilingual support (en, es, it, etc.)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )

    # Relationships
    owner = relationship("User", back_populates="cards")
