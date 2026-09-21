import { api } from './client'
import type { IndicatorResult, IndicatorInfo } from '../core/types.ts'
import { applyIndicatorPeriodColor } from '../core/indicatorColors.ts'

/** 后端返回的原始结构(snake_case) */
interface ApiMarkerSpec {
  field: string
  price_field?: string | null
  label_index_field?: string | null
  label_tag_field?: string | null
  label_tags?: Record<number, string>
  size?: number
  spacing?: number
  buy_color: string
  sell_color: string
  buy_label: string
  sell_label: string
}

interface ApiIndicatorResult {
  type: string
  params: Record<string, number>
  values: Record<string, number>[]
  render: {
    window: string
    plots: { field: string; type: string; color: string; label: string }[]
    markers?: ApiMarkerSpec[]
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
  errors?: IndicatorCalculationError[]
}

interface ApiInfo {
  type: string
  name: string
  description: string
  default_params: Record<string, number>
  outputs?: { field: string; label: string }[]
  render: {
    window: string
    plots: { field: string; type: string; color: string; label: string }[]
    markers?: ApiMarkerSpec[]
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
      markers: (r.render.markers ?? []).map(marker => ({
        field: marker.field,
        priceField: marker.price_field ?? undefined,
        labelIndexField: marker.label_index_field ?? undefined,
        labelTagField: marker.label_tag_field ?? undefined,
        labelTags: marker.label_tags,
        size: marker.size,
        spacing: marker.spacing,
        buyColor: marker.buy_color,
        sellColor: marker.sell_color,
        buyLabel: marker.buy_label,
        sellLabel: marker.sell_label,
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

export interface IndicatorCalculationError {
  type: string
  code: string
  message: string
}

export interface IndicatorCalculationResponse {
  results: IndicatorResult[]
  errors: IndicatorCalculationError[]
}

export async function calculateIndicatorsDetailed(
  symbol: string,
  timeframe: string,
  indicators: IndicatorRequest[],
  klineLimit = 200,
): Promise<IndicatorCalculationResponse> {
  console.log(`[SL:API] POST /indicator/calculate`, { symbol, timeframe, indicators })
  const raw = await api.post<ApiCalculateResponse>('/indicator/calculate', {
    symbol,
    timeframe,
    kline_limit: klineLimit,
    indicators,
  })
  const errors = raw.errors ?? []
  if (errors.length > 0) console.warn('[SL:API] isolated indicator failures', errors)
  console.log(`[SL:API] POST /indicator/calculate -> ${raw.results.length} results, ${errors.length} errors`)
  return { results: raw.results.map(toFrontend), errors }
}

/** 计算指标 */
export async function calculateIndicators(
  symbol: string,
  timeframe: string,
  indicators: IndicatorRequest[],
  klineLimit = 200,
): Promise<IndicatorResult[]> {
  return (await calculateIndicatorsDetailed(symbol, timeframe, indicators, klineLimit)).results
}

/** 获取指标列表(指标库) */
export async function fetchIndicatorList(): Promise<IndicatorInfo[]> {
  const raw = await api.get<ApiListResponse>('/indicator/list')
  return raw.indicators.map(i => ({
    type: i.type,
    name: i.name,
    description: i.description,
    default_params: i.default_params,
    outputs: i.outputs,
    render: {
      window: i.render.window as 'main' | 'sub',
      plots: i.render.plots.map(p => ({
        field: p.field,
        type: p.type as 'line' | 'histogram' | 'marker' | 'profile',
        color: p.color,
        label: p.label,
      })),
      markers: (i.render.markers ?? []).map(marker => ({
        field: marker.field,
        priceField: marker.price_field ?? undefined,
        labelIndexField: marker.label_index_field ?? undefined,
        labelTagField: marker.label_tag_field ?? undefined,
        labelTags: marker.label_tags,
        size: marker.size,
        spacing: marker.spacing,
        buyColor: marker.buy_color,
        sellColor: marker.sell_color,
        buyLabel: marker.buy_label,
        sellLabel: marker.sell_label,
      })),
    },
  }))
}
