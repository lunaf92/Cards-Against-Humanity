# Cards Against Humanity Clone

Cross-platform multiplayer card game backend built with FastAPI, PostgreSQL, and Redis.

## Tech Stack

- **Backend**: FastAPI (Python 3.13)
- **Database**: PostgreSQL (async via SQLAlchemy)
- **Cache/Game State**: Redis
- **Containerization**: Docker + Docker Compose
- **Dependency Manager**: Poetry

## Project Structure

```
app/
├── core/              # Config, database, security, dependencies
├── models/            # SQLAlchemy ORM models
├── schemas/           # Pydantic request/response models
├── services/          # Business logic
├── routers/           # API endpoints
└── main.py            # FastAPI app entrypoint

scripts/               # Database seeding, migrations
tests/                 # Test suite
.envs/                 # Environment configuration files
```

## Phase 1: Backend Foundation ✓

Completed:
- ✓ FastAPI app with async SQLAlchemy ORM
- ✓ PostgreSQL and Redis integration
- ✓ JWT authentication with server-side token revocation
- ✓ Auth endpoints: register, login, refresh, logout
- ✓ Health check endpoint
- ✓ Docker + Docker Compose setup
- ✓ Placeholder card deck seeder
- ✓ Basic auth and health tests

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Poetry (optional, for local development)

### Start Services

```bash
docker compose up --build
```

This starts:
- `backend` on `http://localhost:8000`
- `postgres` on `localhost:5432`
- `redis` on `localhost:6379`

### API Documentation

Open browser to `http://localhost:8000/docs` for interactive Swagger UI.

### Phase 1 Verification

Run all Phase 1 verification steps:

```bash
# 1. Initialize database and seed cards
docker compose run --rm backend python scripts/seed_cards.py

# 2. Run tests
docker compose run --rm backend pytest tests/ -v

# 3. Check health
curl http://localhost:8000/health

# 4. Register a user (password must be at least 8 characters)
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testplayer","email":"test@example.com","password":"securepass123"}'

# 5. Get access token and test protected route
ACCESS_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username_or_email":"testplayer","password":"securepass123"}' | jq -r '.access_token')

curl -X GET http://localhost:8000/users/me \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

### Development Workflow

#### Run app
```bash
docker compose up
```

#### Run tests
```bash
docker compose run --rm backend pytest tests/ -v --cov=app
```

#### Lint code
```bash
docker compose run --rm backend ruff check app/
```

#### Format code
```bash
docker compose run --rm backend black app/ tests/
```

#### View logs
```bash
docker compose logs -f backend
```

#### Stop everything
```bash
docker compose down
```

## Environment Variables

Configuration is loaded from `.envs/.env.dev` by default. For production, use `.envs/.env.prod`.

Key variables:
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `JWT_SECRET_KEY`: Secret for signing tokens (change in production!)
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`: Access token TTL (default 24h)
- `JWT_REFRESH_TOKEN_EXPIRE_DAYS`: Refresh token TTL (default 30d)

## Next: Phase 2

Phase 2 implements full REST API for cards and rooms management.

See [plan.md](plan.md) for detailed Phase 2 roadmap.
