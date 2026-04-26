# AGENT.md

## Purpose

Project-level operating rules for all contributors and coding agents working on this repository.

## Project Status

- **Phase 1** (Backend Foundation) — ✅ Complete
- **Phase 2** (REST API — Cards & Rooms) — ✅ Complete
- **Phase 3** (WebSockets & Game Engine) — ✅ Complete
- **Phase 4** (Frontend Foundation) — Not started
- **Phase 5** (Frontend Lobby & Matchmaking) — Not started
- **Phase 6** (Frontend Gameplay) — Not started
- **Phase 7** (Polish & NFRs) — Not started

Backend services (FastAPI, PostgreSQL, Redis) are fully operational and tested. The frontend has not been scaffolded yet.

## Repository Structure

```
/                        # Repo root
├── app/                 # FastAPI backend
├── tests/               # Backend test suite (pytest, Docker-executed)
├── alembic/             # DB migrations
├── scripts/             # Seed and utility scripts
├── docs/                # Phase documentation
├── .envs/               # Environment files for compose services
├── frontend/            # Expo/React Native app (Phase 4+, not yet created)
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

- Frontend (`frontend/`) is an Expo app; run it with `npx expo start` from inside the `frontend/` directory.
- The backend must be running via `docker compose up` for any frontend integration flows.
- Do not add the frontend as a Docker Compose service unless explicitly decided.
- Frontend environment: base API URL is read from `EXPO_PUBLIC_API_URL` in `frontend/.env`.

## Frontend State Management

**Decided**: use **Zustand** for all shared client state. Do not introduce Redux.

- Stores: `authStore`, `roomStore`, `gameStore`.
- Token storage via a cross-platform `secureStorage` abstraction (`src/utils/secureStorage.ts`): expo-secure-store on native, sessionStorage on web. Never call either directly — always use the abstraction.

## Frontend Platform Target

**Decided**: iOS, Android, and web. Build mobile-first, web-compatible from the start.

- Do not use native-only APIs without a web fallback.
- Use `Pressable` everywhere; avoid platform-specific touch primitives.
- Web production build (`npx expo export --platform web`) produces a static bundle served by nginx. A Compose service for this will be added in Phase 7.
- Check the web target with `npx expo start --web` at the end of every phase.

## Frontend Open Decisions (resolve before Phase 5)

- Confirm `EXPO_PUBLIC_API_URL` for local dev (typically `http://localhost:8000` on simulator/web, or the host LAN IP for physical device testing).

## Frontend Tooling Decisions (locked)

- **Expo Go** for development. All libraries in Phases 4–6 are Expo Go compatible. If a future library requires a native module outside Expo Go's set, migrate to a dev build via `eas build --profile development` at that point. The migration is a one-time reinstall with no code changes required.

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

- Use **jest** + **@testing-library/react-native** for unit and component tests.
- Run from `frontend/`: `npx jest`
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
- Keep `docs/plan.md` aligned with delivered behavior.
- WebSocket event contracts (event names, payload shapes) are documented in `docs/PHASE_3_FINAL.md` and are stable. Do not change event names without updating that document and all frontend consumers.

## Phase-Close Documentation Protocol

- At the end of every completed phase, update `AGENT.md` with any new execution standards, constraints, and quality gates introduced during that phase.
- At the end of every completed phase, create or update phase documentation under `docs/` with:
  - what was implemented
  - architecture and flow explanation for non-boilerplate code
  - file and line references for key logic paths
  - behavior notes, edge cases, and known limitations
- For non-boilerplate code, include implementation-focused explanations similar in depth to the auth/revocation documentation style already used in `docs/`.
- Keep phase docs actionable: include verification steps and expected outcomes.

## Code Comment Policy

- Add a one-line comment above any non-trivial function or complex logic block.
- Keep comments intent-focused (why/constraint), not line-by-line restatements.
- Update comments when behavior changes.

## Definition of Done

A task is complete only when all are true:

1. Implementation works (backend: in Docker; frontend: in Expo).
2. Relevant tests are added/updated and pass.
3. Regression risk is covered by tests.
4. Swagger/OpenAPI docs are accurate (for backend changes).
5. Project docs are updated for non-trivial changes.
6. Phase-close docs in `docs/` are updated when a phase is completed.

## PR Checklist

- [ ] Runs fully (backend: Docker/Compose; frontend: Expo)
- [ ] Tests added early and passing
- [ ] Regression tests included where needed
- [ ] Backward compatibility reviewed
- [ ] Swagger/OpenAPI updated (backend)
- [ ] Non-trivial functions include one-line intent comments
- [ ] `docs/plan.md` updated if scope changed
- [ ] `docs/` phase documentation updated for non-boilerplate implementations
