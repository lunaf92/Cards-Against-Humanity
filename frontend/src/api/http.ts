import { tokenStorage } from './tokenStorage'
import type { TokenPair } from './types'

export const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Turn FastAPI's `detail` (string or validation list) into one readable sentence.
function describeError(body: unknown, status: number): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { loc?: unknown[]; msg?: string }
      const field = first.loc?.[first.loc.length - 1]
      return field ? `${String(field)}: ${first.msg}` : (first.msg ?? 'Invalid input')
    }
  }
  return `Request failed (${status})`
}

let refreshInFlight: Promise<string | null> | null = null

// Exchange the refresh token for a new access token; concurrent callers share one request.
export function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight
  const refresh = tokenStorage.get()?.refresh_token
  if (!refresh) return Promise.resolve(null)
  refreshInFlight = fetch(`${API_BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refresh }),
  })
    .then(async (res) => {
      if (!res.ok) {
        tokenStorage.clear()
        return null
      }
      const body = (await res.json()) as { access_token: string }
      const current = tokenStorage.get()
      if (current) tokenStorage.set({ ...current, access_token: body.access_token })
      return body.access_token
    })
    .catch(() => null)
    .finally(() => {
      refreshInFlight = null
    })
  return refreshInFlight
}

interface RequestOptions {
  method?: string
  body?: unknown
  auth?: boolean
}

// JSON fetch against the backend that attaches the bearer token and retries once after a refresh.
export async function api<T>(path: string, { method = 'GET', body, auth = true }: RequestOptions = {}): Promise<T> {
  const send = (token: string | undefined) =>
    fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(auth && token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })

  let res = await send(tokenStorage.get()?.access_token)
  // Missing bearer header comes back as 403 from FastAPI's HTTPBearer, expired as 401.
  if (auth && res.status === 401) {
    const fresh = await refreshAccessToken()
    if (fresh) res = await send(fresh)
  }

  if (res.status === 204) return undefined as T
  const text = await res.text()
  const parsed: unknown = text ? JSON.parse(text) : undefined
  if (!res.ok) {
    if (auth && res.status === 401) tokenStorage.clear()
    throw new ApiError(res.status, describeError(parsed, res.status))
  }
  return parsed as T
}

export type { TokenPair }
