# AGENT.md

## Purpose

Project-level operating rules for all contributors and coding agents working on this repository.

## Non-Negotiable Rules

1. Docker-first execution only.
2. Tests are created early and run for every change.
3. Backward compatibility is preserved unless a breaking change is explicitly approved.
4. Documentation is updated with every non-trivial change.

## Docker-First Policy

- Run the app, tests, linting, and scripts through Docker/Compose.
- Do not run project services directly on the host machine.
- Prefer commands in this style:
  - `docker compose up --build`
  - `docker compose run --rm backend pytest`
  - `docker compose run --rm backend ruff check .`
  - `docker compose run --rm backend alembic upgrade head`

If a needed Docker command is missing, add it to project docs/scripts before continuing.

## Testing and Regression Policy

- Write tests as part of implementation, not after the fact.
- For bug fixes, add a failing regression test first, then fix the code.
- Keep or improve test coverage for touched modules.
- Minimum test expectations per change:
  - Unit tests for business logic.
  - API tests for endpoint behavior and validation.
  - Regression tests for previously broken behavior.
- Do not merge changes that alter behavior without corresponding test updates.

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
- Keep `requirements.md` and `plan.md` aligned with delivered behavior.

## Code Comment Policy

- Add a one-line comment above any non-trivial function or complex logic block.
- Keep comments intent-focused (why/constraint), not line-by-line restatements.
- Update comments when behavior changes.

## Definition of Done

A task is complete only when all are true:

1. Implementation works in Docker.
2. Relevant tests are added/updated and pass in Docker.
3. Regression risk is covered by tests.
4. Swagger/OpenAPI docs are accurate.
5. Project docs are updated for non-trivial changes.

## PR Checklist

- [ ] Runs fully via Docker/Compose
- [ ] Tests added early and passing
- [ ] Regression tests included where needed
- [ ] Backward compatibility reviewed
- [ ] Swagger/OpenAPI updated
- [ ] Non-trivial functions include one-line intent comments
- [ ] `requirements.md`/`plan.md` updated if scope changed
