# 2) FastAPI and Layered Architecture

## FastAPI Wiring

The application is assembled in [../../app/main.py](../../app/main.py):

- app metadata and docs URLs
- CORS middleware
- router registration
- lifespan hooks that start/stop the Redis pub/sub bridge

The lifespan hook is important: WebSocket broadcast fanout across instances is infrastructure, so it is started once with app lifecycle, not ad-hoc per request.

## Transport vs Business Logic

This codebase follows a strong separation:

- Routers own HTTP/WebSocket protocol concerns.
- Services own business rules and state transitions.

Examples:

- [../../app/routers/rooms.py](../../app/routers/rooms.py) handles endpoint shape and response models.
- [../../app/services/rooms.py](../../app/services/rooms.py) handles room creation, matchmaking, game start, submissions, winner selection.

Why it matters:

- easier unit testing of core behavior
- lower coupling to FastAPI-specific objects
- easier future migration if protocol layer changes

## Dependency Injection Pattern

FastAPI `Depends` is used for:

- DB session injection ([../../app/core/database.py](../../app/core/database.py))
- authenticated user resolution ([../../app/core/dependencies.py](../../app/core/dependencies.py))

This lets endpoint functions stay declarative while still getting the correct request-scoped dependencies.

## Schema Layer (Pydantic)

Schemas in [../../app/schemas](../../app/schemas) define public contracts:

- request payload constraints (`min_length`, ranges, literals)
- response shape and typing
- protocol envelope for WebSocket messages ([../../app/schemas/ws.py](../../app/schemas/ws.py))

This gives automatic request validation and OpenAPI docs while enforcing contract stability.

## Router Inventory (HTTP)

- [../../app/routers/auth.py](../../app/routers/auth.py): register/login/refresh/logout
- [../../app/routers/cards.py](../../app/routers/cards.py): default cards, my cards, create/update/delete custom cards
- [../../app/routers/users.py](../../app/routers/users.py): current profile read/update
- [../../app/routers/rooms.py](../../app/routers/rooms.py): create/join/get/configure rooms, queue enter/leave
- [../../app/routers/health.py](../../app/routers/health.py): DB and Redis health checks

## Why FastAPI Works Well Here

For this project, FastAPI gives practical wins:

- async-first request handling
- excellent ergonomics for typed request/response models
- built-in OpenAPI docs for contract visibility
- straightforward WebSocket endpoint support in same app

For an experienced web developer, the closest analogy is typed controller methods with declarative dependency injection, but with Python async and Pydantic model validation tightly integrated.
