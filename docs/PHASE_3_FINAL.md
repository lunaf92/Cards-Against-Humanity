# Phase 3 — Backend WebSockets & Game Engine: Final Summary

**Status:** ✅ Complete  
**All 19 tests passing** (`tests/endpoints/test_ws_rooms.py` + `tests/endpoints/test_rooms.py`)

---

## What Was Built

Phase 3 delivers the entire real-time multiplayer layer: WebSocket infrastructure, lobby events, random matchmaking orchestration, the full game state machine, a round timer with auto-submit, and disconnect/reconnect handling.

---

## Architecture Overview

```
Client (WebSocket)
    │
    ▼
ws/rooms/{room_id}  ←──────────────────────────────────┐
    │                                                   │
    ▼                                                   │
RoomConnectionManager (in-memory per-instance)          │
    │                                                   │
    ├── broadcast_event() ──► Redis pub/sub channel ────┘
    │                         ws:room:{room_id}
    │
    ├── _handle_start_game()
    ├── _handle_submit_cards()
    └── _handle_pick_winner()
         │
         ▼
     RoomService (app/services/rooms.py)
         │
         ├── PostgreSQL (SQLAlchemy async)
         └── Redis (hands, decks, reconnect windows)

Matchmaking Worker (app/workers/matchmaking.py)
    │
    ▼
process_matchmaking_tick() → publishes WS events via Redis pub/sub
```

---

## Files Changed / Created

| File | What changed |
|---|---|
| `app/routers/ws_rooms.py` | WebSocket handler, all game command handlers, round timer tasks, reconnect task management |
| `app/services/rooms.py` | Full game engine: `start_game`, `submit_cards`, `pick_winner`, matchmaking state, reconnect window, hand/deck management in Redis |
| `app/services/ws_connection_manager.py` | Redis pub/sub bridge: `start_pubsub_bridge`, `_run_pubsub_bridge`, `_publish_room_event`, cross-instance broadcast |
| `app/workers/matchmaking.py` | Matchmaking tick worker; publishes countdown/locked events via Redis pub/sub |
| `app/routers/rooms.py` | `join_matchmaking_queue` emits `matchmaking.countdown_reset` when a player joins an existing countdown |
| `app/main.py` | Lifespan context manager: starts/stops Redis pub/sub bridge on startup/shutdown |
| `app/models/game_round.py` | `GameRound` model (round number, czar, black card, status) |
| `app/models/room_player.py` | `RoomPlayer` model (score, join order, connection state) |
| `app/models/submission.py` | `Submission` model (player, round, white card IDs, is_winner) |
| `tests/endpoints/test_ws_rooms.py` | WebSocket integration tests |
| `tests/endpoints/test_rooms.py` | REST + matchmaking integration tests |

---

## WebSocket Events Reference

### Connection lifecycle
| Event | Direction | Description |
|---|---|---|
| `room.connected` | S→C | Sent to the connecting client on auth success |
| `room.state_sync` | S→C | Full room + game snapshot; sent on connect and on `room.state_sync.request` |
| `error` | S→C | Protocol or game error |

### Lobby
| Event | Direction | Description |
|---|---|---|
| `room.player_joined` | S→all | A player successfully connected |
| `room.player_left` | S→all | A player disconnected (lobby/matchmaking_lobby only) |
| `room.host_changed` | S→all | Host privilege transferred |

### Matchmaking
| Event | Direction | Description |
|---|---|---|
| `matchmaking.match_found` | S→all | Room promoted to `matchmaking_lobby` |
| `matchmaking.countdown_started` | S→all | 10-second fill window began |
| `matchmaking.countdown_reset` | S→all | New player joined; countdown reset to 10 s |
| `matchmaking.countdown_canceled` | S→all | Player count dropped below 3 |
| `matchmaking.locked` | S→all | Lobby locked; game starting |

### Game
| Event | Direction | Description |
|---|---|---|
| `lobby.start_game` | C→S | Host command to start the game |
| `game.started` | S→all | Game started; includes round number and player list |
| `round.started` | S→all | New round; czar, black card, `round_expires_at` |
| `game.submit_cards` | C→S | Player submits white cards |
| `round.submission_accepted` | S→all | Partial submission ack; submitted/required counts |
| `round.timer_expired` | S→all | Round timer ran out; auto-submissions made |
| `round.judging` | S→all | All submitted; anonymised shuffled submissions revealed |
| `game.pick_winner` | C→S | Czar picks winning submission |
| `round.result` | S→all | Winner revealed; updated scores |
| `game.over` | S→all | Game ended; final scoreboard |

### Disconnect / reconnect
| Event | Direction | Description |
|---|---|---|
| `player.reconnect_window_started` | S→all | Player disconnected; 60 s window open |
| `player.reconnected` | S→all | Player reconnected within window |
| `player.removed_timeout` | S→all | Reconnect window expired; player removed |

### Utility
| Event | Direction | Description |
|---|---|---|
| `client.ping` | C→S | Keepalive ping |
| `server.pong` | S→C | Keepalive pong with round-trip timestamp |
| `room.state_sync.request` | C→S | Request a fresh state sync |

---

## Game State Machine

```
lobby / matchmaking_lobby
    │
    │  lobby.start_game (host)
    ▼
in_progress
    │
    │  ROUND_START: czar rotates, black card drawn, hands refilled,
    │               round timer spawned (asyncio.create_task)
    ▼
[waiting for submissions]
    │
    ├── game.submit_cards (each non-czar player)
    │       └── if all submitted → cancel round timer → round.judging
    │
    └── round timer expires → auto-submit random card for pending players
                            → round.judging (if all now submitted)
    ▼
[judging]
    │
    │  game.pick_winner (czar)
    ▼
round.result broadcast
    │
    ├── if winner reached winning_score → game.over → finished
    │
    └── else → next ROUND_START (schedule new timer, cancel old)
```

---

## Round Timer

- Spawned via `asyncio.create_task(_run_round_timer(...))` immediately after `round.started` broadcast.
- Tracked in `_round_timer_tasks: dict[tuple[UUID, UUID], asyncio.Task]` keyed by `(room_id, round_id)`.
- On expiry: opens a fresh DB session + Redis client, finds non-submitting players, auto-submits the first card from each player's Redis hand, then broadcasts `round.timer_expired` and (if all are now in) `round.judging`.
- Cancelled early when: all players submit before the timer (transition → `"judging"` in `_handle_submit_cards`), or the next round starts (in `_handle_pick_winner`).

---

## Redis Key Scheme

| Key | Type | Content |
|---|---|---|
| `game:{room_id}:deck` | JSON string | Remaining white card UUID list |
| `game:{room_id}:hand:{user_id}` | JSON string | Player's current hand (white card UUIDs) |
| `reconnect:{room_id}:{user_id}` | String (TTL 60 s) | Reconnect window marker |
| `matchmaking:queue` | Sorted set | Player UUIDs scored by join timestamp |
| `ws:room:{room_id}` | Pub/sub channel | Cross-instance WebSocket event envelope |

---

## Cross-Instance Pub/Sub Bridge

All `connection_manager.broadcast_event()` calls publish a JSON envelope to `ws:room:{room_id}`. Each backend instance runs a `psubscribe("ws:room:*")` listener that fans out incoming envelopes to its locally connected sockets. Envelopes from the same instance are filtered by `source == self._instance_id` to prevent double-delivery.

---

## Disconnect / Reconnect Flow

1. On disconnect: `RoomService.start_reconnect_window()` writes a 60-second TTL key; `_schedule_reconnect_timeout_task()` starts a background task.
2. On reconnect within 60 s: task cancelled, TTL key cleared, `player.reconnected` broadcast, full `room.state_sync` sent including current hand from Redis.
3. On timeout: `player.removed_timeout` broadcast; player removed from room and hand key deleted from Redis.
4. If the disconnected player was the active Czar in a waiting round: the server automatically skips that round, creates the next round with the next Czar, emits `round.started`, and schedules the new round timer.

---

## Test Coverage

| Test | What it validates |
|---|---|
| `test_ws_room_connect_*` | Auth, ROOM_NOT_FOUND, FORBIDDEN |
| `test_ws_lobby_player_joined_broadcast` | `room.player_joined` on connect |
| `test_ws_lobby_player_left_on_disconnect` | `room.player_left` on disconnect |
| `test_ws_host_changed_on_host_disconnect` | Host transfer |
| `test_ws_matchmaking_*` | match_found, countdown_started, locked events |
| `test_ws_matchmaking_locked_when_host_starts_from_random_lobby` | locked broadcast before game start |
| `test_ws_reconnect_*` | reconnect window, state_sync restore, timeout removal |
| `test_handle_player_timeout_skips_waiting_round_when_czar_times_out` | active-czar timeout skips current round and creates the next round deterministically at service level |
| `test_ws_game_start_submit_pick_winner` | Full game loop |
| `test_matchmaking_queue_promotes_first_three_players` | countdown_reset on 4th player join |
