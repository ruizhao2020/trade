import { describe, expect, it } from 'vitest'
import { findProfileSnapshot } from './profileData.ts'

const profile = {
  prices: [10, 11],
  snapshots: [
    { time: 100, weights: [70, 30], metrics: { peak_price: 10 } },
    { time: 200, weights: [40, 60], metrics: { peak_price: 11 } },
  ],
}

describe('profile snapshot lookup', () => {
  it('uses latest snapshot without cursor time', () => {
    expect(findProfileSnapshot(profile, null)?.time).toBe(200)
  })

  it('uses the hovered bar or nearest prior snapshot', () => {
    expect(findProfileSnapshot(profile, 200)?.time).toBe(200)
    expect(findProfileSnapshot(profile, 150)?.time).toBe(100)
    expect(findProfileSnapshot(profile, 50)?.time).toBe(100)
  })
})
