---
name: alembic-migration-workflow
description: Alembic-first schema change workflow, migration review checklist, and validation commands for this repository.
---

# Alembic Migration Workflow

## When to Use

Use this skill whenever a change affects SQLAlchemy models, database schema, defaults, indexes, constraints, or persisted data behavior.

## Project Rules

- Database schema is managed by Alembic, not by `Base.metadata.create_all()`.
- Do not reintroduce automatic table creation at application startup.
- Treat database data as the source of truth. Schema evolution must preserve existing data unless an intentional destructive migration is approved.
- Docker Compose runs `alembic upgrade head` once via the one-shot `migrate` service on every `docker compose up`; `backend` and `worker` wait for it to complete successfully before starting. Migrations still need to be authored explicitly — `migrate` only applies what already exists in `alembic/versions/`.

## Standard Workflow

1. Change the SQLAlchemy model(s).
2. Generate a migration: `docker compose run --rm backend alembic revision --autogenerate -m "<message>"`
3. Review the generated migration carefully. Do not trust autogeneration blindly.
4. Apply the migration: `docker compose run --rm backend alembic upgrade head`
5. Verify the resulting schema or behavior with a focused check.

## Review Checklist For Migrations

- Table and column names match model intent.
- New non-nullable columns have a safe default or backfill path.
- Indexes and foreign keys are present where required.
- Enum changes are handled safely for PostgreSQL.
- Downgrade path is present and sensible.
- Migration names reflect what they actually do.

## Commands

- Show current revision: `docker compose run --rm backend alembic current`
- Show migration history: `docker compose run --rm backend alembic history`
- Upgrade to head: `docker compose run --rm backend alembic upgrade head`
- Downgrade one step: `docker compose run --rm backend alembic downgrade -1`

## Pitfalls

- A generated migration can be wrong or incomplete, especially for renames and enum changes.
- Do not use `down -v` during migration verification unless you explicitly want a fresh database.
- If Postgres inspection is needed through compose exec, use the service name: `docker compose exec -T postgres psql -U cah_user -d cah_dev -c "\\dt"`

## Expected Validation

After editing models or migrations:

1. Run `alembic upgrade head`.
2. Run a narrow app-level or schema-level check.
3. Run tests covering the touched behavior.
4. If a migration changed API responses, verify the response schema remains aligned.
