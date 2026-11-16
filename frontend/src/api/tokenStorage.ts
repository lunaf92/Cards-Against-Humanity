import type { TokenPair } from './types'

const KEY = 'cah.tokens'
type Listener = (tokens: TokenPair | null) => void
const listeners = new Set<Listener>()

// localStorage keeps players signed in across tab closes on their phones; every access is guarded
// because private browsing modes can throw.
export const tokenStorage = {
  get(): TokenPair | null {
    try {
      const raw = localStorage.getItem(KEY)
      return raw ? (JSON.parse(raw) as TokenPair) : null
    } catch {
      return null
    }
  },
  set(tokens: TokenPair) {
    try {
      localStorage.setItem(KEY, JSON.stringify(tokens))
    } catch {
      /* storage unavailable: session lasts for this page only */
    }
    listeners.forEach((l) => l(tokens))
  },
  clear() {
    try {
      localStorage.removeItem(KEY)
    } catch {
      /* ignore */
    }
    listeners.forEach((l) => l(null))
  },
  subscribe(listener: Listener) {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
}
