import { describe, expect, it } from 'vitest'
import type { BuySellPoint, Divergence } from '../core/types.ts'
import { buildDivergenceMarkerDetail, divergenceMarkerId, divergenceMarkerLabel, placeMarkerDetailPopup, arrangeSeriesMarkersVertically } from './markerDetails.ts'

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

    expect(byId['chan:bi-point:21']).toBe(100.8)
    expect(byId['chan:duan-point:3']).toBe(101.6)
    expect(byId['chan:buy-sell:sell1']).toBe(102.4)
  })
})
