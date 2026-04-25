# Authentication and Revocation Sequence Diagrams

This document provides sequence diagrams for the current auth and server-side token revocation implementation.

Related reference document:
- [auth-revocation-and-flow.md](auth-revocation-and-flow.md)

## 1. Register Flow

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant R as Auth Router (/auth/register)
    participant S as AuthService
    participant DB as PostgreSQL
    participant SEC as Security Utils

    C->>R: POST /auth/register {username, email, password}
    R->>S: get_user_by_username_or_email(username)
    S->>DB: SELECT user by username/email
    DB-->>S: none found
    S-->>R: available

    alt email provided
        R->>S: get_user_by_username_or_email(email)
        S->>DB: SELECT user by email
        DB-->>S: none found
        S-->>R: available
    end

    R->>S: register_user(...)
    S->>SEC: hash_password(password)
    SEC-->>S: bcrypt hash
    S->>DB: INSERT users
    DB-->>S: user row
    S-->>R: user

    R->>DB: COMMIT

    R->>S: create_tokens(user.id)
    S->>SEC: create_access_token({sub,jti})
    SEC-->>S: access token
    S->>SEC: create_refresh_token({sub,jti})
    SEC-->>S: refresh token
    S-->>R: token pair

    R-->>C: 201 TokenPair
```

## 2. Login Flow

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant R as Auth Router (/auth/login)
    participant S as AuthService
    participant DB as PostgreSQL
    participant SEC as Security Utils

    C->>R: POST /auth/login {username_or_email, password}
    R->>S: verify_user_password(...)
    S->>S: get_user_by_username_or_email(...)
    S->>DB: SELECT user
    DB-->>S: user or none

    alt user found
        S->>SEC: verify_password(plain, hash)
        SEC-->>S: true/false
    end

    alt invalid credentials
        S-->>R: None
        R-->>C: 401 Invalid credentials
    else valid credentials
        S-->>R: user
        R->>S: create_tokens(user.id)
        S->>SEC: create_access_token({sub,jti})
        SEC-->>S: access token
        S->>SEC: create_refresh_token({sub,jti})
        SEC-->>S: refresh token
        S-->>R: token pair
        R-->>C: 200 TokenPair
    end
```

## 3. Refresh Flow

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant R as Auth Router (/auth/refresh)
    participant SEC as Security Utils
    participant S as AuthService
    participant DB as PostgreSQL

    C->>R: POST /auth/refresh {refresh_token}
    R->>SEC: decode_token(refresh_token)
    SEC-->>R: payload or None

    alt decode failed
        R-->>C: 401 Invalid refresh token
    else payload ok
        R->>R: validate sub claim
        alt missing sub
            R-->>C: 401 Invalid token payload
        else sub exists
            R->>S: is_token_revoked(refresh_token)
            S->>SEC: decode_token(token)
            SEC-->>S: payload
            S->>DB: SELECT token_revocations by jti
            DB-->>S: row or none
            S-->>R: revoked true/false

            alt revoked
                R-->>C: 401 Token revoked
            else not revoked
                R->>S: create_tokens(user_id)
                S->>SEC: create_access_token({sub,jti})
                SEC-->>S: new access token
                S-->>R: token pair
                R-->>C: 200 TokenResponse(access_token)
            end
        end
    end
```

## 4. Logout Flow (Revocation Write)

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant R as Auth Router (/auth/logout)
    participant SEC as Security Utils
    participant S as AuthService
    participant DB as PostgreSQL

    C->>R: POST /auth/logout (Bearer token)
    R->>R: parse/validate bearer format

    alt invalid/missing authorization
        R-->>C: 401
    else format valid
        R->>SEC: decode_token(token)
        SEC-->>R: payload or None

        alt decode failed or missing sub
            R-->>C: 401
        else valid payload
            R->>S: revoke_token(db, user_id, token)
            S->>SEC: decode_token(token)
            SEC-->>S: payload with jti, exp
            S->>DB: INSERT token_revocations(user_id, jti, expires_at)
            DB-->>S: inserted
            S-->>R: ok
            R->>DB: COMMIT
            R-->>C: 204 No Content
        end
    end
```

## 5. Protected Endpoint Authentication (Revocation Read)

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant D as get_current_user dependency
    participant SEC as Security Utils
    participant S as AuthService
    participant DB as PostgreSQL
    participant E as Protected Endpoint

    C->>D: Request with Bearer access token
    D->>SEC: decode_token(token)
    SEC-->>D: payload or None

    alt invalid or expired token
        D-->>C: 401
    else payload ok
        D->>D: validate sub claim

        alt missing sub
            D-->>C: 401
        else sub exists
            D->>S: is_token_revoked(token)
            S->>SEC: decode_token(token)
            SEC-->>S: payload
            S->>DB: SELECT token_revocations by jti
            DB-->>S: row or none
            S-->>D: revoked true/false

            alt revoked
                D-->>C: 401 Token revoked
            else not revoked
                D->>DB: SELECT user by id
                DB-->>D: user or none

                alt user not found
                    D-->>C: 401
                else user found
                    D-->>E: inject current_user
                    E-->>C: 200 endpoint response
                end
            end
        end
    end
```

## 6. Revocation Cleanup Job

```mermaid
sequenceDiagram
    autonumber
    participant J as Cleanup Job/Task
    participant S as AuthService
    participant DB as PostgreSQL

    J->>S: cleanup_expired_revocations(db)
    S->>DB: DELETE FROM token_revocations WHERE expires_at < now(UTC)
    DB-->>S: rows deleted count
    S-->>J: done
```

## 7. Notes About Current Behavior

- Access and refresh tokens in one issuance share one JTI.
- Refresh currently returns only a new access token.
- Revocation checks are fail-closed (invalid decode or missing JTI treated as revoked).
