import { api } from './client'
import { marketRequestTtl, recentMarketRequests } from './requestCache.ts'

export interface ApiKlineItem {
  open_time: number
  open: string
  high: string
  low: string
  close: string
  volume: string
  amount?: string
  turnover?: string
  turnover_rate?: string
  circulating_shares?: string
  adjustment_factor?: string
  adjustment_type?: string
  is_closed: boolean
}

export interface ApiKlineResponse {
  symbol: string
  timeframe: string
  data: ApiKlineItem[]
  from_time: number | null
  to_time: number | null
  count: number
  stale?: boolean
  refresh_failed?: boolean
  expected_time?: number | null
  status_message?: string | null
}

export interface FrontendKline {
  openTime: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount?: number
  turnover?: number
  turnoverRate?: number
  circulatingShares?: number
  adjustmentFactor?: number
  adjustmentType?: string
  isClosed: boolean
}

export interface FrontendKlineResponse {
  symbol: string
  timeframe: string
  data: FrontendKline[]
  count: number
  toTime?: number | null
  stale: boolean
  refreshFailed: boolean
  expectedTime?: number | null
  statusMessage?: string | null
}

function toFrontend(item: ApiKlineItem): FrontendKline {
  return {
    openTime: item.open_time,
    open: parseFloat(item.open),
    high: parseFloat(item.high),
    low: parseFloat(item.low),
    close: parseFloat(item.close),
    volume: parseFloat(item.volume),
    ...(item.amount ? { amount: parseFloat(item.amount) } : {}),
    ...(item.turnover ? { turnover: parseFloat(item.turnover) } : {}),
    ...(item.turnover_rate ? { turnoverRate: parseFloat(item.turnover_rate) } : {}),
    ...(item.circulating_shares ? { circulatingShares: parseFloat(item.circulating_shares) } : {}),
    ...(item.adjustment_factor ? { adjustmentFactor: parseFloat(item.adjustment_factor) } : {}),
    ...(item.adjustment_type ? { adjustmentType: item.adjustment_type } : {}),
    isClosed: item.is_closed,
  }
}

export async function fetchKlines(
  symbol: string, timeframe: string, limit = 200,
): Promise<FrontendKlineResponse> {
  const key = `kline:${symbol}:${timeframe}:${limit}`
  return recentMarketRequests.run(key, marketRequestTtl(timeframe), async () => {
    console.log(`[SL:API] GET /klines/${symbol}`, { timeframe, limit })
    const raw = await api.get<ApiKlineResponse>(`/klines/${symbol}`, { timeframe, limit: String(limit) })
    console.log(`[SL:API] GET /klines/${symbol} -> OK ${raw.count} candles`)
    return {
      symbol: raw.symbol, timeframe: raw.timeframe, data: raw.data.map(toFrontend), count: raw.count,
      toTime: raw.to_time, stale: Boolean(raw.stale), refreshFailed: Boolean(raw.refresh_failed),
      expectedTime: raw.expected_time, statusMessage: raw.status_message,
    }
  })
}

/** 按时间范围读取 K 线。服务端会先查 DB，只从外部行情源补齐缺失区间。 */
export async function fetchKlineRange(
  symbol: string,
  timeframe: string,
  startTime: number,
  endTime: number,
): Promise<FrontendKlineResponse> {
  const raw = await api.get<ApiKlineResponse>(`/klines/${symbol}`, {
    timeframe,
    start_time: String(startTime),
    end_time: String(endTime),
    limit: '10000',
  })
  return {
    symbol: raw.symbol, timeframe: raw.timeframe, data: raw.data.map(toFrontend), count: raw.count,
    toTime: raw.to_time, stale: Boolean(raw.stale), refreshFailed: Boolean(raw.refresh_failed),
    expectedTime: raw.expected_time, statusMessage: raw.status_message,
  }
}
