# 12) Troubleshooting Playbook

Use this chapter when behavior does not match expectations in local development.

## Quick Triage Sequence

1. Check stack status.

```bash
docker compose ps
```

2. Check backend logs.

```bash
docker compose logs -f backend
```

3. Check worker logs (matchmaking issues often appear here).

```bash
docker compose logs -f worker
```

4. Verify service health.

```bash
curl http://localhost:8000/health
```

## WebSocket Connect Fails (`4401`, `4403`, `4404`)

Likely causes:

- expired or revoked JWT (`4401`)
- valid token but user not in room (`4403`)
- bad room id (`4404`)

Where to inspect:

- auth and membership gating in [../../app/routers/ws_rooms.py](../../app/routers/ws_rooms.py)
- revocation checks in [../../app/services/auth.py](../../app/services/auth.py)

Practical checks:

- re-login to obtain fresh token
- call `GET /rooms/{room_id}` with same bearer token to verify membership

## Matchmaking Countdown Never Starts or Locks

Likely causes:

- player count not reaching threshold
- worker not running
- room state not `matchmaking_lobby`

Where to inspect:

- queue/join logic in [../../app/services/rooms.py](../../app/services/rooms.py)
- tick processor in [../../app/services/rooms.py](../../app/services/rooms.py)
- worker loop in [../../app/workers/matchmaking.py](../../app/workers/matchmaking.py)

Practical checks:

```bash
docker compose logs -f worker
```

## Game Does Not Progress to Judging

Likely causes:

- required submissions not reached
- invalid submission payload
- round not in `waiting`

Where to inspect:

- submit flow in [../../app/services/rooms.py](../../app/services/rooms.py)
- command handler in [../../app/routers/ws_rooms.py](../../app/routers/ws_rooms.py)

Practical checks:

- verify submitted card count matches black card `pick`
- verify submitting user is not current czar

## Czar Pick Fails

Likely causes:

- caller is not czar
- round not in `judging`
- `submission_id` not in that round

Where to inspect:

- `pick_winner` in [../../app/services/rooms.py](../../app/services/rooms.py)

## Reconnect Behavior Looks Wrong

Likely causes:

- reconnect window marker not being set/cleared as expected
- timeout task won race before reconnect

Where to inspect:

- timeout scheduling and handling in [../../app/routers/ws_rooms.py](../../app/routers/ws_rooms.py)
- reconnect key helpers in [../../app/services/rooms.py](../../app/services/rooms.py)

Practical checks:

- observe `player.reconnect_window_started`, `player.reconnected`, `player.removed_timeout` events
- reconnect within 60 seconds and request `room.state_sync`

## Tests Pass Locally but Runtime Behaves Differently

Likely causes:

- SQLite test semantics differ from PostgreSQL runtime semantics
- Redis-dependent flow not represented in a specific test

Where to inspect:

- test fixture DB in [../../tests/conftest.py](../../tests/conftest.py)
- dialect-aware list type in [../../app/models/submission.py](../../app/models/submission.py)

Practical checks:

- reproduce in running compose stack, not only unit tests
- add endpoint-level regression test for observed issue

## When in Doubt: Minimal Repro Loop

1. create fresh users
2. create/join one room
3. connect two websocket clients
4. send one command at a time
5. capture event stream and compare against [../PHASE_3_WEBSOCKET_PROTOCOL.md](../PHASE_3_WEBSOCKET_PROTOCOL.md)
