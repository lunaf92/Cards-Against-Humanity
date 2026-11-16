// Shapes mirror the backend's Pydantic schemas and docs/websocket-protocol.md.

export type RoomKind = 'private' | 'random'
export type RoomStatus = 'lobby' | 'matchmaking_lobby' | 'in_progress' | 'finished'

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface User {
  id: string
  username: string
  email: string | null
  created_at: string
}

export interface Player {
  player_id: string
  username: string
  join_order: number
  score: number
  is_connected: boolean
}

export interface Room {
  id: string
  code: string
  host_id: string | null
  room_kind: RoomKind
  status: RoomStatus
  max_players: number
  winning_score: number
  round_timer_seconds: number
  decks: RoomDeck[]
  matchmaking_fill_expires_at: string | null
}

export interface RoomDetails extends Room {
  created_at: string
  players: Player[]
}

export interface RoomConfig {
  max_players: number
  winning_score: number
  round_timer_seconds: number
  deck_ids: string[]
}

export interface RoomDeck {
  id: string
  name: string
  is_builtin: boolean
  is_public: boolean
  black_count: number
  white_count: number
}

export interface DeckSummary extends RoomDeck {
  is_owner: boolean
  // In the selection a room gets when nobody picks.
  is_default: boolean
}

export interface QueueResponse {
  queued: boolean
  queue_size: number
  matched_room_id: string | null
}

export interface WhiteCard {
  id: string
  text: string
}

export interface BlackCard {
  id: string
  text: string
  pick: number
}

export interface Submission {
  submission_id: string
  white_card_texts: string[]
}

export interface GameSnapshot {
  round_id: string
  round_number: number
  status: 'waiting' | 'judging'
  czar_id: string
  submitted_count: number
  required_count: number
  submitted_player_ids: string[]
  has_submitted: boolean
  black_card: BlackCard
  hand: string[]
  hand_cards: WhiteCard[]
  submissions?: Submission[]
  phase_expires_at: string | null
}

export interface StateSyncPayload {
  room: Room
  players: Player[]
  game: GameSnapshot | null
}

export interface WSEnvelope<P = Record<string, unknown>> {
  version: string
  event: string
  room_id: string
  message_id: string
  timestamp: string
  correlation_id: string | null
  payload: P
}

export interface WSErrorPayload {
  code: string
  message: string
  details?: Record<string, unknown>
}

export interface DeckCard {
  id: string
  type: 'black' | 'white'
  text: string
  pick: number
}

export interface DeckDetail extends RoomDeck {
  is_owner: boolean
  can_edit: boolean
  owner_name: string | null
  share_code: string | null
  copied_from_name: string | null
  members: { user_id: string; username: string }[]
  cards: DeckCard[]
}
