# Self-hosting on a home network

One machine runs everything with Docker Compose: Postgres, Redis, a single backend
process, the matchmaking worker, and Caddy. Caddy serves the web app, forwards `/api`
and `/ws` to the backend, and handles HTTPS automatically when you give it a domain.

```
browser ──► Caddy (:80/:443) ──► /            static web app
                              ├─► /api/*      backend:8000 (prefix stripped)
                              └─► /ws/*       backend:8000 (WebSocket)
```

## 1. Configure

```bash
cp .envs/.env.prod.example .envs/.env.prod
openssl rand -hex 32   # use one for POSTGRES_PASSWORD, another for JWT_SECRET_KEY
```

Edit `.envs/.env.prod`:

| Variable | What to set |
|---|---|
| `SITE_ADDRESS` | Your domain (e.g. `cah.example.com`) for automatic HTTPS, or `:80` for plain HTTP by IP. |
| `POSTGRES_PASSWORD` | Random string. Changing it later requires recreating the database volume. |
| `JWT_SECRET_KEY` | Random string. Changing it signs everyone out. |
| `RECONNECT_WINDOW_SECONDS` | How long a dropped phone may be away before it is removed (default 180). |
| `HTTP_PORT` / `HTTPS_PORT` | Optional host ports if 80/443 are taken (HTTPS via Let's Encrypt needs the router to forward external 80 and 443 to them). |

### HTTPS or plain HTTP?

- **Domain (recommended):** point a DNS A record (or a dynamic-DNS name) at your public
  IP, forward ports 80 and 443 on the router to this machine, set `SITE_ADDRESS` to the
  domain. Caddy gets and renews the certificate on its own. Phones get the native share
  sheet and clipboard, which browsers only allow over HTTPS.
- **IP only:** `SITE_ADDRESS=:80` and forward port 80. Everything works; sharing the room
  code falls back to showing it on screen.

## 2. Start

```bash
docker compose --env-file .envs/.env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .envs/.env.prod -f docker-compose.prod.yml run --rm backend python -m scripts.seed_cards
```

Open `https://<your domain>` (or `http://<your IP>`). Check health at `/api/health`.

Migrations run automatically on every `up` (the `migrate` service). Seed cards once;
rerunning the current seeder adds duplicates.

## 3. Update

```bash
git pull
docker compose --env-file .envs/.env.prod -f docker-compose.prod.yml up -d --build
```

Updating restarts the backend, which ends sockets; clients reconnect on their own and
round timers are re-armed at startup.

## Operating notes

- **Exactly one backend process.** Do not scale `backend` or add uvicorn workers: timers
  and socket presence live in process memory (known-risks §1).
- **Logs:** `docker compose -f docker-compose.prod.yml logs -f backend web`.
- **Backups:** `docker compose -f docker-compose.prod.yml exec postgres pg_dump -U cah cah > backup.sql`.
- Postgres and Redis are not published on host ports in this file; only Caddy is.

## Verified

The stack in this file was brought up, seeded, and a 3-player game was played to the
end through Caddy on plain HTTP, including a mid-game page reload and resume. The
sandbox it was tested in could not run the Dockerfiles' package downloads, so the images
were assembled from the same code and Caddyfile rather than built by `--build`; run the
first `up --build` on your machine and check `/api/health`.
