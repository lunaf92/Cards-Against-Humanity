# Future Work — Known Risks and Things That Need Attention

Status as of 2026-07-15, after the backend hardening pass (logout fix, token type
claims, per-message WebSocket DB sessions, judging-phase timer, Redis game-state
cleanup, shuffled black decks, membership unique constraint).

Updated 2026-11-16 after the browser-readiness review pass (reconnect-timeout
removal actually firing, per-socket broadcast isolation, deck reshuffle,
startable worker-locked matchmaking rooms, pick-N auto-submit, richer
`room.state_sync`, `player.hand`, timer restore on startup).

This is the list of things that were **deliberately not fixed** (or only
mitigated) and should be revisited — roughly ordered by how likely they are to
bite.

**When to fix each of these** is covered separately in
[development-roadmap.md](development-roadmap.md), which maps every item here
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
one container). A restart (deploy, crash, `--reload`) drops the in-memory timer
tasks; on startup `restore_game_timers` (`app/routers/ws_rooms.py`) re-arms a
fresh full-length timer for every round that was `waiting`/`judging`, so games
no longer stall, but pending reconnect-timeout removals are not restored and
`room_players.is_connected` may be stale until players reconnect.

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
- **Token revocation checks hit Postgres on every request.** Expired rows are
  now purged hourly by the matchmaking worker loop
  (`REVOCATION_CLEANUP_INTERVAL_SECONDS`), so the table stays bounded as long as
  the worker runs; moving revocations to Redis with TTL is still the better fix.
- **HTTPBearer on logout returns 403** (FastAPI default) for a missing header
  where the rest of the API uses 401 — cosmetic inconsistency.

## 4. Gameplay gaps

- **`card_pool_mode` is not implemented.** The room config accepts five modes
  but `_select_white_cards_for_room` always uses default white cards, and black
  cards are drawn from *all* black cards (not filtered by `is_default` or
  language). The frontend should only offer `default_only` until this lands.
- **White deck exhaustion** is handled by reshuffling already-played cards
  (everything not in a hand or the deck) back in. If the whole card pool is
  smaller than what the table needs, hands are refilled only partially instead
  of failing the czar's pick; a player without enough cards simply cannot
  submit and the round timer moves on.
- **Czar disconnect during judging** relies on the judging timer for recovery:
  `handle_player_timeout` only skips rounds in `waiting` status, so a judging
  round waits for `_run_judging_timer` to auto-pick a random winner. Acceptable,
  but the round can take up to `round_timer_seconds` to resolve after the czar
  is removed.
- **A reconnect timeout is harsh in small games.** A player still offline after
  `RECONNECT_WINDOW_SECONDS` (default 60) is removed; in a 3-player game that
  ends the game (`game.over`, `reason = "not_enough_players"`). Before this was
  fixed the removal never actually fired (the Redis marker expired at the same
  moment the timeout task woke up), so this is newly observable behaviour.
  Raise `RECONNECT_WINDOW_SECONDS` for casual play (phones locking, flaky
  Wi-Fi) if it bites.
- **Host role moves on a lobby disconnect.** If the host's socket drops in the
  lobby while another player is connected, that player becomes host immediately
  (a page refresh is enough). A lone host now keeps the role. Deferring the
  transfer to the reconnect timeout would be friendlier.
- **No rematch.** A `finished` room cannot be restarted; players create a new
  room. Joining a finished room by code returns 409.
- **Mid-game joins are half-supported.** A player joining an `in_progress`
  private room by code (including one removed by timeout, who comes back with a
  fresh score) only receives a hand at the next round start, so the round in
  flight waits for its timer. No spectators.
- **Auto-submit picks the first cards in the hand**, not random ones —
  predictable but fine.

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
- **Health check doesn't cover the pub/sub bridge.** The bridge now
  resubscribes after unexpected errors (it is the only path for the worker's
  matchmaking events), but nothing reports its state.
- **Dependencies are not locked.** `poetry.lock` is git-ignored, so every image
  build resolves fresh versions. SQLAlchemy had to be constrained to `~2.0`
  (2.1 drops the implicit greenlet dependency and hangs the multi-socket
  aiosqlite tests). Commit a lock file before relying on rebuilds.
- **Lint tooling is old.** ruff 0.1.x cannot target py313 (configured as
  py312); `ruff check app/` is clean, `tests/` and `scripts/` still have
  unused-import/variable findings.

## 7. Testing gaps

- Round-timer, judging-timer and reconnect-timeout expiry are covered by
  `tests/endpoints/test_ws_timers.py`, which drives the timer coroutines
  directly with zero-length sleeps and captured broadcasts. They are still not
  exercised through real sockets: the WebSocket gameplay tests *disable*
  wall-clock timer scheduling (`_disable_wallclock_timers` in
  `tests/endpoints/test_ws_rooms.py`) because a slow run can otherwise cross
  the 90 s round timer mid-test.
- Coverage runs need `COVERAGE_CORE=sysmon` (set in `docker-compose.yml`);
  without it the pure-Python tracer slows the suite ~10x, which is how the
  timer flakiness was originally triggered.
- WebSocket tests require real Redis (docker); service tests use hand-rolled
  fakes duplicated in two files — consider `fakeredis` to consolidate.
- No concurrency tests (races in §2 are effectively untestable without them).
- `test_ws_reconnect_timeout_task_emits_removed_timeout` talks to the real dev
  Postgres (it bypasses the `test_db` fixture), so it silently depends on the
  dev DB schema existing.
- **The rest of the suite can't catch model/migration drift.** `test_db` (see
  `tests/conftest.py`) builds its schema via `Base.metadata.create_all(...)`
  straight from the ORM models — it never runs Alembic at all. A column
  declared on a model but missing from a migration passes every test in this
  file silently and only breaks against a real, migrated Postgres. This is
  exactly what happened with `GameRound.created_at` and `Submission.created_at`
  (migration 001 never created them; fixed in migration 005) — every test was
  green the whole time. `tests/test_schema_drift.py` is the regression guard:
  it diffs the live, migrated `postgres` service's schema against `Base.metadata`
  via `alembic.autogenerate.compare_metadata`, and only runs when a real
  Postgres is reachable (skips itself otherwise). It immediately caught two
  more real mismatches on first run — `Card.pick` was nullable on the model but
  `NOT NULL` in the DB, and `TokenRevocation.token_jti` was `String(255)` on
  the model but `VARCHAR(500)` in the DB — both now fixed by correcting the
  models to match the already-deployed schema, not the other way around.

## 8. Frontend protocol notes (leftovers to design around)

- `matchmaking.match_found` and `matchmaking.countdown_started` are re-broadcast
  every time any player's socket connects to a matchmaking lobby — handle them
  idempotently.
- On reconnect, clients should always send `room.state_sync.request` (or rely on
  the automatic `room.state_sync`) rather than trying to replay missed events.
  The snapshot's `game` object carries the hand with card texts, who has
  submitted, judging submissions and the phase deadline.
- The matchmaking worker locks a random lobby by setting it to `in_progress`
  without starting a round; the host must still send `lobby.start_game`
  (accepted in that state). A locked room with `game = null` in the state sync
  means "waiting for host to start". Auto-starting on lock would be nicer.
- `game.over.winner_player_id` can be `null` (`reason = "not_enough_players"`).
- `round.judging_expired` (new) fires when the czar timed out; it is followed by
  the normal `round.result` / `round.started` or `game.over` sequence with
  `correlation_id = null`.
- Token type claims are new: tokens issued before this change are rejected —
  clients must re-login once.
