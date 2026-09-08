import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './client.ts'

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
