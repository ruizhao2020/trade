import { describe, expect, it } from 'vitest'
import { volumeBarColor, volumeClassStyle, volumeShapeStyle } from './volumeIndicator.ts'

describe('volume indicator styles', () => {
  it('maps every classified volume bar to a distinct label', () => {
    expect([1, 2, 3, 4, 5].map(code => volumeClassStyle(code).label))
      .toEqual(['缩量', '增量', '倍量', '三倍量', '多倍量'])
  })

  it('maps the five structural volume shapes', () => {
    expect([1, 2, 3, 4, 5].map(code => volumeShapeStyle(code).label))
      .toEqual(['高量柱', '低量柱', '平量柱', '梯量柱', '连续缩量'])
    expect(volumeBarColor(true)).toBe('#ff5b62')
    expect(volumeBarColor(false)).toBe('#2fc58d')
  })

  it('uses Chinese red-up green-down colors for normal and increased volume', () => {
    expect(volumeClassStyle(0, true).color).toBe('#ff5b62')
    expect(volumeClassStyle(0, false).color).toBe('#2fc58d')
    expect(volumeClassStyle(2, true).color).toBe('#ff5b62')
    expect(volumeClassStyle(2, false).color).toBe('#2fc58d')
    expect(volumeClassStyle(3, false).color).not.toBe('#2fc58d')
  })
})
