# 8) Testing and Docker Workflow

## Docker-First Execution

The repository standard is to run backend work through Docker Compose.

Canonical commands:

```bash
docker compose up --build
docker compose run --rm backend pytest tests/ -v
docker compose run --rm backend ruff check .
docker compose run --rm backend black .
docker compose run --rm backend alembic upgrade head
```

References:

- [../../AGENT.md](../../AGENT.md)
- [../../docker-compose.yml](../../docker-compose.yml)

## Test Architecture

### Endpoint tests

Files in [../../tests/endpoints](../../tests/endpoints) validate API and WebSocket behavior:

- auth and health
- room creation/join/config/matchmaking queue
- websocket join/leave, matchmaking events, game loop events

### Service tests

Files in [../../tests/services](../../tests/services) validate business rules in isolation:

- game start/deal/submit/judging progression
- timeout behavior, including timed-out czar round skip
- matchmaking tick transitions

### Shared fixtures

[../../tests/conftest.py](../../tests/conftest.py) uses in-memory SQLite for quick test execution and overrides app DB dependency.

Important nuance:

- production uses PostgreSQL
- tests use SQLite fallback for speed and portability
- model code accounts for this (for example UUID array fallback type in submission model)

## Why This Test Mix Is Good

- endpoint tests catch transport and integration contract regressions
- service tests catch state-machine regressions quickly
- both layers together reduce risk in multiplayer logic where small regressions are expensive

## Practical Validation Flow for Changes

1. run focused service/endpoint tests first
2. run broader suite once focused tests pass
3. verify API docs at `/docs` for contract changes
4. for WS changes, run a multiplayer flow manually if behavior is timing-sensitive

## Existing Regression-Sensitive Areas

- auth revocation behavior
- matchmaking countdown transitions
- round timer auto-submit
- disconnect/reconnect timeout and czar skip

When editing those areas, add or update tests in the same change.
