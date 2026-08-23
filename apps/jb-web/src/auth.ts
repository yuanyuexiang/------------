import { create } from 'zustand'
import { api, getToken, setToken, User } from './api'

/** 登录态：令牌在 localStorage，用户信息启动时经 /api/auth/me 恢复。 */
interface AuthState {
  user: User | null
  devSecret: boolean
  loaded: boolean
  load: () => Promise<void>
  login: (username: string, password: string) => Promise<User>
  logout: () => void
  refresh: () => Promise<void>
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  devSecret: false,
  loaded: false,
  load: async () => {
    if (!getToken()) { set({ user: null, loaded: true }); return }
    try { const r = await api.me(); set({ user: r.user, devSecret: r.dev_secret, loaded: true }) } catch { setToken(''); set({ user: null, loaded: true }) }
  },
  login: async (username, password) => {
    const r = await api.login(username, password)
    setToken(r.token)
    set({ user: r.user, devSecret: r.dev_secret, loaded: true })
    return r.user
  },
  logout: () => { setToken(''); set({ user: null }) },
  refresh: async () => { try { const r = await api.me(); set({ user: r.user }) } catch { /* ignore */ } },
}))
