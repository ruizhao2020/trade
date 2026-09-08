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

function riskExitTag(exitReason: string): number | undefined {
  if (exitReason === 'stop_loss') return 1
  if (exitReason === 'take_profit') return 2
  return undefined
}

/** 将真实回测交易转换成图表买卖标记，并映射到当前图表周期。 */
export function buildStrategyTradeMarkerResult(
  result: BacktestResult | null,
  targetTimeframe: string,
  klines: RawKline[],
): IndicatorResult[] {
  if (!result || result.trades.length === 0 || klines.length === 0) return []
  const values: Record<string, number>[] = []
  const seen = new Set<string>()
  result.trades.forEach((trade, tradeIndex) => {
    const entryTime = resolveMarkerTime(trade.entryTime, 'entry', result.timeframe, targetTimeframe, klines)
    const exitTime = resolveMarkerTime(trade.exitTime, 'exit', result.timeframe, targetTimeframe, klines)
    const exitTag = riskExitTag(trade.exitReason)
    if (entryTime !== null && !seen.has(`entry:${entryTime}`)) {
      const entryValue: Record<string, number> = { time: entryTime, _trade: 1, _tradeIndex: tradeIndex }
      if (exitTag !== undefined) entryValue._tradeExitTag = exitTag
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
        labelTags: { 1: '止损', 2: '止盈' },
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
