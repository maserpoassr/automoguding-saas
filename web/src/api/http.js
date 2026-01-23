import axios from 'axios'

const TOKEN_KEY = 'auth_token'
const USER_KEY = 'auth_user'
const ROLE_KEY = 'auth_role'

export const http = axios.create({
  baseURL: '/api',
  timeout: 20000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error?.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
      localStorage.removeItem(ROLE_KEY)
      if (typeof window !== 'undefined') {
        const path = window.location.hash || '#/'
        if (!path.startsWith('#/login')) window.location.hash = '#/login'
      }
    }
    const message = error?.response?.data?.detail || error?.message || '请求失败'
    return Promise.reject({ ...error, friendlyMessage: message })
  }
)
