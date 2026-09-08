import { describe, expect, it } from 'vitest'
import type { IndicatorResult } from './types.ts'
import { applyIndicatorPeriodColor, getMaPeriodColor } from './indicatorColors.ts'

function maResult(period: number): IndicatorResult {
  return {
    type: 'ma',
    params: { period },
    values: [{ time: 1, value: 10 }],
    render: {
      window: 'main',
      plots: [{ field: 'value', type: 'line', color: '#same-backend-color', label: `MA${period}` }],
    },
  }
}

describe('indicator period colors', () => {
  it('uses stable distinct colors for supported MA periods', () => {
    const periods = [5, 10, 20, 60, 120, 260]
    const colors = periods.map(getMaPeriodColor)
    expect(new Set(colors).size).toBe(periods.length)
  })

  it('overrides the backend MA color according to its period', () => {
    const ma5 = applyIndicatorPeriodColor(maResult(5))
    const ma10 = applyIndicatorPeriodColor(maResult(10))
    expect(ma5.render.plots[0]?.color).toBe(getMaPeriodColor(5))
    expect(ma10.render.plots[0]?.color).toBe(getMaPeriodColor(10))
    expect(ma5.render.plots[0]?.color).not.toBe(ma10.render.plots[0]?.color)
  })

  it('does not change non-MA indicator plot colors', () => {
    const macd = { ...maResult(5), type: 'macd' }
    expect(applyIndicatorPeriodColor(macd)).toBe(macd)
  })
})
