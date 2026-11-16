import { create } from 'zustand'
import { authApi } from '../api/endpoints'
import { tokenStorage } from '../api/tokenStorage'
import type { User } from '../api/types'

interface AuthState {
  user: User | null
  status: 'loading' | 'signed_out' | 'signed_in'
  init: () => Promise<void>
  login: (usernameOrEmail: string, password: string) => Promise<void>
  register: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => {
  // A failed refresh anywhere in the app signs the user out here too.
  tokenStorage.subscribe((tokens) => {
    if (!tokens) set({ user: null, status: 'signed_out' })
  })

  const loadMe = async () => {
    const user = await authApi.me()
    set({ user, status: 'signed_in' })
  }

  return {
    user: null,
    status: 'loading',
    async init() {
      if (!tokenStorage.get()) {
        set({ status: 'signed_out' })
        return
      }
      try {
        await loadMe()
      } catch {
        tokenStorage.clear()
      }
    },
    async login(usernameOrEmail, password) {
      tokenStorage.set(await authApi.login(usernameOrEmail, password))
      await loadMe()
    },
    async register(username, password) {
      tokenStorage.set(await authApi.register(username, password))
      await loadMe()
    },
    async logout() {
      try {
        await authApi.logout()
      } catch {
        /* the token is dropped locally either way */
      }
      tokenStorage.clear()
    },
  }
})
