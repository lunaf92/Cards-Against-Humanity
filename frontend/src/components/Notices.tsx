import { useEffect } from 'react'
import { useRoomStore } from '../stores/roomStore'

// Short-lived toasts for server errors and timer events.
export function Notices() {
  const notices = useRoomStore((s) => s.notices)
  const dismiss = useRoomStore((s) => s.dismissNotice)

  useEffect(() => {
    if (notices.length === 0) return
    const oldest = notices[0]
    const id = window.setTimeout(() => dismiss(oldest.id), 3500)
    return () => window.clearTimeout(id)
  }, [notices, dismiss])

  return (
    <div className="notices" aria-live="polite">
      {notices.map((n) => (
        <button key={n.id} className={`notice ${n.kind}`} onClick={() => dismiss(n.id)}>
          {n.text}
        </button>
      ))}
    </div>
  )
}
