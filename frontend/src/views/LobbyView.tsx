import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { decksApi, roomsApi } from '../api/endpoints'
import type { DeckSummary, RoomConfig } from '../api/types'
import { DeckPicker } from '../components/DeckPicker'
import { useCountdown } from '../hooks/useCountdown'
import { useRoomStore } from '../stores/roomStore'
import { Stepper } from '../pages/HomePage'
import { PlayerList } from '../components/PlayerList'
import { MuteButton, ReactionButton } from '../components/Reactions'

const MIN_PLAYERS = 3

export default function LobbyView({ meId }: { meId: string }) {
  const navigate = useNavigate()
  const room = useRoomStore((s) => s.room)!
  const players = useRoomStore((s) => s.players)
  const startGame = useRoomStore((s) => s.startGame)
  const countdownExpiresAt = useRoomStore((s) => s.countdownExpiresAt)
  const secondsLeft = useCountdown(countdownExpiresAt)
  const [copied, setCopied] = useState(false)
  const [savingError, setSavingError] = useState<string | null>(null)

  const isHost = room.host_id === meId
  const isRandom = room.room_kind === 'random'
  const lockedRandom = isRandom && room.status === 'in_progress'
  const enough = players.length >= MIN_PLAYERS
  const canStart = isHost && enough && (!isRandom || lockedRandom)

  // The host picks from every deck they can use; everyone else just sees the room's decks.
  const [usable, setUsable] = useState<DeckSummary[] | null>(null)
  useEffect(() => {
    if (!isHost || isRandom) return
    let live = true
    decksApi
      .usable()
      .then((list) => live && setUsable(list))
      .catch(() => {})
    return () => {
      live = false
    }
  }, [isHost, isRandom])
  const roomDecks: DeckSummary[] = (room.decks ?? []).map((d) => ({ ...d, is_owner: false, is_default: false }))
  const deckChoices = isHost && usable ? usable : roomDecks

  async function saveConfig(patch: Partial<RoomConfig>) {
    setSavingError(null)
    try {
      await roomsApi.updateConfig(room.id, patch)
    } catch (err) {
      setSavingError(err instanceof Error ? err.message : 'Could not save')
    }
  }

  async function share() {
    const text = `Join my game! Code ${room.code}`
    try {
      if (navigator.share) await navigator.share({ title: 'Join my game', text, url: window.location.origin })
      else {
        await navigator.clipboard.writeText(room.code)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      }
    } catch {
      /* share sheet dismissed */
    }
  }

  return (
    <main className="screen lobby">
      <header className="topbar">
        <button className="btn ghost small" onClick={() => navigate('/')}>
          ← Home
        </button>
        <span className="muted grow center">{isRandom ? 'Random match' : 'Private room'}</span>
        <div className="top-actions">
          <MuteButton />
          <ReactionButton />
        </div>
      </header>

      {!isRandom && (
        <button className="room-code" onClick={() => void share()} aria-label="Share room code">
          <span className="muted">Room code</span>
          <strong>{room.code}</strong>
          <span className="hint">{copied ? 'Copied!' : 'Tap to share'}</span>
        </button>
      )}

      {isRandom && (
        <div className="panel center">
          {room.status === 'matchmaking_lobby' && secondsLeft !== null && (
            <p>
              Locking the lobby in <strong>{secondsLeft}s</strong>
            </p>
          )}
          {room.status === 'matchmaking_lobby' && secondsLeft === null && <p>Waiting for more players…</p>}
          {lockedRandom && <p>Lobby locked. {isHost ? 'Start whenever you are ready.' : 'Waiting for the host to start.'}</p>}
        </div>
      )}

      <section className="panel">
        <h2>
          Players <span className="muted">
            {players.length}/{room.max_players}
          </span>
        </h2>
        <PlayerList players={players} hostId={room.host_id} meId={meId} />
      </section>

      {!isRandom && (
        <section className="panel stack">
          <h2>Settings</h2>
          <Stepper
            label="Points to win"
            value={room.winning_score}
            min={3}
            max={20}
            disabled={!isHost}
            onChange={(v) => void saveConfig({ winning_score: v })}
          />
          <Stepper
            label="Seconds per round"
            value={room.round_timer_seconds}
            min={30}
            max={300}
            step={15}
            disabled={!isHost}
            onChange={(v) => void saveConfig({ round_timer_seconds: v })}
          />
          <Stepper
            label="Max players"
            value={room.max_players}
            min={Math.max(3, players.length)}
            max={10}
            disabled={!isHost}
            onChange={(v) => void saveConfig({ max_players: v })}
          />
          {deckChoices.length > 0 && (
            <DeckPicker
              decks={deckChoices}
              selected={roomDecks.map((d) => d.id)}
              onChange={(ids) => void saveConfig({ deck_ids: ids })}
              players={players.length}
              disabled={!isHost}
            />
          )}
          {!isHost && <p className="hint">Only the host can change settings.</p>}
          {savingError && <p className="error">{savingError}</p>}
        </section>
      )}

      <footer className="sticky-footer">
        {isHost ? (
          <button className="btn primary big" disabled={!canStart} onClick={startGame}>
            {enough ? 'Start game' : `Need ${MIN_PLAYERS - players.length} more to start`}
          </button>
        ) : (
          <p className="muted center">Waiting for the host to start the game…</p>
        )}
      </footer>
    </main>
  )
}
