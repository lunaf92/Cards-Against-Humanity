import { create } from 'zustand'
import type {
  GameSnapshot,
  Player,
  Room,
  StateSyncPayload,
  Submission,
  WSEnvelope,
  WSErrorPayload,
  WhiteCard,
} from '../api/types'
import { RoomSocket, type SocketStatus } from '../ws/roomSocket'

export interface RoundResult {
  round_id: string
  winner_player_id: string | null
  winning_submission_id: string | null
  winning_texts: string[]
  black_card_text: string | null
}

export interface GameOver {
  winner_player_id: string | null
  reason: string
  scoreboard: { player_id: string; score: number }[]
}

export interface Notice {
  id: number
  kind: 'info' | 'error'
  text: string
}

interface RoomState {
  roomId: string | null
  room: Room | null
  players: Player[]
  game: GameSnapshot | null
  socketStatus: SocketStatus
  fatalError: string | null
  countdownExpiresAt: string | null
  reconnectDeadlines: Record<string, string>
  lastResult: RoundResult | null
  gameOver: GameOver | null
  notices: Notice[]
  connect: (roomId: string) => void
  disconnect: () => void
  startGame: () => void
  submitCards: (cardIds: string[]) => void
  pickWinner: (submissionId: string) => void
  requestSync: () => void
  dismissNotice: (id: number) => void
  applyEvent: (event: WSEnvelope) => void
}

let socket: RoomSocket | null = null
let noticeSeq = 0

const initial = {
  roomId: null,
  room: null,
  players: [],
  game: null,
  socketStatus: 'closed' as SocketStatus,
  fatalError: null,
  countdownExpiresAt: null,
  reconnectDeadlines: {},
  lastResult: null,
  gameOver: null,
  notices: [],
}

function withScores(players: Player[], scores: { player_id: string; score: number }[] | undefined): Player[] {
  if (!scores) return players
  const byId = new Map(scores.map((s) => [s.player_id, s.score]))
  return players.map((p) => (byId.has(p.player_id) ? { ...p, score: byId.get(p.player_id)! } : p))
}

function patchPlayer(players: Player[], id: string, patch: Partial<Player>): Player[] {
  return players.map((p) => (p.player_id === id ? { ...p, ...patch } : p))
}

const ERROR_TEXT: Record<string, string> = {
  NOT_HOST: 'Only the host can do that.',
  INVALID_CARD_SELECTION: "Those cards can't be played.",
  DUPLICATE_SUBMISSION: 'You already played this round.',
  NOT_CZAR: 'Only the judge can pick the winner.',
}

export const useRoomStore = create<RoomState>((set, get) => {
  const notify = (kind: Notice['kind'], text: string) =>
    set((s) => ({ notices: [...s.notices.slice(-2), { id: ++noticeSeq, kind, text }] }))

  return {
    ...initial,

    connect(roomId) {
      if (socket && get().roomId === roomId) return
      socket?.stop()
      set({ ...initial, roomId })
      socket = new RoomSocket(roomId, {
        onEvent: (e) => get().applyEvent(e),
        onStatus: (socketStatus) => set({ socketStatus }),
        onFatal: (_code, reason) => set({ fatalError: reason }),
      })
      socket.start()
    },

    disconnect() {
      socket?.stop()
      socket = null
      set({ ...initial })
    },

    startGame: () => void socket?.send('lobby.start_game'),
    submitCards(cardIds) {
      const game = get().game
      if (!game) return
      socket?.send('game.submit_cards', { round_id: game.round_id, white_card_ids: cardIds })
    },
    pickWinner(submissionId) {
      const game = get().game
      if (!game) return
      socket?.send('game.pick_winner', { round_id: game.round_id, submission_id: submissionId })
    },
    requestSync: () => void socket?.send('room.state_sync.request'),
    dismissNotice: (id) => set((s) => ({ notices: s.notices.filter((n) => n.id !== id) })),

    // Fold one server event into local state; unknown events are ignored per protocol.
    applyEvent({ event, payload: raw }) {
      const p = raw as Record<string, unknown>
      const s = get()
      switch (event) {
        case 'room.state_sync': {
          const sync = raw as unknown as StateSyncPayload
          set({
            room: sync.room,
            players: sync.players,
            game: sync.game,
            countdownExpiresAt:
              sync.room.status === 'matchmaking_lobby' ? sync.room.matchmaking_fill_expires_at : null,
          })
          return
        }
        case 'room.player_joined': {
          const player = p.player as Player
          set({ players: [...s.players.filter((x) => x.player_id !== player.player_id), player] })
          return
        }
        case 'room.player_left':
          set({ players: patchPlayer(s.players, p.player_id as string, { is_connected: false }) })
          s.requestSync()
          return
        case 'room.host_changed':
          if (s.room) set({ room: { ...s.room, host_id: p.new_host_id as string } })
          return
        case 'room.config_updated':
          set({ room: { ...(s.room ?? {}), ...(p.room as Room) } })
          return
        case 'matchmaking.countdown_started':
        case 'matchmaking.countdown_reset':
          set({ countdownExpiresAt: p.expires_at as string })
          return
        case 'matchmaking.countdown_canceled':
          set({ countdownExpiresAt: null })
          return
        case 'matchmaking.locked':
          set({ countdownExpiresAt: null })
          s.requestSync()
          return
        case 'game.started':
          set({
            room: s.room ? { ...s.room, status: 'in_progress' } : s.room,
            players: withScores(s.players, p.players as GameOver['scoreboard']),
            lastResult: null,
            gameOver: null,
          })
          return
        case 'round.started':
          set({
            game: {
              round_id: p.round_id as string,
              round_number: p.round_number as number,
              czar_id: p.czar_id as string,
              black_card: p.black_card as GameSnapshot['black_card'],
              status: 'waiting',
              submitted_count: 0,
              required_count: s.game?.required_count ?? Math.max(0, s.players.length - 1),
              submitted_player_ids: [],
              has_submitted: false,
              hand: s.game?.hand ?? [],
              hand_cards: s.game?.hand_cards ?? [],
              phase_expires_at: (p.round_expires_at as string | null) ?? null,
            },
          })
          // The sync carries the exact required_count and the refilled hand.
          s.requestSync()
          return
        case 'player.hand': {
          const hand = p.hand as WhiteCard[]
          if (s.game && s.game.round_id === p.round_id) {
            set({ game: { ...s.game, hand_cards: hand, hand: hand.map((c) => c.id) } })
          }
          return
        }
        case 'round.submission_accepted': {
          if (!s.game || s.game.round_id !== p.round_id) return
          const playerId = p.player_id as string
          set({
            game: {
              ...s.game,
              submitted_count: p.submitted_count as number,
              required_count: p.required_count as number,
              submitted_player_ids: Array.from(new Set([...s.game.submitted_player_ids, playerId])),
            },
          })
          return
        }
        case 'round.judging':
          if (!s.game || s.game.round_id !== p.round_id) return s.requestSync()
          set({
            game: {
              ...s.game,
              status: 'judging',
              submissions: p.submissions as Submission[],
              phase_expires_at: (p.judging_expires_at as string | null) ?? null,
            },
          })
          return
        case 'round.timer_expired':
          notify('info', "Time's up! Cards were played automatically.")
          return
        case 'round.judging_expired':
          notify('info', 'The judge ran out of time, so a random winner was picked.')
          return
        case 'round.result': {
          const winning = s.game?.submissions?.find((x) => x.submission_id === p.winning_submission_id)
          set({
            players: withScores(s.players, p.scores as GameOver['scoreboard']),
            lastResult: {
              round_id: p.round_id as string,
              winner_player_id: (p.winner_player_id as string | null) ?? null,
              winning_submission_id: (p.winning_submission_id as string | null) ?? null,
              winning_texts: winning?.white_card_texts ?? [],
              black_card_text: s.game && s.game.round_id === p.round_id ? s.game.black_card.text : null,
            },
          })
          return
        }
        case 'game.over':
          set({
            room: s.room ? { ...s.room, status: 'finished' } : s.room,
            players: withScores(s.players, p.scoreboard as GameOver['scoreboard']),
            gameOver: raw as unknown as GameOver,
            game: null,
          })
          return
        case 'player.reconnect_window_started':
          set({
            players: patchPlayer(s.players, p.player_id as string, { is_connected: false }),
            reconnectDeadlines: { ...s.reconnectDeadlines, [p.player_id as string]: p.expires_at as string },
          })
          return
        case 'player.reconnected': {
          const rest = { ...s.reconnectDeadlines }
          delete rest[p.player_id as string]
          set({
            players: patchPlayer(s.players, p.player_id as string, { is_connected: true }),
            reconnectDeadlines: rest,
          })
          return
        }
        case 'player.removed_timeout': {
          const gone = s.players.find((x) => x.player_id === p.player_id)
          set({ players: s.players.filter((x) => x.player_id !== p.player_id) })
          if (gone) notify('info', `${gone.username} left the game.`)
          s.requestSync()
          return
        }
        case 'error': {
          const err = raw as unknown as WSErrorPayload
          if (err.code === 'INTERNAL_ERROR') s.requestSync()
          notify('error', ERROR_TEXT[err.code] ?? err.message)
          return
        }
        default:
          return
      }
    },
  }
})
