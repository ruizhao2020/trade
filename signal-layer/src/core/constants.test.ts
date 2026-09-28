import { describe, expect, it } from 'vitest'
import {
  DEFAULT_TIMEFRAMES, SUPPORTED_TIMEFRAME_IDS,
  conditionTimeframeLabel, isSupportedTimeframeId, resolveConditionTimeframes, timeframeLabel,
} from './constants.ts'

describe('supported chart timeframes', () => {
  it('lists periods from coarsest to finest', () => {
    expect(DEFAULT_TIMEFRAMES.map((timeframe) => timeframe.id)).toEqual(['1d', '60m', '30m', '15m', '5m'])
    expect(timeframeLabel('5m')).toBe('5分钟')
    expect(timeframeLabel('60m')).toBe('60分钟')
    expect(isSupportedTimeframeId('15m')).toBe(true)
  })

  it('keeps the supported id list in the same order as the picker', () => {
    expect(SUPPORTED_TIMEFRAME_IDS).toEqual(DEFAULT_TIMEFRAMES.map((timeframe) => timeframe.id))
  })
})

describe('条件级别的解析与展示', () => {
  it('哨兵值展开为次级周期集合，或的关系由评估方处理', () => {
    expect(resolveConditionTimeframes('secondary', '1d', ['60m', '30m'])).toEqual(['60m', '30m'])
    expect(resolveConditionTimeframes('secondary', '1d', [])).toEqual([])
    expect(resolveConditionTimeframes(undefined, '1d', ['30m'])).toEqual(['1d'])
    expect(resolveConditionTimeframes('30m', '1d', ['30m'])).toEqual(['30m'])
  })

  it('展示文案把哨兵值显示为「次级周期」', () => {
    expect(conditionTimeframeLabel('secondary', '1d')).toBe('次级周期')
    expect(conditionTimeframeLabel(undefined, '1d')).toBe('日线')
    expect(conditionTimeframeLabel('15m', '1d')).toBe('15分钟')
  })
})
