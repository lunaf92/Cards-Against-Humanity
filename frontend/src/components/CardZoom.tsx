import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { playSound } from '../sound/sfx'

export interface ZoomItem {
  key: string
  render: (active: boolean) => ReactNode
}

interface Props {
  items: ZoomItem[]
  startIndex: number
  onClose: () => void
  // Action area under the card, for the card currently in view.
  renderActions: (index: number) => ReactNode
  header?: ReactNode
}

// Full-screen tap-to-zoom viewer: one big card at a time, swipe (scroll-snap) to browse the rest.
export function CardZoom({ items, startIndex, onClose, renderActions, header }: Props) {
  const track = useRef<HTMLDivElement>(null)
  const [index, setIndex] = useState(startIndex)

  useEffect(() => playSound('zoom', 0.6), [])

  useLayoutEffect(() => {
    const el = track.current
    if (!el) return
    el.scrollLeft = startIndex * el.clientWidth
  }, [startIndex])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight') go(index + 1)
      if (e.key === 'ArrowLeft') go(index - 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // Keep the index valid if the list shrinks (e.g. a played card leaves the hand).
  useEffect(() => {
    if (items.length === 0) onClose()
    else if (index > items.length - 1) setIndex(items.length - 1)
  }, [items.length, index, onClose])

  function go(i: number) {
    const el = track.current
    if (!el || i < 0 || i >= items.length) return
    el.scrollTo({ left: i * el.clientWidth, behavior: 'smooth' })
  }

  function onScroll() {
    const el = track.current
    if (!el || el.clientWidth === 0) return
    setIndex(Math.round(el.scrollLeft / el.clientWidth))
  }

  return (
    <div className="zoom" role="dialog" aria-modal="true">
      <div className="zoom-backdrop" onClick={onClose} />
      <div className="zoom-top">
        {header}
        <button className="btn ghost small zoom-close" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>
      <div className="zoom-track" ref={track} onScroll={onScroll}>
        {items.map((item, i) => (
          <div className="zoom-slide" key={item.key} onClick={(e) => e.target === e.currentTarget && onClose()}>
            {item.render(i === index)}
          </div>
        ))}
      </div>
      {items.length > 1 && (
        <div className="zoom-nav">
          <button className="btn round" onClick={() => go(index - 1)} disabled={index === 0} aria-label="Previous card">
            ‹
          </button>
          <span className="dots" aria-label={`Card ${index + 1} of ${items.length}`}>
            {items.map((item, i) => (
              <span key={item.key} className={i === index ? 'dot on' : 'dot'} />
            ))}
          </span>
          <button
            className="btn round"
            onClick={() => go(index + 1)}
            disabled={index === items.length - 1}
            aria-label="Next card"
          >
            ›
          </button>
        </div>
      )}
      <div className="zoom-actions">{items[index] ? renderActions(index) : null}</div>
    </div>
  )
}
