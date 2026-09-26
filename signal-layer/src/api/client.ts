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
import { getAppSurface } from '../surface.ts'

const BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api/v1'
const TOKEN_KEY = 'signal_layer_access_token'

/** 极端缓慢请求的兜底上限。行情首次冷启动需要从外部数据源补齐历史，实测可超过 150 秒，
 *  因此这里只作为“彻底挂死”的保护，不作为正常超时来用。 */
const DEFAULT_TIMEOUT_MS = 180_000

/** 带 HTTP 状态码的接口错误。message 已经是可直接展示给用户的中文文案。 */
export class ApiError extends Error {
  readonly status: number
  /** 后端返回的原始 detail，仅用于日志排查，不要直接渲染给用户 */
  readonly detail: string | null

  constructor(status: number, message: string, detail: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

const STATUS_MESSAGES: Record<number, string> = {
  400: '请求参数有误，请检查后重试',
  401: '登录状态已失效，请重新登录',
  403: '没有权限执行该操作',
  404: '请求的数据不存在或已被移除',
  405: '该操作暂不支持',
  409: '数据已被其他操作修改，请刷新后重试',
  413: '提交的内容过大，请精简后重试',
  422: '提交的数据格式不正确，请检查后重试',
  429: '操作过于频繁，请稍后重试',
}

/** 框架生成的英文样板 detail，对用户没有意义，按“无 detail”处理 */
const BOILERPLATE_DETAILS = new Set([
  'not found',
  'internal server error',
  'method not allowed',
  'bad request',
  'unprocessable entity',
  'forbidden',
  'unauthorized',
])

function statusMessage(status: number): string {
  const known = STATUS_MESSAGES[status]
  if (known) return known
  // 5xx 统一收敛，避免把后端堆栈细节暴露到界面上
  if (status >= 500) return '服务暂时不可用，请稍后重试'
  return `请求失败（${status}）`
}

/** 从响应体里取出后端给的中文说明（FastAPI 约定为 detail 字段） */
function extractDetail(text: string): string | null {
  if (!text) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return null
  }
  const detail = (parsed as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') {
    const trimmed = detail.trim()
    return BOILERPLATE_DETAILS.has(trimmed.toLowerCase()) ? null : trimmed || null
  }
  // FastAPI 校验失败时 detail 是数组，取第一条可读的 msg
  if (Array.isArray(detail)) {
    for (const item of detail) {
      const msg = (item as { msg?: unknown } | null)?.msg
      if (typeof msg === 'string' && msg.trim()) {
        return msg.replace(/^value error,\s*/i, '').trim()
      }
    }
  }
  return null
}

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
  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    options?: { signal?: AbortSignal; timeoutMs?: number },
  ): Promise<T> {
    const token = getAccessToken()
    const headers: Record<string, string> = {}
    headers['X-Signal-Surface'] = getAppSurface()
    if (body) headers['Content-Type'] = 'application/json'
    if (token) headers.Authorization = `Bearer ${token}`

    const externalSignal = options?.signal
    if (externalSignal?.aborted) throw new ApiError(0, '请求已取消')
    const timeoutMs = options?.timeoutMs ?? DEFAULT_TIMEOUT_MS
    const controller = new AbortController()
    const abortFromExternal = () => controller.abort()
    externalSignal?.addEventListener('abort', abortFromExternal)
    let timedOut = false
    const timer = timeoutMs > 0
      ? setTimeout(() => { timedOut = true; controller.abort() }, timeoutMs)
      : undefined

    let res: Response
    try {
      res = await fetch(`${BASE}${path}`, {
        method,
        headers: Object.keys(headers).length > 0 ? headers : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      })
    } catch (fetchError) {
      if (timedOut) throw new ApiError(0, '请求超时，请稍后重试')
      if (externalSignal?.aborted) throw new ApiError(0, '请求已取消')
      // fetch 仅在网络层失败时抛错：端口未监听、DNS 解析失败、连接被中断等
      console.error(`[SL:API] ${method} ${path} -> NETWORK FAIL`, fetchError)
      throw new ApiError(0, '无法连接服务，请检查网络或稍后重试')
    } finally {
      if (timer) clearTimeout(timer)
      externalSignal?.removeEventListener('abort', abortFromExternal)
    }

    if (!res.ok) {
      const text = await res.text()
      if (res.status === 401 && !path.startsWith('/auth/')) {
        setAccessToken(null)
        window.dispatchEvent(new Event('signal-layer:unauthorized'))
      }
      const detail = extractDetail(text)
      // 5xx 一律用收敛后的文案，不把后端内部细节带到界面上
      const message = res.status >= 500 ? statusMessage(res.status) : detail ?? statusMessage(res.status)
      console.error(`[SL:API] ${method} ${path} -> FAIL ${res.status}`, detail ?? text)
      throw new ApiError(res.status, message, detail)
    }
    if (res.status === 204) return undefined as T
    const responseText = await res.text()
    return responseText ? JSON.parse(responseText) as T : undefined as T
  }

  /** GET 请求。params 自动序列化为 query string */
  get<T>(path: string, params?: Record<string, string>, options?: { signal?: AbortSignal; timeoutMs?: number }) {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return this.request<T>('GET', path + qs, undefined, options)
  }

  /** POST 请求。body 自动 JSON 序列化 */
  post<T>(path: string, body: unknown, options?: { signal?: AbortSignal; timeoutMs?: number }) {
    return this.request<T>('POST', path, body, options)
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
