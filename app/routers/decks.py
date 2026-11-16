"""Deck endpoints: picking decks for rooms, and building, sharing and copying your own."""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User
from app.schemas.deck import (
    DeckCard,
    DeckCardCreate,
    DeckCardUpdate,
    DeckCreate,
    DeckDetail,
    DeckShare,
    DeckSummary,
    DeckUpdate,
)
from app.services.decks import DeckEditor, DeckService

router = APIRouter(prefix="/decks", tags=["decks"])


async def _detail(db: AsyncSession, deck_id: UUID, user: User) -> DeckDetail:
    deck, role = await DeckEditor.get(db, deck_id, user.id)
    return DeckDetail(**await DeckEditor.detail(db, deck, role, user.id))


def _card(card) -> DeckCard:
    return DeckCard(id=card.id, type=card.type, text=card.text, pick=card.pick)


@router.get("", response_model=list[DeckSummary])
async def list_usable_decks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Decks the caller can put in a room: built-in, their own, and ones they co-edit."""
    return await DeckService.usable_decks(db, current_user.id)


@router.post("", response_model=DeckDetail, status_code=status.HTTP_201_CREATED)
async def create_deck(
    payload: DeckCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a new private deck."""
    deck = await DeckEditor.create(db, current_user.id, payload.name)
    await db.commit()
    return await _detail(db, deck.id, current_user)


@router.post("/join/{code}", response_model=DeckDetail)
async def join_deck(code: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Open a share link: the caller becomes a co-editor of the deck."""
    deck = await DeckEditor.join(db, code, current_user.id)
    await db.commit()
    return await _detail(db, deck.id, current_user)


@router.get("/{deck_id}", response_model=DeckDetail)
async def get_deck(deck_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A deck with its cards. Built-in and public decks are visible to everyone."""
    return await _detail(db, deck_id, current_user)


@router.patch("/{deck_id}", response_model=DeckDetail)
async def update_deck(
    deck_id: UUID,
    payload: DeckUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rename (any editor) or make public/private (owner)."""
    deck = await DeckEditor.get_editable(db, deck_id, current_user.id)
    role = "owner" if deck.owner_id == current_user.id else "editor"
    await DeckEditor.update(db, deck, role, payload.name, payload.is_public)
    await db.commit()
    return await _detail(db, deck_id, current_user)


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deck(deck_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Delete a deck and its cards (owner only)."""
    deck = await DeckEditor.get_editable(db, deck_id, current_user.id, owner_only=True)
    await DeckEditor.delete(db, deck)
    await db.commit()


@router.post("/{deck_id}/cards", response_model=DeckCard, status_code=status.HTTP_201_CREATED)
async def add_card(
    deck_id: UUID,
    payload: DeckCardCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a card. Black cards take one answer per ___ blank."""
    deck = await DeckEditor.get_editable(db, deck_id, current_user.id)
    card = await DeckEditor.add_card(db, deck, current_user.id, payload.type, payload.text)
    await db.commit()
    return _card(card)


@router.patch("/{deck_id}/cards/{card_id}", response_model=DeckCard)
async def edit_card(
    deck_id: UUID,
    card_id: UUID,
    payload: DeckCardUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deck = await DeckEditor.get_editable(db, deck_id, current_user.id)
    card = await DeckEditor.edit_card(db, deck, card_id, payload.text)
    await db.commit()
    return _card(card)


@router.delete("/{deck_id}/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    deck_id: UUID,
    card_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deck = await DeckEditor.get_editable(db, deck_id, current_user.id)
    await DeckEditor.delete_card(db, deck, card_id)
    await db.commit()


@router.post("/{deck_id}/share", response_model=DeckShare)
async def share_deck(deck_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Turn on the share link. Anyone who opens it can edit the deck."""
    deck = await DeckEditor.get_editable(db, deck_id, current_user.id)
    code = await DeckEditor.share(db, deck)
    await db.commit()
    return DeckShare(share_code=code)


@router.delete("/{deck_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def unshare_deck(deck_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Turn the share link off (owner only). People who joined keep access until removed."""
    deck = await DeckEditor.get_editable(db, deck_id, current_user.id, owner_only=True)
    await DeckEditor.unshare(db, deck)
    await db.commit()


@router.delete("/{deck_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    deck_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The owner removes a co-editor, or a co-editor leaves."""
    deck = await DeckEditor.get_editable(db, deck_id, current_user.id, owner_only=user_id != current_user.id)
    await DeckEditor.remove_member(db, deck, user_id)
    await db.commit()


@router.post("/{deck_id}/copy", response_model=DeckDetail, status_code=status.HTTP_201_CREATED)
async def copy_deck(deck_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Copy a built-in, public, or editable deck into a new private deck of your own."""
    source, _ = await DeckEditor.get(db, deck_id, current_user.id)
    deck = await DeckEditor.copy(db, source, current_user.id)
    await db.commit()
    return await _detail(db, deck.id, current_user)
