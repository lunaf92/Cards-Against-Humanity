# 3) Data Model and Persistence

## Durable Domain Entities (PostgreSQL)

Core entities live under [../../app/models](../../app/models):

- [../../app/models/user.py](../../app/models/user.py): account identity and credentials
- [../../app/models/card.py](../../app/models/card.py): black/white cards, ownership, default/custom flag, language
- [../../app/models/room.py](../../app/models/room.py): room settings and lifecycle status
- [../../app/models/room_player.py](../../app/models/room_player.py): room membership, join order, score, connectivity
- [../../app/models/game_round.py](../../app/models/game_round.py): round index, czar, black card, round status
- [../../app/models/submission.py](../../app/models/submission.py): submitted white card ids and winner flag
- [../../app/models/token_revocation.py](../../app/models/token_revocation.py): revoked JWT handles (JTI)

## Why This Schema

### Room + RoomPlayer split

This is a standard multiplayer modeling move:

- `Room` contains configuration and coarse state
- `RoomPlayer` contains per-user room state

Benefits:

- clean player ordering (`join_order`) for host transfer and czar rotation
- independent score and connectivity tracking
- easier queries for room-level aggregates

### GameRound + Submission

Rounds and submissions are separated to encode lifecycle cleanly:

- one round has many submissions
- a round transitions waiting -> judging -> complete
- winner selection marks one submission as winner and increments player score

This supports auditability and replay-like diagnostics from DB rows.

### UUID arrays for submitted cards

In [../../app/models/submission.py](../../app/models/submission.py), `white_card_ids` uses a dialect-aware custom type:

- PostgreSQL uses `UUID[]`
- test DB fallback uses JSON

That keeps production efficient while preserving test portability.

## Enum-Driven State Safety

Several fields are strongly constrained by enums/literals:

- `room_kind`, `room_status`, `card_pool_mode`
- `card_type`
- `round_status`

Why: a finite state space prevents silent invalid states and simplifies transition logic in services.

## Migrations

Migrations are in [../../alembic/versions](../../alembic/versions).

Current migration history includes:

- language support on cards
- auth provider support on users
- expiry on token revocations

This indicates a schema strategy that prepares for future features while maintaining backward compatibility.
