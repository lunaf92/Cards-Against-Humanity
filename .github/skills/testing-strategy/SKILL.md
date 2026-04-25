---
name: testing-strategy
description: Testing expectations and validation flow for API, migration, startup, and regression changes in this repository.
---

# Testing Strategy

## When to Use

Use this skill whenever code changes affect API behavior, business logic, database persistence, migrations, startup behavior, or regression risk.

## Project Rules

- Tests are created early and run for every change.
- For bug fixes, add a failing regression test first when practical.
- Do not treat `git diff` as validation if a focused executable check exists.
- Docker is the default execution path for tests in this repository.

## Minimum Expectations

- Business logic changes: add or update unit tests.
- Endpoint changes: add or update API tests for status codes, payload shape, and validation.
- Schema or migration changes: validate migrations plus the affected behavior.
- Startup or compose changes: validate container startup and at least one live endpoint.

## Canonical Commands

- Run all tests: `docker compose run --rm backend pytest tests/ -v`
- Run quiet suite: `docker compose run --rm backend pytest -q tests/`
- Run a focused test file: `docker compose run --rm backend pytest tests/<file>.py -v`
- Lint: `docker compose run --rm backend ruff check .`
- Format: `docker compose run --rm backend black .`

## Choosing The First Validation Step

1. Prefer the narrowest test that can falsify the change.
2. If no focused test exists, run the smallest relevant behavioral check.
3. If the change affects startup or infrastructure, validate container behavior before widening scope.
4. Only widen to the full suite after the touched slice passes.

## Regression Focus Areas In This Repo

- Authentication flows and token revocation.
- Response schema compatibility.
- Database-backed model changes.
- Compose startup behavior, especially migration execution before app launch.

## Expected Validation For Recent Patterns

- Model plus migration change: `alembic upgrade head` plus focused tests.
- Compose startup change: `docker compose config`, recreate service, `curl` a live endpoint.
- Router response change: focused API test plus schema review.
