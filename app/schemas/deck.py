"""Deck schemas."""
from uuid import UUID

from pydantic import BaseModel


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
