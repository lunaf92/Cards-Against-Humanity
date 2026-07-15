# 7) Redis Strategy and Key Design

## Why Redis Is Used Here

Redis is not a generic cache in this project. It is a gameplay state engine for data that is:

- fast-changing
- short-lived
- expensive to model transactionally in SQL for every move

Using Redis for these slices reduces DB write pressure and simplifies game-loop performance.

## Key Patterns

Implemented primarily in [../../app/services/rooms.py](../../app/services/rooms.py) and [../../app/services/ws_connection_manager.py](../../app/services/ws_connection_manager.py):

- `matchmaking:queue` (sorted set): random queue ordered by enqueue time
- `game:{room_id}:white_deck` (JSON string list): remaining deck order
- `game:{room_id}:hand:{user_id}` (JSON string list): private hand per player
- `reconnect_window:{room_id}:{player_id}` (TTL marker): disconnect grace window
- `ws:room:{room_id}` (pub/sub channel): cross-instance WS event fanout

## Data Structure Choices

### Sorted set for queue

Sorted sets naturally support timestamp ordering and efficient pop/range patterns.

### JSON lists for deck and hands

Given moderate card counts, JSON list operations are simple and sufficient. This favors readability and portability over highly optimized custom structures.

### TTL reconnect markers

A TTL key is the simplest source of truth for grace-period validity. It removes the need for extra cleanup cron logic.

### Pub/sub channels for room broadcasts

Pub/sub gives at-most-once fire-and-forget event delivery between app instances. Appropriate because clients also receive periodic full state sync and can request explicit resync.

## Tradeoffs You Should Understand

- Redis state can be lost on restart unless persistence is configured; this is acceptable for in-progress ephemeral game state in local/dev context.
- JSON list updates are not atomic multi-step game transactions; service-level guards and round-state checks provide consistency boundaries.
- Pub/sub is not a durable message queue; missing events should be recoverable via `room.state_sync`.

## If You Need Stronger Guarantees Later

Potential future upgrades:

- Lua scripts for atomic hand/deck transitions
- Redis Streams for durable event history/replay
- Snapshotting active game state into SQL at interval checkpoints

Current design intentionally stays simpler while meeting project requirements.
