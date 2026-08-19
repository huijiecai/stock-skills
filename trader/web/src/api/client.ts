/** API 客户端:fetch 封装,Bearer 自动携带,401 统一踢回登录。 */
export const TOKEN_KEY = 'trader_token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

export function setToken(t: string) {
  localStorage.setItem(TOKEN_KEY, t)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export async function api<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
      ...(opts.headers ?? {}),
    },
  })
  if (res.status === 401) {
    clearToken()
    if (!location.pathname.startsWith('/login')) location.href = '/login'
    throw new Error('未登录或登录已过期')
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}

export const get = <T = any>(p: string) => api<T>(p)
export const post = <T = any>(p: string, body?: unknown) =>
  api<T>(p, { method: 'POST', body: JSON.stringify(body ?? {}) })
export const put = <T = any>(p: string, body?: unknown) =>
  api<T>(p, { method: 'PUT', body: JSON.stringify(body ?? {}) })
