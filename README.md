# Cards Against Humanity Clone

A self-hosted, mobile-first party card game you play with friends in the browser.
FastAPI + PostgreSQL + Redis on the backend, React + Vite in `frontend/`.

Create a private room, share the code, pick which decks to play with, and go:
tap a card to see it big, play it, and let the judge pick the funniest answer.
See [docs/development-roadmap.md](docs/development-roadmap.md) for what's next.

## Tech Stack

- **Backend**: FastAPI (Python 3.13)
- **Frontend**: React 19 + Vite + TypeScript, Zustand, plain CSS
- **Web server (production)**: Caddy with automatic HTTPS
- **Database**: PostgreSQL (async via SQLAlchemy, Alembic migrations)
- **Cache/Game State**: Redis (decks, hands, matchmaking queue, pub/sub)
- **Containerization**: Docker + Docker Compose
- **Dependency Manager**: Poetry

## Project Structure

```
app/
├── core/              # Config, database, security, dependencies
├── models/            # SQLAlchemy ORM models
├── schemas/           # Pydantic request/response models
├── services/          # Business logic (rooms/game engine, auth, ws manager)
├── routers/           # REST endpoints + WebSocket room channel
├── workers/           # Matchmaking countdown worker
└── main.py            # FastAPI app entrypoint

frontend/              # Web app (pages, game views, socket client, sounds)
alembic/               # Database migrations
scripts/               # Card pack seeder + bundled packs (scripts/card_packs)
tests/                 # Test suite (endpoints, services, websocket)
docs/                  # Plans, protocol specs, developer guide
.envs/                 # Environment configuration files
```

## Features

**Playing**
- Private rooms with a 6-character code + password; the host sets points to win,
  round timer, max players and decks, and can change them in the lobby
- Random matchmaking with strangers (lobby fill countdown)
- Real-time rounds over WebSockets: play, judge, score, round/judging timers with
  auto-submit and auto-pick, and a reconnect window if your phone drops
- Mobile-first table: tap any card to zoom it, swipe through your hand,
  judge sees all answers side by side; the judge's hand is greyed out
- Quick reactions (6 emoji + 6 short phrases) that pop over the player, with a
  2-second cooldown
- Sound effects and haptics, with a mute toggle (original synthesized sounds in
  `frontend/public/sounds`; swap any `.wav` for one with the same name)

**Decks**
- 10 built-in English packs (Family Edition is seeded only on request)
- Pick one deck or any combination per room; default is every built-in pack but
  Family Edition. The game won't start if the decks can't fill every hand
- **My decks**: build your own decks with black and white cards (`___` marks a
  blank, and "Pick N" follows the number of blanks)
- **Share this deck**: one link; anyone who opens it can add and edit cards
- **Public / Private** tick box (owner only). After a game, players can copy any
  public deck it used into their own decks and add cards to it
- Any deck you can see can be copied with "Make a copy"

**Under the hood**
- JWT auth (access + refresh, server-side revocation on logout)
- WebSocket protocol reference: [docs/websocket-protocol.md](docs/websocket-protocol.md)
  and [docs/guide/14-realtime-protocol-quick-reference.md](docs/guide/14-realtime-protocol-quick-reference.md)

> **Deployment note**: run exactly **one** backend process. Round/reconnect timers
> and socket presence are process-local; multiple workers or replicas will
> misbehave. See [docs/known-risks-and-technical-debt.md](docs/known-risks-and-technical-debt.md) §1.

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Poetry (optional, for local development)

### Start Services

```bash
docker compose up --build
```

This starts:
- `migrate` (applies database migrations, then exits)
- `backend` on `http://localhost:8000`
- `worker` (matchmaking countdown)
- `postgres` on `localhost:5432`
- `redis` on `localhost:6379`

### API Documentation

Open browser to `http://localhost:8000/docs` for interactive Swagger UI.

### Quick Verification

```bash
# 1. Seed the built-in decks
docker compose run --rm backend python -m scripts.seed_cards
# safe to rerun; --list shows the packs, --packs a,b picks them, --packs all adds Family Edition

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

## Development Workflow

#### Run app
```bash
docker compose up
```

#### Run tests
```bash
docker compose run --rm backend pytest tests/ -v --cov=app
```

Notes:
- WebSocket tests need the `redis` service running (compose handles this).
- Coverage uses the fast `sys.monitoring` tracer via `COVERAGE_CORE=sysmon`
  (set in docker-compose); without it the suite is ~10x slower.

#### Updating an existing install
```bash
docker compose up -d --build     # the migrate service applies new migrations
docker compose run --rm backend python -m scripts.seed_cards   # tags cards with their deck (after migration 006)
```

#### Migrations
```bash
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend alembic revision -m "description"
```

#### Lint / format
```bash
docker compose run --rm backend ruff check app/
docker compose run --rm backend black app/ tests/
```

#### Logs / stop
```bash
docker compose logs -f backend
docker compose down
```

## Environment Variables

Configuration is loaded from `.envs/.env.dev` by default (see
[docs/known-risks-and-technical-debt.md](docs/known-risks-and-technical-debt.md) §6 before any production deployment).

Key variables:
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `JWT_SECRET_KEY`: Secret for signing tokens (change in production!)
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`: Access token TTL (default 24h; lower for production)
- `JWT_REFRESH_TOKEN_EXPIRE_DAYS`: Refresh token TTL (default 30d)
- `CORS_ORIGINS`: JSON list of allowed browser origins for the REST API, e.g.
  `["http://localhost:5173"]` for a Vite dev server, plus the public origin when
  served behind a reverse proxy
- `RECONNECT_WINDOW_SECONDS`: how long a disconnected player may reconnect before
  being removed from the room (default 60)

## Documentation

- [docs/implementation-plan.md](docs/implementation-plan.md) — phased implementation plan (Phases 4–7 = frontend)
- [docs/development-roadmap.md](docs/development-roadmap.md) — what to build/fix at which milestone
- [docs/known-risks-and-technical-debt.md](docs/known-risks-and-technical-debt.md) — known risks and technical debt
- [docs/guide/](docs/guide/README.md) — full developer guide (architecture, protocol, onboarding)
- [docs/product-requirements.md](docs/product-requirements.md) — functional requirements

## Frontend

Mobile-first web app in `frontend/` (React + Vite + TypeScript, Zustand).

```bash
docker compose up -d          # backend, worker, Postgres, Redis
cd frontend
npm install
npm run dev                   # http://localhost:5173, also reachable on your LAN
npm test                      # unit tests
```

The app calls same-origin `/api` and `/ws`; Vite proxies them to the backend in dev.

## Self-hosting

Production stack with Caddy (automatic HTTPS): see [docs/deployment.md](docs/deployment.md).

## Card content and licence

The built-in packs in `scripts/card_packs` are a snapshot of
[BixelPitch/cah-cards](https://github.com/BixelPitch/cah-cards), which is based on
Cards Against Humanity® and released under
[CC BY-NC-SA 2.0](https://creativecommons.org/licenses/by-nc-sa/2.0/). See
`scripts/card_packs/CREDITS.md`. This is a non-commercial fan project and isn't
affiliated with Cards Against Humanity LLC.
