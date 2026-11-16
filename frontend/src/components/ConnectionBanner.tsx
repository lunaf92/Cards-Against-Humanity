import { useRoomStore } from '../stores/roomStore'

export function ConnectionBanner() {
  const status = useRoomStore((s) => s.socketStatus)
  if (status !== 'reconnecting') return null
  return (
    <div className="banner" role="status">
      Connection lost, reconnecting…
    </div>
  )
}
