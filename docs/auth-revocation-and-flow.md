# Authentication and Server-Side Token Revocation

This document explains the current implementation of server-side token revocation and the authentication flow, with direct references to code locations.

## 1. Server-Side Token Revocation

### 1.1 Revocation Storage Model

The revocation table is defined in [app/models/token_revocation.py](../app/models/token_revocation.py#L10).

Key fields:
- JTI key for revocation checks: [app/models/token_revocation.py](../app/models/token_revocation.py#L16)
- Revocation timestamp: [app/models/token_revocation.py](../app/models/token_revocation.py#L17)
- Original token expiration: [app/models/token_revocation.py](../app/models/token_revocation.py#L18)

Design intent:
- Persist token invalidations server-side (instead of relying only on JWT expiry).
- Use JTI as a unique revocation handle.
- Keep expires_at to enable cleanup of stale revocation rows.

### 1.2 Where JTI Comes From

Token issuance happens in [app/services/auth.py](../app/services/auth.py#L46).

How it works:
- A random UUID JTI is generated.
- The same JTI is embedded in both access and refresh tokens in this issuance.
- JWT encoding is performed by:
  - Access token creation: [app/core/security.py](../app/core/security.py#L21)
  - Refresh token creation: [app/core/security.py](../app/core/security.py#L36)

### 1.3 Revocation Write Path (Logout)

Logout endpoint starts at [app/routers/auth.py](../app/routers/auth.py#L127).

Flow:
1. Parse and validate bearer token format in [app/routers/auth.py](../app/routers/auth.py#L141).
2. Decode JWT payload with [app/core/security.py](../app/core/security.py#L46).
3. Revoke through service call in [app/routers/auth.py](../app/routers/auth.py#L163).
4. Service persists revocation row in [app/services/auth.py](../app/services/auth.py#L58).
5. Router commits transaction in [app/routers/auth.py](../app/routers/auth.py#L164).

### 1.4 Revocation Check Path

The revocation check function is [app/services/auth.py](../app/services/auth.py#L78).

Behavior:
- If token decoding fails, treat as revoked (fail closed).
- If JTI claim is missing, treat as revoked.
- Otherwise query token_revocations by token_jti.

### 1.5 Enforcement Points

Revocation is enforced in two critical places:
- Protected-route dependency in [app/core/dependencies.py](../app/core/dependencies.py#L14), revocation call at [app/core/dependencies.py](../app/core/dependencies.py#L38)
- Refresh endpoint in [app/routers/auth.py](../app/routers/auth.py#L91), revocation call at [app/routers/auth.py](../app/routers/auth.py#L109)

This ensures revoked tokens are blocked both for API access and refresh attempts.

### 1.6 Revocation Cleanup

Expired revocations are removed by [app/services/auth.py](../app/services/auth.py#L92).

Purpose:
- Prevent unbounded table growth.
- Keep only revocations that still matter for unexpired tokens.

## 2. Authentication Flow (auth router)

Auth endpoints are implemented in [app/routers/auth.py](../app/routers/auth.py).

### 2.1 Register

Entry point: [app/routers/auth.py](../app/routers/auth.py#L24)

Steps:
1. Username uniqueness check using service lookup.
2. Optional email uniqueness check.
3. User creation through service in [app/services/auth.py](../app/services/auth.py#L14).
4. Password hashing via security helper in [app/core/security.py](../app/core/security.py#L10).
5. Commit transaction.
6. Issue token pair through service function in [app/services/auth.py](../app/services/auth.py#L46).

Response model:
- TokenPair schema from [app/schemas/auth.py](../app/schemas/auth.py)

### 2.2 Login

Entry point: [app/routers/auth.py](../app/routers/auth.py#L64)

Steps:
1. Resolve user by username or email via [app/services/auth.py](../app/services/auth.py#L26).
2. Verify password via [app/services/auth.py](../app/services/auth.py#L38) and [app/core/security.py](../app/core/security.py#L14).
3. On success, issue fresh token pair via [app/services/auth.py](../app/services/auth.py#L46).
4. On failure, return 401.

### 2.3 Refresh

Entry point: [app/routers/auth.py](../app/routers/auth.py#L91)

Steps:
1. Decode submitted refresh token via [app/core/security.py](../app/core/security.py#L46).
2. Validate required subject claim.
3. Check revocation in [app/services/auth.py](../app/services/auth.py#L78).
4. Issue a new access token (current implementation calls token pair creator and returns access token only).

### 2.4 Logout

Entry point: [app/routers/auth.py](../app/routers/auth.py#L127)

Steps:
1. Validate authorization token input format.
2. Decode token and validate subject claim.
3. Persist revocation record through [app/services/auth.py](../app/services/auth.py#L58).
4. Commit and return 204.

## 3. Protected Endpoint Authentication Path

Authentication dependency is [app/core/dependencies.py](../app/core/dependencies.py#L14).

Execution order:
1. Extract bearer token.
2. Decode token payload.
3. Validate subject claim.
4. Check revocation status.
5. Load user from database and return user context.

If any step fails, request is rejected with 401.

## 4. Security Properties Achieved

With this implementation:
- JWTs are stateless for verification, but revocation is stateful and immediate.
- Logout can invalidate tokens before natural expiry.
- Revoked tokens are denied for both resource access and refresh.
- Revocation records are bounded over time through cleanup.

## 5. Current Behavior Notes

- A token pair is issued with a shared JTI per issuance in [app/services/auth.py](../app/services/auth.py#L46).
- Refresh currently returns only a new access token in [app/routers/auth.py](../app/routers/auth.py#L117).
- Decode helper centralization is in [app/core/security.py](../app/core/security.py#L46).
