"""Cards endpoints for default and custom card management."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import Card, Room, RoomPlayer, User
from app.schemas.card import CardCreate, CardResponse, CardUpdate, PaginatedCardsResponse

router = APIRouter(prefix="/cards", tags=["cards"])


async def _assert_user_not_in_active_game(db: AsyncSession, user_id: UUID) -> None:
    """Block card mutations while player is in a room with an active game."""
    result = await db.execute(
        select(RoomPlayer.id)
        .join(Room, RoomPlayer.room_id == Room.id)
        .where(RoomPlayer.player_id == user_id, Room.status == "in_progress")
        .limit(1)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Card changes are blocked during active games",
        )


@router.get("/default", response_model=PaginatedCardsResponse, summary="Get default cards")
async def list_default_cards(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Return a paginated list of default deck cards."""
    total_result = await db.execute(
        select(func.count()).select_from(Card).where(Card.is_default.is_(True))
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(Card)
        .where(Card.is_default.is_(True))
        .order_by(Card.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    cards = result.scalars().all()

    return PaginatedCardsResponse(
        items=[CardResponse.model_validate(card) for card in cards],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/mine", response_model=list[CardResponse], summary="Get my custom cards")
async def list_my_cards(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return cards created by the authenticated player."""
    result = await db.execute(
        select(Card)
        .where(Card.owner_id == current_user.id, Card.is_default.is_(False))
        .order_by(Card.created_at.desc())
    )
    cards = result.scalars().all()
    return [CardResponse.model_validate(card) for card in cards]


@router.post(
    "",
    response_model=CardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create custom card",
)
async def create_card(
    payload: CardCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom black or white card for the authenticated player."""
    card = Card(
        type=payload.type,
        text=payload.text,
        pick=payload.pick,
        owner_id=current_user.id,
        is_default=False,
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return CardResponse.model_validate(card)


@router.patch("/{card_id}", response_model=CardResponse, summary="Update custom card")
async def update_card(
    card_id: UUID,
    payload: CardUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a custom card owned by the authenticated player."""
    await _assert_user_not_in_active_game(db, current_user.id)
    result = await db.execute(
        select(Card).where(Card.id == card_id, Card.owner_id == current_user.id)
    )
    card = result.scalar_one_or_none()
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")

    if payload.text is not None:
        card.text = payload.text
    if payload.pick is not None and card.type == "black":
        card.pick = payload.pick

    await db.commit()
    await db.refresh(card)
    return CardResponse.model_validate(card)


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete custom card")
async def delete_card(
    card_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a custom card owned by the authenticated player."""
    await _assert_user_not_in_active_game(db, current_user.id)
    result = await db.execute(
        select(Card).where(Card.id == card_id, Card.owner_id == current_user.id)
    )
    card = result.scalar_one_or_none()
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")

    await db.delete(card)
    await db.commit()
    return None
