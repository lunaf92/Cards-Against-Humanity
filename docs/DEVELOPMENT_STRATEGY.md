# Development Strategy — Sequencing the Road to a Playable Product

Written 2026-07-15, after the backend hardening pass. Companion documents:

- [plan.md](plan.md) — the original phased implementation plan (Phases 4–7 = frontend)
- [FUTURE_WORK.md](FUTURE_WORK.md) — the full inventory of known risks and debt

This document answers a different question than those two: **in what order should
the remaining work happen, and what must be true before each step?** The core
idea is to attach every known risk to the milestone where it actually starts to
matter, instead of fixing everything up front or discovering it in production.

---

## Guiding principles

1. **The frontend is the priority now.** The backend is functional and tested;
   its remaining weaknesses mostly matter under real concurrent load or public
   exposure — neither exists yet. Building the frontend first will also surface
   protocol/API problems that are much cheaper to fix before hardening.
2. **Fix backend issues at the milestone that makes them real.** Each gate below
   lists the FUTURE_WORK items that become blocking at that point. Until then,
   they are documented, not urgent.
3. **Don't scale prematurely.** The single-process constraint (FUTURE_WORK §1)
   is fine for development, playtesting with friends, and even a small beta.
   Solving distributed timers/presence before there's a frontend would be
   effort spent on a problem you don't have yet.

---

## Milestone 0 — Now: frontend development (plan.md Phases 4–6)

Build the Expo app against the existing backend. No backend changes required to
start. Backend facts the frontend must be designed around (details in
FUTURE_WORK §8):

- **Auth**: access tokens now carry a `type` claim; keep access-token TTL
  assumptions out of the client (read expiry from the JWT). Build the refresh
  flow from day one — it is much harder to retrofit.
- **WebSocket protocol**: treat `matchmaking.match_found` /
  `matchmaking.countdown_started` as idempotent; on any reconnect, rely on
  `room.state_sync` rather than replaying missed events. Handle
  `round.judging_expired` and `round.timer_expired` as informational — the
  authoritative state always arrives in the events that follow.
- **Room config**: only expose `card_pool_mode = "default_only"` in the UI —
  the other modes are accepted by the API but not implemented.
- Expect `player.reconnect_window_started` (60 s) on any disconnect during a
  game; the UI should show "waiting for player X" rather than removing them.

**Backend work during this milestone: only what the frontend flushes out.**
Keep a running list of protocol friction; batch fixes rather than context-
switching per issue.

## Milestone 1 — First real playtests (friends / LAN / single server)

Trigger: the full game loop is playable from the app (end of plan.md Phase 6).

Must do before inviting other humans:

- **Deployment constraint**: pin to exactly one backend process (no
  `--workers`, one container). Document it in the run instructions. This is a
  constraint to respect, not code to write (FUTURE_WORK §1).
- **A dev-like deployment without `--reload`**: reload restarts drop all
  in-flight timers mid-game and will look like mysterious game freezes during
  playtests (FUTURE_WORK §6).
- **Timer test coverage** (FUTURE_WORK §7): round-timer and judging-timer
  expiry are now core game mechanics with no end-to-end tests. Playtests will
  exercise them constantly; get deterministic tests first (inject short
  durations — don't sleep 90 s in tests).
- **Fix what playtesting reveals in the reconnect flow.** Reconnect/timeout is
  the least battle-tested part of the engine, and phones on WiFi are the
  perfect chaos monkey for it.

Explicitly *not* needed yet: rate limiting, multi-instance support, room
garbage collection, observability.

## Milestone 2 — Public/remote deployment (small beta, real internet users)

Trigger: the app leaves your LAN — TestFlight/APK builds pointing at a hosted
backend.

Security gate (FUTURE_WORK §3 and §6 — all of these become real the moment the
API is reachable from the internet):

- Real `JWT_SECRET_KEY`, `ENVIRONMENT=production` env file, restricted CORS,
  TLS termination (reverse proxy), SQL echo off.
- **Rate limiting** on `/auth/*` (reverse-proxy level is fine to start).
- **Drop access-token TTL to ≤ 1 h** — the 24 h TTL contradicts FR-AUTH-03's
  spirit once refresh works in the client (which Milestone 0 guarantees).
- **Revocation-table cleanup** wired into the worker loop — the table grows
  unboundedly with every logout.
- Health-check/restart policy for the pub/sub bridge and the worker
  (FUTURE_WORK §6) — on a remote host nobody is watching the logs.

Robustness gate (FUTURE_WORK §2 — real users double-click):

- HTTP room join: lock the room row (same `FOR UPDATE` pattern the WS handlers
  use) to close the capacity race.
- Matchmaking queue promotion: move it entirely into the worker (single
  consumer = no race) or make it atomic in Redis. The worker-owned design is
  simpler and the code is already half there.
- Catch-and-retry on room-code collision.

Hygiene: basic structured logging with request/room IDs. Debugging a remote
multiplayer bug without logs is guesswork.

## Milestone 3 — Growth features (post-MVP, order by demand)

Only after the core loop is stable with strangers playing:

- **Custom card pools** (`card_pool_mode` implementation — FUTURE_WORK §4).
  This is the headline feature of the requirements doc; implement per-room deck
  selection in `_select_white_cards_for_room` / `_draw_black_card`, filtered by
  mode and language.
- **White-deck exhaustion handling** (reshuffle used submissions) — becomes
  reachable once custom pools allow small decks.
- **Room/data garbage collection** (FUTURE_WORK §5): a worker sweep for
  finished/abandoned rooms and their rounds/submissions.
- **OAuth providers** (FR-AUTH-05) — the `auth_provider` column already exists.
- Account deletion + cascade rules (FUTURE_WORK §5) — required for app-store
  compliance if the app is published.

## Milestone 4 — Scaling beyond one process

Trigger: a single process actually becomes the bottleneck (hundreds of
concurrent sockets), **not before**. This is the big architectural item
(FUTURE_WORK §1):

- Move round/judging/reconnect deadlines into storage (a `deadline_at` column
  or Redis key) and let the worker fire them — the pattern already exists in
  `matchmaking_fill_expires_at` + `process_matchmaking_tick`. Delete the
  in-process `asyncio` timer registries entirely.
- Move presence to Redis (heartbeat keys with TTL) so `has_user_connections`
  is instance-agnostic.
- Only then: multiple uvicorn workers / replicas behind a load balancer. The
  pub/sub bridge already handles the broadcast side.
- At this point also add FK indexes (`room_players.room_id`,
  `submissions.round_id`, `game_rounds.room_id`) and consider timezone-aware
  timestamps while touching the schema (FUTURE_WORK §5).

---

## Summary table

| Milestone | Trigger | Blocking backend work |
|---|---|---|
| 0. Frontend | now | none — build the app, log friction |
| 1. Playtests | game loop playable in app | single-process pin, no `--reload`, timer tests, reconnect fixes |
| 2. Public beta | hosted backend, real users | prod config, rate limiting, short token TTL, revocation cleanup, join/matchmaking races, logging |
| 3. Growth | stable core loop | custom card pools, deck reshuffle, data GC, OAuth, account deletion |
| 4. Scale | single process saturated | worker-driven timers, Redis presence, multi-instance, indexes |

The failure mode to avoid: jumping to Milestone 4 problems (distributed
systems) while Milestone 0 (a frontend that exists) is still open.
