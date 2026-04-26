"""Main FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import auth, cards, health, rooms, users, ws_rooms
from app.services.ws_connection_manager import connection_manager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start and stop shared websocket pub/sub bridge with app lifecycle."""
    await connection_manager.start_pubsub_bridge(settings.REDIS_URL)
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
app.include_router(users.router)
app.include_router(rooms.router)
app.include_router(ws_rooms.router)

# Note: Database schema is managed by Alembic migrations.
# Always run 'alembic upgrade head' before starting the app to ensure schema is current.


@app.get("/", tags=["root"], summary="API root")
async def root():
    """Welcome endpoint."""
    return {"message": "Cards Against Humanity Clone API"}
