import { describe, expect, it } from 'vitest'
import {
  ARROW_OFFSET_RATIO, arrowEndpointValue, arrowHeadPoints, arrowPadOf,
} from './DivergenceArrowPrimitive.ts'

describe('MACD 柱群背驰箭头', () => {
  it('顶背驰画在柱群上方，底背驰画在下方', () => {
    expect(arrowEndpointValue(0.5, 'top', 0.1)).toBeCloseTo(0.6)
    expect(arrowEndpointValue(-0.5, 'bottom', 0.1)).toBeCloseTo(-0.6)
  })

  it('箭头尖落在终点，两翼在尖端的后侧', () => {
    const from = { x: 10, y: 50 }
    const to = { x: 110, y: 20 }

    const [tip, left, right] = arrowHeadPoints(from, to)

    expect(tip).toEqual(to)
    expect(left.x).toBeLessThan(to.x)
    expect(right.x).toBeLessThan(to.x)
  })

  it('偏移量取箭头峰值的固定比例，且不受时间戳字段影响', () => {
    const arrows = [
      {
        fromTime: 1_700_000_000_000, fromValue: 0.4,
        toTime: 1_700_086_400_000, toValue: -1.2,
        direction: 'top' as const, color: '#ff5b62',
      },
    ]

    // 0.4 / -1.2 的绝对值最大是 1.2；时间戳（1.7e12）不能参与
    expect(arrowPadOf(arrows)).toBeCloseTo(1.2 * ARROW_OFFSET_RATIO)
    expect(arrowPadOf([])).toBe(0)
  })
})
