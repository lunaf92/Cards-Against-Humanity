---
name: websocket-game-state
description: WebSocket lifecycle, reconnect handling, event dispatch, and gameplay state management patterns for the Expo frontend.
---

# WebSocket & Game State Management

## When to Use

Use this skill when implementing or modifying the WebSocket connection lifecycle, dispatching or receiving game events, managing `gameStore` or `roomStore`, or building any screen that reacts to real-time server events.

## WebSocket Architecture

- One persistent WebSocket connection per joined room, opened on the Lobby screen and held open through gameplay.
- Connection is managed by a **custom hook**: `useWebSocket(roomId: string)`.
- The hook owns the socket reference, open/close lifecycle, and event dispatch into the store.
- Screens do not touch the socket directly; they read from the store and call store actions.

## Connection Lifecycle

```
User joins room
    ↓
useWebSocket opens socket: WS /ws/rooms/{room_id}?token={access_token}
    ↓
Socket receives events → dispatched into roomStore / gameStore
    ↓
User leaves room or navigates to auth stack
    ↓
useWebSocket closes socket cleanly
```

- Open the socket in a `useEffect` with a cleanup that calls `socket.close()`.
- Do not open a new socket on every render; guard with a ref.
- Token comes from `authStore`. If the access token is refreshed mid-session, close and reopen the socket with the new token.

## Reconnect Handling

The backend keeps a player in the room for **60 seconds** after disconnect before removing them. The frontend must:

1. Detect socket close (`onclose` event).
2. Start a visible countdown timer in the UI (reconnect banner).
3. Attempt reconnect with exponential backoff (1s → 2s → 4s → cap at 10s) within the 60-second window.
4. On successful reconnect, the server sends `game_state_sync`; merge it into `gameStore` as the authoritative restore point.
5. If the 60-second window expires with no successful reconnect, clear `gameStore` and navigate to home.

## Event Name Constants

Define all WebSocket event type strings in `src/constants/wsEvents.ts`. Never hardcode event strings in hooks or components.

```ts
// src/constants/wsEvents.ts
export const WS_EVENTS = {
  // Lobby
  ROOM_PLAYER_JOINED: 'room.player_joined',
  ROOM_PLAYER_LEFT: 'room.player_left',
  ROOM_HOST_CHANGED: 'room.host_changed',
  // Matchmaking
  MATCHMAKING_MATCH_FOUND: 'matchmaking.match_found',
  MATCHMAKING_COUNTDOWN_STARTED: 'matchmaking.countdown_started',
  MATCHMAKING_COUNTDOWN_RESET: 'matchmaking.countdown_reset',
  MATCHMAKING_COUNTDOWN_CANCELED: 'matchmaking.countdown_canceled',
  MATCHMAKING_LOCKED: 'matchmaking.locked',
  // Game
  GAME_STARTED: 'game.started',
  ROUND_STARTED: 'round.started',
  CARDS_SUBMITTED: 'game.cards_submitted',
  ROUND_JUDGE: 'round.judge',
  ROUND_RESULT: 'round.result',
  GAME_OVER: 'game.over',
  GAME_STATE_SYNC: 'game.state_sync',
  // Commands (outbound)
  CMD_START_GAME: 'START_GAME',
  CMD_SUBMIT_CARDS: 'SUBMIT_CARDS',
  CMD_PICK_WINNER: 'PICK_WINNER',
} as const;
```

## Store Responsibilities

### `roomStore`
- Holds: `roomId`, `players[]`, `hostId`, `status`, `matchmakingCountdownEndsAt`
- Updated by: lobby events (`player_joined`, `player_left`, `host_changed`) and matchmaking events.
- Reset on: leaving the room or navigating to home.

### `gameStore`
- Holds: `roundNumber`, `czarId`, `blackCard`, `hand[]`, `submissions[]`, `scores{}`, `phase` (`waiting_submissions` | `judging` | `round_result` | `game_over`)
- Updated by: `game.started`, `round.started`, `round.judge`, `round.result`, `game.over`, `game.state_sync`.
- `hand` is the player's private white cards — never shared with other players.
- Reset on: game over or leaving the room.

## Sending Commands

Outbound commands are plain JSON messages. Send via the socket ref held in `useWebSocket`:

```ts
sendCommand({ type: WS_EVENTS.CMD_SUBMIT_CARDS, card_ids: ['abc', 'def'] });
```

- Validate locally before sending (e.g. card count matches pick count) to avoid round-trip errors.
- Disable the Submit button after sending; re-enable only if an error event is received.

## Czar Timeout Behavior

The backend automatically skips a round when the active Czar disconnects and their reconnect window expires. The next `round.started` event is emitted automatically. The frontend must:

- Handle `round.started` at any time, including when the current phase is not `round_result`.
- Reset all submission and judging state when `round.started` arrives.
- Show a brief "Czar disconnected — next round" toast before the new round UI renders.

## Gameplay Phase State Machine

```
game.started
    ↓
round.started  →  phase = 'waiting_submissions'
    ↓ (all submitted or timer expires)
round.judge    →  phase = 'judging'
    ↓ (Czar picks winner)
round.result   →  phase = 'round_result'
    ↓ (win condition not met)
round.started  →  phase = 'waiting_submissions'  (loop)
    ↓ (win condition met)
game.over      →  phase = 'game_over'
```

The `phase` value in `gameStore` drives which gameplay sub-screen is shown. Use a single `GameScreen` component that renders conditionally based on `phase`.

## Timer Bar

- `round.started` includes `round_expires_at` (ISO timestamp from backend).
- Derive elapsed fraction client-side using `Date.now()` and a `setInterval` at 100ms.
- Do not trust client-side countdown as authoritative; it is display only.
- Cancel the interval when phase advances past `waiting_submissions`.

## Expected Validation

- Unit test the `useWebSocket` hook with a mocked WebSocket to confirm event dispatch and reconnect logic.
- Component test the GameScreen sub-states by injecting mock `gameStore` values.
- End-to-end: run backend via `docker compose up`, connect three test clients, and exercise the full round loop.
