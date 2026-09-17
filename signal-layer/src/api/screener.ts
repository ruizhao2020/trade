import { api } from './client.ts'
import { templateToSnake } from './signal.ts'
import type { ConditionTemplate } from '../core/types.ts'
import type { SymbolItem } from './symbol.ts'

interface ApiScreenerMatch {
  symbol: string
  name: string
  market: string
  industry?: string
  exchange?: string
  state: string
  is_ready: boolean
  progress_percent: number
}

interface ApiScreenerResponse {
  market: string
  universe_total: number
  scanned_count: number
  matched_count: number
  failed_count: number
  target_count: number
  stopped_early: boolean
  results: ApiScreenerMatch[]
}

export interface ScreenerMatch {
  item: SymbolItem
  state: string
  isReady: boolean
  progressPercent: number
}

export interface ScreenerResponse {
  market: string
  universeTotal: number
  scannedCount: number
  matchedCount: number
  failedCount: number
  targetCount: number
  stoppedEarly: boolean
  results: ScreenerMatch[]
}

export async function runScreener(
  template: ConditionTemplate,
  options: { market?: string; limit?: number; offset?: number; targetCount?: number; minProgress?: number; concurrency?: number } = {},
): Promise<ScreenerResponse> {
  const raw = await api.post<ApiScreenerResponse>('/screener/run', {
    template: templateToSnake(template),
    market: options.market ?? 'stock',
    limit: options.limit ?? 500,
    offset: options.offset ?? 0,
    target_count: options.targetCount ?? 10,
    min_progress: options.minProgress ?? 1,
    concurrency: options.concurrency ?? 4,
    kline_limit: 200,
  })
  return {
    market: raw.market,
    universeTotal: raw.universe_total,
    scannedCount: raw.scanned_count,
    matchedCount: raw.matched_count,
    failedCount: raw.failed_count,
    targetCount: raw.target_count,
    stoppedEarly: raw.stopped_early,
    results: raw.results.map((result) => ({
      item: {
        symbol: result.symbol,
        name: result.name,
        market: result.market,
        industry: result.industry,
        exchange: result.exchange,
      },
      state: result.state,
      isReady: result.is_ready,
      progressPercent: result.progress_percent,
    })),
  }
}
