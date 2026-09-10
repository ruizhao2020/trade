/**
 * ============================================================================
 * SignalLayer API 客户端
 * ============================================================================
 *
 * 前端与 Python 后端（FastAPI）之间的通信层。
 * 封装了 HTTP 请求（GET/POST），所有前端数据请求都经过此模块。
 *
 * 使用示例:
 *   import { api } from './api/client'
 *   const data = await api.get('/klines/BTCUSDT', { timeframe: '15m' })
 *
 * 后端对应 app/api/ 目录下的各个路由模块。
 * 所有 API 前缀为 /api/v1/，通过 VITE_API_BASE 环境变量配置。
 */

/** 后端 API 基地址。开发环境默认 localhost:8000，生产环境通过环境变量覆盖 */
const BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api/v1'
const TOKEN_KEY = 'signal_layer_access_token'

export function getAccessToken() {
  return typeof window === 'undefined' || !window.localStorage
    ? null
    : window.localStorage.getItem(TOKEN_KEY)
}

export function setAccessToken(token: string | null) {
  if (typeof window === 'undefined' || !window.localStorage) return
  if (token) window.localStorage.setItem(TOKEN_KEY, token)
  else window.localStorage.removeItem(TOKEN_KEY)
}

class ApiClient {
  /**
   * 通用 HTTP 请求方法
   * @param method  HTTP 方法 (GET/POST)
   * @param path    请求路径（自动拼接 BASE 前缀），如 "/klines/BTCUSDT"
   * @param body    请求体（POST 时使用，自动 JSON 序列化）
   * @returns       反序列化后的 JSON 响应
   * @throws        当 HTTP 状态码非 2xx 时抛出 Error
   */
  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    console.log(`[SL:API] ${method} ${path}`, body ? { body } : undefined)
    const token = getAccessToken()
    const headers: Record<string, string> = {}
    if (body) headers['Content-Type'] = 'application/json'
    if (token) headers.Authorization = `Bearer ${token}`
    const res = await fetch(`${BASE}${path}`, {
      method,
      headers: Object.keys(headers).length > 0 ? headers : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!res.ok) {
      const text = await res.text()
      if (res.status === 401 && !path.startsWith('/auth/')) {
        setAccessToken(null)
        window.dispatchEvent(new Event('signal-layer:unauthorized'))
      }
      console.error(`[SL:API] ${method} ${path} -> FAIL ${res.status}`, text)
      throw new Error(`API ${res.status}: ${text}`)
    }
    if (res.status === 204) {
      console.log(`[SL:API] ${method} ${path} -> OK (no content)`)
      return undefined as T
    }
    const responseText = await res.text()
    const data = responseText ? JSON.parse(responseText) as T : undefined as T
    console.log(`[SL:API] ${method} ${path} -> OK`)
    return data
  }

  /** GET 请求。params 自动序列化为 query string */
  get<T>(path: string, params?: Record<string, string>) {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return this.request<T>('GET', path + qs)
  }

  /** POST 请求。body 自动 JSON 序列化 */
  post<T>(path: string, body: unknown) {
    return this.request<T>('POST', path, body)
  }

  /** PUT 请求。body 自动 JSON 序列化 */
  put<T>(path: string, body: unknown) {
    return this.request<T>('PUT', path, body)
  }

  /** DELETE 请求 */
  delete(path: string) {
    return this.request<void>('DELETE', path)
  }
}

/** 全局 API 客户端单例。所有模块通过此实例与后端通信 */
export const api = new ApiClient()
