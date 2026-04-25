"""Seed database with placeholder cards."""
import asyncio
import json
from uuid import uuid4
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings
from app.models import Base, Card


# Placeholder card deck for development
PLACEHOLDER_CARDS = {
    "black_cards": [
        {"text": "What's the worst thing about kindergarten?", "pick": 1},
        {"text": "What is Batman's secret identity?", "pick": 1},
        {"text": "I drink to forget ___ and ___.", "pick": 2},
        {"text": "What did I bring back from Jonestown?", "pick": 1},
        {"text": "What's a girl's best friend?", "pick": 1},
        {"text": "___ is a slippery slope that leads to ___.", "pick": 2},
        {"text": "What's that smell?", "pick": 1},
        {"text": "What will I definitely regret in the morning?", "pick": 1},
    ],
    "white_cards": [
        {"text": "Cats"},
        {"text": "Farting and walking away"},
        {"text": "My collection of high-tech sex toys"},
        {"text": "The blood of Christ"},
        {"text": "A time-traveling dinosaur"},
        {"text": "Glenn Beck caught mid-masturbation"},
        {"text": "Licking things to determine if they're good"},
        {"text": "A salty surprise"},
        {"text": "Sniffing glue"},
        {"text": "Eating the last known bison"},
        {"text": "Getting my tongue stuck to a lamppost"},
        {"text": "A homoerotic volleyball montage"},
        {"text": "Vehicular manslaughter"},
        {"text": "Genital piercings"},
        {"text": "A lifetime of sadness"},
    ],
}


async def seed_cards():
    """Seed database with placeholder cards."""
    # Create async engine
    engine = create_async_engine(settings.DATABASE_URL, echo=True)

    # Create async session factory
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Add placeholder cards
    async with async_session() as session:
        for black_card_text in PLACEHOLDER_CARDS["black_cards"]:
            card = Card(
                type="black",
                text=black_card_text["text"],
                pick=black_card_text.get("pick", 1),
                is_default=True,
                owner_id=None,
            )
            session.add(card)

        for white_card_text in PLACEHOLDER_CARDS["white_cards"]:
            card = Card(
                type="white",
                text=white_card_text["text"],
                is_default=True,
                owner_id=None,
            )
            session.add(card)

        await session.commit()
        print(
            f"✓ Seeded {len(PLACEHOLDER_CARDS['black_cards'])} black cards"
        )
        print(
            f"✓ Seeded {len(PLACEHOLDER_CARDS['white_cards'])} white cards"
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_cards())
