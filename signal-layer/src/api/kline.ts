import { api } from './client'

export interface ApiKlineItem {
  open_time: number
  open: string
  high: string
  low: string
  close: string
  volume: string
  turnover?: string
  is_closed: boolean
}

export interface ApiKlineResponse {
  symbol: string
  timeframe: string
  data: ApiKlineItem[]
  from_time: number | null
  to_time: number | null
  count: number
}

export interface FrontendKline {
  openTime: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  turnover?: number
  isClosed: boolean
}

export interface FrontendKlineResponse {
  symbol: string
  timeframe: string
  data: FrontendKline[]
  count: number
}

function toFrontend(item: ApiKlineItem): FrontendKline {
  return {
    openTime: item.open_time,
    open: parseFloat(item.open),
    high: parseFloat(item.high),
    low: parseFloat(item.low),
    close: parseFloat(item.close),
    volume: parseFloat(item.volume),
    ...(item.turnover ? { turnover: parseFloat(item.turnover) } : {}),
    isClosed: item.is_closed,
  }
}

export async function fetchKlines(
  symbol: string, timeframe: string, limit = 200,
): Promise<FrontendKlineResponse> {
  console.log(`[SL:API] GET /klines/${symbol}`, { timeframe, limit })
  const raw = await api.get<ApiKlineResponse>(`/klines/${symbol}`, { timeframe, limit: String(limit) })
  console.log(`[SL:API] GET /klines/${symbol} -> OK ${raw.count} candles`)
  return { symbol: raw.symbol, timeframe: raw.timeframe, data: raw.data.map(toFrontend), count: raw.count }
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
  return { symbol: raw.symbol, timeframe: raw.timeframe, data: raw.data.map(toFrontend), count: raw.count }
}
