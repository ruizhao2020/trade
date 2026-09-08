import { describe, expect, it } from 'vitest'
import { DEFAULT_TIMEFRAMES, isSupportedTimeframeId, timeframeLabel } from './constants.ts'

describe('supported chart timeframes', () => {
  it('includes five-minute, thirty-minute, and daily periods', () => {
    expect(DEFAULT_TIMEFRAMES.map((timeframe) => timeframe.id)).toEqual(['5m', '30m', '1d'])
    expect(timeframeLabel('5m')).toBe('5分钟')
    expect(isSupportedTimeframeId('5m')).toBe(true)
  })
})
