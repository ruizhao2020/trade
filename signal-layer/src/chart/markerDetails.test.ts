import { describe, expect, it } from 'vitest'
import type { BuySellPoint, Divergence } from '../core/types.ts'
import { buildBuySellMarkerDetail, buildDivergenceMarkerDetail, buySellMarkerLabel, divergenceMarkerId, divergenceMarkerLabel, placeMarkerDetailPopup, arrangeSeriesMarkersVertically } from './markerDetails.ts'

const divergence: Divergence = {
  index: 2,
  type: 'bottom',
  level: 'bi',
  kind: 'consolidation',
  price: 10.25,
  time: 1_757_500_000_000,
  zhongshuIndex: 1,
  referenceBiIndex: 8,
  currentBiIndex: 10,
  referencePower: 20,
  currentPower: 8,
  strengthRatio: 0.4,
  confirmed: true,
  reasons: ['创新低', '力度衰减'],
}

describe('indicator marker details', () => {
  it('builds divergence information supplied by the indicator', () => {
    const point = { type: 'buy1', divergenceIndex: 2 } as BuySellPoint
    const detail = buildDivergenceMarkerDetail(divergence, [point])

    expect(detail.id).toBe(divergenceMarkerId(divergence))
    expect(detail.title).toBe('底背驰')
    expect(detail.reasons).toEqual(['创新低', '力度衰减'])
    expect(detail.fields).toContainEqual({ label: '力度衰减', value: '60.00%' })
    expect(detail.fields).toContainEqual({ label: '对应信号', value: '一买' })
  })

  it('marks both top and bottom divergence labels as interactive', () => {
    expect(divergenceMarkerLabel(divergence)).toBe('[底背驰]')
    expect(divergenceMarkerLabel({ ...divergence, type: 'top' })).toBe('[顶背驰]')
    expect(buildDivergenceMarkerDetail({ ...divergence, type: 'top' }, []).title).toBe('顶背驰')
  })

  it('builds details and bracketed labels for all buy and sell points', () => {
    const labels = { buy1: '一买', buy2: '二买', buy3: '三买', sell1: '一卖', sell2: '二卖', sell3: '三卖' } as const
    for (const type of ['buy1', 'buy2', 'buy3', 'sell1', 'sell2', 'sell3'] as const) {
      const point = { type, price: 10, time: divergence.time, biIndex: 3, confirmed: true, strength: 0.8 }
      const detail = buildBuySellMarkerDetail(point)
      expect(buySellMarkerLabel(point)).toBe(`[${labels[type]}]`)
      expect(detail.fields).toContainEqual({ label: '对应笔', value: '笔 3' })
      expect(detail.title).toBe(labels[type])
    }
  })

  it('keeps the popup inside the chart near each edge', () => {
    expect(placeMarkerDetailPopup({ x: 790, y: 590 }, { width: 800, height: 600 }))
      .toEqual({ left: 476, top: 236 })
    expect(placeMarkerDetailPopup({ x: 5, y: 5 }, { width: 800, height: 600 }))
      .toEqual({ left: 19, top: 19 })
  })

  it('stacks coincident markers vertically in semantic order', () => {
    const markers = arrangeSeriesMarkersVertically([
      { id: 'chan:buy-sell:sell1', time: 1 as never, position: 'atPriceTop', price: 100, color: '#f00', shape: 'arrowDown', text: '一卖' },
      { id: 'chan:duan-point:3', time: 1 as never, position: 'atPriceTop', price: 100, color: '#00f', shape: 'square', text: 'D3' },
      { id: 'chan:bi-point:21', time: 1 as never, position: 'atPriceTop', price: 100, color: '#ff0', shape: 'circle', text: '21' },
    ])
    const byId = Object.fromEntries(markers.map(marker => [marker.id, 'price' in marker ? marker.price : 0]))

    expect(byId['chan:bi-point:21']).toBeCloseTo(100.344)
    expect(byId['chan:duan-point:3']).toBeCloseTo(101.24)
    expect(byId['chan:buy-sell:sell1']).toBeCloseTo(103.28)
  })

  it('keeps marker and label layers separated in screen pixels', () => {
    const markers = arrangeSeriesMarkersVertically([
      { id: 'chan:bi-point:1', time: 1 as never, position: 'atPriceTop', price: 100, color: '#ff0', shape: 'circle', text: '1' },
      { id: 'chan:duan-point:1', time: 1 as never, position: 'atPriceTop', price: 100, color: '#00f', shape: 'square', text: 'D1' },
      { id: 'chan:divergence:1:1', time: 1 as never, position: 'atPriceTop', price: 100, color: '#f0f', shape: 'square', text: '[顶背驰]' },
      { id: 'chan:buy-sell:sell1', time: 1 as never, position: 'atPriceTop', price: 100, color: '#f00', shape: 'arrowDown', text: '[一卖]' },
    ], {
      priceToCoordinate: (price) => 1000 - price * 10,
      coordinateToPrice: (coordinate) => (1000 - coordinate) / 10,
    })
    const byId = Object.fromEntries(markers.map(marker => [marker.id, marker.price]))
    expect(byId['chan:bi-point:1']).toBeCloseTo(100.8)
    expect(byId['chan:duan-point:1']).toBeCloseTo(103.4)
    expect(byId['chan:divergence:1:1']).toBeCloseTo(106)
    expect(byId['chan:buy-sell:sell1']).toBeCloseTo(108.8)
  })
})

// ── 量价形态的点击说明 ──────────────────────────────────────────────────
import type { IndicatorResult } from '../core/types.ts'
import { buildFormMarkerDetail, formMarkerId, formSignalNumbers, parseFormMarkerId, popupMarkerLabel } from './markerDetails.ts'

const TIME_MS = 1_757_500_000_000

function volumePriceResult(): IndicatorResult {
  const marker = (field: string, label: string, index: number, rule: string) => ({
    field, buyColor: '#ff5b62', sellColor: '#2fc58d', buyLabel: label, sellLabel: label, index, rule,
  })
  return {
    type: 'volume_price',
    params: { volume_ratio_min: 1.5, breakout_window: 20, position_window: 60, consecutive_bars: 3 },
    values: [{
      time: TIME_MS,
      volume: 200_000, baseline: 100_000, relative_volume: 2,
      change_pct: 0.5, drawdown_pct: 5,
      volume_stagnation: -1, price_volume_rise: 1,
    }],
    render: {
      window: 'sub',
      plots: [],
      markers: [
        marker('price_volume_rise', '量价齐升', 3, '连续 {consecutive_bars} 根 K 线逐根收涨、且成交量逐根放大'),
        marker('volume_stagnation', '放量滞涨', 4, '相对量能 ≥ {volume_ratio_min} 且 收阳、当日涨幅在 0% ~ 1% 之间'),
      ],
    },
  }
}

describe('量价形态的点击说明', () => {
  it('给出标号、当前值与替换参数后的计算口径', () => {
    const detail = buildFormMarkerDetail(volumePriceResult(), Math.round(TIME_MS / 1000))!

    // 同一根上两个形态成立时，按标记顺序取第一个作标题
    expect(detail.title).toBe('量价齐升')
    expect(detail.subtitle).toBe('信号 #1 · 买入侧')
    expect(detail.accentColor).toBe('#ff5b62')
    expect(detail.reasonsTitle).toBe('计算口径')
    expect(detail.reasons?.[0]).toContain('连续 3 根')
    expect(detail.fields).toContainEqual({ label: '相对量能', value: '2' })
    expect(detail.fields).toContainEqual({ label: '当日涨幅', value: '+0.50%' })
    expect(detail.fields).toContainEqual({ label: '距高点回撤', value: '5.00%' })
    expect(detail.fields).toContainEqual({ label: '同时成立', value: '放量滞涨 #2' })
  })

  it('该根没有形态、或时间对不上时返回 undefined', () => {
    const result = volumePriceResult()
    result.values[0]!.volume_stagnation = 0
    result.values[0]!.price_volume_rise = 0
    expect(buildFormMarkerDetail(result, Math.round(TIME_MS / 1000))).toBeUndefined()
    expect(buildFormMarkerDetail(volumePriceResult(), 1)).toBeUndefined()
  })

  it('没有口径文本的指标（普通标记）不参与弹窗', () => {
    const result = volumePriceResult()
    result.render.markers = result.render.markers!.map((marker) => ({ ...marker, rule: undefined }))
    expect(buildFormMarkerDetail(result, Math.round(TIME_MS / 1000))).toBeUndefined()
  })
})

describe('标记 id 与中括号约定', () => {
  it('按字段精确取用：同一根上两个形态，点哪个显示哪个', () => {
    const detail = buildFormMarkerDetail(volumePriceResult(), Math.round(TIME_MS / 1000), 'volume_stagnation')!
    expect(detail.title).toBe('放量滞涨')
    expect(detail.subtitle).toBe('信号 #2 · 顶部预警')
    expect(detail.accentColor).toBe('#2fc58d')
    expect(detail.reasons?.[0]).toContain('相对量能 ≥ 1.5')
    // 只显示被点中的那一个，不再列"同时成立"
    expect(detail.fields.find((field) => field.label === '同时成立')).toBeUndefined()
  })

  it('marker id 往返可解析，缠论前缀不参与', () => {
    const id = formMarkerId('volume_price', 'failed_breakout', 1761500000)
    expect(parseFormMarkerId(id)).toEqual({ resultType: 'volume_price', field: 'failed_breakout', timeSeconds: 1761500000 })
    expect(parseFormMarkerId('chan:buy-sell:buy1:123:4')).toBeUndefined()
    expect(parseFormMarkerId('form:volume_price')).toBeUndefined()
  })

  it('带弹窗的指标文字加中括号，普通文字不加', () => {
    expect(popupMarkerLabel('放量冲高回落', true)).toBe('[放量冲高回落]')
    expect(popupMarkerLabel('放量冲高回落', true, 12)).toBe('[12. 放量冲高回落]')
    expect(popupMarkerLabel('底分型', false)).toBe('底分型')
  })
})

describe('信号自增编号', () => {
  it('按时间先后累计，同一根再按形态顺序，每个触发占一个号', () => {
    const result = volumePriceResult()
    result.values = [
      { time: 1_000_000, price_volume_rise: 1, volume_stagnation: -1 },
      { time: 2_000_000, price_volume_rise: 0, volume_stagnation: -1 },
      { time: 3_000_000, price_volume_rise: 0, volume_stagnation: 0 },
    ]

    const numbers = formSignalNumbers(result)
    expect(numbers.get('price_volume_rise:1000')).toBe(1)
    expect(numbers.get('volume_stagnation:1000')).toBe(2)
    expect(numbers.get('volume_stagnation:2000')).toBe(3)
    expect(numbers.size).toBe(3)
  })

  it('弹窗与图上文字使用同一个编号', () => {
    const result = volumePriceResult()
    result.values = [
      { time: 1_000_000, price_volume_rise: 1, volume_stagnation: 0 },
      { time: 2_000_000, price_volume_rise: 0, volume_stagnation: -1,
        volume: 200_000, baseline: 100_000, relative_volume: 2, change_pct: 0.5, drawdown_pct: 5 },
    ]

    const detail = buildFormMarkerDetail(result, 2000, 'volume_stagnation')!
    expect(detail.subtitle).toBe('信号 #2 · 顶部预警')
    const number = formSignalNumbers(result).get('volume_stagnation:2000')
    expect(popupMarkerLabel('放量滞涨', true, number)).toBe('[2. 放量滞涨]')
  })
})
