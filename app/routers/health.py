"""Health check endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, engine
import redis.asyncio as redis
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Health check",
    responses={
        200: {"description": "Service is healthy"},
        503: {"description": "Service is unavailable"},
    },
)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Check database, Redis, and API connectivity."""
    try:
        # Test database connection
        await db.execute("SELECT 1")

        # Test Redis connection
        redis_client = redis.from_url(settings.REDIS_URL)
        await redis_client.ping()
        await redis_client.close()

        return {
            "status": "healthy",
            "database": "connected",
            "redis": "connected",
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }
