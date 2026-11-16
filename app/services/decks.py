"""Deck access and the card pool a room deals from."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models import Card, Deck, DeckMember, Room, RoomDeck

# Built-in packs left out of the default selection (kid-friendly set).
EXCLUDED_BY_DEFAULT = {"family-edition"}


def _can_use(user_id: UUID) -> ColumnElement[bool]:
    """Decks a user may put in a room: built-in, owned, or joined as co-editor."""
    member = select(DeckMember.deck_id).where(DeckMember.user_id == user_id)
    return or_(Deck.owner_id.is_(None), Deck.owner_id == user_id, Deck.id.in_(member))


async def _card_counts(db: AsyncSession, deck_ids: list[UUID]) -> dict[UUID, dict[str, int]]:
    counts: dict[UUID, dict[str, int]] = {deck_id: {"black": 0, "white": 0} for deck_id in deck_ids}
    if not deck_ids:
        return counts
    result = await db.execute(
        select(Card.deck_id, Card.type, func.count())
        .where(Card.deck_id.in_(deck_ids))
        .group_by(Card.deck_id, Card.type)
    )
    for deck_id, card_type, count in result.all():
        counts[deck_id][card_type] = count
    return counts


def _summary(deck: Deck, counts: dict[str, int]) -> dict:
    return {
        "id": deck.id,
        "name": deck.name,
        "is_builtin": deck.owner_id is None,
        "is_public": deck.is_public,
        "black_count": counts["black"],
        "white_count": counts["white"],
    }


class DeckService:
    """Which decks exist for a user, and which cards a room deals."""

    @staticmethod
    async def default_deck_ids(db: AsyncSession) -> list[UUID]:
        """Built-in decks a room uses when the host picked none."""
        result = await db.execute(
            select(Deck.id)
            .where(Deck.owner_id.is_(None), or_(Deck.slug.is_(None), Deck.slug.not_in(EXCLUDED_BY_DEFAULT)))
            .order_by(Deck.name)
        )
        return [deck_id for (deck_id,) in result.all()]

    @staticmethod
    async def room_deck_ids(db: AsyncSession, room_id: UUID) -> list[UUID]:
        """Decks the room deals from: the host's choice, else the defaults."""
        result = await db.execute(select(RoomDeck.deck_id).where(RoomDeck.room_id == room_id))
        chosen = [deck_id for (deck_id,) in result.all()]
        return chosen or await DeckService.default_deck_ids(db)

    @staticmethod
    async def card_filter(db: AsyncSession, room_id: UUID) -> ColumnElement[bool]:
        """WHERE clause for the room's card pool.

        A database seeded before decks existed has no decks yet; it keeps
        dealing every built-in card until the seeder is rerun.
        """
        deck_ids = await DeckService.room_deck_ids(db, room_id)
        if not deck_ids:
            return Card.is_default.is_(True)
        return Card.deck_id.in_(deck_ids)

    @staticmethod
    async def room_decks(db: AsyncSession, room_id: UUID) -> list[dict]:
        """Summaries of the decks a room deals from, for room payloads."""
        deck_ids = await DeckService.room_deck_ids(db, room_id)
        if not deck_ids:
            return []
        decks = (await db.execute(select(Deck).where(Deck.id.in_(deck_ids)).order_by(Deck.name))).scalars().all()
        counts = await _card_counts(db, [deck.id for deck in decks])
        return [_summary(deck, counts[deck.id]) for deck in decks]

    @staticmethod
    async def usable_decks(db: AsyncSession, user_id: UUID) -> list[dict]:
        """Every deck the user can pick for a room, built-in first."""
        decks = (
            await db.execute(select(Deck).where(_can_use(user_id)).order_by(Deck.owner_id.is_not(None), Deck.name))
        ).scalars().all()
        defaults = set(await DeckService.default_deck_ids(db))
        counts = await _card_counts(db, [deck.id for deck in decks])
        return [
            {**_summary(deck, counts[deck.id]), "is_owner": deck.owner_id == user_id, "is_default": deck.id in defaults}
            for deck in decks
        ]

    @staticmethod
    async def set_room_decks(db: AsyncSession, room: Room, deck_ids: list[UUID], user_id: UUID) -> None:
        """Replace the room's deck choice after checking the user may use each deck."""
        wanted = list(dict.fromkeys(deck_ids))
        if not wanted:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Pick at least one deck")
        result = await db.execute(select(Deck.id).where(Deck.id.in_(wanted), _can_use(user_id)))
        allowed = {deck_id for (deck_id,) in result.all()}
        if len(allowed) != len(wanted):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
        await db.execute(delete(RoomDeck).where(RoomDeck.room_id == room.id))
        db.add_all(RoomDeck(room_id=room.id, deck_id=deck_id) for deck_id in wanted)
        await db.flush()
