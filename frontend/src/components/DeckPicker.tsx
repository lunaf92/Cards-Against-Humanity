import { useState } from 'react'
import type { DeckSummary } from '../api/types'

const HAND_SIZE = 10

interface Props {
  decks: DeckSummary[]
  selected: string[]
  onChange: (ids: string[]) => void
  // Players the deck has to deal for; at least 3.
  players: number
  disabled?: boolean
}

// Collapsible list of deck checkboxes with card counts and a "big enough?" check.
export function DeckPicker({ decks, selected, onChange, players, disabled }: Props) {
  const [open, setOpen] = useState(false)
  const chosen = decks.filter((d) => selected.includes(d.id))
  const black = chosen.reduce((n, d) => n + d.black_count, 0)
  const white = chosen.reduce((n, d) => n + d.white_count, 0)
  const needWhite = Math.max(3, players) * HAND_SIZE
  const tooSmall = black < 1 || white < needWhite

  const toggle = (id: string) => {
    const next = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]
    if (next.length > 0) onChange(next)
  }
  const builtin = decks.filter((d) => d.is_builtin)
  const own = decks.filter((d) => !d.is_builtin)
  const summary =
    chosen.length === 0
      ? 'No decks'
      : chosen.length === 1
        ? chosen[0].name
        : `${chosen[0].name} + ${chosen.length - 1} more`

  return (
    <div className="deck-picker">
      <button
        type="button"
        className="deck-summary"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="deck-summary-label">Decks</span>
        <span className="deck-summary-value">{summary}</span>
        <span className="muted">{open ? '▴' : '▾'}</span>
      </button>
      <p className={tooSmall ? 'hint error' : 'hint'}>
        {black} black · {white} white cards
        {tooSmall && ` · need at least 1 black and ${needWhite} white`}
      </p>
      {open && (
        <div className="deck-list">
          {!disabled && (
            <div className="row">
              <button type="button" className="btn ghost small" onClick={() => onChange(decks.map((d) => d.id))}>
                All
              </button>
              <button
                type="button"
                className="btn ghost small"
                onClick={() => onChange(decks.filter((d) => d.is_default).map((d) => d.id))}
              >
                Default
              </button>
            </div>
          )}
          <DeckGroup title="Built-in" decks={builtin} selected={selected} toggle={toggle} disabled={disabled} />
          {own.length > 0 && (
            <DeckGroup title="Your decks" decks={own} selected={selected} toggle={toggle} disabled={disabled} />
          )}
        </div>
      )}
    </div>
  )
}

function DeckGroup({
  title,
  decks,
  selected,
  toggle,
  disabled,
}: {
  title: string
  decks: DeckSummary[]
  selected: string[]
  toggle: (id: string) => void
  disabled?: boolean
}) {
  return (
    <fieldset className="deck-group" disabled={disabled}>
      <legend className="muted">{title}</legend>
      {decks.map((d) => (
        <label key={d.id} className="deck-row">
          <input type="checkbox" checked={selected.includes(d.id)} onChange={() => toggle(d.id)} />
          <span className="deck-name">
            {d.name}
            <span className="deck-counts muted">
              {d.black_count} black · {d.white_count} white
            </span>
          </span>
        </label>
      ))}
    </fieldset>
  )
}
