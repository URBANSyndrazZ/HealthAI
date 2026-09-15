import { computed, ref } from 'vue'
import { apiUrl } from './client'

const TOKEN_KEY = 'ai_health_token'
const USERNAME_KEY = 'ai_health_username'

function decodeJwtPayload(rawToken: string): Record<string, any> | null {
  try {
    const payload = rawToken.split('.')[1]
    if (!payload) return null
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
    return JSON.parse(decodeURIComponent(escape(window.atob(padded))))
  } catch {
    return null
  }
}

function isTokenUsable(rawToken: string | null) {
  if (!rawToken) return false
  const payload = decodeJwtPayload(rawToken)
  if (!payload || typeof payload.exp !== 'number') return false
  // Leave a small buffer so a token that is about to expire does not pass route guards.
  return payload.exp * 1000 > Date.now() + 30_000
}

function clearStoredAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USERNAME_KEY)
}

function getInitialToken() {
  const storedToken = localStorage.getItem(TOKEN_KEY)
  if (!isTokenUsable(storedToken)) {
    clearStoredAuth()
    return null
  }
  return storedToken
}

const token = ref(getInitialToken())
const username = ref(token.value ? localStorage.getItem(USERNAME_KEY) : null)

export interface AuthPayload {
  username: string
  password: string
}

export interface AuthResponse {
  user_id: string
  username: string
  token: string
}

export function getToken() {
  return token.value
}

export function getUsername() {
  return username.value
}

export function isAuthenticated() {
  if (!isTokenUsable(token.value)) {
    logout()
    return false
  }
  return true
}

export function authHeaders(): Record<string, string> {
  return isAuthenticated() && token.value ? { Authorization: `Bearer ${token.value}` } : {}
}

function saveAuth(data: AuthResponse) {
  localStorage.setItem(TOKEN_KEY, data.token)
  localStorage.setItem(USERNAME_KEY, data.username)
  token.value = data.token
  username.value = data.username
  return data
}

export function logout() {
  clearStoredAuth()
  token.value = null
  username.value = null
}

export function handleUnauthorized(redirect = true) {
  logout()
  if (redirect && window.location.pathname !== '/login') {
    const redirectPath = `${window.location.pathname}${window.location.search}`
    window.location.assign(`/login?redirect=${encodeURIComponent(redirectPath)}`)
  }
}

export function ensureAuthorizedResponse(response: Response) {
  if (response.status === 401 || response.status === 403) {
    handleUnauthorized()
    return false
  }
  return true
}

export function useAuthState() {
  return {
    token,
    username,
    loggedIn: computed(() => isAuthenticated()),
  }
}

function formatAuthError(error: any, fallback: string) {
  const detail = error?.detail
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : ''
        const message = item?.msg || '参数不合法'
        return field ? `${field}: ${message}` : message
      })
      .join('；')
  }
  return fallback
}

export async function login(payload: AuthPayload) {
  const response = await fetch(apiUrl('/api/v1/auth/login'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(formatAuthError(error, '登录失败'))
  }
  return saveAuth(await response.json())
}

export async function register(payload: AuthPayload) {
  const response = await fetch(apiUrl('/api/v1/auth/register'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(formatAuthError(error, '注册失败'))
  }
  return saveAuth(await response.json())
}
