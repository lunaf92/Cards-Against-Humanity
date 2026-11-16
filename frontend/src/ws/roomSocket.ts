import { refreshAccessToken } from '../api/http'
import { tokenStorage } from '../api/tokenStorage'
import type { WSEnvelope } from '../api/types'

export type SocketStatus = 'connecting' | 'open' | 'reconnecting' | 'closed'

interface Handlers {
  onEvent: (event: WSEnvelope) => void
  onStatus: (status: SocketStatus) => void
  // Called for close codes that retrying cannot fix (not a member, no such room, signed out).
  onFatal: (code: number, reason: string) => void
}

const FATAL_CODES: Record<number, string> = {
  4403: 'You are not a member of this room.',
  4404: 'This room no longer exists.',
}
const PING_INTERVAL_MS = 25_000

// crypto.randomUUID only exists in secure contexts; plain-HTTP LAN hosting needs a fallback.
function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const b = crypto.getRandomValues(new Uint8Array(16))
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}
const MAX_BACKOFF_MS = 10_000

export function wsBaseUrl(): string {
  const configured = import.meta.env.VITE_WS_BASE as string | undefined
  if (configured) return configured
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}`
}

// One room channel with keepalive pings and automatic reconnect; the server re-sends a full
// room.state_sync on every connect, so a reconnect needs no client-side replay.
export class RoomSocket {
  private ws: WebSocket | null = null
  private pingTimer: number | undefined
  private retryTimer: number | undefined
  private attempts = 0
  private stopped = false
  private readonly roomId: string
  private readonly handlers: Handlers

  constructor(roomId: string, handlers: Handlers) {
    this.roomId = roomId
    this.handlers = handlers
  }

  start() {
    this.stopped = false
    this.open()
  }

  stop() {
    this.stopped = true
    window.clearTimeout(this.retryTimer)
    window.clearInterval(this.pingTimer)
    this.ws?.close(1000)
    this.ws = null
    this.handlers.onStatus('closed')
  }

  send(event: string, payload: Record<string, unknown> = {}): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false
    const message_id = newId()
    this.ws.send(
      JSON.stringify({
        version: 'v1',
        event,
        room_id: this.roomId,
        message_id,
        correlation_id: message_id,
        timestamp: new Date().toISOString(),
        payload,
      }),
    )
    return true
  }

  private open() {
    const token = tokenStorage.get()?.access_token
    if (!token) {
      this.handlers.onFatal(4401, 'Please sign in again.')
      return
    }
    this.handlers.onStatus(this.attempts === 0 ? 'connecting' : 'reconnecting')
    const ws = new WebSocket(`${wsBaseUrl()}/ws/rooms/${this.roomId}?token=${encodeURIComponent(token)}`)
    this.ws = ws

    ws.onopen = () => {
      this.attempts = 0
      this.handlers.onStatus('open')
      window.clearInterval(this.pingTimer)
      this.pingTimer = window.setInterval(
        () => this.send('client.ping', { sent_at: new Date().toISOString() }),
        PING_INTERVAL_MS,
      )
    }
    ws.onmessage = (msg) => {
      try {
        this.handlers.onEvent(JSON.parse(msg.data as string) as WSEnvelope)
      } catch {
        /* ignore malformed frames */
      }
    }
    ws.onclose = (ev) => {
      window.clearInterval(this.pingTimer)
      if (this.ws !== ws || this.stopped) return
      this.ws = null
      if (FATAL_CODES[ev.code]) {
        this.stopped = true
        this.handlers.onStatus('closed')
        this.handlers.onFatal(ev.code, FATAL_CODES[ev.code])
        return
      }
      void this.scheduleRetry(ev.code === 4401)
    }
  }

  private async scheduleRetry(authFailed: boolean) {
    if (authFailed) {
      const fresh = await refreshAccessToken()
      if (!fresh) {
        this.stopped = true
        this.handlers.onStatus('closed')
        this.handlers.onFatal(4401, 'Your session expired. Please sign in again.')
        return
      }
    }
    this.handlers.onStatus('reconnecting')
    const delay = Math.min(MAX_BACKOFF_MS, 500 * 2 ** this.attempts)
    this.attempts += 1
    this.retryTimer = window.setTimeout(() => {
      if (!this.stopped) this.open()
    }, delay)
  }
}
