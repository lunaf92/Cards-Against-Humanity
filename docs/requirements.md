# Cards Against Humanity Clone — Requirements

## 1. Overview

A cross-platform mobile application (iOS & Android) that replicates the core mechanics of Cards Against Humanity, supporting online multiplayer via random matchmaking or private rooms, and allowing players to extend the default card set with custom cards.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React Native (Expo) |
| Backend | FastAPI (Python) |
| Real-time | FastAPI WebSockets |
| Cache / Game State | Redis |
| Database | PostgreSQL (SQLAlchemy ORM) |
| Containerization | Docker + Docker Compose |

---

## 3. Functional Requirements

### 3.1 Authentication & Accounts

- **FR-AUTH-01** Players must register with a username and password. Email is optional but, if provided, must be unique and can be used for account recovery.
- **FR-AUTH-02** Players must be able to log in (via username or email) and log out.
- **FR-AUTH-03** Sessions are managed via JWT tokens (access token + refresh token). Tokens expire after 24 hours.
- **FR-AUTH-04** Players may update their username, email, and password.
- **FR-AUTH-05** _(Post-MVP)_ Third-party OAuth providers (Google, Apple, etc.) will be supported. The OAuth flow will exchange the provider token for an internal JWT, keeping the auth layer consistent. OAuth users without a password will be flagged accordingly; username remains required.

---

### 3.2 Card Management

- **FR-CARD-01** The system ships with a default deck of Black Cards (prompts) and White Cards (answers).
- **FR-CARD-02** A player can create custom White Cards (answers) to be added to their personal library.
- **FR-CARD-03** A player can create custom Black Cards (prompts) to be added to their personal library.
- **FR-CARD-04** Custom cards are owned by the player who created them.
- **FR-CARD-05** The card pool used in a game is determined by the host's configuration (see FR-MATCH-04). Custom cards are mixed into the same shared draw pile as default cards.
- **FR-CARD-06** Custom cards are visible only to their owner and game participants in rooms where they are enabled.
- **FR-CARD-07** A player can edit or delete their own custom cards (only when not in an active game).

---

### 3.3 Matchmaking & Lobbies

- **FR-MATCH-01** A player can queue for **random matchmaking**.
- **FR-MATCH-02** A player can create a **private room** protected by a 6-character alphanumeric password.
- **FR-MATCH-03** A player can join a private room by entering its password.
- **FR-MATCH-04** The room creator (host) can configure the following before the game starts:
  - Maximum number of players (3–10)
  - Points needed to win (default: 8)
  - Round timer duration (30–180 seconds, default 90)
  - **Card pool mode** — one of:
    - `default_only` — only the built-in default deck is used
    - `host_custom_only` — only the host's custom cards are used (no default deck)
    - `host_custom_mixed` — the host's custom cards are merged with the default deck
    - `all_custom_only` — every player's custom cards are pooled together (no default deck)
    - `all_custom_mixed` — every player's custom cards are merged with the default deck
- **FR-MATCH-05** The host can start the game once at least 3 players are in the lobby.
- **FR-MATCH-06** Players in the lobby see a live list of connected players.
- **FR-MATCH-07** If the host leaves the lobby, host privileges transfer to the next player in join order.

Random matchmaking flow:

- **FR-MATCH-08** When random matchmaking reaches 3 players, the system creates a random-match room and starts a 10-second fill countdown.
- **FR-MATCH-09** If an additional player joins during the 10-second window and the room has fewer than 10 players, the player is added and the countdown resets to 10 seconds.
- **FR-MATCH-10** The random-match game starts when either:
  - Countdown expires with 3–9 players, or
  - Player count reaches 10 (immediate start).
- **FR-MATCH-11** If player count drops below 3 during the countdown, the countdown is canceled and only restarts after the room returns to at least 3 players.
- **FR-MATCH-12** Random-match rooms use system defaults and are not host-configurable.

---

### 3.4 Gameplay

The game follows standard Cards Against Humanity rules:

- **FR-GAME-01** At the start of each round, all players are dealt White Cards until they hold 10 in hand.
- **FR-GAME-02** One player is designated the **Card Czar** each round, rotating in join order.
- **FR-GAME-03** The Card Czar draws a Black Card and it is displayed to all players.
- **FR-GAME-04** All non-Czar players select the number of White Cards required by the Black Card (1 or 2, as indicated by blank slots) and submit them anonymously.
- **FR-GAME-05** Once all players have submitted, the Card Czar sees all submitted responses in shuffled, anonymous order.
- **FR-GAME-06** The Card Czar selects the winning response.
- **FR-GAME-07** The winner of the round is revealed and awarded 1 point (one "Awesome Point").
- **FR-GAME-08** The winning White Cards are added to the winner's "trophies" for the session.
- **FR-GAME-09** Played White Cards are discarded. Players draw back up to 10 cards at the start of the next round.
- **FR-GAME-10** The game ends when a player reaches the configured winning point threshold.
- **FR-GAME-11** A final scoreboard is displayed at the end of the game showing all players, points, and notable winning combos.
- **FR-GAME-12** A player who disconnects mid-game is given a 60-second reconnection window. If they do not reconnect, they are removed and their hand is discarded.
- **FR-GAME-13** If a player disconnects during their Czar turn, the round is skipped and the Czar role passes to the next player.

---

### 3.5 Real-time Communication

- **FR-RT-01** All game state changes (card draws, submissions, Czar selection, score updates) are pushed to all players in the room via WebSocket.
- **FR-RT-02** The lobby shows real-time player join/leave events.
- **FR-RT-03** A round timer (configurable, default 90 seconds) triggers automatic submission of whatever cards a player has selected (or a random card if none selected) when it expires.
- **FR-RT-04** Random-match lobbies push countdown lifecycle events in real time (countdown started, reset, canceled, and locked/start).

---

## 4. Non-Functional Requirements

- **NFR-01 Performance:** The backend must support at least 50 concurrent game rooms.
- **NFR-02 Latency:** WebSocket events must be delivered within 300ms under normal network conditions.
- **NFR-03 Availability:** The service should target 99.5% uptime.
- **NFR-04 Security:** Passwords are hashed with bcrypt. JWT access tokens expire after 24 hours; refresh tokens after 30 days. Room passwords are not stored in plaintext. OAuth provider tokens are never persisted — only the derived internal JWT is stored client-side.
- **NFR-05 Scalability:** Redis is used for shared game state to allow horizontal scaling of backend instances.
- **NFR-06 Platform:** The mobile app must run on iOS 16+ and Android 10+.
- **NFR-07 Accessibility:** Text must meet WCAG AA contrast ratios. Cards must support dynamic font sizes.
- **NFR-08 Containerization:** All backend services (API, PostgreSQL, Redis, worker processes) must run via Docker Compose in development, testing, and CI.
- **NFR-09 Reproducible Build:** The project must provide a single containerized workflow for setup, migrations, test execution, and local startup to minimize host-environment drift.

---

## 5. Out of Scope (v1)

- Spectator mode
- Voice/video chat
- In-app purchases or monetization
- Card sharing / marketplace between players
- Web browser client
- Localization / multi-language support
- AI/bot players
- Third-party OAuth login (Google, Apple) — planned for v2, fully compatible with current JWT architecture

---

## 6. Data Models (High Level)

### User
| Field | Type | Notes |
|---|---|---|
| id | UUID | |
| username | string (unique) | |
| email | string (unique, nullable) | Optional; required only for account recovery |
| password_hash | string (nullable) | Null for OAuth-only accounts (post-MVP) |
| auth_provider | enum (nullable) | `google` / `apple` / null — post-MVP |
| created_at | timestamp | |

### Card
| Field | Type | Notes |
|---|---|---|
| id | UUID | |
| type | enum | `black` / `white` |
| text | string | Blanks represented as `_` |
| pick | int | Number of white cards required (black cards only, default 1) |
| owner_id | UUID (nullable) | null = default deck card |
| is_default | bool | |

### Room
| Field | Type |
|---|---|
| id | UUID |
| code | string (6 chars) |
| password_hash | string (nullable, private rooms only) |
| host_id | UUID (nullable for random rooms until assignment) |
| room_kind | enum: `private` / `random` |
| status | enum: `lobby` / `matchmaking_lobby` / `in_progress` / `finished` |
| max_players | int |
| winning_score | int |
| round_timer_seconds | int |
| card_pool_mode | enum: `default_only` / `host_custom_only` / `host_custom_mixed` / `all_custom_only` / `all_custom_mixed` |
| matchmaking_fill_expires_at | timestamp (nullable, random rooms only) |
| created_at | timestamp |

### RoomPlayer
| Field | Type |
|---|---|
| id | UUID |
| room_id | UUID |
| player_id | UUID |
| join_order | int |
| score | int |
| is_connected | bool |

### GameRound
| Field | Type |
|---|---|
| id | UUID |
| room_id | UUID |
| round_number | int |
| czar_id | UUID |
| black_card_id | UUID |
| status | enum: `waiting` / `judging` / `complete` |

### Submission
| Field | Type |
|---|---|
| id | UUID |
| round_id | UUID |
| player_id | UUID |
| white_card_ids | UUID[] |
| is_winner | bool |
