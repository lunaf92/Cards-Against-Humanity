# 10) 90-Minute Onboarding Path

This chapter is a hands-on reading and validation plan for a developer joining this project for the first time.

Goal for 90 minutes:

- run the stack
- understand architecture boundaries
- trace one full auth + room + gameplay flow
- locate where to add features safely

## 0-10 Minutes: Boot and Observe

1. Start services.

```bash
docker compose up --build
```

2. Open API docs.

- http://localhost:8000/docs

3. Quick health check.

```bash
curl http://localhost:8000/health
```

What to learn:

- which services are required for local runtime
- whether DB and Redis dependencies are healthy

## 10-25 Minutes: Read App Wiring and Boundaries

Read these files in order:

1. [../../app/main.py](../../app/main.py)
2. [../../app/core/config.py](../../app/core/config.py)
3. [../../app/core/dependencies.py](../../app/core/dependencies.py)
4. [../../app/routers](../../app/routers)
5. [../../app/services](../../app/services)

Questions to answer:

- where does transport logic stop?
- where do business rules live?
- how are auth and DB sessions injected?

## 25-45 Minutes: Trace Authentication End-to-End

Read:

1. [../../app/routers/auth.py](../../app/routers/auth.py)
2. [../../app/services/auth.py](../../app/services/auth.py)
3. [../../app/core/security.py](../../app/core/security.py)
4. [../../app/models/token_revocation.py](../../app/models/token_revocation.py)
5. [../auth-revocation-and-flow.md](../auth-revocation-and-flow.md)

Then run a minimal flow:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"onboard_user","email":"onboard@example.com","password":"pass12345"}'
```

What to learn:

- why JWT revocation exists in a token-based system
- where failures are intentionally fail-closed

## 45-65 Minutes: Trace Rooms and Matchmaking

Read:

1. [../../app/routers/rooms.py](../../app/routers/rooms.py)
2. [../../app/services/rooms.py](../../app/services/rooms.py)
3. [../../app/workers/matchmaking.py](../../app/workers/matchmaking.py)

Focus areas:

- room creation/join guards
- queue promotion behavior
- countdown transitions in worker tick

What to learn:

- how random rooms are orchestrated without client authority
- why join order is central to host/czar transitions

## 65-80 Minutes: Trace WebSocket Gameplay Loop

Read:

1. [../../app/routers/ws_rooms.py](../../app/routers/ws_rooms.py)
2. [../../app/services/ws_connection_manager.py](../../app/services/ws_connection_manager.py)
3. [../../app/schemas/ws.py](../../app/schemas/ws.py)
4. [../websocket-protocol.md](../websocket-protocol.md)

Focus areas:

- connection bootstrap (`room.connected`, `room.state_sync`)
- command handlers (`lobby.start_game`, `game.submit_cards`, `game.pick_winner`)
- round timer and reconnect timeout tasks

What to learn:

- how the backend stays authoritative despite real-time concurrency
- how cross-instance fanout works via Redis pub/sub

## 80-90 Minutes: Verify Tests and Contribution Flow

Run focused tests:

```bash
docker compose run --rm backend pytest tests/endpoints/test_auth.py -v
docker compose run --rm backend pytest tests/endpoints/test_rooms.py -v
docker compose run --rm backend pytest tests/endpoints/test_ws_rooms.py -v
```

Then scan:

- [../../tests/services/test_rooms_gameplay.py](../../tests/services/test_rooms_gameplay.py)
- [../../tests/services/test_rooms_matchmaking.py](../../tests/services/test_rooms_matchmaking.py)
- [../../AGENT.md](../../AGENT.md)

What to learn:

- how behavior is guarded by endpoint tests and service tests
- project-level non-negotiables (Docker-first, test-first, compatibility)

## After 90 Minutes: First Safe Task Suggestions

1. Add a small room config validation improvement with one service test and one endpoint test.
2. Add a new WebSocket error detail field without changing event names.
3. Improve docs for one existing event payload and verify it against tests.

If you can complete one of these changes with passing tests, you are ready to work on larger gameplay or protocol tasks.
