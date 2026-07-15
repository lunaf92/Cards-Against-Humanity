# 1) System Overview

## What This System Is Solving

The backend implements a multiplayer Cards Against Humanity style game where:

- users authenticate and manage profile data
- users create/join rooms (private or random matchmaking)
- game rounds progress in real time
- room and game state remain consistent under joins/leaves/reconnects

This is not just CRUD. It is a hybrid architecture: durable entities in PostgreSQL, volatile gameplay state in Redis, and event-driven updates via WebSockets.

## Runtime Topology

At local development time, Docker Compose runs four services:

- `backend`: FastAPI app
- `worker`: matchmaking background process
- `postgres`: primary relational database
- `redis`: cache + ephemeral game state + pub/sub

See [../../docker-compose.yml](../../docker-compose.yml).

## High-Level Request/Event Flow

1. HTTP requests hit FastAPI routers.
2. Routers validate payloads through Pydantic schemas.
3. Routers delegate behavior to service classes.
4. Services read/write SQL models through async SQLAlchemy.
5. Real-time actions are emitted as WebSocket events.
6. Broadcasts are published through Redis pub/sub so multiple backend instances can fan out the same events.

Key entry point: [../../app/main.py](../../app/main.py).

## Why This Split Exists

- PostgreSQL is authoritative for users, cards, room metadata, rounds, and submissions.
- Redis is optimized for fast changing state (hands, deck order, reconnect window markers, matchmaking queue).
- WebSockets let the server push state transitions instantly, rather than polling.

This design keeps integrity where it matters and speed where it matters.

## Directory Mental Model

- [../../app/core](../../app/core): config, security, DB/session dependencies
- [../../app/models](../../app/models): SQLAlchemy ORM entities
- [../../app/schemas](../../app/schemas): request/response contracts
- [../../app/routers](../../app/routers): HTTP + WebSocket transport layer
- [../../app/services](../../app/services): business logic
- [../../app/workers](../../app/workers): background loops (matchmaking)
- [../../tests](../../tests): endpoint and service tests

## Design Principles You Will Notice

- Thin routers, fat services
- Explicit state guards in gameplay transitions
- Event envelopes for protocol consistency
- Idempotent-ish operations where practical (queue leave, reconnect cleanup)
- Docker-first reproducibility for all backend operations
