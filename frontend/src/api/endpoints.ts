import { api } from './http'
import type { DeckCard, DeckDetail, DeckSummary, QueueResponse, RoomConfig, RoomDetails, TokenPair, User } from './types'

export const authApi = {
  register: (username: string, password: string) =>
    api<TokenPair>('/auth/register', { method: 'POST', body: { username, password }, auth: false }),
  login: (username_or_email: string, password: string) =>
    api<TokenPair>('/auth/login', { method: 'POST', body: { username_or_email, password }, auth: false }),
  logout: () => api<void>('/auth/logout', { method: 'POST' }),
  me: () => api<User>('/users/me'),
}

export const roomsApi = {
  create: (password: string, config: Partial<RoomConfig>) =>
    api<RoomDetails>('/rooms', { method: 'POST', body: { password, ...config } }),
  join: (code: string, password: string) =>
    api<RoomDetails>('/rooms/join', { method: 'POST', body: { code: code.toUpperCase(), password } }),
  get: (roomId: string) => api<RoomDetails>(`/rooms/${roomId}`),
  active: () => api<{ room: RoomDetails | null }>('/rooms/active'),
  updateConfig: (roomId: string, config: Partial<RoomConfig>) =>
    api<RoomDetails>(`/rooms/${roomId}/config`, { method: 'PATCH', body: config }),
  queue: () => api<QueueResponse>('/rooms/queue', { method: 'POST' }),
  leaveQueue: () => api<{ removed: boolean }>('/rooms/queue', { method: 'DELETE' }),
}

export const decksApi = {
  usable: () => api<DeckSummary[]>('/decks'),
  get: (id: string) => api<DeckDetail>(`/decks/${id}`),
  create: (name: string) => api<DeckDetail>('/decks', { method: 'POST', body: { name } }),
  update: (id: string, patch: { name?: string; is_public?: boolean }) =>
    api<DeckDetail>(`/decks/${id}`, { method: 'PATCH', body: patch }),
  remove: (id: string) => api<void>(`/decks/${id}`, { method: 'DELETE' }),
  addCard: (id: string, type: DeckCard['type'], text: string) =>
    api<DeckCard>(`/decks/${id}/cards`, { method: 'POST', body: { type, text } }),
  editCard: (id: string, cardId: string, text: string) =>
    api<DeckCard>(`/decks/${id}/cards/${cardId}`, { method: 'PATCH', body: { text } }),
  removeCard: (id: string, cardId: string) => api<void>(`/decks/${id}/cards/${cardId}`, { method: 'DELETE' }),
  share: (id: string) => api<{ share_code: string }>(`/decks/${id}/share`, { method: 'POST' }),
  unshare: (id: string) => api<void>(`/decks/${id}/share`, { method: 'DELETE' }),
  removeMember: (id: string, userId: string) => api<void>(`/decks/${id}/members/${userId}`, { method: 'DELETE' }),
  join: (code: string) => api<DeckDetail>(`/decks/join/${encodeURIComponent(code)}`, { method: 'POST' }),
  copy: (id: string) => api<DeckDetail>(`/decks/${id}/copy`, { method: 'POST' }),
}

export const deckShareUrl = (code: string) => `${window.location.origin}/decks/join/${code}`
