# 4) Authentication and Security

## Auth Flow in Practice

Auth endpoints are defined in [../../app/routers/auth.py](../../app/routers/auth.py):

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`

Core auth operations are in [../../app/services/auth.py](../../app/services/auth.py).

## Password Handling

Passwords are hashed with bcrypt via Passlib in [../../app/core/security.py](../../app/core/security.py).

Why bcrypt:

- slow, adaptive hash designed for password storage
- reduces risk from offline hash cracking if DB is leaked

## JWT Strategy

The project issues access and refresh tokens with claims including:

- `sub` (user id)
- `jti` (token id)
- `exp` (expiry)

Token creation helpers are in [../../app/core/security.py](../../app/core/security.py).

## Server-Side Revocation (Important Design Choice)

Stateless JWT alone cannot support immediate logout. This project adds stateful revocation:

1. token JTI is stored in `token_revocations` on logout
2. protected requests verify token is not revoked
3. refresh also verifies revocation

References:

- [../../app/models/token_revocation.py](../../app/models/token_revocation.py)
- [../../app/services/auth.py](../../app/services/auth.py)
- [../../app/core/dependencies.py](../../app/core/dependencies.py)

Why this choice:

- immediate invalidation for compromised or logged-out sessions
- better operational security than waiting for JWT natural expiry

Tradeoff:

- every authenticated request performs a revocation lookup
- acceptable for this system because security is prioritized over fully stateless auth

## HTTP Auth Dependency

Protected HTTP endpoints depend on `get_current_user` from [../../app/core/dependencies.py](../../app/core/dependencies.py).

That function performs:

1. bearer extraction
2. JWT decode
3. payload validation
4. revocation check
5. user existence check

Only then does endpoint logic execute.

## WebSocket Auth

WebSocket auth uses `?token=<jwt>` query parameter at connect time in [../../app/routers/ws_rooms.py](../../app/routers/ws_rooms.py).

Reason:

- browser and many clients cannot set arbitrary headers during WS upgrade in the same way as HTTP requests

The same revocation-aware user resolution is applied before accepting gameplay events.

## Suggested Deep Dive

For a full walk-through with additional notes, read [../auth-revocation-and-flow.md](../auth-revocation-and-flow.md).
