import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { roomsApi } from '../api/endpoints'
import type { RoomDetails } from '../api/types'
import { Logo } from '../components/Logo'
import { useAuthStore } from '../stores/authStore'

type Panel = 'menu' | 'create' | 'join' | 'queue'
const QUEUE_POLL_MS = 2500

export default function HomePage() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const [panel, setPanel] = useState<Panel>('menu')
  const [active, setActive] = useState<RoomDetails | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Offer to jump back into an unfinished room (page reload, closed tab).
  useEffect(() => {
    roomsApi
      .active()
      .then((r) => setActive(r.room))
      .catch(() => setActive(null))
  }, [])

  const goTo = useCallback((roomId: string) => navigate(`/room/${roomId}`), [navigate])

  return (
    <main className="screen home">
      <header className="topbar">
        <Logo small />
        <div className="topbar-user">
          <span>{user?.username}</span>
          <button className="btn ghost small" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </header>

      {active && panel === 'menu' && (
        <button className="panel resume" onClick={() => goTo(active.id)}>
          <strong>Back to your game</strong>
          <span className="muted">
            Room {active.code} · {active.players.length} players
          </span>
        </button>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {panel === 'menu' && (
        <div className="menu stack">
          <button className="btn primary big" onClick={() => setPanel('create')}>
            Create a private room
          </button>
          <button className="btn secondary big" onClick={() => setPanel('join')}>
            Join with a code
          </button>
          <button className="btn ghost big" onClick={() => setPanel('queue')}>
            Play with strangers
          </button>
        </div>
      )}
      {panel === 'create' && <CreateRoom onBack={() => setPanel('menu')} onDone={goTo} onError={setError} />}
      {panel === 'join' && <JoinRoom onBack={() => setPanel('menu')} onDone={goTo} onError={setError} />}
      {panel === 'queue' && <Queue onBack={() => setPanel('menu')} onDone={goTo} onError={setError} />}
    </main>
  )
}

interface PanelProps {
  onBack: () => void
  onDone: (roomId: string) => void
  onError: (msg: string | null) => void
}

function CreateRoom({ onBack, onDone, onError }: PanelProps) {
  const [password, setPassword] = useState('')
  const [winningScore, setWinningScore] = useState(8)
  const [timer, setTimer] = useState(90)
  const [maxPlayers, setMaxPlayers] = useState(10)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    onError(null)
    setBusy(true)
    try {
      const room = await roomsApi.create(password, {
        winning_score: winningScore,
        round_timer_seconds: timer,
        max_players: maxPlayers,
      })
      onDone(room.id)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Could not create the room')
      setBusy(false)
    }
  }

  return (
    <form className="panel stack" onSubmit={submit}>
      <h2>New private room</h2>
      <label className="field">
        <span>Room password</span>
        <input value={password} onChange={(e) => setPassword(e.target.value)} minLength={4} required />
      </label>
      <p className="hint">Friends join with the room code and this password.</p>
      <Stepper label="Points to win" value={winningScore} min={3} max={20} onChange={setWinningScore} />
      <Stepper label="Seconds per round" value={timer} min={30} max={300} step={15} onChange={setTimer} />
      <Stepper label="Max players" value={maxPlayers} min={3} max={10} onChange={setMaxPlayers} />
      <div className="row">
        <button type="button" className="btn ghost" onClick={onBack}>
          Back
        </button>
        <button className="btn primary grow" disabled={busy}>
          Create room
        </button>
      </div>
    </form>
  )
}

function JoinRoom({ onBack, onDone, onError }: PanelProps) {
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    onError(null)
    setBusy(true)
    try {
      const room = await roomsApi.join(code.trim(), password)
      onDone(room.id)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Could not join the room')
      setBusy(false)
    }
  }

  return (
    <form className="panel stack" onSubmit={submit}>
      <h2>Join a room</h2>
      <label className="field">
        <span>Room code</span>
        <input
          className="code-input"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))}
          maxLength={6}
          minLength={6}
          autoCapitalize="characters"
          autoComplete="off"
          required
        />
      </label>
      <label className="field">
        <span>Password</span>
        <input value={password} onChange={(e) => setPassword(e.target.value)} required />
      </label>
      <div className="row">
        <button type="button" className="btn ghost" onClick={onBack}>
          Back
        </button>
        <button className="btn primary grow" disabled={busy}>
          Join
        </button>
      </div>
    </form>
  )
}

// Matchmaking: enqueue once, then poll /rooms/active until the server places us in a room.
function Queue({ onBack, onDone, onError }: PanelProps) {
  const [queueSize, setQueueSize] = useState<number | null>(null)
  const done = useRef(false)

  useEffect(() => {
    let timer: number | undefined
    let cancelled = false
    const poll = async () => {
      try {
        const { room } = await roomsApi.active()
        if (room && room.room_kind === 'random' && !cancelled) {
          done.current = true
          onDone(room.id)
          return
        }
      } catch {
        /* keep polling */
      }
      if (!cancelled) timer = window.setTimeout(poll, QUEUE_POLL_MS)
    }
    roomsApi
      .queue()
      .then((res) => {
        if (cancelled) return
        setQueueSize(res.queue_size)
        if (res.matched_room_id) {
          done.current = true
          onDone(res.matched_room_id)
        } else timer = window.setTimeout(poll, QUEUE_POLL_MS)
      })
      .catch((err) => onError(err instanceof Error ? err.message : 'Could not join the queue'))
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      if (!done.current) void roomsApi.leaveQueue().catch(() => undefined)
    }
  }, [onDone, onError])

  return (
    <div className="panel stack center">
      <div className="spinner" aria-hidden />
      <h2>Looking for players…</h2>
      <p className="muted">
        {queueSize === null ? 'Joining the queue' : `${queueSize} waiting. A game starts once 3 players are found.`}
      </p>
      <button className="btn ghost" onClick={onBack}>
        Cancel
      </button>
    </div>
  )
}

export function Stepper({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  disabled,
}: {
  label: string
  value: number
  min: number
  max: number
  step?: number
  onChange: (v: number) => void
  disabled?: boolean
}) {
  return (
    <div className="stepper">
      <span>{label}</span>
      <div className="stepper-controls">
        <button
          type="button"
          className="btn round"
          aria-label={`Decrease ${label}`}
          disabled={disabled || value <= min}
          onClick={() => onChange(Math.max(min, value - step))}
        >
          −
        </button>
        <output aria-label={label}>{value}</output>
        <button
          type="button"
          className="btn round"
          aria-label={`Increase ${label}`}
          disabled={disabled || value >= max}
          onClick={() => onChange(Math.min(max, value + step))}
        >
          +
        </button>
      </div>
    </div>
  )
}
