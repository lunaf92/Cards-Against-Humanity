import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { WSEnvelope } from '../api/types'
import { useRoomStore } from './roomStore'

const ROOM = {
  id: 'r1', code: 'ABC123', host_id: 'u1', room_kind: 'private' as const, status: 'lobby' as const,
  max_players: 10, winning_score: 8, round_timer_seconds: 90, card_pool_mode: 'default_only',
  matchmaking_fill_expires_at: null,
}
const players = ['u1', 'u2', 'u3'].map((id, i) => ({
  player_id: id, username: `p${i + 1}`, join_order: i + 1, score: 0, is_connected: true,
}))

function ev(event: string, payload: unknown): WSEnvelope {
  return { version: 'v1', event, room_id: 'r1', message_id: 'm', timestamp: '', correlation_id: null, payload: payload as Record<string, unknown> }
}

describe('roomStore.applyEvent', () => {
  beforeEach(() => {
    useRoomStore.getState().disconnect()
    useRoomStore.getState().applyEvent(ev('room.state_sync', { room: ROOM, players, game: null }))
  })

  it('plays a round from start to result', () => {
    const apply = useRoomStore.getState().applyEvent
    apply(ev('game.started', { players: players.map((p) => ({ player_id: p.player_id, score: 0 })) }))
    apply(ev('round.started', {
      round_id: 'rd1', round_number: 1, czar_id: 'u1',
      black_card: { id: 'b', text: 'Why ___?', pick: 1 }, round_expires_at: '2030-01-01T00:00:00Z',
    }))
    apply(ev('player.hand', { round_id: 'rd1', hand: [{ id: 'w1', text: 'Cats' }] }))
    let s = useRoomStore.getState()
    expect(s.room?.status).toBe('in_progress')
    expect(s.game?.hand_cards).toEqual([{ id: 'w1', text: 'Cats' }])
    expect(s.game?.required_count).toBe(2)

    apply(ev('round.submission_accepted', { round_id: 'rd1', player_id: 'u2', submitted_count: 1, required_count: 2 }))
    expect(useRoomStore.getState().game?.submitted_player_ids).toEqual(['u2'])

    apply(ev('round.judging', {
      round_id: 'rd1', judging_expires_at: null,
      submissions: [{ submission_id: 's1', white_card_texts: ['Cats'] }],
    }))
    expect(useRoomStore.getState().game?.status).toBe('judging')

    apply(ev('round.result', {
      round_id: 'rd1', winner_player_id: 'u2', winning_submission_id: 's1',
      scores: [{ player_id: 'u2', score: 1 }],
    }))
    s = useRoomStore.getState()
    expect(s.lastResult?.winning_texts).toEqual(['Cats'])
    expect(s.players.find((p) => p.player_id === 'u2')?.score).toBe(1)
  })

  it('tracks host changes, config updates and removals', () => {
    const apply = useRoomStore.getState().applyEvent
    apply(ev('room.host_changed', { previous_host_id: 'u1', new_host_id: 'u2' }))
    apply(ev('room.config_updated', { room: { ...ROOM, host_id: 'u2', winning_score: 5 } }))
    apply(ev('player.removed_timeout', { player_id: 'u3', reason: 'reconnect_timeout' }))
    const s = useRoomStore.getState()
    expect(s.room?.host_id).toBe('u2')
    expect(s.room?.winning_score).toBe(5)
    expect(s.players.map((p) => p.player_id)).toEqual(['u1', 'u2'])
    expect(s.notices.at(-1)?.text).toContain('p3')
  })

  it('ends the game on game.over', () => {
    useRoomStore.getState().applyEvent(ev('game.over', {
      winner_player_id: null, reason: 'not_enough_players', scoreboard: [{ player_id: 'u1', score: 2 }],
    }))
    const s = useRoomStore.getState()
    expect(s.room?.status).toBe('finished')
    expect(s.gameOver?.reason).toBe('not_enough_players')
    expect(s.game).toBeNull()
  })

  it('shows a reaction bubble per player and hides it after a while', () => {
    vi.useFakeTimers()
    const apply = useRoomStore.getState().applyEvent
    apply(ev('room.reaction', { player_id: 'u2', reaction_id: 'oh_come_on' }))
    expect(useRoomStore.getState().reactions.u2?.reaction_id).toBe('oh_come_on')
    vi.advanceTimersByTime(3000)
    expect(useRoomStore.getState().reactions.u2).toBeUndefined()
    vi.useRealTimers()
  })

  it('does not toast rate-limit errors', () => {
    const before = useRoomStore.getState().notices.length
    useRoomStore.getState().applyEvent(ev('error', { code: 'RATE_LIMITED', message: 'slow down' }))
    expect(useRoomStore.getState().notices.length).toBe(before)
  })
})
