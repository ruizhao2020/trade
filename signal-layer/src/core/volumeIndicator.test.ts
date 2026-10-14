import { describe, expect, it } from 'vitest'
import {
  isVolumeBarSeries,
  shouldSkipVolumePane,
  volumeBarColor,
  volumeClassStyle,
  volumeShapeStyle,
} from './volumeIndicator.ts'

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

describe('成交量柱的上色判据', () => {
  it('画的是 volume 柱且带了 is_up，就逐根按阴阳上色', () => {
    expect(isVolumeBarSeries('volume', [{ volume: 1, is_up: 1 }])).toBe(true)
    expect(isVolumeBarSeries('volume', [{ volume: 1, is_up: 0 }])).toBe(true)
    // 量价输出同样的字段，因此落在同一套判据里——不必去改指标名列表
    expect(isVolumeBarSeries('volume', [{ volume: 1, is_up: 1 }, { volume: 2 }])).toBe(true)
  })

  it('别的柱状字段、或没有 is_up 的序列，仍用 RenderSpec 声明的颜色', () => {
    expect(isVolumeBarSeries('histogram', [{ histogram: 1, is_up: 1 }])).toBe(false)
    expect(isVolumeBarSeries('volume', [{ volume: 1 }])).toBe(false)
    expect(isVolumeBarSeries('volume', [])).toBe(false)
  })
})

describe('避免重复的量能副图', () => {
  it('量柱结构或量价在场时，普通成交量不再单独出图', () => {
    expect(shouldSkipVolumePane('volume', ['volume', 'volume_structure'])).toBe(true)
    expect(shouldSkipVolumePane('volume', ['volume', 'volume_price'])).toBe(true)
    expect(shouldSkipVolumePane('volume', ['volume', 'volume_price', 'volume_structure'])).toBe(true)
  })

  it('只有成交量自己时照常出图', () => {
    expect(shouldSkipVolumePane('volume', ['volume'])).toBe(false)
    expect(shouldSkipVolumePane('volume', ['volume', 'ma', 'macd'])).toBe(false)
  })

  it('被跳过的只有普通成交量：自带量柱的那两个指标自己不能被跳掉', () => {
    const types = ['volume', 'volume_price', 'volume_structure']
    expect(shouldSkipVolumePane('volume_price', types)).toBe(false)
    expect(shouldSkipVolumePane('volume_structure', types)).toBe(false)
    // 别的副图指标（如 MACD）不受影响
    expect(shouldSkipVolumePane('macd', types)).toBe(false)
  })
})
