import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from './client.ts'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ApiClient no-content responses', () => {
  it('resolves DELETE 204 without attempting to parse JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(api.delete('/templates/template-1')).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/templates/template-1'),
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('still parses normal JSON responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"ok":true}', { status: 200 })))
    await expect(api.get<{ ok: boolean }>('/health')).resolves.toEqual({ ok: true })
  })
})

describe('ApiClient 错误文案', () => {
  const errorCases: Array<{ name: string; status: number; body: string; expected: string }> = [
    { name: '优先使用后端给的中文 detail', status: 401, body: '{"detail":"用户名或密码错误"}', expected: '用户名或密码错误' },
    { name: '404 的英文样板 detail 被忽略', status: 404, body: '{"detail":"Not Found"}', expected: '请求的数据不存在或已被移除' },
    { name: '403 映射为权限提示', status: 403, body: '{"detail":"Forbidden"}', expected: '没有权限执行该操作' },
    { name: '5xx 收敛为通用文案', status: 500, body: '{"detail":"KeyError: internal_column"}', expected: '服务暂时不可用，请稍后重试' },
    { name: '非 JSON 响应体不泄漏到界面', status: 502, body: '<html>bad gateway</html>', expected: '服务暂时不可用，请稍后重试' },
  ]

  for (const item of errorCases) {
    it(item.name, async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(item.body, { status: item.status })))
      await expect(api.get('/anything')).rejects.toMatchObject({ name: 'ApiError', message: item.expected })
    })
  }

  it('FastAPI 校验错误数组取第一条 msg', async () => {
    const body = JSON.stringify({ detail: [{ loc: ['body', 'password'], msg: 'Value error, 密码至少需要 8 位', type: 'value_error' }] })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 422 })))
    await expect(api.post('/auth/register', {})).rejects.toMatchObject({ message: '密码至少需要 8 位' })
  })

  it('网络层失败给出可读提示而不是 TypeError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const error = await api.get('/klines/000001_sz').catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).message).toBe('无法连接服务，请检查网络或稍后重试')
  })

  it('外部取消时抛出已取消而不是网络错误', async () => {
    const controller = new AbortController()
    vi.stubGlobal('fetch', vi.fn().mockImplementation((_url: string, init?: RequestInit) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      })))
    const promise = api.get('/klines/000001_sz', undefined, { signal: controller.signal })
    controller.abort()
    await expect(promise).rejects.toMatchObject({ message: '请求已取消' })
  })

  it('保存 detail 供排查，但 message 不包含原始 JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"用户名或密码错误"}', { status: 401 })))
    const error = await api.get('/auth/login').catch((caught: unknown) => caught as ApiError)
    expect((error as ApiError).detail).toBe('用户名或密码错误')
    expect((error as ApiError).message).not.toContain('{')
  })
})
