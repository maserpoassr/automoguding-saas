import { defineStore } from 'pinia'

const TOKEN_KEY = 'auth_token'
const USER_KEY = 'auth_user'
const ROLE_KEY = 'auth_role'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    username: localStorage.getItem(USER_KEY) || '',
    role: localStorage.getItem(ROLE_KEY) || '',
  }),
  getters: {
    isAuthed: (s) => !!s.token,
    isAdmin: (s) => s.role === 'admin',
    canWrite: (s) => s.role === 'admin' || s.role === 'operator',
  },
  actions: {
    setAuth(token, username, role) {
      this.token = token || ''
      this.username = username || ''
      this.role = role || ''
      if (this.token) localStorage.setItem(TOKEN_KEY, this.token)
      else localStorage.removeItem(TOKEN_KEY)
      if (this.username) localStorage.setItem(USER_KEY, this.username)
      else localStorage.removeItem(USER_KEY)
      if (this.role) localStorage.setItem(ROLE_KEY, this.role)
      else localStorage.removeItem(ROLE_KEY)
    },
    logout() {
      this.setAuth('', '', '')
    },
  },
})
