interface CacheEntry {
  expiresAt: number
  promise: Promise<unknown>
}

/** 合并相同的在途请求，并在短时间内复用最近成功结果。 */
export class RecentRequestCache {
  private readonly entries = new Map<string, CacheEntry>()
  private readonly now: () => number

  constructor(now: () => number = Date.now) {
    this.now = now
  }

  run<T>(key: string, ttlMs: number, request: () => Promise<T>): Promise<T> {
    const existing = this.entries.get(key)
    if (existing && existing.expiresAt > this.now()) {
      return existing.promise as Promise<T>
    }
    const promise = request()
    this.entries.set(key, { expiresAt: this.now() + ttlMs, promise })
    while (this.entries.size > 128) {
      const oldestKey = this.entries.keys().next().value
      if (oldestKey === undefined) break
      this.entries.delete(oldestKey)
    }
    promise.catch(() => {
      if (this.entries.get(key)?.promise === promise) this.entries.delete(key)
    })
    return promise
  }
}

/** 与后端 MarketDataManager 的 latest 缓存 TTL 保持一致 */
const MARKET_REQUEST_TTL_MS: Record<string, number> = {
  '5m': 15_000,
  '15m': 30_000,
  '30m': 60_000,
  '60m': 90_000,
  '1d': 300_000,
}

export function marketRequestTtl(timeframe: string): number {
  return MARKET_REQUEST_TTL_MS[timeframe] ?? 300_000
}

export const recentMarketRequests = new RecentRequestCache()
