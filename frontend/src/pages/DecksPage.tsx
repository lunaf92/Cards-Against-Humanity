import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { decksApi } from '../api/endpoints'
import type { DeckSummary } from '../api/types'

// "My decks": the decks you own or co-edit, plus starting a new one or joining a shared one.
export default function DecksPage() {
  const navigate = useNavigate()
  const [decks, setDecks] = useState<DeckSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<'none' | 'new' | 'join'>('none')
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    decksApi
      .usable()
      .then((list) => setDecks(list.filter((d) => !d.is_builtin)))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Could not load your decks'))
  }, [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const code = value.trim().split('/').pop() ?? ''
      const deck = mode === 'new' ? await decksApi.create(value.trim()) : await decksApi.join(code)
      navigate(`/decks/${deck.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
      setBusy(false)
    }
  }

  const open = (m: 'new' | 'join') => {
    setMode(m)
    setValue('')
    setError(null)
  }

  return (
    <main className="screen decks">
      <header className="topbar">
        <button className="btn ghost small" onClick={() => navigate('/')}>
          ← Home
        </button>
        <span className="grow center">
          <strong>My decks</strong>
        </span>
        <span className="topbar-spacer" />
      </header>

      {mode === 'none' ? (
        <div className="row">
          <button className="btn primary grow" onClick={() => open('new')}>
            New deck
          </button>
          <button className="btn secondary grow" onClick={() => open('join')}>
            Join a deck
          </button>
        </div>
      ) : (
        <form className="panel stack" onSubmit={submit}>
          <label className="field">
            <span>{mode === 'new' ? 'Deck name' : 'Share link or code'}</span>
            <input
              autoFocus
              value={value}
              onChange={(e) => setValue(e.target.value)}
              maxLength={mode === 'new' ? 100 : 200}
              required
            />
          </label>
          <div className="row">
            <button type="button" className="btn ghost" onClick={() => setMode('none')}>
              Cancel
            </button>
            <button className="btn primary grow" disabled={busy}>
              {mode === 'new' ? 'Create deck' : 'Join deck'}
            </button>
          </div>
        </form>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {decks === null && !error && <p className="muted center">Loading…</p>}
      {decks?.length === 0 && (
        <p className="muted center">No decks yet. Make one, or open a link a friend shared with you.</p>
      )}
      {decks && decks.length > 0 && (
        <ul className="deck-cards">
          {decks.map((d) => (
            <li key={d.id}>
              <Link to={`/decks/${d.id}`} className="panel deck-tile">
                <span className="deck-tile-name">{d.name}</span>
                <span className="muted">
                  {d.black_count} black · {d.white_count} white
                </span>
                <span className="badges">
                  <span className={d.is_public ? 'badge ok' : 'badge'}>{d.is_public ? 'Public' : 'Private'}</span>
                  {!d.is_owner && <span className="badge dark">Shared with you</span>}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}
