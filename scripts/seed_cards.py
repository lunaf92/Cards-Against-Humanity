"""Load the bundled card packs (scripts/card_packs) into the cards table.

Each pack becomes a built-in deck (matched by its file name). Safe to rerun:
a card whose (type, text, language) already exists is not inserted again, but
it is tagged with its pack's deck if it has none yet, so running this once
after migration 006 fills in the deck for cards seeded before decks existed.

    python -m scripts.seed_cards                      # default packs
    python -m scripts.seed_cards --list               # show available packs
    python -m scripts.seed_cards --packs base-game,the-first-expansion
    python -m scripts.seed_cards --packs all          # every English pack

"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Card, Deck

PACKS_DIR = Path(__file__).parent / "card_packs"
DEFAULT_LANGUAGE = "en"
# Family Edition is the kid-friendly set; mixed into the adult packs it dilutes them.
EXCLUDED_BY_DEFAULT = {"family-edition"}
BLANK = re.compile(r"_{2,}")
MAX_PICK = 3


@dataclass(frozen=True)
class SeedCard:
    """One card ready to insert."""

    type: str
    text: str
    pick: int
    language: str
    pack: str


def pick_for(text: str) -> int:
    """Number of white cards a prompt takes: one per ___ blank, 1 for plain questions."""
    return max(1, min(MAX_PICK, len(BLANK.findall(text))))


def available_packs(language: str = DEFAULT_LANGUAGE) -> dict[str, Path]:
    """Pack slug -> JSON file for one language."""
    folder = PACKS_DIR / language
    return {path.stem: path for path in sorted(folder.glob("*.json"))}


def resolve_packs(spec: str | None, language: str = DEFAULT_LANGUAGE) -> list[str]:
    """Turn the --packs argument into slugs; None means the default selection."""
    packs = available_packs(language)
    if spec is None:
        return [slug for slug in packs if slug not in EXCLUDED_BY_DEFAULT]
    if spec.strip() == "all":
        return list(packs)
    wanted = [slug.strip() for slug in spec.split(",") if slug.strip()]
    unknown = [slug for slug in wanted if slug not in packs]
    if unknown:
        raise SystemExit(f"Unknown pack(s): {', '.join(unknown)}. Use --list to see them.")
    return wanted


def pack_name(slug: str, language: str = DEFAULT_LANGUAGE) -> str:
    """Display name stored in the pack file."""
    data = json.loads(available_packs(language)[slug].read_text(encoding="utf-8"))
    return str(data.get("name") or slug.replace("-", " ").title())


def load_cards(slugs: list[str], language: str = DEFAULT_LANGUAGE) -> list[SeedCard]:
    """Read the chosen packs, de-duplicated across packs (first pack wins), in a stable order."""
    packs = available_packs(language)
    seen: set[tuple[str, str]] = set()
    cards: list[SeedCard] = []
    for slug in slugs:
        data = json.loads(packs[slug].read_text(encoding="utf-8"))
        for kind, key in (("black", "black_cards"), ("white", "white_cards")):
            for raw in data.get(key, []):
                text = " ".join(str(raw).split())
                if not text or (kind, text) in seen:
                    continue
                seen.add((kind, text))
                pick = pick_for(text) if kind == "black" else 1
                cards.append(SeedCard(kind, text, pick, language, slug))
    return cards


async def ensure_decks(session: AsyncSession, slugs: list[str], language: str = DEFAULT_LANGUAGE) -> dict[str, Deck]:
    """Create (or rename) the built-in deck for each pack. Returns slug -> deck."""
    result = await session.execute(select(Deck).where(Deck.slug.in_(slugs)))
    decks = {deck.slug: deck for deck in result.scalars()}
    for slug in slugs:
        name = pack_name(slug, language)
        deck = decks.get(slug)
        if deck is None:
            deck = Deck(slug=slug, name=name, language=language, owner_id=None, is_public=True)
            session.add(deck)
            decks[slug] = deck
        else:
            deck.name = name
    await session.flush()
    return decks


async def insert_cards(session: AsyncSession, cards: list[SeedCard]) -> tuple[int, int, int]:
    """Insert missing cards and tag untagged ones with their deck.

    Returns (black_added, white_added, tagged).
    """
    slugs = list(dict.fromkeys(card.pack for card in cards))
    language = cards[0].language if cards else DEFAULT_LANGUAGE
    decks = await ensure_decks(session, slugs, language)
    result = await session.execute(
        select(Card.id, Card.type, Card.text, Card.language, Card.deck_id).where(Card.is_default.is_(True))
    )
    existing = {(row.type, row.text, row.language): row for row in result}
    added = {"black": 0, "white": 0}
    to_tag: dict[object, list[object]] = {}
    for card in cards:
        deck = decks[card.pack]
        row = existing.get((card.type, card.text, card.language))
        if row is not None:
            if row.deck_id is None:
                to_tag.setdefault(deck.id, []).append(row.id)
            continue
        session.add(
            Card(
                type=card.type,
                text=card.text,
                pick=card.pick,
                language=card.language,
                is_default=True,
                owner_id=None,
                deck_id=deck.id,
            )
        )
        added[card.type] += 1
    for deck_id, card_ids in to_tag.items():
        await session.execute(update(Card).where(Card.id.in_(card_ids)).values(deck_id=deck_id))
    await session.commit()
    return added["black"], added["white"], sum(len(ids) for ids in to_tag.values())


async def count_untagged(session: AsyncSession) -> int:
    """Built-in cards that belong to no deck (e.g. from a pack no longer seeded)."""
    result = await session.execute(
        select(func.count()).select_from(Card).where(Card.is_default.is_(True), Card.deck_id.is_(None))
    )
    return result.scalar_one()


async def seed_cards(pack_spec: str | None = None, language: str = DEFAULT_LANGUAGE) -> None:
    """Seed the configured database (tables come from Alembic migrations)."""
    from app.core.config import settings

    slugs = resolve_packs(pack_spec, language)
    cards = load_cards(slugs, language)
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            black, white, tagged = await insert_cards(session, cards)
            untagged = await count_untagged(session)
    finally:
        await engine.dispose()
    print(f"Packs: {', '.join(slugs)}")
    print(f"Added {black} black and {white} white cards ({len(cards) - black - white} already present)")
    if tagged:
        print(f"Tagged {tagged} existing cards with their deck")
    if untagged:
        print(f"{untagged} built-in cards match no seeded pack and have no deck")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--packs", help="comma-separated pack slugs, or 'all' (default: all but family-edition)")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="pack language folder (default: en)")
    parser.add_argument("--list", action="store_true", help="list available packs and exit")
    args = parser.parse_args()

    if args.list:
        for slug, path in available_packs(args.language).items():
            data = json.loads(path.read_text(encoding="utf-8"))
            mark = " (not in default)" if slug in EXCLUDED_BY_DEFAULT else ""
            print(
                f"{slug:28} {len(data.get('black_cards', [])):4} black "
                f"{len(data.get('white_cards', [])):5} white{mark}"
            )
        return
    asyncio.run(seed_cards(args.packs, args.language))


if __name__ == "__main__":
    main()
