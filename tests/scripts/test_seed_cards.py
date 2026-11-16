"""Tests for the card pack seeder."""
from sqlalchemy import func, select

from app.models import Card, Deck
from scripts.seed_cards import (
    EXCLUDED_BY_DEFAULT,
    available_packs,
    insert_cards,
    load_cards,
    pick_for,
    resolve_packs,
)


def test_pick_counts_blanks():
    assert pick_for("Why can't I sleep at night?") == 1
    assert pick_for("TSA guidelines now prohibit ___ on airplanes.") == 1
    assert pick_for("When I was tripping on acid, ___ turned into ___.") == 2
    assert pick_for("___ + ___ = ___.") == 3


def test_default_packs_skip_family_edition():
    slugs = resolve_packs(None)
    assert "base-game" in slugs
    assert not EXCLUDED_BY_DEFAULT & set(slugs)
    assert set(resolve_packs("all")) == set(available_packs())


def test_default_selection_size():
    cards = load_cards(resolve_packs(None))
    black = [c for c in cards if c.type == "black"]
    white = [c for c in cards if c.type == "white"]
    assert len(black) >= 240 and len(white) >= 1000
    assert {c.pick for c in black} == {1, 2, 3}


async def test_seeding_twice_adds_nothing(test_db):
    cards = load_cards(["base-game"])
    async with test_db() as session:
        first = await insert_cards(session, cards)
    async with test_db() as session:
        second = await insert_cards(session, cards)
        total = (await session.execute(select(func.count()).select_from(Card))).scalar_one()
    assert first == (80, 502, 0)
    assert second == (0, 0, 0)
    assert total == 582


async def test_seeding_creates_one_public_deck_per_pack(test_db):
    cards = load_cards(["base-game", "90s-nostalgia-pack"])
    async with test_db() as session:
        await insert_cards(session, cards)
        decks = {d.slug: d for d in (await session.execute(select(Deck))).scalars()}
        per_deck = dict(
            (await session.execute(select(Card.deck_id, func.count()).group_by(Card.deck_id))).all()
        )
    assert set(decks) == {"base-game", "90s-nostalgia-pack"}
    assert decks["base-game"].name == "Base Game"
    assert all(d.is_public and d.owner_id is None for d in decks.values())
    assert per_deck[decks["base-game"].id] == 582
    assert None not in per_deck


async def test_reseed_tags_cards_seeded_before_decks(test_db):
    async with test_db() as session:
        session.add(Card(type="white", text="A windmill full of corpses", pick=1, language="en", is_default=True))
        session.add(Card(type="white", text="Something no pack has.", pick=1, language="en", is_default=True))
        await session.commit()
    async with test_db() as session:
        black, white, tagged = await insert_cards(session, load_cards(["base-game"]))
        deck = (await session.execute(select(Deck).where(Deck.slug == "base-game"))).scalar_one()
        old = (await session.execute(select(Card).where(Card.text == "A windmill full of corpses"))).scalar_one()
        orphan = (await session.execute(select(Card).where(Card.text == "Something no pack has."))).scalar_one()
    assert tagged == 1 and white == 501
    assert old.deck_id == deck.id
    assert orphan.deck_id is None
