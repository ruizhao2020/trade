import { describe, expect, it } from 'vitest'
import { TickMarkType } from 'lightweight-charts'
import type { UTCTimestamp } from 'lightweight-charts'
import { DISPLAY_TIME_ZONE, formatCrosshairTime, formatTickMark } from './timeAxis.ts'

/**
 * 日线时间戳是"北京时间 00:00"，也就是 UTC 的前一日 16:00。
 * 图表库默认按 UTC 渲染，会把 23 日的 K 线显示成 22 日——这些用例守住修复。
 */
const DAILY_23_OCT_2026 = 1792684800 as UTCTimestamp  // 2026-10-23 00:00 +08:00 = 2026-10-22 16:00Z
const INTRADAY_0935_23_OCT = (Date.UTC(2026, 9, 23, 1, 35) / 1000) as UTCTimestamp  // 09:35 +08:00

describe('时间轴显示格式化', () => {
  it('时区固定为北京时间', () => {
    expect(DISPLAY_TIME_ZONE).toBe('Asia/Shanghai')
  })

  it('日线刻度显示本地日期，不会早一天', () => {
    expect(formatTickMark(DAILY_23_OCT_2026, TickMarkType.DayOfMonth)).toBe('23日')
    expect(formatTickMark(DAILY_23_OCT_2026, TickMarkType.Month)).toBe('10月')
    expect(formatTickMark(DAILY_23_OCT_2026, TickMarkType.Year)).toBe('2026年')
  })

  it('分钟线刻度显示北京时间，不是 UTC', () => {
    expect(formatTickMark(INTRADAY_0935_23_OCT, TickMarkType.Time)).toBe('09:35')
    expect(formatTickMark(INTRADAY_0935_23_OCT, TickMarkType.TimeWithSeconds)).toBe('09:35:00')
  })

  it('十字光标：日线只显示日期，分钟线带时分', () => {
    expect(formatCrosshairTime(DAILY_23_OCT_2026)).toBe('2026/10/23')
    expect(formatCrosshairTime(INTRADAY_0935_23_OCT)).toBe('2026/10/23 09:35')
  })

  it('非数字时间（BusinessDay / 字符串）不处理', () => {
    expect(formatTickMark({ year: 2026, month: 10, day: 23 }, TickMarkType.DayOfMonth)).toBe('')
    expect(formatCrosshairTime('2026-10-23')).toBe('')
  })

  it('非法时间戳不抛异常，退化为空标签', () => {
    // 刻度/光标格式化在每次重绘里都会调用，抛错会中断这次重绘（表现为光标不跟随）。
    expect(formatTickMark(Number.NaN as unknown as UTCTimestamp, TickMarkType.DayOfMonth)).toBe('')
    expect(formatCrosshairTime(Number.NaN as unknown as UTCTimestamp)).toBe('')
    expect(formatTickMark(Number.POSITIVE_INFINITY as unknown as UTCTimestamp, TickMarkType.Time)).toBe('')
    // 超出 Date 可表示范围时 Intl 会抛 RangeError，必须被兜住
    expect(formatCrosshairTime(9e15 as unknown as UTCTimestamp)).toBe('')
  })

  it('跨年边界按北京时间判断', () => {
    // 2027-01-01 00:00 +08:00 = 2026-12-31 16:00Z
    const newYear = (Date.UTC(2026, 11, 31, 16, 0) / 1000) as UTCTimestamp
    expect(formatTickMark(newYear, TickMarkType.Year)).toBe('2027年')
    expect(formatTickMark(newYear, TickMarkType.DayOfMonth)).toBe('1日')
  })
})
