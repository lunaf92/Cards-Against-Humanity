"""Tests for the card pack seeder."""
from sqlalchemy import func, select

from app.models import Card
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
    assert first == (80, 502)
    assert second == (0, 0)
    assert total == 582
