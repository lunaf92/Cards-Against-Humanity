# 11) Contributor Task Map

This chapter helps you jump directly to the right files based on the kind of change you want to make.

## Change Type -> Start Here

## Authentication and Identity

- Transport: [../../app/routers/auth.py](../../app/routers/auth.py)
- Business logic: [../../app/services/auth.py](../../app/services/auth.py)
- Security primitives: [../../app/core/security.py](../../app/core/security.py)
- Auth dependency enforcement: [../../app/core/dependencies.py](../../app/core/dependencies.py)
- Revocation persistence: [../../app/models/token_revocation.py](../../app/models/token_revocation.py)
- Tests: [../../tests/endpoints/test_auth.py](../../tests/endpoints/test_auth.py)

Typical tasks:

- login/register payload changes
- refresh/logout behavior changes
- revocation policy changes

## Cards API and Card Rules

- Transport: [../../app/routers/cards.py](../../app/routers/cards.py)
- Model: [../../app/models/card.py](../../app/models/card.py)
- Schema: [../../app/schemas/card.py](../../app/schemas/card.py)
- Related guards (active game constraints): [../../app/services/rooms.py](../../app/services/rooms.py)

Typical tasks:

- card validation constraints
- card listing/filtering/pagination
- custom card mutation restrictions

## Users/Profile

- Transport: [../../app/routers/users.py](../../app/routers/users.py)
- Model: [../../app/models/user.py](../../app/models/user.py)
- Schema: [../../app/schemas/user.py](../../app/schemas/user.py)

Typical tasks:

- profile edit constraints
- username/email uniqueness behavior

## Private Rooms and Matchmaking

- Transport: [../../app/routers/rooms.py](../../app/routers/rooms.py)
- Business logic: [../../app/services/rooms.py](../../app/services/rooms.py)
- Worker loop: [../../app/workers/matchmaking.py](../../app/workers/matchmaking.py)
- Room models: [../../app/models/room.py](../../app/models/room.py), [../../app/models/room_player.py](../../app/models/room_player.py)
- Tests: [../../tests/endpoints/test_rooms.py](../../tests/endpoints/test_rooms.py), [../../tests/services/test_rooms_matchmaking.py](../../tests/services/test_rooms_matchmaking.py)

Typical tasks:

- queue behavior and countdown rules
- room config validation
- host transfer behavior

## WebSocket Protocol and Gameplay

- WebSocket router: [../../app/routers/ws_rooms.py](../../app/routers/ws_rooms.py)
- Core game engine logic: [../../app/services/rooms.py](../../app/services/rooms.py)
- Cross-instance fanout: [../../app/services/ws_connection_manager.py](../../app/services/ws_connection_manager.py)
- WS schema envelope: [../../app/schemas/ws.py](../../app/schemas/ws.py)
- Gameplay models: [../../app/models/game_round.py](../../app/models/game_round.py), [../../app/models/submission.py](../../app/models/submission.py)
- Tests: [../../tests/endpoints/test_ws_rooms.py](../../tests/endpoints/test_ws_rooms.py), [../../tests/services/test_rooms_gameplay.py](../../tests/services/test_rooms_gameplay.py)

Typical tasks:

- add/modify command handlers
- event payload changes
- round timer and reconnect behavior

## Infrastructure and Runtime

- App startup/lifespan: [../../app/main.py](../../app/main.py)
- Environment configuration: [../../app/core/config.py](../../app/core/config.py)
- Compose setup: [../../docker-compose.yml](../../docker-compose.yml)
- DB migrations: [../../alembic](../../alembic)

Typical tasks:

- startup sequencing
- service dependency wiring
- migration and schema rollouts

## How to Work Safely (Mini-Checklist)

1. Identify owning service and router first.
2. Change schema only if contract truly changes.
3. Add or update focused tests in same commit.
4. Run Docker-based test commands.
5. Update protocol/docs for any non-trivial behavior change.
