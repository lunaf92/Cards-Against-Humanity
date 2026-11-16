# AGENT.md

## Purpose

Project-level operating rules for all contributors and coding agents working on this repository.

## Project Status

- **Phase 1** (Backend Foundation) — ✅ Complete
- **Phase 2** (REST API — Cards & Rooms) — ✅ Complete
- **Phase 3** (WebSockets & Game Engine) — ✅ Complete
- **Phase 4** (Frontend Foundation) — ✅ Complete (web, React + Vite)
- **Phase 5** (Frontend Lobby & Matchmaking) — ✅ Complete
- **Phase 6** (Frontend Gameplay) — ✅ Complete
- **Phase 7** (Polish & NFRs) — Not started

Backend services (FastAPI, PostgreSQL, Redis) are fully operational and tested. The web frontend lives in `frontend/`.

## Repository Structure

```
/                        # Repo root
├── app/                 # FastAPI backend
├── tests/               # Backend test suite (pytest, Docker-executed)
├── alembic/             # DB migrations
├── scripts/             # Seed and utility scripts
├── docs/                # Developer guide, protocol reference, roadmap, known risks
├── .envs/               # Environment files for compose services
├── frontend/            # React + Vite web app
└── docker-compose.yml
```

## Non-Negotiable Rules

1. Docker-first execution only for backend work.
2. Tests are created early and run for every change.
3. Backward compatibility is preserved unless a breaking change is explicitly approved.
4. Documentation is updated with every non-trivial change.

## Docker-First Policy (Backend)

- Run the backend app, tests, linting, and scripts through Docker/Compose.
- Do not run backend services directly on the host machine.
- Prefer commands in this style:
  - `docker compose up --build`
  - `docker compose run --rm backend pytest`
  - `docker compose run --rm backend ruff check .`
  - `docker compose run --rm backend alembic upgrade head`

If a needed Docker command is missing, add it to project docs/scripts before continuing.

## Frontend Execution Policy

**Decided (2026-11)**: the frontend is a browser web app (React + Vite + TypeScript), not Expo/React Native. v1 target is friends playing in a browser on a self-hosted server; no app-store release.

- Run it from `frontend/`: `npm install`, then `npm run dev` (http://localhost:5173). The backend must be running via `docker compose up`.
- The app only talks to same-origin `/api` (REST, prefix stripped) and `/ws` (room sockets). Vite proxies both to `BACKEND_URL` (default `http://localhost:8000`) in dev; the reverse proxy does the same in production. Override with `VITE_API_BASE` / `VITE_WS_BASE` only if they live on another origin.
- Checks before committing: `npx tsc -b`, `npm run lint`, `npm test`, `npm run build`.

## Frontend State Management

**Decided**: use **Zustand** for all shared client state. Do not introduce Redux.

- Stores: `authStore` (session) and `roomStore` (room, players, game, socket). Server events are folded into state in `roomStore.applyEvent`; add new events there.
- Tokens live in `src/api/tokenStorage.ts` (localStorage, guarded). Never touch storage directly.
- `src/ws/roomSocket.ts` owns the socket: pings every 25 s, reconnects with backoff, refreshes the access token on close code 4401, and stops on 4403/4404. The server re-sends `room.state_sync` on every connect.

## Frontend Platform Target

- Mobile-first, works on desktop browsers. Test at phone width (e.g. Playwright `devices['iPhone 13']`).
- Card interaction: tap a card to open the zoom viewer (`components/CardZoom.tsx`), swipe between cards, act from there.
- Card visuals are original; do not copy art or branding from any published game.

## Testing and Regression Policy

- Write tests as part of implementation, not after the fact.
- For bug fixes, add a failing regression test first, then fix the code.
- Keep or improve test coverage for touched modules.
- Minimum test expectations per change:
  - Unit tests for business logic.
  - API tests for endpoint behavior and validation.
  - Regression tests for previously broken behavior.
- Do not merge changes that alter behavior without corresponding test updates.

### Backend Tests

- All tests executed via Docker: `docker compose run --rm backend pytest`
- WebSocket/disconnect tests are prone to race conditions in the aiosqlite test harness; prefer service-level tests for timeout/disconnect logic over websocket endpoint tests.

### Frontend Tests

- Use **vitest** + **@testing-library/react** for unit and component tests.
- Run from `frontend/`: `npm test`
- Test what the user sees and can interact with; do not test implementation details.
- Mock the WebSocket and API client in unit tests; use real backend for end-to-end validation.

## Compatibility Policy

- Preserve existing API contracts and payload shapes unless explicitly approved.
- If behavior must change, document it clearly and include migration notes.
- Ensure old clients do not break unexpectedly (status codes, required fields, event names).

## Documentation Policy

- Keep documentation in sync with implementation.
- Use FastAPI Swagger/OpenAPI as the API source of truth.
- For each endpoint, provide clear:
  - request/response models
  - status codes
  - validation constraints
  - examples when behavior is not obvious
- Keep `docs/implementation-plan.md` aligned with delivered behavior.
- WebSocket event contracts (event names, payload shapes) are documented in `docs/websocket-protocol.md` and `docs/guide/14-realtime-protocol-quick-reference.md`, and are stable. Do not change event names without updating those documents and all frontend consumers.

## Phase-Close Documentation Protocol

- At the end of every completed phase, update `AGENT.md` with any new execution standards, constraints, and quality gates introduced during that phase.
- **Do not create new freestanding `docs/PHASE_N.md`-style files.** That pattern rotted in practice — three of them (covering Phases 1–3) went stale and were deleted once the developer guide superseded them. Route what would have gone into one of those into the existing structure instead:
  - What was implemented, architecture/flow explanations, and file/line references for key logic paths → the relevant chapter under `docs/guide/`. Only add a new chapter if the change doesn't fit any existing one — if you do, update `docs/guide/README.md` and `docs/guide/TOC.md` to index it.
  - Notable design decisions and their tradeoffs → `docs/guide/13-architecture-decision-log.md`.
  - Newly discovered risks, deferred work, or known limitations → `docs/known-risks-and-technical-debt.md`.
  - Protocol/contract changes (WebSocket events, REST payloads) → `docs/websocket-protocol.md` and `docs/guide/14-realtime-protocol-quick-reference.md`.
  - Changes to what's next or milestone sequencing → `docs/development-roadmap.md` and `docs/implementation-plan.md`.
- For non-boilerplate code, include implementation-focused explanations similar in depth to the auth/revocation documentation style already used in `docs/`.
- Keep these updates actionable: include verification steps and expected outcomes, same bar a standalone phase doc would have had.

## Code Comment Policy

- Add a one-line comment above any non-trivial function or complex logic block.
- Keep comments intent-focused (why/constraint), not line-by-line restatements.
- Update comments when behavior changes.

## Definition of Done

A task is complete only when all are true:

1. Implementation works (backend: in Docker; frontend: in the browser at phone width).
2. Relevant tests are added/updated and pass.
3. Regression risk is covered by tests.
4. Swagger/OpenAPI docs are accurate (for backend changes).
5. Project docs are updated for non-trivial changes.
6. When a phase is completed, its documentation is folded into the existing `docs/` structure per the Phase-Close Documentation Protocol above — not written as a new freestanding file.

## PR Checklist

- [ ] Runs fully (backend: Docker/Compose; frontend: `npm run dev` + browser)
- [ ] Tests added early and passing
- [ ] Regression tests included where needed
- [ ] Backward compatibility reviewed
- [ ] Swagger/OpenAPI updated (backend)
- [ ] Non-trivial functions include one-line intent comments
- [ ] `docs/implementation-plan.md` updated if scope changed
- [ ] Non-boilerplate implementations documented in the relevant existing `docs/` file (guide chapter, ADR log, protocol reference, or known-risks doc) — no new freestanding `docs/PHASE_N.md`-style file
