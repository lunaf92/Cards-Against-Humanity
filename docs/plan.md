# Plan: CAH Clone — Phased Implementation
## Approach:
Build the backend end-to-end first (it's the hard part), then the frontend consumes a fully working API. Each phase produces something independently testable, and all run/build/test workflows are executed through Docker Compose.

## Phase 1 — Backend Foundation
Goal: runnable server with DB, migrations, and auth.

1. Project scaffold — FastAPI app, pyproject.toml (or requirements.txt), folder structure (app/routers, app/models, app/schemas, app/services, app/core)
2. Configuration — app/core/config.py via pydantic-settings; .env for DB URL, Redis URL, JWT secret, token TTLs
3. Database — SQLAlchemy async engine + session dependency; Alembic for migrations
4. ORM models — User, Card, Room, RoomPlayer, GameRound, Submission (matching requirements #6)
5. Auth endpoints — POST /auth/register, POST /auth/login, POST /auth/refresh, POST /auth/logout; bcrypt password hashing; access + refresh JWT pair
6. Auth middleware — get_current_user dependency injected into protected routes
7. Default deck seeder — a one-shot script (scripts/seed_cards.py) that loads a JSON card file into the DB (is_default=True, owner_id=null)
8. Health check endpoint — GET /health (confirms DB + Redis connectivity)
9. Container baseline — add backend Dockerfile and docker-compose services for backend, postgres, redis, and worker; wire env vars through compose
10. Containerized dev commands — add documented compose commands for migrations, seed, test, and lint

_Verify_: `docker compose up --build` starts services; register a user, log in, get a token, hit a protected route, and confirm seeded cards exist in DB.

## Phase 2 — Backend REST API (Cards & Rooms)
Goal: all non-real-time endpoints working. Parallel with nothing — depends on Phase 1.

### Cards
1. GET /cards/default — paginated list of default deck cards
2. GET /cards/mine — player's custom cards
3. POST /cards — create custom card (black or white)
4. PATCH /cards/{id} — edit own card (guard: not in active game)
5. DELETE /cards/{id} — delete own card (same guard)

### User Profile
6. GET /users/me — return current user profile
7. PATCH /users/me — update username, email, and password

### Rooms
8. ✅ POST /rooms — create private room; generate 6-char code; store config (max players, winning score, timer, card_pool_mode); hash room password with bcrypt
9. ✅ POST /rooms/join — join by code + password; validate capacity; insert RoomPlayer row
10. ✅ POST /rooms/queue — enter random matchmaking queue (Redis sorted set by join time); queue promotes first 3 players into a random matchmaking_lobby room
11. ✅ DELETE /rooms/queue — leave the matchmaking queue
12. ✅ GET /rooms/{id} — room details + current player list (for reconnect restoration)
13. ✅ PATCH /rooms/{id}/config — host-only; update room settings while in lobby status
14. ✅ Add room fields for random flow: room_kind and matchmaking_fill_expires_at
15. ✅ Add matcher worker service for rolling 10-second fill countdown and reset logic

_Verify_: run endpoint checks against compose-hosted API; confirm card guard blocks edits during active games.

## Phase 3 — Backend WebSockets & Game Engine
Goal: real-time multiplayer works end-to-end. This is the most complex phase. Depends on Phase 2.

### WebSocket infrastructure

1. WS /ws/rooms/{room_id} — authenticated via JWT query param on connect
2. Connection manager — in-memory dict of room_id → set[WebSocket]; wraps broadcast and send_personal
3. Redis pub/sub bridge — each backend instance subscribes to a Redis channel per room; broadcasts from any instance reach all connected players (enables horizontal scaling)
### Lobby events (can be developed parallel with game engine)
4. On connect → broadcast player_joined event to room
5. On disconnect → broadcast player_left; if host, transfer host to next in join order and broadcast host_changed

### Random matchmaking orchestrator
6. When queue reaches 3 players, create random room with status matchmaking_lobby and start fill window (10 seconds)
7. If another player joins before expiry and room size is below 10, add player and reset fill window to 10 seconds
8. If room reaches 10 players, lock lobby and start immediately
9. If fill timer expires with 3–9 players, lock lobby and start
10. If room drops below 3 during fill window, cancel timer and wait until room returns to at least 3
11. Emit WS events: match_found, matchmaking_countdown_started, matchmaking_countdown_reset, matchmaking_countdown_canceled, matchmaking_locked

### Game state machine — implemented as a GameService class backed by Redis hashes for active game state
12. START_GAME command (host only) → validate ≥3 players → assemble card pool per card_pool_mode → shuffle → deal 10 white cards to each player → persist hands in Redis → broadcast game_started + each player's private hand
13. ROUND_START → select Czar (rotate) → draw black card → broadcast round_started {czar_id, black_card}
14. SUBMIT_CARDS command → validate player is not Czar, card count matches pick, cards are in hand → store submission in Redis → if all submitted, advance automatically; else start/continue timer
15. ROUND_JUDGE → broadcast all submissions shuffled + anonymized to all players
16. PICK_WINNER command (Czar only) → record winner in Submission row → award point → broadcast round_result {winner, cards, scores}
17. Check win condition → if met, broadcast game_over {scoreboard}, persist final state to DB, close room; else loop to step 13

### Round timer
18. On ROUND_START spawn an asyncio.create_task for the configured duration; on expiry, auto-submit random unplayed white card for any non-submitting player; cancel task on early completion

### Disconnect/reconnect
19. On disconnect during game → store disconnected_at timestamp in Redis; keep player in room for 60s
20. On reconnect within window → restore hand from Redis, send current game state via game_state_sync event
21. On timeout → remove player, discard hand; if Czar, skip round (step 13 with next Czar)

_Verify_: manual multiplayer test against compose-hosted backend with 3 browser/wscat clients; simulate disconnection and timer expiry.

## Phase 4 — Frontend Foundation
Goal: Expo app boots, can authenticate, and has a working API client. Can start after Phase 1.

1. Expo scaffold — npx create-expo-app with TypeScript template; configure app.json (bundle IDs, icons placeholder)
2. Navigation — expo-router (file-based) or react-navigation with two stacks: AuthStack and AppStack (tab navigator: Home, My Cards, Profile)
3. Auth screens — Register, Login; form validation with react-hook-form + zod
4. Token storage — expo-secure-store for access + refresh tokens; auto-refresh interceptor in API client
5. API client — axios instance with base URL from env; request interceptor attaches Authorization header; response interceptor handles 401 → token refresh → retry
6. Auth state — React Context (or Zustand store) holding user + token; guards AppStack from unauthenticated access
7. Verify: register → login → token stored → protected screen renders → token refresh works on expiry simulation while API runs via Docker Compose.

## Phase 5 — Frontend — Lobby & Matchmaking
Goal: players can find each other and configure a game. Depends on Phase 4; can run parallel with Phase 3 backend work using mocked WS.

1. Home screen — two CTAs: "Find a Game" (random queue) and "Create / Join Private Room"
2. Create room screen — host configures max players, winning score, timer, card pool mode; POST /rooms
3. Join room screen — enter 6-char code + password; POST /rooms/join
4. Matchmaking screen — shows random-lobby countdown (server-authoritative), displays reset when new player joins, and cancel button calls DELETE /rooms/queue
5. Lobby screen — live player list (WebSocket player_joined / player_left / host_changed); host sees "Start Game" button (enabled at ≥3 players); non-host sees waiting state
6. My Cards screen — list custom cards (black/white tabs); add / edit / delete via REST API; character limit validation client-side
_Verify_: two simulators can enter the same private room and see each other's join event in real time against compose-hosted services.

## Phase 6 — Frontend — Gameplay
Goal: full game loop playable. Depends on Phase 5 and Phase 3.

1. Game screen layout — black card at top; player hand (scrollable row of white cards) at bottom; Czar indicator + player score strip
2. Submission UI — tap to select card(s); selected cards snap into black card blank slots; "Submit" CTA; disabled for Czar
3. Waiting state — after submission, show how many players still pending (aggregate count only, not who)
4. Czar judging screen — anonymous response cards displayed; Czar taps to pick winner; other players see "Czar is choosing…"
5. Round result reveal — animated reveal of winner's identity + their cards; +1 point animation on scoreboard strip
6. Timer bar — countdown progress bar; pulses red in final 10 seconds
7. Disconnect UX — if own connection drops, show reconnect banner with countdown; if opponent disconnects, show notification
8. End game screen — full scoreboard; trophy combos (winning black+white card pairs); "Play Again" (returns to lobby) / "Leave" buttons
_Verify_: full game loop with 3 test accounts from start to win condition; timer auto-submit; reconnect within window; backend services running in Compose.

## Phase 7 — Polish & NFRs
Goal: production-ready quality. Parallel across concerns.

1. Accessibility — audit contrast ratios; add accessibilityLabel to all interactive elements; test with system font size at maximum
2. Error handling — global error boundary in React Native; toast notifications for API/WS errors; backend returns structured error responses (detail, code)
3. Loading & skeleton states — all async data fetches show skeletons, not blank screens
4. Performance — load test backend with Locust (50 concurrent rooms, 10 players each); profile Redis memory usage per room
5. Security audit — confirm room passwords hashed; JWT not in AsyncStorage (use SecureStore); rate-limit auth endpoints; validate all user inputs server-side
6. CI pipeline — GitHub Actions runs backend tests/lint in containers and frontend checks in reproducible environment on PR
7. Deployment config — maintain docker-compose.yml for local dev/test and Dockerfiles for backend worker/runtime images; provide production compose profile or equivalent container orchestration manifest
Dependency graph
```
Phase 1 ──► Phase 2 ──► Phase 3
                │               \
                └──► Phase 4 ──► Phase 5 ──► Phase 6 ──► Phase 7
```

Phases 3 and 4 can run in parallel once Phase 2 is done. Phase 5 frontend work can begin against a mocked WebSocket while Phase 3 is still in progress.

Biggest risks to flag:

The game state machine (Phase 3) is the most complex piece — worth prototyping the asyncio timer + Redis state approach early
React Native WebSocket state management gets messy fast — decide on Zustand vs Redux before Phase 5
