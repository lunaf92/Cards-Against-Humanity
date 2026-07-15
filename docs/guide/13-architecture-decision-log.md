# 13) Architecture Decision Log

This chapter records key architectural choices and why they were made.

## ADR-001: Docker-First Execution

Decision:

- run backend app, tests, and migrations via Docker Compose

Why:

- consistent runtime across developers
- avoids host-environment drift
- keeps service dependencies (Postgres/Redis) predictable

Where this is encoded:

- [../../AGENT.md](../../AGENT.md)
- [../../docker-compose.yml](../../docker-compose.yml)

## ADR-002: Thin Routers, Service-Centric Business Logic

Decision:

- routers manage transport concerns only; service layer owns domain logic

Why:

- testability of state transitions
- cleaner separation of concerns
- easier protocol evolution

Where this is encoded:

- routers: [../../app/routers](../../app/routers)
- services: [../../app/services](../../app/services)

## ADR-003: JWT + Server-Side Revocation

Decision:

- use JWT access/refresh tokens, with JTI revocation table for immediate invalidation

Why:

- supports real logout and token invalidation before expiry
- improves security for compromised tokens

Tradeoff:

- revocation lookup on protected requests

Where this is encoded:

- [../../app/services/auth.py](../../app/services/auth.py)
- [../../app/core/dependencies.py](../../app/core/dependencies.py)
- [../../app/models/token_revocation.py](../../app/models/token_revocation.py)

## ADR-004: PostgreSQL for Durable State, Redis for Ephemeral Game State

Decision:

- keep durable business entities in PostgreSQL
- keep deck/hand/reconnect markers/matchmaking queue in Redis

Why:

- fast read/write loop for real-time gameplay
- reduced DB contention on high-frequency card operations
- natural fit for TTL and queue semantics

Tradeoff:

- Redis state is operationally separate from SQL state

Where this is encoded:

- SQL models: [../../app/models](../../app/models)
- Redis state logic: [../../app/services/rooms.py](../../app/services/rooms.py)

## ADR-005: Redis Pub/Sub for Cross-Instance WebSocket Fanout

Decision:

- publish room events to `ws:room:{room_id}` and bridge to local sockets in each instance

Why:

- supports horizontal scaling without sticky event routing logic
- keeps event fanout simple and room-scoped

Tradeoff:

- pub/sub is not durable messaging

Where this is encoded:

- [../../app/services/ws_connection_manager.py](../../app/services/ws_connection_manager.py)
- startup lifecycle in [../../app/main.py](../../app/main.py)

## ADR-006: Matchmaking Countdown Driven by Background Worker

Decision:

- evaluate matchmaking lobby transitions in a periodic worker tick

Why:

- server-authoritative countdown behavior
- independent from any specific websocket client connection

Tradeoff:

- eventual consistency bounded by poll interval

Where this is encoded:

- [../../app/workers/matchmaking.py](../../app/workers/matchmaking.py)
- [../../app/services/rooms.py](../../app/services/rooms.py)

## ADR-007: Round Timers as In-Process Async Tasks

Decision:

- create one asyncio timer task per active round in websocket layer

Why:

- simple coupling to round lifecycle
- easy cancelation when all submissions arrive

Tradeoff:

- timer lifecycle tied to app process instance

Where this is encoded:

- [../../app/routers/ws_rooms.py](../../app/routers/ws_rooms.py)

## ADR-008: Czar Timeout Skips Waiting Round

Decision:

- if active czar times out during waiting state, skip the round and rotate czar

Why:

- prevents gameplay deadlock
- preserves momentum for remaining players

Where this is encoded:

- [../../app/services/rooms.py](../../app/services/rooms.py)
- regression test in [../../tests/services/test_rooms_gameplay.py](../../tests/services/test_rooms_gameplay.py)

## ADR-009: Contract Stability via Pydantic Schemas and WS Envelope

Decision:

- enforce explicit request/response models and a standard websocket event envelope

Why:

- predictable integration surface for frontend clients
- easier backward-compatibility management

Where this is encoded:

- [../../app/schemas](../../app/schemas)
- protocol docs in [../PHASE_3_WEBSOCKET_PROTOCOL.md](../PHASE_3_WEBSOCKET_PROTOCOL.md)

## ADR-010: Join-Order Determinism for Host and Czar Rotation

Decision:

- use `join_order` as canonical ordering for host handoff and czar selection

Why:

- deterministic, debuggable multiplayer behavior
- avoids hidden arbitration rules

Where this is encoded:

- [../../app/models/room_player.py](../../app/models/room_player.py)
- [../../app/services/rooms.py](../../app/services/rooms.py)
