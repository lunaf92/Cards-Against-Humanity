import { useEffect, useState } from 'react'

// Whole seconds left until an ISO deadline (server timestamps are UTC), ticking every 250 ms.
export function useCountdown(deadline: string | null | undefined): number | null {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!deadline) return
    const id = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(id)
  }, [deadline])
  if (!deadline) return null
  const iso = /[zZ]|[+-]\d\d:\d\d$/.test(deadline) ? deadline : `${deadline}Z`
  return Math.max(0, Math.ceil((Date.parse(iso) - now) / 1000))
}
