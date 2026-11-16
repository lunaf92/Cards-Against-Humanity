"""Deck models: built-in packs and user-made decks, plus their co-editors."""
from datetime import datetime, UTC
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Deck(Base):
    """A named set of cards.

    Built-in packs have no owner and a slug matching their file in
    scripts/card_packs. User decks have an owner; everyone in deck_members can
    edit them too. Public decks can be copied by players at the end of a game.
    """

    __tablename__ = "decks"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(64), unique=True, nullable=True)
    name = Column(String(100), nullable=False)
    language = Column(String(10), default="en", nullable=False)
    owner_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    is_public = Column(Boolean, default=False, nullable=False)
    # Opening the share link with this code makes the visitor a co-editor.
    share_code = Column(String(12), unique=True, nullable=True)
    copied_from_id = Column(PG_UUID(as_uuid=True), ForeignKey("decks.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    cards = relationship("Card", back_populates="deck")
    members = relationship("DeckMember", back_populates="deck", cascade="all, delete-orphan")

    @property
    def is_builtin(self) -> bool:
        return self.owner_id is None


class DeckMember(Base):
    """A co-editor of someone else's deck (joined through the share link)."""

    __tablename__ = "deck_members"

    deck_id = Column(PG_UUID(as_uuid=True), ForeignKey("decks.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    created_at = Column(DateTime, default=_now, nullable=False)

    deck = relationship("Deck", back_populates="members")


class RoomDeck(Base):
    """A deck chosen for a room. A room with no rows deals from the default packs."""

    __tablename__ = "room_decks"

    room_id = Column(PG_UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    deck_id = Column(PG_UUID(as_uuid=True), ForeignKey("decks.id", ondelete="CASCADE"), primary_key=True)
