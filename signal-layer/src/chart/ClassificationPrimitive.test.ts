import { describe, expect, it } from 'vitest'
import { buildClassificationBranches } from './ClassificationPrimitive.ts'

describe('完全分类分支', () => {
  it('按中枢上下沿换算三条分支：向上延续 / 中枢扩展 / 向下转折', () => {
    const branches = buildClassificationBranches({
      position: 'inside',
      zhongshuHigh: 110,
      zhongshuLow: 100,
      lastClose: 105,
      scenarios: [],
    })

    expect(branches.map((item) => item.label)).toEqual(['向上延续', '中枢扩展', '向下转折'])
    expect(branches[0]!.price).toBe(120)
    expect(branches[1]!.price).toBe(105)
    expect(branches[2]!.price).toBe(90)
  })

  it('缺少中枢边界时不画分支', () => {
    expect(buildClassificationBranches({ position: 'unknown', scenarios: [] })).toEqual([])
  })
})
