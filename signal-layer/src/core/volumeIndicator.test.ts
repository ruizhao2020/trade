import { describe, expect, it } from 'vitest'
import { volumeClassStyle } from './volumeIndicator.ts'

describe('volume indicator styles', () => {
  it('maps every classified volume bar to a distinct label', () => {
    expect([1, 2, 3, 4, 5].map(code => volumeClassStyle(code).label))
      .toEqual(['缩量', '增量', '倍量', '三倍量', '多倍量'])
  })

  it('uses Chinese red-up green-down colors for normal and increased volume', () => {
    expect(volumeClassStyle(0, true).color).toBe('#ff5b62')
    expect(volumeClassStyle(0, false).color).toBe('#2fc58d')
    expect(volumeClassStyle(2, true).color).toBe('#ff5b62')
    expect(volumeClassStyle(2, false).color).toBe('#2fc58d')
    expect(volumeClassStyle(3, false).color).not.toBe('#2fc58d')
  })
})
