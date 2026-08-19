/** API 客户端:fetch 封装,Bearer 自动携带,401 统一踢回登录,自动解包标准响应信封。 */
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

export interface Envelope<T = any> {
  data: T
  status: 'SUCCESS' | 'ERROR'
  message?: string
  traceId?: string
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
  const body: Envelope<T> = await res.json().catch(() => ({ data: null, status: 'ERROR' }))
  if (!res.ok || body.status === 'ERROR') {
    throw new Error(body.message ?? `HTTP ${res.status}`)
  }
  // 登录接口的 token 在 data 里,直接透传
  return body.data
}

export const get = <T = any>(p: string) => api<T>(p)
export const post = <T = any>(p: string, body?: unknown) =>
  api<T>(p, { method: 'POST', body: JSON.stringify(body ?? {}) })
export const put = <T = any>(p: string, body?: unknown) =>
  api<T>(p, { method: 'PUT', body: JSON.stringify(body ?? {}) })
