"""Test configuration and fixtures."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db
from app.models import Base


@pytest_asyncio.fixture
async def test_db():
    """Create in-memory SQLite database for tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    yield async_session

    await engine.dispose()


@pytest.fixture
def client(test_db):
    """Create test client."""
    return TestClient(app)
