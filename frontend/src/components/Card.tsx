import type { ReactNode } from 'react'

interface Props {
  kind: 'black' | 'white'
  text: string
  size?: 'mini' | 'medium' | 'full' | 'wide'
  pick?: number
  badge?: ReactNode
  selected?: boolean
  dimmed?: boolean
  onClick?: () => void
  label?: string
}

// Render "___" blanks in prompts as a visible line the answer slots into.
function renderText(text: string) {
  const parts = text.split(/_{2,}/)
  if (parts.length === 1) return text
  return parts.flatMap((part, i) => (i === 0 ? [part] : [<span key={i} className="blank" />, part]))
}

export function Card({ kind, text, size = 'medium', pick, badge, selected, dimmed, onClick, label }: Props) {
  const className = ['card', kind, size, selected ? 'selected' : '', dimmed ? 'dimmed' : '', onClick ? 'tappable' : '']
    .filter(Boolean)
    .join(' ')
  const content = (
    <>
      <span className="card-text">{renderText(text)}</span>
      <span className="card-foot">
        <span className="card-mark" aria-hidden>
          ▰
        </span>
        {kind === 'black' && pick && pick > 1 ? <span className="pick">Pick {pick}</span> : null}
      </span>
      {badge !== undefined && badge !== null && <span className="card-badge">{badge}</span>}
    </>
  )
  if (onClick) {
    return (
      <button type="button" className={className} onClick={onClick} aria-label={label ?? text}>
        {content}
      </button>
    )
  }
  return <div className={className}>{content}</div>
}
