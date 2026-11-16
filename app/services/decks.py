"""Deck access and the card pool a room deals from."""
from __future__ import annotations

import re
import secrets
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models import Card, Deck, DeckMember, Room, RoomDeck, User

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


SHARE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SHARE_CODE_LENGTH = 8
_BLANK = re.compile(r"_{2,}")
MAX_PICK = 3


def pick_for(text: str) -> int:
    """White cards a prompt takes: one per ___ blank, 1 for plain questions."""
    return max(1, min(MAX_PICK, len(_BLANK.findall(text))))


async def _role(db: AsyncSession, deck: Deck, user_id: UUID) -> str | None:
    """'owner', 'editor', or None for someone with no edit rights."""
    if deck.owner_id == user_id:
        return "owner"
    if deck.owner_id is None:
        return None
    member = await db.get(DeckMember, (deck.id, user_id))
    return "editor" if member is not None else None


class DeckEditor:
    """Creating, editing, sharing and copying user decks."""

    @staticmethod
    async def get(db: AsyncSession, deck_id: UUID, user_id: UUID) -> tuple[Deck, str | None]:
        """A deck the user may look at, with their role. Private decks are hidden from outsiders."""
        deck = await db.get(Deck, deck_id)
        if deck is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
        role = await _role(db, deck, user_id)
        if role is None and not (deck.owner_id is None or deck.is_public):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
        return deck, role

    @staticmethod
    async def get_editable(db: AsyncSession, deck_id: UUID, user_id: UUID, *, owner_only: bool = False) -> Deck:
        deck, role = await DeckEditor.get(db, deck_id, user_id)
        if role is None or (owner_only and role != "owner"):
            detail = "Only the deck's owner can do that" if role else "You can't edit this deck"
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
        return deck

    @staticmethod
    async def detail(db: AsyncSession, deck: Deck, role: str | None, user_id: UUID) -> dict:
        """Everything the deck screen shows."""
        cards = (
            await db.execute(select(Card).where(Card.deck_id == deck.id).order_by(Card.created_at.desc(), Card.id))
        ).scalars().all()
        members = (
            await db.execute(
                select(User.id, User.username)
                .join(DeckMember, DeckMember.user_id == User.id)
                .where(DeckMember.deck_id == deck.id)
                .order_by(DeckMember.created_at)
            )
        ).all()
        owner_name = None
        if deck.owner_id is not None:
            owner = await db.get(User, deck.owner_id)
            owner_name = owner.username if owner else None
        source_name = None
        if deck.copied_from_id is not None:
            source = await db.get(Deck, deck.copied_from_id)
            source_name = source.name if source else None
        black = sum(1 for card in cards if card.type == "black")
        return {
            **_summary(deck, {"black": black, "white": len(cards) - black}),
            "is_owner": role == "owner",
            "can_edit": role is not None,
            "owner_name": owner_name,
            "share_code": deck.share_code if role is not None else None,
            "copied_from_name": source_name,
            "members": [{"user_id": uid, "username": name} for uid, name in members],
            "cards": [{"id": c.id, "type": c.type, "text": c.text, "pick": c.pick} for c in cards],
        }

    @staticmethod
    async def create(db: AsyncSession, user_id: UUID, name: str) -> Deck:
        deck = Deck(name=name.strip(), owner_id=user_id, is_public=False)
        db.add(deck)
        await db.flush()
        return deck

    @staticmethod
    async def update(db: AsyncSession, deck: Deck, role: str, name: str | None, is_public: bool | None) -> None:
        if name is not None:
            deck.name = name.strip()
        if is_public is not None:
            if role != "owner":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the deck's owner can do that")
            deck.is_public = is_public
        await db.flush()

    @staticmethod
    async def add_card(db: AsyncSession, deck: Deck, user_id: UUID, card_type: str, text: str) -> Card:
        text = " ".join(text.split())
        card = Card(
            type=card_type,
            text=text,
            pick=pick_for(text) if card_type == "black" else 1,
            owner_id=user_id,
            is_default=False,
            language=deck.language,
            deck_id=deck.id,
        )
        db.add(card)
        await db.flush()
        return card

    @staticmethod
    async def _card(db: AsyncSession, deck: Deck, card_id: UUID) -> Card:
        card = await db.get(Card, card_id)
        if card is None or card.deck_id != deck.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
        return card

    @staticmethod
    async def edit_card(db: AsyncSession, deck: Deck, card_id: UUID, text: str) -> Card:
        card = await DeckEditor._card(db, deck, card_id)
        card.text = " ".join(text.split())
        if card.type == "black":
            card.pick = pick_for(card.text)
        await db.flush()
        return card

    @staticmethod
    async def _assert_not_in_game(db: AsyncSession, deck: Deck) -> None:
        """Cards can't vanish from under a running game."""
        result = await db.execute(
            select(Room.id)
            .join(RoomDeck, RoomDeck.room_id == Room.id)
            .where(RoomDeck.deck_id == deck.id, Room.status == "in_progress")
            .limit(1)
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This deck is in a game right now. Try again when it ends.",
            )

    @staticmethod
    async def delete_card(db: AsyncSession, deck: Deck, card_id: UUID) -> None:
        await DeckEditor._assert_not_in_game(db, deck)
        await db.delete(await DeckEditor._card(db, deck, card_id))
        await db.flush()

    @staticmethod
    async def share(db: AsyncSession, deck: Deck) -> str:
        """Turn the share link on (keeping an existing code) and return its code."""
        while deck.share_code is None:
            code = "".join(secrets.choice(SHARE_CODE_ALPHABET) for _ in range(SHARE_CODE_LENGTH))
            taken = await db.execute(select(Deck.id).where(Deck.share_code == code))
            if taken.scalar_one_or_none() is None:
                deck.share_code = code
        await db.flush()
        return deck.share_code

    @staticmethod
    async def unshare(db: AsyncSession, deck: Deck) -> None:
        """Turn the share link off. People who already joined stay until removed."""
        deck.share_code = None
        await db.flush()

    @staticmethod
    async def join(db: AsyncSession, code: str, user_id: UUID) -> Deck:
        """Become a co-editor through a share code."""
        result = await db.execute(select(Deck).where(Deck.share_code == code.strip().upper()))
        deck = result.scalar_one_or_none()
        if deck is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That share link doesn't work any more")
        if deck.owner_id != user_id and await db.get(DeckMember, (deck.id, user_id)) is None:
            db.add(DeckMember(deck_id=deck.id, user_id=user_id))
            await db.flush()
        return deck

    @staticmethod
    async def remove_member(db: AsyncSession, deck: Deck, member_id: UUID) -> None:
        member = await db.get(DeckMember, (deck.id, member_id))
        if member is not None:
            await db.delete(member)
            await db.flush()

    @staticmethod
    async def copy(db: AsyncSession, source: Deck, user_id: UUID) -> Deck:
        """A private deck owned by the user with the same cards."""
        deck = Deck(
            name=source.name,
            language=source.language,
            owner_id=user_id,
            is_public=False,
            copied_from_id=source.id,
        )
        db.add(deck)
        await db.flush()
        cards = (await db.execute(select(Card).where(Card.deck_id == source.id))).scalars().all()
        db.add_all(
            Card(
                type=card.type,
                text=card.text,
                pick=card.pick,
                owner_id=user_id,
                is_default=False,
                language=card.language,
                deck_id=deck.id,
            )
            for card in cards
        )
        await db.flush()
        return deck

    @staticmethod
    async def delete(db: AsyncSession, deck: Deck) -> None:
        await DeckEditor._assert_not_in_game(db, deck)
        await db.execute(delete(RoomDeck).where(RoomDeck.deck_id == deck.id))
        await db.execute(delete(Card).where(Card.deck_id == deck.id))
        await db.delete(deck)
        await db.flush()
