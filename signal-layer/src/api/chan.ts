import { api } from './client'
import { marketRequestTtl, recentMarketRequests } from './requestCache.ts'
import type {
  ChanAnalysis, ChanKLine, Fenxing, Bi, Duan, Zhongshu, BuySellPoint, Divergence, SignalType,
} from '../core/types.ts'

interface ApiBi {
  index: number; direction: 'up' | 'down'
  start_time: number; end_time: number
  start_price: string; end_price: string
  high: string; low: string
}

interface ApiZhongshu {
  index: number; high: string; low: string; mid: string
  start_time: number; end_time: number
  level: string; broken: boolean
  bi_indices?: number[]
  break_direction?: 'up' | 'down' | null
}

interface ApiBsp {
  type: string; price: string; time: number; confirmed: boolean; strength: number
  zhongshu_index?: number | null; bi_index?: number
  reason?: string | null; divergence_index?: number | null
}

interface ApiDivergence {
  index: number; type: 'top' | 'bottom'; level: 'bi'; kind: 'consolidation'
  price: string; time: number; zhongshu_index: number
  reference_bi_index: number; current_bi_index: number
  reference_power: number; current_power: number; strength_ratio: number
  confirmed: boolean; reasons?: string[]
}

interface ApiFeatElement {
  first: number; last: number; bi: number
}

interface ApiDuan {
  index: number; direction: 'up' | 'down'
  start_time: number; end_time: number
  start_price: string; end_price: string
  high: string; low: string
  bi_indices?: number[]
  feat_elements?: ApiFeatElement[]
  merged_feat?: ApiFeatElement[]
  fenxing_type?: string
}

interface ApiChanResponse {
  symbol: string; timeframe: string
  bis: ApiBi[]; duans: ApiDuan[]
  zhongshus: ApiZhongshu[]           // 笔中枢(level="bi")
  duan_zhongshus: ApiZhongshu[]      // 段中枢(level="duan")
  buy_sell_points: ApiBsp[]
  divergences?: ApiDivergence[]
  updated_at: number
  cached: boolean
}

function f(s: string): number { return parseFloat(s) }

/**
 * 把后端返回的缠论数据转换为前端 ChanAnalysis 结构。
 *
 * 注意:后端不返回 chanKLines 和 fenxings(渲染不需要),
 * 这里给空数组占位,渲染层不会用到这两项。
 */
function toChanAnalysis(raw: ApiChanResponse): ChanAnalysis {
  const bis: Bi[] = raw.bis.map(b => ({
    index: b.index,
    direction: b.direction,
    startFenxingIndex: 0,
    endFenxingIndex: 0,
    startTime: b.start_time,
    endTime: b.end_time,
    startPrice: f(b.start_price),
    endPrice: f(b.end_price),
    high: f(b.high),
    low: f(b.low),
    power: Math.abs(f(b.end_price) - f(b.start_price)),
    klineRange: [0, 0],
  }))

  const duans: Duan[] = raw.duans.map(d => ({
    index: d.index,
    direction: d.direction,
    biIndices: d.bi_indices ?? [],
    startTime: d.start_time,
    endTime: d.end_time,
    startPrice: f(d.start_price),
    endPrice: f(d.end_price),
    high: f(d.high),
    low: f(d.low),
    featElements: d.feat_elements?.map(fe => ({ first: fe.first, last: fe.last, bi: fe.bi })),
    mergedFeat: d.merged_feat?.map(fe => ({ first: fe.first, last: fe.last, bi: fe.bi })),
    fenxingType: d.fenxing_type as 'top' | 'bottom' | undefined,
  }))

  const zhongshus: Zhongshu[] = raw.zhongshus.map(z => toZhongshu(z))
  const duanZhongshus: Zhongshu[] = (raw.duan_zhongshus ?? []).map(z => toZhongshu(z))

  const buySellPoints: BuySellPoint[] = raw.buy_sell_points.map(p => ({
    type: p.type as SignalType,
    price: f(p.price),
    time: p.time,
    zhongshuIndex: p.zhongshu_index ?? undefined,
    biIndex: p.bi_index ?? 0,
    confirmed: p.confirmed,
    strength: p.strength,
    reason: p.reason ?? undefined,
    divergenceIndex: p.divergence_index ?? undefined,
  }))

  const divergences: Divergence[] = (raw.divergences ?? []).map(item => ({
    index: item.index,
    type: item.type,
    level: item.level,
    kind: item.kind,
    price: f(item.price),
    time: item.time,
    zhongshuIndex: item.zhongshu_index,
    referenceBiIndex: item.reference_bi_index,
    currentBiIndex: item.current_bi_index,
    referencePower: item.reference_power,
    currentPower: item.current_power,
    strengthRatio: item.strength_ratio,
    confirmed: item.confirmed,
    reasons: item.reasons ?? [],
  }))

  return {
    timeframeId: raw.timeframe,
    chanKLines: [] as ChanKLine[],
    fenxings: [] as Fenxing[],
    bis,
    duans,
    zhongshus,
    duanZhongshus,
    buySellPoints,
    divergences,
    updatedAt: raw.updated_at,
    isComplete: true,
  }
}

function toZhongshu(z: ApiZhongshu): Zhongshu {
  return {
    index: z.index,
    high: f(z.high),
    low: f(z.low),
    mid: f(z.mid),
    biIndices: z.bi_indices ?? [],
    startTime: z.start_time,
    endTime: z.end_time,
    level: z.level,
    broken: z.broken,
    breakDirection: z.break_direction ?? undefined,
  }
}

export async function fetchChanAnalysis(symbol: string, timeframe: string, limit = 200, forceRefresh = false): Promise<ChanAnalysis> {
  const key = `chan:${symbol}:${timeframe}:${limit}`
  const request = async () => {
    console.log(`[SL:API] GET /chan/${symbol}/${timeframe}`, { limit, forceRefresh })
    const raw = await api.get<ApiChanResponse>(`/chan/${symbol}/${timeframe}`, { limit: String(limit) })
    console.log(`[SL:API] GET /chan/${symbol}/${timeframe} -> OK`, {
      bis: raw.bis.length, duans: raw.duans.length,
      zhongshus: raw.zhongshus.length,
      duanZhongshus: raw.duan_zhongshus?.length ?? 0,
      buySellPoints: raw.buy_sell_points.length,
      divergences: raw.divergences?.length ?? 0,
    })
    return toChanAnalysis(raw)
  }
  if (forceRefresh) return request()
  return recentMarketRequests.run(key, marketRequestTtl(timeframe), request)
}
