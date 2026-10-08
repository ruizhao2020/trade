import type { BacktestResult } from '../api/signal.ts'
import type { IndicatorResult, RawKline } from './types.ts'

const dateFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

function dateKey(time: number) {
  return dateFormatter.format(new Date(time))
}

function resolveMarkerTime(
  time: number,
  side: 'entry' | 'exit',
  sourceTimeframe: string,
  targetTimeframe: string,
  klines: RawKline[],
): number | null {
  const exact = klines.find((kline) => kline.openTime === time)
  if (exact) return exact.openTime
  if (sourceTimeframe === targetTimeframe) return null
  const sameDay = klines.filter((kline) => dateKey(kline.openTime) === dateKey(time))
  if (sameDay.length === 0) return null
  return side === 'entry' ? sameDay[0]!.openTime : sameDay.at(-1)!.openTime
}

/**
 * 出场原因 → 展示文案。
 *
 * 图上的标记统一叫「策略卖」，只有带上原因后缀才解释得清"它为什么平仓"——
 * 之前只映射了止损/止盈，于是"到期平仓"在图上看就是一个没有来由的「策略卖」。
 */
export const EXIT_REASON_LABEL: Record<string, string> = {
  stop_loss: '止损',
  take_profit: '止盈',
  timeout: '到期平仓',
  condition: '条件平仓',
}

/** 标记上的原因后缀代码（对应下面 markers 的 labelTags）。 */
const EXIT_REASON_TAG: Record<string, number> = {
  stop_loss: 1, take_profit: 2, timeout: 3, condition: 4,
}

function riskExitTag(exitReason: string): number | undefined {
  return EXIT_REASON_TAG[exitReason]
}

/** 将真实回测交易转换成图表买卖标记，并映射到当前图表周期。 */
export function buildStrategyTradeMarkerResult(
  result: BacktestResult | null,
  targetTimeframe: string,
  klines: RawKline[],
): IndicatorResult[] {
  // 只有持仓（还没有任何已完成交易）也要画买入标记：只设入场条件、没设出场规则的
  // 策略就属于这种，以前这里直接返回空数组，图上什么都看不到。
  if (!result || klines.length === 0) return []
  if (result.trades.length === 0 && !result.openPosition) return []
  const values: Record<string, number>[] = []
  const seen = new Set<string>()
  result.trades.forEach((trade, tradeIndex) => {
    const entryTime = resolveMarkerTime(trade.entryTime, 'entry', result.timeframe, targetTimeframe, klines)
    const exitTime = resolveMarkerTime(trade.exitTime, 'exit', result.timeframe, targetTimeframe, klines)
    const exitTag = riskExitTag(trade.exitReason)
    if (entryTime !== null && !seen.has(`entry:${entryTime}`)) {
      const entryValue: Record<string, number> = { time: entryTime, _trade: 1, _tradeIndex: tradeIndex }
      values.push(entryValue)
      seen.add(`entry:${entryTime}`)
    }
    if (exitTime !== null && !seen.has(`exit:${exitTime}`)) {
      const exitValue: Record<string, number> = { time: exitTime, _trade: -1, _tradeIndex: tradeIndex }
      if (exitTag !== undefined) exitValue._tradeExitTag = exitTag
      values.push(exitValue)
      seen.add(`exit:${exitTime}`)
    }
  })
  values.sort((left, right) => left.time - right.time)
  // 区间结束时仍持仓：只画买入，不画卖出——卖出位置回测自己都不知道，
  // 凭空补一个就等于替策略编了一个出场价。序号排在已完成交易之后。
  const open = result.openPosition
  if (open) {
    const openTime = resolveMarkerTime(open.entryTime, 'entry', result.timeframe, targetTimeframe, klines)
    if (openTime !== null && !seen.has(`entry:${openTime}`)) {
      values.push({ time: openTime, _trade: 1, _tradeIndex: result.trades.length })
      values.sort((left, right) => left.time - right.time)
    }
  }
  if (values.length === 0) return []
  return [{
    type: `strategy_trades_${result.templateId}`,
    params: {},
    values,
    render: {
      window: 'main',
      plots: [],
      markers: [{
        field: '_trade',
        labelIndexField: '_tradeIndex',
        labelTagField: '_tradeExitTag',
        labelTags: Object.fromEntries(Object.entries(EXIT_REASON_TAG).map(([reason, tag]) => [tag, EXIT_REASON_LABEL[reason]!])),
        size: 1.25,
        spacing: 1.5,
        // 使用界面已有的蓝色与橙色强调色，避免与红/绿 K 线冲突。
        buyColor: '#6c8cff',
        sellColor: '#f0a35a',
        buyLabel: '策略买',
        sellLabel: '策略卖',
      }],
    },
  }]
}
