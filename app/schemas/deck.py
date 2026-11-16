"""Deck schemas."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class DeckSummary(BaseModel):
    """A deck the caller can pick for a room."""

    id: UUID
    name: str
    is_builtin: bool
    is_public: bool
    is_owner: bool
    # Part of the selection a room gets when the host picks nothing.
    is_default: bool
    black_count: int
    white_count: int


class DeckCard(BaseModel):
    id: UUID
    type: Literal["black", "white"]
    text: str
    pick: int


class DeckMemberOut(BaseModel):
    user_id: UUID
    username: str


class DeckDetail(BaseModel):
    """A deck with its cards, for the deck screen."""

    id: UUID
    name: str
    is_builtin: bool
    is_public: bool
    is_owner: bool
    can_edit: bool
    owner_name: str | None
    # Only shown to people who can edit; null while the share link is off.
    share_code: str | None
    copied_from_name: str | None
    black_count: int
    white_count: int
    members: list[DeckMemberOut]
    cards: list[DeckCard]


class DeckCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class DeckUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_public: bool | None = None


class DeckCardCreate(BaseModel):
    type: Literal["black", "white"]
    text: str = Field(min_length=1, max_length=500)


class DeckCardUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class DeckShare(BaseModel):
    share_code: str
