import type { IndicatorResult } from './types.ts'

/** 均线周期固定配色：同一周期在指标、策略、选股页面始终使用同一种颜色。 */
export const MA_PERIODS = [5, 10, 20, 60, 120, 260] as const

export const MA_PERIOD_COLORS: Record<number, string> = {
  5: '#e7c66b',
  10: '#f0a35a',
  20: '#9b8cf2',
  60: '#6c8cff',
  120: '#36c995',
  260: '#e879b9',
}

const FALLBACK_MA_COLORS = ['#36c995', '#5fb3f3', '#e879b9', '#d4a5ff', '#f07178', '#7fd1b9']

export function getMaPeriodColor(period: number): string {
  const configured = MA_PERIOD_COLORS[period]
  if (configured) return configured
  const index = Math.abs(Math.trunc(period)) % FALLBACK_MA_COLORS.length
  return FALLBACK_MA_COLORS[index]!
}

/** 覆盖后端的通用 MA 颜色，避免多条不同周期均线画成同一种颜色。 */
export function applyIndicatorPeriodColor(result: IndicatorResult): IndicatorResult {
  if (result.type !== 'ma' || result.render.plots.length === 0) return result
  const period = Number(result.params.period)
  if (!Number.isFinite(period)) return result
  const color = getMaPeriodColor(period)
  return {
    ...result,
    render: {
      ...result.render,
      plots: result.render.plots.map((plot, index) => index === 0 ? { ...plot, color } : plot),
    },
  }
}
