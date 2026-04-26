"""Test configuration and fixtures."""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.core.database import get_db
from app.models import Card, GameRound, Room, RoomPlayer, Submission, TokenRevocation, User


@pytest_asyncio.fixture
async def test_db():
    """Create in-memory SQLite DB for endpoint and service tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Keep the test schema aligned with the gameplay flow exercised by websocket tests.
    async with engine.begin() as conn:
        await conn.run_sync(
            User.metadata.create_all,
            tables=[
                User.__table__,
                TokenRevocation.__table__,
                Card.__table__,
                Room.__table__,
                RoomPlayer.__table__,
                GameRound.__table__,
                Submission.__table__,
            ],
        )

    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    yield async_session

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
def client(test_db):
    """Create test client."""
    return TestClient(app)
