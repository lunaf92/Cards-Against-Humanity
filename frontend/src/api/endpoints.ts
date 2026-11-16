import { api } from './http'
import type { QueueResponse, RoomConfig, RoomDetails, TokenPair, User } from './types'

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
