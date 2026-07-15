"""User model."""
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from datetime import datetime, UTC
import uuid

from app.models.base import Base


class User(Base):
    """User model matching FR-AUTH requirements."""
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Length must match migration 001 (users.username is String(50) in the DB).
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    auth_provider = Column(String(50), nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )

    # Relationships
    cards = relationship("Card", back_populates="owner")
    rooms = relationship("Room", back_populates="host")
