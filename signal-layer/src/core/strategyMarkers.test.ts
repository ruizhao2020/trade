import { describe, expect, it } from 'vitest'
import type { BacktestResult } from '../api/signal.ts'
import type { RawKline } from './types.ts'
import { EXIT_REASON_LABEL, buildStrategyTradeMarkerResult } from './strategyMarkers.ts'

function kline(time: string): RawKline {
  return { openTime: Date.parse(time), open: 1, high: 2, low: 0.5, close: 1.5, volume: 100, isClosed: true }
}

const result: BacktestResult = {
  templateId: 'strategy-1',
  symbol: '000001_sz',
  timeframe: '1d',
  totalTrades: 1,
  winTrades: 1,
  winRate: 100,
  totalReturn: 5,
  avgReturn: 5,
  maxDrawdown: 0,
  profitFactor: 999,
  payoffRatio: 0,
  suggestedPosition: 100,
  openPosition: null,
  trades: [{
    entryTime: Date.parse('2026-09-01T00:00:00+08:00'),
    exitTime: Date.parse('2026-09-02T00:00:00+08:00'),
    entryPrice: 10,
    exitPrice: 10.5,
    pnlPct: 5,
    exitReason: 'condition',
  }],
}

describe('strategy trade chart markers', () => {
  it('uses exact times on the execution timeframe', () => {
    const klines = [
      kline('2026-09-01T00:00:00+08:00'),
      kline('2026-09-02T00:00:00+08:00'),
    ]
    const values = buildStrategyTradeMarkerResult(result, '1d', klines)[0]!.values
    expect(values).toEqual([
      { time: klines[0]!.openTime, _trade: 1, _tradeIndex: 0 },
      { time: klines[1]!.openTime, _trade: -1, _tradeIndex: 0, _tradeExitTag: 4 },
    ])
  })

  it('maps daily entry to first intraday bar and exit to last intraday bar', () => {
    const klines = [
      kline('2026-09-01T09:30:00+08:00'),
      kline('2026-09-01T14:30:00+08:00'),
      kline('2026-09-02T09:30:00+08:00'),
      kline('2026-09-02T14:30:00+08:00'),
    ]
    const values = buildStrategyTradeMarkerResult(result, '30m', klines)[0]!.values
    expect(values).toEqual([
      { time: klines[0]!.openTime, _trade: 1, _tradeIndex: 0 },
      { time: klines[3]!.openTime, _trade: -1, _tradeIndex: 0, _tradeExitTag: 4 },
    ])
  })

  it('does not fabricate markers outside the visible data range', () => {
    expect(buildStrategyTradeMarkerResult(result, '30m', [kline('2026-09-05T09:30:00+08:00')])).toEqual([])
  })

  it('uses UI accent colors, fixed spacing, and indexed labels', () => {
    const marker = buildStrategyTradeMarkerResult(result, '1d', [
      kline('2026-09-01T00:00:00+08:00'),
      kline('2026-09-02T00:00:00+08:00'),
    ])[0]!.render.markers![0]!
    expect(marker).toMatchObject({
      buyColor: '#6c8cff',
      sellColor: '#f0a35a',
      labelIndexField: '_tradeIndex',
      size: 1.25,
      spacing: 1.5,
    })
  })

  it('numbers each buy and sell marker by its trade index', () => {
    const secondResult: BacktestResult = {
      ...result,
      trades: [
        result.trades[0]!,
        {
          ...result.trades[0]!,
          entryTime: Date.parse('2026-09-03T00:00:00+08:00'),
          exitTime: Date.parse('2026-09-04T00:00:00+08:00'),
        },
      ],
    }
    const klines = [
      kline('2026-09-01T00:00:00+08:00'),
      kline('2026-09-02T00:00:00+08:00'),
      kline('2026-09-03T00:00:00+08:00'),
      kline('2026-09-04T00:00:00+08:00'),
    ]
    expect(buildStrategyTradeMarkerResult(secondResult, '1d', klines)[0]!.values).toEqual([
      { time: klines[0]!.openTime, _trade: 1, _tradeIndex: 0 },
      { time: klines[1]!.openTime, _trade: -1, _tradeIndex: 0, _tradeExitTag: 4 },
      { time: klines[2]!.openTime, _trade: 1, _tradeIndex: 1 },
      { time: klines[3]!.openTime, _trade: -1, _tradeIndex: 1, _tradeExitTag: 4 },
    ])
  })

  // 到期平仓（timeout）以前在图上是没有来由的「策略卖」：它必须和止损/止盈一样带原因。
  it.each([
    ['stop_loss', 1, '止损'],
    ['take_profit', 2, '止盈'],
    ['timeout', 3, '到期平仓'],
    ['condition', 4, '条件平仓'],
  ])('tags only the exit side of a %s trade', (exitReason, exitTag, tagLabel) => {
    const riskResult: BacktestResult = {
      ...result,
      trades: [{ ...result.trades[0]!, exitReason }],
    }
    const klines = [
      kline('2026-09-01T00:00:00+08:00'),
      kline('2026-09-02T00:00:00+08:00'),
    ]
    const markerResult = buildStrategyTradeMarkerResult(riskResult, '1d', klines)[0]!

    expect(markerResult.values).toEqual([
      { time: klines[0]!.openTime, _trade: 1, _tradeIndex: 0 },
      { time: klines[1]!.openTime, _trade: -1, _tradeIndex: 0, _tradeExitTag: exitTag },
    ])
    expect(markerResult.render.markers![0]).toMatchObject({
      labelTagField: '_tradeExitTag',
      labelTags: { [exitTag]: tagLabel },
    })
  })

  it('四种出场原因都有中文文案，且图上标签与交易明细共用同一份映射', () => {
    // 交易明细用的是 EXIT_REASON_LABEL[trade.exitReason]，图上用的是 labelTags：
    // 两者必须是同一份数据，否则同一个原因在两处会写成不同的话。
    expect(EXIT_REASON_LABEL).toEqual({
      stop_loss: '止损',
      take_profit: '止盈',
      timeout: '到期平仓',
      condition: '条件平仓',
    })

    const marker = buildStrategyTradeMarkerResult(result, '1d', [
      kline('2026-09-01T00:00:00+08:00'),
      kline('2026-09-02T00:00:00+08:00'),
    ])[0]!.render.markers![0]!
    expect(Object.values(marker.labelTags!)).toEqual(Object.values(EXIT_REASON_LABEL))
    // 没有原因代码的出场（后端新增了原因，前端还没跟上）在图上退化成不带后缀的「策略卖」，
    // 不能凭空显示一个错的标签。
    expect(marker.labelTags![99]).toBeUndefined()
  })
})

describe('仍持仓（open position）', () => {
  const openOnly: BacktestResult = {
    ...result,
    totalTrades: 0,
    trades: [],
    openPosition: {
      entryTime: Date.parse('2026-09-01T00:00:00+08:00'),
      entryPrice: 10,
      side: 'long',
      barsHeld: 5,
      lastTime: Date.parse('2026-09-05T00:00:00+08:00'),
      lastPrice: 11,
      pnlPct: 10,
    },
  }

  it('只有持仓、没有已完成交易时也画出买入标记（这是它以前完全消失的场景）', () => {
    const klines = [
      kline('2026-09-01T00:00:00+08:00'),
      kline('2026-09-05T00:00:00+08:00'),
    ]
    const values = buildStrategyTradeMarkerResult(openOnly, '1d', klines)[0]!.values
    expect(values).toEqual([
      { time: klines[0]!.openTime, _trade: 1, _tradeIndex: 0 },
    ])
  })

  it('不给持仓中的那一笔编造卖出标记', () => {
    const klines = [
      kline('2026-09-01T00:00:00+08:00'),
      kline('2026-09-05T00:00:00+08:00'),
    ]
    const values = buildStrategyTradeMarkerResult(openOnly, '1d', klines)[0]!.values
    expect(values.some((value) => value._trade === -1)).toBe(false)
    expect(values.every((value) => value._tradeExitTag === undefined)).toBe(true)
  })

  it('已完成交易在前、持仓中的买入排在其后，序号不重复', () => {
    const mixed: BacktestResult = {
      ...result,
      trades: [{ ...result.trades[0]!, exitTime: Date.parse('2026-09-02T00:00:00+08:00') }],
      openPosition: {
        entryTime: Date.parse('2026-09-03T00:00:00+08:00'),
        entryPrice: 10, side: 'long', barsHeld: 2,
        lastTime: Date.parse('2026-09-04T00:00:00+08:00'), lastPrice: 12, pnlPct: 20,
      },
    }
    const klines = [
      kline('2026-09-01T00:00:00+08:00'),
      kline('2026-09-02T00:00:00+08:00'),
      kline('2026-09-03T00:00:00+08:00'),
      kline('2026-09-04T00:00:00+08:00'),
    ]

    const values = buildStrategyTradeMarkerResult(mixed, '1d', klines)[0]!.values

    expect(values.map((value) => value._trade)).toEqual([1, -1, 1])
    expect(values.map((value) => value._tradeIndex)).toEqual([0, 0, 1])
  })
})
