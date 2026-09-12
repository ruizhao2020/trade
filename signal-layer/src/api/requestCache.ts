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

export function marketRequestTtl(timeframe: string): number {
  if (timeframe === '5m') return 15_000
  if (timeframe === '30m') return 60_000
  return 300_000
}

export const recentMarketRequests = new RecentRequestCache()
