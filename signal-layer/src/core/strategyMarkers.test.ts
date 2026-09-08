import { describe, expect, it } from 'vitest'
import type { BacktestResult } from '../api/signal.ts'
import type { RawKline } from './types.ts'
import { buildStrategyTradeMarkerResult } from './strategyMarkers.ts'

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
      { time: klines[1]!.openTime, _trade: -1, _tradeIndex: 0 },
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
      { time: klines[3]!.openTime, _trade: -1, _tradeIndex: 0 },
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
      { time: klines[1]!.openTime, _trade: -1, _tradeIndex: 0 },
      { time: klines[2]!.openTime, _trade: 1, _tradeIndex: 1 },
      { time: klines[3]!.openTime, _trade: -1, _tradeIndex: 1 },
    ])
  })

  it.each([
    ['stop_loss', 1, '止损'],
    ['take_profit', 2, '止盈'],
  ])('tags both sides of a %s trade', (exitReason, exitTag, tagLabel) => {
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
      { time: klines[0]!.openTime, _trade: 1, _tradeIndex: 0, _tradeExitTag: exitTag },
      { time: klines[1]!.openTime, _trade: -1, _tradeIndex: 0, _tradeExitTag: exitTag },
    ])
    expect(markerResult.render.markers![0]).toMatchObject({
      labelTagField: '_tradeExitTag',
      labelTags: { [exitTag]: tagLabel },
    })
  })
})
