import type { LayerConfig, Timeframe } from './types.ts'
import { PeriodType } from './types.ts'

export type SupportedTimeframeId = '5m' | '30m' | '1d'
export const SUPPORTED_TIMEFRAME_IDS: SupportedTimeframeId[] = ['5m', '30m', '1d']

/** 默认支持的时间周期列表 */
export const DEFAULT_TIMEFRAMES: Timeframe[] = [
  { id: '5m', label: '5分钟', type: PeriodType.Intraday, intervalMinutes: 5, layerIndex: 0, expanded: true },
  { id: '30m', label: '30分钟', type: PeriodType.Intraday, intervalMinutes: 30, layerIndex: 1, expanded: true },
  { id: '1d', label: '日线', type: PeriodType.Calendar, intervalMinutes: null, layerIndex: 2, expanded: true },
]

export function timeframeLabel(timeframeId: string): string {
  return DEFAULT_TIMEFRAMES.find((timeframe) => timeframe.id === timeframeId)?.label ?? timeframeId
}

export function isSupportedTimeframeId(value: string): value is SupportedTimeframeId {
  return SUPPORTED_TIMEFRAME_IDS.includes(value as SupportedTimeframeId)
}

export const DEFAULT_LAYER_CONFIGS: LayerConfig[] = [
  { timeframeId: '5m', layerIndex: 0, visible: true, opacity: 0.2, indicators: [] },
  { timeframeId: '30m', layerIndex: 1, visible: true, opacity: 0.3, indicators: [
    { type: 'ma', params: { period: 10 }, window: 'main', color: '#ffa726' },
  ]},
  { timeframeId: '1d', layerIndex: 2, visible: true, opacity: 1.0, indicators: [
    { type: 'ma', params: { period: 5 }, window: 'main', color: '#ef5350' },
  ]},
]

export const DEFAULT_SETTINGS = {
  symbol: '000006_sz',
  primaryTimeframe: '30m',
  showVolume: true,
  theme: 'dark' as const,
}
