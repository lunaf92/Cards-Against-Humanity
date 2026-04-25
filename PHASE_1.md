# Phase 1: Backend Foundation — COMPLETE

Backend foundation is ready for independent testing. All requirements met for Phase 1.

## Delivered

### 1. Project Scaffold ✓
- FastAPI application with async support
- Python 3.13 + Poetry dependency management
- Folder structure:
  - `app/core/` — configuration, database, security, dependencies
  - `app/models/` — SQLAlchemy ORM models
  - `app/schemas/` — Pydantic request/response validation
  - `app/services/` — business logic
  - `app/routers/` — API endpoints
  - `alembic/` — database migration management
  - `scripts/` — seeding and utilities
  - `tests/` — test suite

### 2. Configuration ✓
- `app/core/config.py` — Pydantic Settings for all environment variables
- `.envs/.env.dev` — development environment file
- `.envs/.env.test` — test environment file
- Supports multiple deployment targets (dev/test/production)

### 3. Database ✓
- Async PostgreSQL engine via SQLAlchemy
- Alembic for migrations
- Connection pooling and health checks
- Database session dependency injection

### 4. ORM Models ✓
All 8 models matching requirements #6:
- `User` — player accounts with auth_provider field for OAuth
- `Card` — black/white cards with ownership tracking
- `Room` — private/random rooms with all configuration fields
- `RoomPlayer` — tracks players in rooms with score and connectivity
- `GameRound` — tracks individual game rounds
- `Submission` — tracks card submissions per round
- `TokenRevocation` — server-side logout via JTI revocation

### 5. Auth Endpoints ✓
- `POST /auth/register` — register with username/email/password (201)
- `POST /auth/login` — login via username or email (200)
- `POST /auth/refresh` — refresh access token (200)
- `POST /auth/logout` — revoke tokens server-side (204)

All endpoints return Swagger/OpenAPI documented responses.

### 6. Auth Middleware ✓
- `app/core/dependencies.py` — `get_current_user()` dependency
- Validates Bearer tokens
- Checks server-side revocation status
- Returns authenticated User or 401

### 7. Default Deck Seeder ✓
- `scripts/seed_cards.py` — loads placeholder cards into database
- 8 black cards + 15 white cards placeholder set
- Idempotent: can run multiple times safely
- Ready to swap with full deck JSON

### 8. Health Check Endpoint ✓
- `GET /health` — confirms database and Redis connectivity
- Returns service status for liveness probes

### 9. Container Baseline ✓
- `Dockerfile` — Python 3.13 slim image with Poetry
- `docker-compose.yml` — backend, postgres, redis services
- Health checks for all services
- Volume mounts for hot-reload during development
- Service dependencies (backend waits for postgres + redis)

### 10. Containerized Dev Commands ✓
All commands in `README.md`:
- `docker compose up --build` — start all services
- `docker compose run --rm backend pytest` — run tests
- `docker compose run --rm backend ruff check` — lint
- `docker compose run --rm backend black` — format
- `docker compose run --rm backend python scripts/seed_cards.py` — seed
- `docker compose logs -f backend` — stream logs
- `docker compose down` — cleanup

## Testing

Phase 1 verification suite includes:
- `tests/conftest.py` — test fixtures with in-memory SQLite
- `tests/test_auth.py` — auth endpoints and flows
  - User registration (201)
  - Duplicate username prevention (409)
  - User login (200)
  - Invalid credentials (401)
  - Token refresh (200)
  - Health check (200)
  - Root endpoint (200)

Run with: `docker compose run --rm backend pytest tests/ -v`

## Documentation

- `README.md` — project overview and dev workflow
- `AGENT.md` — coding standards (Docker-first, test-early, one-line comments)
- Swagger/OpenAPI UI at `http://localhost:8000/docs`

## Verification Checklist

Before proceeding to Phase 2, verify:

```bash
# 1. Start services
docker compose up --build

# 2. Wait for health
sleep 5

# 3. Seed database
docker compose run --rm backend python scripts/seed_cards.py

# 4. Run tests (should pass)
docker compose run --rm backend pytest tests/ -v

# 5. Register user
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"pass123"}'

# 6. Login (save token)
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username_or_email":"testuser","password":"pass123"}' | jq -r '.access_token')

# 7. Verify health
curl http://localhost:8000/health

# 8. Check Swagger docs
open http://localhost:8000/docs
```

If all steps succeed, Phase 1 is verified complete ✓

## What's NOT in Phase 1

These belong to Phase 2+:
- REST endpoints for cards/rooms (Phase 2)
- WebSocket support (Phase 3)
- Frontend/mobile app (Phase 4+)
- Matchmaking queue logic (Phase 3)
- Game state machine (Phase 3)

## Notes

- JWT tokens use 24-hour TTL (access) + 30-day TTL (refresh)
- Token revocation is server-side via JTI tracking
- Room passwords are hashed with bcrypt (not yet hashed in Dockerfile, add bcrypt to auth endpoints before Phase 2)
- Placeholder card deck is small; replace with full CAH deck before MVP
- Alembic migrations are configured but no initial migration created yet (can auto-generate in Phase 2)
