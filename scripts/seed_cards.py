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
        {"text": "What's the next Happy Meal toy?", "pick": 1},
        {"text": "Alternative medicine is now embracing the healing power of ___.", "pick": 1},
        {"text": "What never fails to liven up the party?", "pick": 1},
        {"text": "TSA guidelines now require all travelers to remove their shoes and ___.", "pick": 1},
        {"text": "What's the new fad diet?", "pick": 1},
        {"text": "Coming to Broadway this season, ___: The Musical.", "pick": 1},
        {"text": "What did the Girl Scouts show up at my house selling?", "pick": 1},
        {"text": "___ + ___ = ___.", "pick": 3},
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
        {"text": "Racially-biased sentencing"},
        {"text": "An asymmetric boob job"},
        {"text": "A robust smoothie"},
        {"text": "Not giving a shit about the environment"},
        {"text": "Poor life choices"},
        {"text": "A subscription to Men's Fitness"},
        {"text": "A big black man"},
        {"text": "Puberty"},
        {"text": "The inevitable heat death of the universe"},
        {"text": "Repression"},
        {"text": "A middle-aged Wiccan woman with a passion for shoplifting"},
        {"text": "Committing tax fraud"},
        {"text": "A sassy black woman"},
        {"text": "German dungeon porn"},
        {"text": "Passive-aggressive Post-it notes"},
        {"text": "Silence"},
        {"text": "Emotional baggage"},
        {"text": "The Rapture"},
        {"text": "A can of whoop-ass"},
        {"text": "White people"},
        {"text": "Auschwitz"},
        {"text": "Roofies"},
        {"text": "A gassy antelope"},
        {"text": "A mopey zoo lion"},
        {"text": "Christian rock"},
        {"text": "Not knowing what to say when someone shows you their new baby"},
        {"text": "An unstoppable wave of gay marriages"},
        {"text": "Eugenics"},
        {"text": "Free samples"},
        {"text": "Waking up half-naked in a Denny's parking lot"},
        {"text": "The hardworking Mexican"},
        {"text": "Girls who don't know how great they are"},
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
