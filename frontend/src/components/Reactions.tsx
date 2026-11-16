import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import type { Player } from '../api/types'
import { REACTION_BY_ID, REACTIONS } from '../reactions'
import { useRoomStore } from '../stores/roomStore'
import { useSoundSettings } from '../sound/sfx'

// Speech-bubble button that opens the tray of quick reactions.
export function ReactionButton() {
  const [open, setOpen] = useState(false)
  const readyAt = useRoomStore((s) => s.reactionReadyAt)
  const cooling = useCooldown(readyAt)
  return (
    <>
      <button
        className={cooling ? 'btn ghost icon cooling' : 'btn ghost icon'}
        onClick={() => setOpen(true)}
        aria-label="Send a reaction"
      >
        💬
      </button>
      {open && createPortal(<ReactionTray onClose={() => setOpen(false)} />, document.body)}
    </>
  )
}

function useCooldown(readyAt: number): boolean {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (readyAt <= Date.now()) return
    const id = window.setTimeout(() => setNow(Date.now()), readyAt - Date.now() + 20)
    return () => window.clearTimeout(id)
  }, [readyAt])
  return readyAt > now
}

function ReactionTray({ onClose }: { onClose: () => void }) {
  const send = useRoomStore((s) => s.sendReaction)
  const readyAt = useRoomStore((s) => s.reactionReadyAt)
  const cooling = useCooldown(readyAt)
  const pick = (id: string) => {
    if (send(id)) onClose()
  }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="sheet" role="dialog" aria-modal="true" aria-label="Reactions">
      <div className="zoom-backdrop light" onClick={onClose} />
      <div className="sheet-body panel tray">
        <div className="tray-emojis">
          {REACTIONS.filter((r) => r.kind === 'emoji').map((r) => (
            <button key={r.id} className="tray-emoji" disabled={cooling} onClick={() => pick(r.id)} aria-label={r.id}>
              {r.label}
            </button>
          ))}
        </div>
        <div className="tray-phrases">
          {REACTIONS.filter((r) => r.kind === 'phrase').map((r) => (
            <button key={r.id} className="tray-phrase" disabled={cooling} onClick={() => pick(r.id)}>
              {r.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// The bubble that pops over a player for a couple of seconds after they react.
export function ReactionBubble({ playerId }: { playerId: string }) {
  const reaction = useRoomStore((s) => s.reactions[playerId])
  if (!reaction) return null
  const def = REACTION_BY_ID.get(reaction.reaction_id)
  if (!def) return null
  return (
    <span key={reaction.key} className={def.kind === 'emoji' ? 'bubble emoji' : 'bubble'} role="status">
      {def.label}
    </span>
  )
}

// Compact strip of everyone at the table: who's judging, who has played, scores, and reactions.
export function AvatarRow({
  players,
  meId,
  czarId,
  submittedIds,
}: {
  players: Player[]
  meId: string
  czarId?: string
  submittedIds: string[]
}) {
  const sorted = [...players].sort((a, b) => a.join_order - b.join_order)
  return (
    <ul className="avatar-row" aria-label="Players">
      {sorted.map((p) => {
        const classes = ['seat']
        if (!p.is_connected) classes.push('offline')
        if (p.player_id === czarId) classes.push('czar')
        if (submittedIds.includes(p.player_id)) classes.push('played')
        return (
          <li key={p.player_id} className={classes.join(' ')}>
            <ReactionBubble playerId={p.player_id} />
            <span className="seat-avatar" aria-hidden>
              {p.username.slice(0, 1).toUpperCase()}
              <span className="seat-score">{p.score}</span>
            </span>
            <span className="seat-name">{p.player_id === meId ? 'You' : p.username}</span>
          </li>
        )
      })}
    </ul>
  )
}

export function MuteButton() {
  const muted = useSoundSettings((s) => s.muted)
  const toggle = useSoundSettings((s) => s.toggle)
  return (
    <button className="btn ghost icon" onClick={toggle} aria-label={muted ? 'Turn sound on' : 'Mute sound'} aria-pressed={muted}>
      {muted ? '🔇' : '🔊'}
    </button>
  )
}
