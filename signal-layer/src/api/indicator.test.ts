import { afterEach, describe, expect, it, vi } from 'vitest'
import { calculateIndicators, calculateIndicatorsDetailed } from './indicator.ts'

describe('indicator API partial success', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('returns successful indicators when another indicator fails', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      symbol: '000001_sz',
      timeframe: '1d',
      results: [{
        type: 'ma',
        params: { period: 5 },
        values: [{ time: 1, value: 10 }],
        render: {
          window: 'main',
          plots: [{ field: 'value', type: 'line', color: '#fff', label: 'MA5' }],
          markers: [],
        },
        cached: false,
      }],
      errors: [{ type: 'broken', code: 'invalid_parameters', message: '参数错误' }],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    const detailed = await calculateIndicatorsDetailed('000001_sz', '1d', [
      { type: 'ma', params: { period: 5 } },
      { type: 'broken', params: {} },
    ])
    expect(detailed.results.map((item) => item.type)).toEqual(['ma'])
    expect(detailed.errors).toEqual([{ type: 'broken', code: 'invalid_parameters', message: '参数错误' }])
  })

  it('keeps the compatibility helper focused on successful results', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      symbol: '000001_sz', timeframe: '1d', results: [],
      errors: [{ type: 'broken', code: 'calculation_failed', message: '失败' }],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    await expect(calculateIndicators('000001_sz', '1d', [{ type: 'broken', params: {} }]))
      .resolves.toEqual([])
  })
})
