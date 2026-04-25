"""Card schemas for request/response validation."""
from datetime import datetime
from typing import Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CardCreate(BaseModel):
    """Request payload for creating a custom card."""

    type: Literal["black", "white"]
    text: str = Field(min_length=1, max_length=500)
    pick: Optional[int] = Field(default=1, ge=1, le=2)

    @model_validator(mode="after")
    def validate_pick_for_type(self):
        """Only black cards use pick; white cards always default to 1."""
        if self.type == "white":
            self.pick = 1
        return self


class CardUpdate(BaseModel):
    """Request payload for updating a custom card."""

    text: Optional[str] = Field(default=None, min_length=1, max_length=500)
    pick: Optional[int] = Field(default=None, ge=1, le=2)


class CardResponse(BaseModel):
    """Card response payload."""

    id: UUID
    type: str
    text: str
    pick: Optional[int]
    owner_id: Optional[UUID]
    is_default: bool
    language: str = "en"  # Future: multilingual support (en, es, it, etc.)
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedCardsResponse(BaseModel):
    """Paginated list response for cards."""

    items: list[CardResponse]
    total: int
    page: int
    page_size: int
