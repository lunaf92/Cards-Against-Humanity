"""Deck endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User
from app.schemas.deck import DeckSummary
from app.services.decks import DeckService

router = APIRouter(prefix="/decks", tags=["decks"])


@router.get("", response_model=list[DeckSummary])
async def list_usable_decks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Decks the caller can put in a room: built-in, their own, and ones they co-edit."""
    return await DeckService.usable_decks(db, current_user.id)
