# 9) How to Extend This Project Safely

This chapter is a practical playbook for implementing features without destabilizing core gameplay.

## Rule 1: Keep Contracts Stable

If you change request/response or WS payload shapes, treat it as a compatibility event.

Checklist:

- update schema models in [../../app/schemas](../../app/schemas)
- update endpoint or protocol docs
- add regression tests covering old and new expectations where feasible

## Rule 2: Put Logic in Services

Routers should orchestrate transport, not own state transitions.

When adding a feature:

1. define or update schema
2. call service from router
3. keep all guards and transitions in service method
4. unit test the service path

## Rule 3: Choose Storage by Data Nature

Use PostgreSQL when data must be durable and queryable later.
Use Redis when data is ephemeral, high-frequency, and room/session-scoped.

Examples:

- durable: users, rooms, rounds, winners
- ephemeral: shuffled deck order, player hand, reconnect marker

## Rule 4: Be Explicit About State Transitions

Whenever you add a new state or event:

- define allowed entry transitions
- define terminal/exit transitions
- define invalid transitions and error codes

Multiplayer bugs are usually transition bugs, not syntax bugs.

## Rule 5: Treat Reconnect as First-Class

Any gameplay change should answer:

- what if player disconnects mid-action?
- what state is restored on reconnect?
- what cleanup occurs on timeout?

If this is unanswered, the feature is incomplete.

## Rule 6: Add Tests Before Refactors in Core Loops

For `RoomService` and websocket handlers, add tests first for currently expected behavior, then refactor.

Suggested minimal pattern:

- one happy path test
- one invalid transition test
- one disconnect or timeout edge case

## Rule 7: Validate in Docker

Do not rely only on local host Python behavior. Use the compose stack to ensure parity with project runtime assumptions.

## Feature Walkthrough Example: Adding New WebSocket Event

1. Add event handling branch in [../../app/routers/ws_rooms.py](../../app/routers/ws_rooms.py).
2. Implement business behavior in [../../app/services/rooms.py](../../app/services/rooms.py) if stateful.
3. Emit event using `WSEvent` envelope from [../../app/schemas/ws.py](../../app/schemas/ws.py).
4. Add endpoint-level WS test in [../../tests/endpoints/test_ws_rooms.py](../../tests/endpoints/test_ws_rooms.py).
5. Add service-level test in [../../tests/services](../../tests/services) if transition logic changed.
6. Update docs:
   - [../websocket-protocol.md](../websocket-protocol.md)
   - this guide chapter or relevant chapter

## Future Evolution Ideas

- implement full `card_pool_mode` dealing variants in `RoomService._select_white_cards_for_room`
- add rate limiting on auth/login paths
- add observability (structured logs, metrics) around event timings
- support frontend clients with typed shared event contracts

This codebase already has good boundaries. Most future complexity should be added by extending service rules, not by bypassing them.
