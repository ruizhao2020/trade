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
