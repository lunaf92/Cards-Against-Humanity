"""Main FastAPI application."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import auth, cards, decks, health, rooms, users, ws_rooms
from app.services.ws_connection_manager import connection_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start and stop shared websocket pub/sub bridge with app lifecycle."""
    await connection_manager.start_pubsub_bridge(settings.REDIS_URL)
    # Round/judging timers are in-process tasks; re-arm them for games that were
    # mid-round when the previous process stopped. Never block startup on this.
    try:
        restored = await ws_rooms.restore_game_timers()
        if restored:
            logger.info("re-armed %s game timer(s) after restart", restored)
    except Exception:
        logger.exception("failed to restore game timers on startup")
    try:
        yield
    finally:
        await connection_manager.stop_pubsub_bridge()

# Create FastAPI app with OpenAPI documentation
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(health.router)
app.include_router(cards.router)
app.include_router(decks.router)
app.include_router(users.router)
app.include_router(rooms.router)
app.include_router(ws_rooms.router)

# Note: Database schema is managed by Alembic migrations.
# Always run 'alembic upgrade head' before starting the app to ensure schema is current.


@app.get("/", tags=["root"], summary="API root")
async def root():
    """Welcome endpoint."""
    return {"message": "Cards Against Humanity Clone API"}
