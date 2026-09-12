import { api } from './client'
import type { IndicatorResult, IndicatorInfo } from '../core/types.ts'
import { applyIndicatorPeriodColor } from '../core/indicatorColors.ts'

/** 后端返回的原始结构(snake_case) */
interface ApiIndicatorResult {
  type: string
  params: Record<string, number>
  values: Record<string, number>[]
  render: {
    window: string
    plots: { field: string; type: string; color: string; label: string }[]
  }
  profile_data?: {
    prices: number[]
    snapshots: Array<{ time: number; weights: number[]; metrics: Record<string, number> }>
  } | null
  cached: boolean
}

interface ApiCalculateResponse {
  symbol: string
  timeframe: string
  results: ApiIndicatorResult[]
}

interface ApiInfo {
  type: string
  name: string
  description: string
  default_params: Record<string, number>
  render: {
    window: string
    plots: { field: string; type: string; color: string; label: string }[]
  }
}

interface ApiListResponse {
  indicators: ApiInfo[]
}

/** 后端 snake_case → 前端类型 */
function toFrontend(r: ApiIndicatorResult): IndicatorResult {
  return applyIndicatorPeriodColor({
    type: r.type,
    params: r.params,
    values: r.values,
    render: {
      window: r.render.window as 'main' | 'sub',
      plots: r.render.plots.map(p => ({
        field: p.field,
        type: p.type as 'line' | 'histogram' | 'marker' | 'profile',
        color: p.color,
        label: p.label,
      })),
    },
    profileData: r.profile_data ? {
      prices: r.profile_data.prices,
      snapshots: r.profile_data.snapshots,
    } : undefined,
  })
}

export interface IndicatorRequest {
  type: string
  params: Record<string, number>
}

/** 计算指标 */
export async function calculateIndicators(
  symbol: string,
  timeframe: string,
  indicators: IndicatorRequest[],
  klineLimit = 200,
): Promise<IndicatorResult[]> {
  console.log(`[SL:API] POST /indicator/calculate`, { symbol, timeframe, indicators })
  const raw = await api.post<ApiCalculateResponse>('/indicator/calculate', {
    symbol,
    timeframe,
    kline_limit: klineLimit,
    indicators,
  })
  console.log(`[SL:API] POST /indicator/calculate -> ${raw.results.length} results`)
  return raw.results.map(toFrontend)
}

/** 获取指标列表(指标库) */
export async function fetchIndicatorList(): Promise<IndicatorInfo[]> {
  const raw = await api.get<ApiListResponse>('/indicator/list')
  return raw.indicators.map(i => ({
    type: i.type,
    name: i.name,
    description: i.description,
    default_params: i.default_params,
    render: {
      window: i.render.window as 'main' | 'sub',
      plots: i.render.plots.map(p => ({
        field: p.field,
        type: p.type as 'line' | 'histogram' | 'marker' | 'profile',
        color: p.color,
        label: p.label,
      })),
    },
  }))
}
