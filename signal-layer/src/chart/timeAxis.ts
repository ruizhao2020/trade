/**
 * 图表时间轴的显示格式化。
 *
 * 背景：Lightweight-Charts 只认 UTCTimestamp，时间轴与十字光标都按 **UTC** 渲染。
 * 而后端的日线时间戳是"北京时间 00:00"（= 前一日 16:00Z），分钟线同理——
 * 不做格式化的话，日线日期会整体早一天（23 日的 K 线显示成 22 日），
 * 分钟线的时间会差 8 小时。
 *
 * 这里把坐标轴刻度与十字光标统一按交易所在时区（Asia/Shanghai）格式化，
 * 只改显示、不动任何时间戳与数据。
 */
import { TickMarkType } from 'lightweight-charts'
import type { Time } from 'lightweight-charts'

/** 交易所在时区。当前市场只有 A 股与国内期货，统一按北京时间显示。 */
export const DISPLAY_TIME_ZONE = 'Asia/Shanghai'

const DEFAULT_LOCALE = 'zh-CN'

// Intl 格式化器的构造不便宜，而刻度格式化每次重绘都要跑十几次、十字光标每移动一次
// 也要跑两次。按 locale + 选项缓存，避免每次调用都新建实例。
const formatterCache = new Map<string, Intl.DateTimeFormat>()

function getFormatter(locale: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${locale}|${JSON.stringify(options)}`
  let formatter = formatterCache.get(key)
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(locale, { timeZone: DISPLAY_TIME_ZONE, ...options })
    formatterCache.set(key, formatter)
  }
  return formatter
}

/**
 * 格式化失败（非法时间戳、极端值）时返回空串，绝不能把异常抛回图表库：
 * 刻度格式化在每次重绘里都会被调用，抛错会中断这次重绘，表现就是光标停在原地。
 */
function formatInZone(seconds: number, options: Intl.DateTimeFormatOptions, locale = DEFAULT_LOCALE): string {
  if (!Number.isFinite(seconds)) return ''
  try {
    return getFormatter(locale, options).format(new Date(seconds * 1000))
  } catch {
    return ''
  }
}

/** 时分始终用 24 小时制、且以 en-GB 输出，避免某些 locale 把零点格式化成 24:00。 */
function clockText(seconds: number, withSeconds = false): string {
  return formatInZone(
    seconds,
    withSeconds
      ? { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }
      : { hour: '2-digit', minute: '2-digit', hour12: false },
    'en-GB',
  )
}

/** 时间轴刻度：按图表给的刻度类型输出本地日期/时间。 */
export function formatTickMark(time: Time, tickMarkType: TickMarkType, locale = DEFAULT_LOCALE): string {
  if (typeof time !== 'number' || !Number.isFinite(time)) return ''
  switch (tickMarkType) {
    case TickMarkType.Year:
      return formatInZone(time, { year: 'numeric' }, locale)
    case TickMarkType.Month:
      return formatInZone(time, { month: 'short' }, locale)
    case TickMarkType.DayOfMonth:
      return formatInZone(time, { day: 'numeric' }, locale)
    case TickMarkType.Time:
      return clockText(time)
    case TickMarkType.TimeWithSeconds:
      return clockText(time, true)
    default:
      return ''
  }
}

/** 十字光标的时间标签：日线（本地 00:00 落点）只显示日期，分钟线补上时分。 */
export function formatCrosshairTime(time: Time, locale = DEFAULT_LOCALE): string {
  if (typeof time !== 'number' || !Number.isFinite(time)) return ''
  const date = { year: 'numeric' as const, month: '2-digit' as const, day: '2-digit' as const }
  return clockText(time) === '00:00'
    ? formatInZone(time, date, locale)
    : formatInZone(time, { ...date, hour: '2-digit', minute: '2-digit', hour12: false }, locale)
}
