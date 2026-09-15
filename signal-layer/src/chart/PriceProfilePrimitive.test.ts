import { describe, expect, it } from 'vitest'
import { hasVisibleProfileWeight } from './PriceProfilePrimitive.ts'

describe('price profile visibility', () => {
  it('does not render zero or floating-point-noise chip weights', () => {
    expect(hasVisibleProfileWeight({ price: 10, weight: 0, isProfit: true })).toBe(false)
    expect(hasVisibleProfileWeight({ price: 10, weight: 1e-10, isProfit: true })).toBe(false)
    expect(hasVisibleProfileWeight({ price: 10, weight: Number.NaN, isProfit: true })).toBe(false)
  })

  it('renders positive chip weights without forcing a minimum pixel width', () => {
    expect(hasVisibleProfileWeight({ price: 10, weight: 0.000001, isProfit: true })).toBe(true)
  })
})
