import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { deckShareUrl, decksApi } from '../api/endpoints'
import type { DeckCard, DeckDetail } from '../api/types'
import { Card } from '../components/Card'
import { useAuthStore } from '../stores/authStore'

type Tab = 'black' | 'white'

// One deck: rename, public/private, share link, co-editors, and its cards split into black and white tabs.
export default function DeckPage() {
  const { deckId = '' } = useParams()
  const navigate = useNavigate()
  const meId = useAuthStore((s) => s.user?.id)
  const [deck, setDeck] = useState<DeckDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('black')
  const [editing, setEditing] = useState<DeckCard | null>(null)
  const [copied, setCopied] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const load = useCallback(() => {
    decksApi
      .get(deckId)
      .then(setDeck)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Could not load the deck'))
  }, [deckId])
  useEffect(load, [load])

  async function run(action: () => Promise<unknown>, reload = true) {
    setError(null)
    try {
      await action()
      if (reload) load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    }
  }

  if (!deck) {
    return (
      <main className="screen center stack">
        {error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}
        <Link className="btn ghost" to="/decks">
          ← My decks
        </Link>
      </main>
    )
  }

  const cards = deck.cards.filter((c) => c.type === tab)

  async function share() {
    let code = deck!.share_code
    if (!code) {
      code = (await decksApi.share(deck!.id)).share_code
      load()
    }
    const url = deckShareUrl(code)
    try {
      if (navigator.share) await navigator.share({ title: deck!.name, text: `Help me build "${deck!.name}"`, url })
      else {
        await navigator.clipboard.writeText(url)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      }
    } catch {
      /* share sheet dismissed */
    }
  }

  async function copyDeck() {
    await run(async () => {
      const copy = await decksApi.copy(deck!.id)
      navigate(`/decks/${copy.id}`)
    }, false)
  }

  return (
    <main className="screen deck-page">
      <header className="topbar">
        <button className="btn ghost small" onClick={() => navigate('/decks')}>
          ← My decks
        </button>
        <span className="grow" />
        <button className="btn ghost small" onClick={() => void copyDeck()}>
          Make a copy
        </button>
      </header>

      <section className="panel stack">
        {deck.can_edit ? (
          <DeckName name={deck.name} onSave={(name) => run(() => decksApi.update(deck.id, { name }))} />
        ) : (
          <h2>{deck.name}</h2>
        )}
        <p className="muted">
          {deck.is_builtin ? 'Built-in pack' : deck.is_owner ? 'Your deck' : `By ${deck.owner_name ?? 'someone'}`}
          {deck.copied_from_name && ` · copied from ${deck.copied_from_name}`}
        </p>

        {deck.can_edit && (
          <>
            <label className="tick">
              <input
                type="checkbox"
                checked={deck.is_public}
                disabled={!deck.is_owner}
                onChange={(e) => {
                  const is_public = e.target.checked
                  setDeck({ ...deck, is_public })
                  void run(() => decksApi.update(deck.id, { is_public }))
                }}
              />
              <span>
                Public
                <span className="hint">
                  {deck.is_owner
                    ? 'Players can copy it after a game that used it.'
                    : 'Only the owner can change this.'}
                </span>
              </span>
            </label>

            <div className="share-box">
              <button className="btn secondary grow" onClick={() => void run(share, false)}>
                {copied ? 'Link copied!' : 'Share this deck'}
              </button>
              {deck.share_code && deck.is_owner && (
                <button className="btn ghost small" onClick={() => void run(() => decksApi.unshare(deck.id))}>
                  Turn off link
                </button>
              )}
            </div>
            <p className="hint">
              {deck.share_code
                ? 'Anyone with the link can add and edit cards.'
                : 'Sharing makes a link. Anyone who opens it can add and edit cards.'}
            </p>

            {deck.members.length > 0 && (
              <div className="members">
                <span className="muted">Editing with you</span>
                <ul>
                  {deck.members.map((m) => (
                    <li key={m.user_id} className="member">
                      <span>{m.user_id === meId ? 'You' : m.username}</span>
                      {(deck.is_owner || m.user_id === meId) && (
                        <button
                          className="btn ghost small"
                          onClick={() =>
                            void run(async () => {
                              await decksApi.removeMember(deck.id, m.user_id)
                              if (m.user_id === meId) navigate('/decks')
                            }, m.user_id !== meId)
                          }
                        >
                          {m.user_id === meId ? 'Leave' : 'Remove'}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </section>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <div className="tabs" role="tablist">
        {(['black', 'white'] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={tab === t ? 'tab on' : 'tab'}
            onClick={() => setTab(t)}
          >
            {t === 'black' ? 'Black' : 'White'} ({t === 'black' ? deck.black_count : deck.white_count})
          </button>
        ))}
      </div>

      {deck.can_edit && (
        <AddCard
          key={tab}
          type={tab}
          onAdd={(text) => run(() => decksApi.addCard(deck.id, tab, text))}
        />
      )}

      <div className="deck-grid">
        {cards.map((c) => (
          <Card
            key={c.id}
            kind={c.type}
            text={c.text}
            pick={c.pick}
            size="mini"
            onClick={deck.can_edit ? () => setEditing(c) : undefined}
          />
        ))}
        {cards.length === 0 && <p className="muted">No {tab} cards yet.</p>}
      </div>

      {deck.is_owner && (
        <button
          className={confirmDelete ? 'btn danger' : 'btn ghost'}
          onClick={() =>
            confirmDelete
              ? void run(async () => {
                  await decksApi.remove(deck.id)
                  navigate('/decks')
                }, false)
              : setConfirmDelete(true)
          }
          onBlur={() => setConfirmDelete(false)}
        >
          {confirmDelete ? 'Tap again to delete this deck' : 'Delete deck'}
        </button>
      )}

      {editing && (
        <EditCardSheet
          card={editing}
          onClose={() => setEditing(null)}
          onSave={(text) => run(() => decksApi.editCard(deck.id, editing.id, text)).then(() => setEditing(null))}
          onDelete={() => run(() => decksApi.removeCard(deck.id, editing.id)).then(() => setEditing(null))}
        />
      )}
    </main>
  )
}

function DeckName({ name, onSave }: { name: string; onSave: (name: string) => void }) {
  const [value, setValue] = useState(name)
  useEffect(() => setValue(name), [name])
  const save = () => {
    const trimmed = value.trim()
    if (trimmed && trimmed !== name) onSave(trimmed)
    else setValue(name)
  }
  return (
    <input
      className="deck-title-input"
      aria-label="Deck name"
      value={value}
      maxLength={100}
      onChange={(e) => setValue(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
    />
  )
}

function AddCard({ type, onAdd }: { type: Tab; onAdd: (text: string) => Promise<unknown> }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault()
    const value = text.trim()
    if (!value || busy) return
    setBusy(true)
    setText('')
    await onAdd(value)
    setBusy(false)
  }
  return (
    <form className={`add-card ${type}`} onSubmit={submit}>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={500}
        rows={2}
        placeholder={type === 'black' ? 'New prompt. Use ___ for each blank.' : 'New answer'}
        aria-label={type === 'black' ? 'New black card' : 'New white card'}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            e.currentTarget.form?.requestSubmit()
          }
        }}
      />
      <button className="btn primary" disabled={busy || !text.trim()}>
        Add
      </button>
    </form>
  )
}

function EditCardSheet({
  card,
  onClose,
  onSave,
  onDelete,
}: {
  card: DeckCard
  onClose: () => void
  onSave: (text: string) => void
  onDelete: () => void
}) {
  const [text, setText] = useState(card.text)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="sheet" role="dialog" aria-modal="true" aria-label="Edit card">
      <div className="zoom-backdrop" onClick={onClose} />
      <div className="sheet-body panel stack">
        <Card kind={card.type} text={text || ' '} size="medium" />
        <textarea
          className="edit-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={500}
          rows={3}
          aria-label="Card text"
          autoFocus
        />
        <div className="row">
          <button className="btn ghost" onClick={onDelete}>
            Delete
          </button>
          <button className="btn primary grow" disabled={!text.trim()} onClick={() => onSave(text)}>
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
