# 14) Real-Time Protocol Quick Reference

This chapter is a one-page matrix for frontend, QA, and backend contributors.

Protocol source of truth:

- [../PHASE_3_WEBSOCKET_PROTOCOL.md](../PHASE_3_WEBSOCKET_PROTOCOL.md)
- implementation in [../../app/routers/ws_rooms.py](../../app/routers/ws_rooms.py)

## WebSocket Endpoint

- `GET /ws/rooms/{room_id}?token=<access_jwt>`

## Common Envelope

All messages follow `WSEvent` from [../../app/schemas/ws.py](../../app/schemas/ws.py):

- `version`, `event`, `room_id`, `message_id`, `timestamp`, optional `correlation_id`, `payload`

## Command Matrix (Client -> Server)

| Event | Who Sends | Main Guardrails | Success Path | Error Codes |
|---|---|---|---|---|
| `client.ping` | any connected client | none | `server.pong` | n/a |
| `room.state_sync.request` | any connected client | room membership already validated at connect | `room.state_sync` | `INVALID_EVENT` only if malformed envelope |
| `lobby.start_game` | host | caller must be host, startable status, >=3 players | `game.started`, then `round.started` | `NOT_HOST`, `STATE_CONFLICT` |
| `game.submit_cards` | non-czar player | active waiting round, valid card ids, pick count match, no duplicate | `round.submission_accepted` or `round.judging` | `GAME_NOT_STARTED`, `ROUND_NOT_ACTIVE`, `NOT_CZAR`, `INVALID_CARD_SELECTION`, `DUPLICATE_SUBMISSION` |
| `game.pick_winner` | current czar | round must be judging, submission in round | `round.result` then `round.started` or `game.over` | `GAME_NOT_STARTED`, `ROUND_NOT_ACTIVE`, `NOT_CZAR`, `INVALID_PAYLOAD` |

## Event Matrix (Server -> Client)

| Event | Emitted By | When | Critical Payload Fields |
|---|---|---|---|
| `room.connected` | ws router | successful connect/auth/member check | `user_id`, `room_status` |
| `room.state_sync` | ws router | connect bootstrap or explicit sync request | `room`, `players`, `game` |
| `room.player_joined` | ws router | first active socket for user in room | `player` snapshot |
| `room.player_left` | ws router | disconnect in lobby/matchmaking_lobby | `player_id`, `reason` |
| `room.host_changed` | room service + ws router | host disconnect in lobby-style room | `previous_host_id`, `new_host_id` |
| `matchmaking.match_found` | ws router | random lobby connection established | `room_id`, `player_count` |
| `matchmaking.countdown_started` | worker/ws | matchmaking threshold reached | `expires_at`, `seconds_remaining`, `player_count` |
| `matchmaking.countdown_reset` | rooms router | player joins existing open countdown room | `expires_at`, `seconds_remaining`, `player_count` |
| `matchmaking.countdown_canceled` | worker | player count drops below 3 | `reason`, `player_count` |
| `matchmaking.locked` | worker or ws start path | countdown expiry, room full, or host-start random lobby | `reason`, `player_count` |
| `game.started` | ws router | start_game succeeds | `started_at`, `round_number`, `players` |
| `round.started` | ws router | initial round, next round, or czar-timeout skip | `round_id`, `round_number`, `czar_id`, `black_card`, `round_expires_at` |
| `round.submission_accepted` | ws router | one valid submission accepted, round still waiting | `round_id`, `player_id`, `submitted_count`, `required_count` |
| `round.timer_expired` | ws round timer task | round timer reaches expiry | `round_id` |
| `round.judging` | ws router/timer task | all submissions available | `round_id`, `submissions` |
| `round.result` | ws router | czar picked winner | `round_id`, `winner_player_id`, `winning_submission_id`, `scores` |
| `game.over` | ws router | winner reached winning score | `winner_player_id`, `scoreboard` |
| `player.reconnect_window_started` | ws router | disconnect detected | `player_id`, `expires_at`, `seconds_remaining` |
| `player.reconnected` | ws router | reconnect within window | `player_id` |
| `player.removed_timeout` | reconnect timeout task | reconnect window expired | `player_id`, `reason` |
| `server.pong` | ws router | ping command response | `sent_at`, `received_at` |
| `error` | ws router | invalid command/event/guard failure | `code`, `message`, `details` |

## Handshake and Close Codes Quick Notes

- auth failure: close `4401`
- non-member: close `4403`
- room missing: close `4404`

## Event Ordering Notes

- connect bootstrap sends `room.connected` then `room.state_sync`
- `game.started` precedes the first `round.started`
- `round.result` is always sent before next `round.started` in non-terminal rounds
- on reconnect success, expect `player.reconnected` broadcast and fresh `room.state_sync` for reconnecting client

## QA Smoke Script (Minimal)

1. Connect websocket to valid room with valid token.
2. Verify `room.connected` + `room.state_sync`.
3. Send `client.ping`; verify `server.pong`.
4. Start game from host socket; verify `game.started` and `round.started`.
5. Submit cards from non-czar; verify `round.submission_accepted` or `round.judging`.
6. Pick winner from czar; verify `round.result`.
