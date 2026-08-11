---
name: fastapi-backend-conventions
description: Conventions for FastAPI routers, services, models, schemas, and wiring in this project.
---

# FastAPI Backend Conventions

## When to Use

Use this skill when adding or changing API endpoints, request and response schemas, models, services, or application wiring.

## Architecture Boundaries

- `app/main.py` wires middleware and routers.
- `app/routers/` owns HTTP concerns: endpoints, status codes, dependency injection, validation boundaries.
- `app/services/` owns business logic and orchestration.
- `app/models/` defines SQLAlchemy ORM persistence models.
- `app/schemas/` defines Pydantic request and response contracts.
- `app/core/` holds config, database, security, and shared dependencies.

## Project Rules

- Keep backward compatibility unless a breaking change is explicitly approved.
- When model fields are exposed publicly, keep response schemas aligned with ORM changes.
- Use async patterns consistently with the existing FastAPI and SQLAlchemy setup.
- Keep `main.py` lean. Do not move business logic into application startup or router modules.
- Add one-line intent comments above non-trivial functions or complex logic blocks.

## API Change Workflow

1. Identify the owning router and schema.
2. Step into the service or model layer where behavior is actually decided.
3. Make the smallest change that preserves current contracts.
4. Update request or response schemas when exposed fields change.
5. Verify Swagger or endpoint behavior after the change.

## Current Schema Direction

- Card records include a `language` field with default `"en"`.
- Multilingual support is planned to expand later; new card-related behavior should not assume English-only forever.
- Future language additions should extend current schema patterns rather than replace them ad hoc.

## Expected Validation

After backend behavior changes:

1. Run a focused test for the touched router or service.
2. Hit the affected endpoint if practical.
3. Confirm docs and schemas still reflect actual behavior.
4. Update `docs/product-requirements.md` or the relevant `docs/guide/` chapter when the change is non-trivial.
