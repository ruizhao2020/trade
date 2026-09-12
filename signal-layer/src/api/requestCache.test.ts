import { describe, expect, it, vi } from 'vitest'
import { RecentRequestCache, marketRequestTtl } from './requestCache.ts'

describe('recent request cache', () => {
  it('deduplicates concurrent and recent requests', async () => {
    let now = 100
    const cache = new RecentRequestCache(() => now)
    const request = vi.fn(async () => '行情')

    const first = cache.run('SF0:1d', 50, request)
    const second = cache.run('SF0:1d', 50, request)
    expect(await Promise.all([first, second])).toEqual(['行情', '行情'])
    expect(request).toHaveBeenCalledTimes(1)

    now = 151
    expect(await cache.run('SF0:1d', 50, request)).toBe('行情')
    expect(request).toHaveBeenCalledTimes(2)
  })

  it('uses shorter freshness for shorter timeframes', () => {
    expect(marketRequestTtl('5m')).toBeLessThan(marketRequestTtl('30m'))
    expect(marketRequestTtl('30m')).toBeLessThan(marketRequestTtl('1d'))
  })
})
