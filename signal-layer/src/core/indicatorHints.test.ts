import { describe, expect, it } from 'vitest'
import { PARAM_HINTS } from './indicatorHints.ts'

/**
 * 参数说明的覆盖率契约。
 *
 * 用**真实后端报文**（`indicator-list.json`）里的 default_params 逐个核对：
 * 后端给指标加了新参数而前端忘了写说明时，这条测试会失败——否则那个参数就
 * 悄悄出现在界面上、没人知道它是什么意思。这正是一个参数面板最容易积累
 * 技术债的地方。
 */
const fixtures = import.meta.glob('../testing/fixtures/indicator-list.json', {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>

function indicatorParams(type: string): string[] {
  const raw = Object.values(fixtures)[0]
  const parsed = JSON.parse(raw) as { indicators: Array<{ type: string; default_params: Record<string, number> }> }
  const target = parsed.indicators.find((item) => item.type === type)
  return target ? Object.keys(target.default_params) : []
}

describe('指标参数说明', () => {
  for (const type of ['liquidity_zone', 'support_resistance']) {
    it(`${type} 的每个参数都有说明`, () => {
      const params = indicatorParams(type)
      expect(params.length).toBeGreaterThan(0)
      const missing = params.filter((key) => !PARAM_HINTS[key]?.trim())
      expect(missing).toEqual([])
    })
  }

  it('说明写的是"改了会怎样"，不是把标签换个说法', () => {
    for (const [key, hint] of Object.entries(PARAM_HINTS)) {
      expect(hint.length, `${key} 的说明太短，讲不清影响`).toBeGreaterThan(20)
    }
  })

  it('没有多余的孤儿说明（参数改名后留下的说明会被这条抓出来）', () => {
    const known = new Set([
      ...indicatorParams('liquidity_zone'),
      ...indicatorParams('support_resistance'),
    ])
    const orphans = Object.keys(PARAM_HINTS).filter((key) => !known.has(key))
    expect(orphans).toEqual([])
  })
})
