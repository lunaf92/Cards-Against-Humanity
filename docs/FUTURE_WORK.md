# Future Work — Known Risks and Things That Need Attention

Status as of 2026-07-15, after the backend hardening pass (logout fix, token type
claims, per-message WebSocket DB sessions, judging-phase timer, Redis game-state
cleanup, shuffled black decks, membership unique constraint).

This is the list of things that were **deliberately not fixed** (or only
mitigated) and should be revisited — roughly ordered by how likely they are to
bite.

**When to fix each of these** is covered separately in
[DEVELOPMENT_STRATEGY.md](DEVELOPMENT_STRATEGY.md), which maps every item here
to the development milestone where it becomes blocking.

---

## 1. Single-process deployment is a hard constraint

The Redis pub/sub bridge distributes *broadcasts* across instances, but core
game mechanics still live in process-local memory in `app/routers/ws_rooms.py`:

- `_round_timer_tasks`, `_judging_timer_tasks`, `_reconnect_timeout_tasks` are
  module-level dicts of `asyncio.Task`s.
- `connection_manager` presence checks (`has_user_connections`,
  `has_other_connected_users`) only see sockets on the local instance.

**Consequences if you run more than one worker/container:**
- A player who disconnects on instance A and reconnects on instance B is still
  removed when A's timeout task fires (the Redis reconnect-window key helps,
  but cancellation is local).
- Round/judging timers can't be cancelled across instances, so a round resolved
  on one instance may be double-resolved by another instance's timer.
- Presence events (`player_joined`) fire spuriously for users connected
  elsewhere.

**Rule for now:** exactly one backend process (`uvicorn` without `--workers`,
one container). Also note `--reload` in `docker-compose.yml` restarts the
process and silently drops all timers mid-game.

**Proper fix:** move timers to a real scheduler (e.g. the matchmaking worker
polling round deadlines stored in the DB/Redis, like
`matchmaking_fill_expires_at` already does) and presence to Redis keys with
heartbeat TTLs.

## 2. Remaining concurrency races

The membership unique constraint (migration 004) and `SELECT ... FOR UPDATE` on
the room row in WebSocket game commands close the worst holes, but these remain:

- **Room capacity:** `join_private_room` checks player count then inserts
  without locking the room row — concurrent joins can exceed `max_players`.
- **`join_order`:** computed as `max + 1` without a lock; concurrent joins can
  get the same order (czar rotation then depends on row order, not uniqueness —
  annoying, not fatal). The unique constraint prevents duplicate membership but
  not duplicate join_order.
- **Matchmaking queue:** `enqueue_for_matchmaking` does non-atomic
  `zadd`/`zrange`/`zrem` plus a DB scan; two simultaneous queuers can create
  two rooms or miscount the queue. A Lua script or `WATCH`/`MULTI` around the
  queue promotion, or doing promotion exclusively in the worker, would fix it.
- **Room code generation:** check-then-insert; a collision between the check
  and the insert raises IntegrityError → 500. Rare (36^6 space), but the
  `rooms.code` unique constraint should be the authority (catch and retry).
- **HTTP room endpoints** (`/rooms`, `/rooms/join`, `/rooms/{id}/config`) don't
  lock the room row like the WS handlers now do.

## 3. Auth hardening

- **No rate limiting** on `/auth/login` and `/auth/register`. Free credential
  stuffing, plus each attempt costs a bcrypt verify (CPU amplification).
  Add slowapi / a reverse-proxy limit before public exposure.
- **Access token TTL is 24 h** (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440` in
  `.envs/.env.dev`). With refresh tokens in place, 15–60 min is the sane range.
- **Refresh flow does not rotate tokens.** `/auth/refresh` now rejects access
  tokens (type claim) and keeps the original `jti`, so logout revokes the whole
  family — but a stolen refresh token is valid for 30 days with no rotation or
  reuse detection.
- **WS auth token travels in the query string** (`?token=...`) and will appear
  in proxy/access logs. Consider a short-lived one-time ticket endpoint
  (`POST /ws-ticket` → 30 s single-use token) later.
- **Token revocation checks hit Postgres on every request** and nothing calls
  `AuthService.cleanup_expired_revocations` periodically — the table grows
  forever. Wire the cleanup into the worker loop, or move revocations to Redis
  with TTL.
- **HTTPBearer on logout returns 403** (FastAPI default) for a missing header
  where the rest of the API uses 401 — cosmetic inconsistency.

## 4. Gameplay gaps

- **`card_pool_mode` is not implemented.** The room config accepts five modes
  but `_select_white_cards_for_room` always uses default white cards, and black
  cards are drawn from *all* black cards (not filtered by `is_default` or
  language). The frontend should only offer `default_only` until this lands.
- **White deck exhaustion ends up as `STATE_CONFLICT` errors.** When the deck
  can't refill hands, `pick_winner` raises and the czar's pick fails. A real
  fix reshuffles discarded submissions back into the deck.
- **Czar disconnect during judging** relies on the judging timer for recovery:
  `handle_player_timeout` only skips rounds in `waiting` status, so a judging
  round waits for `_run_judging_timer` to auto-pick a random winner. Acceptable,
  but the round can take up to `round_timer_seconds` to resolve after the czar
  is removed.
- **Timer-skipped rounds with < 3 remaining players** mark the room `finished`
  without a `game.over` broadcast (clients discover it via state sync). Rare
  (requires zero submissions on timeout), worth a proper event.
- **No spectators, no rejoin after timeout removal** — a removed player who
  rejoins a private room by code gets re-added with a fresh score.
- **Auto-submit picks `hand[0]`**, not a random card — predictable but fine.

## 5. Data model / persistence

- **No FK indexes** on `room_players.room_id`, `submissions.round_id`,
  `game_rounds.room_id` — fine at party-game scale, add before any real load.
- **No cascade rules:** deleting a `User` with cards/rooms/submissions will
  fail or orphan rows. There is no account-deletion endpoint yet, so latent.
- **Rooms are never garbage-collected.** Finished/abandoned rooms and their
  rounds/submissions stay in Postgres forever. Redis state now has a 24 h TTL
  and is cleaned on game over, but the relational rows need a sweeper.
- **`rooms.code` is only 6 chars** and never recycled; at some point old
  finished rooms will exhaust the code space / cause more retry loops.
- **`created_at` columns store naive UTC datetimes** (`.replace(tzinfo=None)`
  everywhere). Works, but switching to `DateTime(timezone=True)` would remove a
  whole class of confusion.

## 6. Operations / deployment

- **No production configuration exists.** `docker-compose.yml` runs uvicorn
  with `--reload`, mounts the source tree, and uses `.envs/.env.dev` with a
  placeholder `JWT_SECRET_KEY`. Before any deployment: real secret, `ENVIRONMENT=production`,
  no reload, no source mount, restricted CORS origins.
- **SQL echo is tied to `ENVIRONMENT=development`** (`app/core/database.py`) —
  very noisy logs; make sure production env value differs.
- **The matchmaking worker races the API** on the same room rows (see §2) and
  its 1 s poll is a busy loop against Postgres; fine for now.
- **No observability:** no structured logging, no request IDs, no metrics.
  With WebSockets + timers, debugging production incidents without logs will
  be painful.
- **Health check doesn't cover the pub/sub bridge** — if the bridge task dies
  (it logs and exits on unexpected exceptions), cross-instance broadcasts stop
  silently. At minimum, restart the task on failure.

## 7. Testing gaps

- Round-timer and judging-timer expiry paths are untested end-to-end. The two
  WebSocket gameplay tests explicitly *disable* wall-clock timer scheduling
  (`_disable_wallclock_timers` in `tests/endpoints/test_ws_rooms.py`) because a
  slow run can otherwise cross the 90 s round timer mid-test. Dedicated timer
  tests should inject a short duration instead of sleeping.
- Coverage runs need `COVERAGE_CORE=sysmon` (set in `docker-compose.yml`);
  without it the pure-Python tracer slows the suite ~10x, which is how the
  timer flakiness was originally triggered.
- WebSocket tests require real Redis (docker); service tests use hand-rolled
  fakes duplicated in two files — consider `fakeredis` to consolidate.
- No concurrency tests (races in §2 are effectively untestable without them).
- `test_ws_reconnect_timeout_task_emits_removed_timeout` talks to the real dev
  Postgres (it bypasses the `test_db` fixture), so it silently depends on the
  dev DB schema existing.

## 8. Frontend protocol notes (leftovers to design around)

- `matchmaking.match_found` and `matchmaking.countdown_started` are re-broadcast
  every time any player's socket connects to a matchmaking lobby — handle them
  idempotently.
- On reconnect, clients should always send `room.state_sync.request` (or rely on
  the automatic `room.state_sync`) rather than trying to replay missed events.
- `round.judging_expired` (new) fires when the czar timed out; it is followed by
  the normal `round.result` / `round.started` or `game.over` sequence with
  `correlation_id = null`.
- Token type claims are new: tokens issued before this change are rejected —
  clients must re-login once.
