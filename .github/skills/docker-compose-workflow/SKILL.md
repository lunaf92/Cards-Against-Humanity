---
name: docker-compose-workflow
description: Docker-first compose commands, validation checks, and pitfalls for this project.
---

# Docker + Compose Workflow

## When to Use

Use this skill for any task that starts, restarts, inspects, validates, or executes backend work in containers for this repository.

## Project Rules

- Docker-first execution only. Do not run app services directly on the host.
- Prefer `docker compose` over direct `docker` commands when interacting with app services.
- The `backend` service now starts with `alembic upgrade head` before Uvicorn.
- `postgres` and `redis` are expected to be healthy before backend startup is considered valid.

## Canonical Commands

- Start stack: `docker compose up --build`
- Restart backend with latest compose command: `docker compose up -d --force-recreate backend`
- Show resolved config: `docker compose config`
- Show service status: `docker compose ps`
- Tail backend logs: `docker compose logs -f backend`
- Open backend one-off command: `docker compose run --rm backend <command>`
- Stop stack: `docker compose down`
- Stop stack and remove volumes only when intentionally resetting state: `docker compose down -v`

## Service Names

- Backend service: `backend`
- Postgres service: `postgres`
- Redis service: `redis`
- Do not use container names where a compose service name is required.

## Common Checks

- Validate compose file after editing it: `docker compose config`
- Confirm backend command changed as expected: `docker compose ps backend`
- Confirm app is serving: `curl -sf http://localhost:8000/`
- Confirm health dependencies are up: `docker compose ps`

## Pitfalls

- `docker compose exec` takes a compose service name, not the container name. Use `postgres`, not `cah_postgres`.
- Avoid `down -v` unless you explicitly want to destroy Postgres and Redis data.
- If startup changes touch backend command or dependencies, recreate the backend container instead of assuming hot reload will pick them up.

## Expected Validation

After changing compose, Dockerfile, or startup behavior:

1. Run `docker compose config`.
2. Recreate the affected service.
3. Confirm `docker compose ps` shows the expected command and running state.
4. Hit at least one live endpoint such as `/` or `/health`.
