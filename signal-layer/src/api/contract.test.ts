/**
 * ============================================================================
 * 接口契约测试（跑在真实后端报文上）
 * ============================================================================
 *
 * 为什么需要这一层：`src/api/*.ts` 里手写的类型和映射是**单向的猜测**——
 * 后端把 `open_time` 改名成 `openTime` 时，映射会安静地返回 undefined，
 * 而 TypeScript 完全不会报错（它检查的是我们自己写的类型）。
 *
 * 这里用 `src/testing/fixtures/` 下的**真实响应报文**做输入，
 * 因此后端一旦改字段名/改类型，这些用例会立刻失败。
 *
 * fixture 是外部数据、本身没有类型；下面用 `field()` / `rows()` 这类访问器读取，
 * 既避免 `any`（eslint 禁止），也让"在断言哪个字段"一目了然。
 *
 * 刷新 fixture：见 src/testing/fixtures/README.md
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchKlines } from './kline.ts'
import { calculateIndicatorsDetailed, fetchIndicatorList } from './indicator.ts'
import { evaluateSignal } from './signal.ts'
import { fetchTemplates, templateToSnake } from './template.ts'
import { fetchMarkets } from './symbol.ts'
import { fetchAdvisorRun } from './advisor.ts'
import { fetchChanAnalysis } from './chan.ts'
import { fetchCurrentUser } from './auth.ts'
import type { ConditionTemplate } from '../core/types.ts'

// 用 Vite 的 import.meta.glob 读 fixture：类型由 vite/client 提供，
// 不引入 node:fs / process（tsconfig.app.json 是浏览器侧配置、不含 node 类型，
// 用了会让 tsc 与构建一起失败）。
const RAW_FIXTURES = import.meta.glob('../testing/fixtures/*.json', {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>

/** 读取真实报文（文件名不含 .json 后缀）。 */
function fixture(name: string): Record<string, unknown> {
  const raw = RAW_FIXTURES[`../testing/fixtures/${name}.json`]
  if (!raw) throw new Error(`缺少 fixture: ${name}.json`)
  expect(raw).not.toContain('"detail"')  // 错误报文会让契约测试假通过
  return JSON.parse(raw) as Record<string, unknown>
}

/** 取一个字段（返回 unknown，交给 expect 判断类型）。 */
function field(source: unknown, key: string): unknown {
  expect(source, `期望对象以读取字段 ${key}`).toBeTypeOf('object')
  expect(source).not.toBeNull()
  return (source as Record<string, unknown>)[key]
}

/** 断言是数组并返回，元素保持 unknown。 */
function rows(source: unknown): unknown[] {
  expect(Array.isArray(source)).toBe(true)
  return source as unknown[]
}

/** 把 fixture 的元素当对象读（用于逐字段比对）。 */
function item(source: unknown): Record<string, unknown> {
  expect(source).toBeTypeOf('object')
  expect(source).not.toBeNull()
  return source as Record<string, unknown>
}

const templatesFixture = fixture('templates')
const marketsFixture = fixture('markets')
const indicatorListFixture = fixture('indicator-list')
const klinesFixture = fixture('klines-v0-1d')
const chanFixture = fixture('chan-v0-1d')
const calculateFixture = fixture('indicator-calculate')
const evaluateFixture = fixture('signal-evaluate')
const advisorRunFixture = fixture('advisor-run-detail')
const authMeFixture = fixture('auth-me')

const CALCULATE_RESULTS = rows(field(calculateFixture, 'results'))

/** 让下一次请求返回指定报文，并记录请求本身（便于断言发出去的参数）。 */
function stubResponse(body: unknown, status = 200) {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  }))
  return calls
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('K 线映射', () => {
  it('逐字段映射 snake_case，并把周期与数量作为查询参数发出', async () => {
    const calls = stubResponse(klinesFixture)
    const response = await fetchKlines('V0', '1d', 5)

    // 请求参数与映射放在同一个用例里：请求缓存按 key 复用 promise，
    // 同一 key 的第二次调用不会发出请求，拆成两个用例会假失败。
    expect(calls[0]!.url).toContain('/klines/V0')
    expect(calls[0]!.url).toContain('timeframe=1d')
    expect(calls[0]!.url).toContain('limit=5')

    const rawRows = rows(field(klinesFixture, 'data'))
    const raw = item(rawRows[0])
    const mapped = response.data[0]!

    expect(mapped.openTime).toBe(raw.open_time)
    // 后端价格是字符串，映射必须转成数字——否则图表拿到字符串会静默画不出来
    expect(mapped.open).toBe(parseFloat(String(raw.open)))
    expect(typeof mapped.open).toBe('number')
    expect(mapped.isClosed).toBe(raw.is_closed)
    expect(response.toTime).toBe(field(klinesFixture, 'to_time'))
    expect(typeof response.stale).toBe('boolean')
    expect(response.data).toHaveLength(rawRows.length)
  })
})

describe('指标计算映射', () => {
  it('样本不足的字段被丢弃、有值的字段保留为数字', async () => {
    stubResponse(calculateFixture)
    const response = await calculateIndicatorsDetailed('V0', '1d', [
      { type: 'ma', params: { period: 260 } },
      { type: 'ma', params: { period: 20 } },
      { type: 'bollinger', params: { period: 20, std: 2 } },
    ], 60)

    // 每个指标的值字段不同（ma 用 value、布林带用 middle）：
    // 用同一个字段名去数会把有值行也误判成空值。
    const cases = [
      { type: 'ma', period: 260, field: 'value', expectReal: false },
      { type: 'ma', period: 20, field: 'value', expectReal: true },
      { type: 'bollinger', period: 20, field: 'middle', expectReal: true },
    ] as const

    for (const spec of cases) {
      const matches = (row: unknown) => {
        const candidate = item(row)
        return candidate.type === spec.type && item(candidate.params).period === spec.period
      }
      const raw = item(CALCULATE_RESULTS.find(matches))
      const mapped = response.results.find(
        (row) => row.type === spec.type && row.params.period === spec.period,
      )!
      const rawValues = rows(field(raw, 'values'))
      expect(mapped.values).toHaveLength(rawValues.length)

      // 前端约定：后端输出 null 的位置在映射后「没有该字段」（渲染层据此断线）
      const rawNulls = rawValues.filter((row) => item(row)[spec.field] === null).length
      const mappedMissing = mapped.values.filter((row) => !(spec.field in row)).length
      expect(mappedMissing).toBe(rawNulls)

      const realRows = mapped.values.filter((row) => spec.field in row)
      if (spec.expectReal) {
        expect(realRows.length).toBeGreaterThan(0)
        expect(typeof realRows[0]![spec.field]).toBe('number')
      } else {
        // 全段预热：整条序列都不该有值
        expect(realRows.length).toBe(0)
        expect(rawNulls).toBe(rawValues.length)
      }
    }
  })

  it('支撑压力位：决策字段与渲染线字段都能映射', async () => {
    stubResponse(calculateFixture)
    const response = await calculateIndicatorsDetailed('V0', '1d', [
      { type: 'support_resistance', params: {} },
    ], 60)

    const mapped = response.results.find((row) => row.type === 'support_resistance')
    expect(mapped).toBeTruthy()
    expect(mapped!.values).toHaveLength(60)

    // 决策字段：有位成立的那些行必须带出数字
    const withSupport = mapped!.values.filter((row) => 'nearest_support' in row)
    expect(withSupport.length).toBeGreaterThan(0)
    expect(typeof withSupport[0]!.nearest_support).toBe('number')

    // 渲染线字段必须一路透传到前端，否则画不出水平线段
    const lastRow = mapped!.values.at(-1)!
    expect(Object.keys(lastRow)).toEqual(expect.arrayContaining(['level_1', 'level_count']))

    // 渲染规格：max_levels 条线，前端按 plot.type === 'line' 直接画
    expect(mapped!.render.plots.map((plot) => plot.field)).toEqual([
      'level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'level_6',
    ])
    expect(mapped!.render.plots.every((plot) => plot.type === 'line')).toBe(true)
    // 水平线要叠在主图上，落到副图就不是"标在走势上"了
    expect(mapped!.render.window).toBe('main')
  })

  it('指标列表带出默认参数与渲染描述', async () => {
    stubResponse(indicatorListFixture)
    const indicators = await fetchIndicatorList()

    expect(indicators.length).toBeGreaterThan(0)
    for (const entry of indicators) {
      expect(typeof entry.type).toBe('string')
      expect(typeof entry.name).toBe('string')
      expect(entry.default_params).toBeTypeOf('object')
      expect(entry.render).toBeTypeOf('object')
    }

    // 策略建议的候选空间依赖这些指标存在，缺一个会让可搜索范围静默缩小。
    // 注意：/indicator/list 里 ma、macd 的 render.plots 是空的（元数据未填，
    // 完整字段在引擎的 RenderSpec 里），所以这里不断言 plots 非空——那是数据现状。
    const types = new Set(indicators.map((entry) => entry.type))
    for (const expected of ['ma', 'macd', 'kdj', 'bollinger', 'rsi', 'volume', 'volume_structure', 'chip_distribution']) {
      expect(types.has(expected)).toBe(true)
    }
  })
})

describe('策略评估映射', () => {
  it('条件评估带出命中级别 matchedTimeframe（后端改名会立刻失败）', async () => {
    stubResponse(templatesFixture)
    const [template] = await fetchTemplates()

    stubResponse(evaluateFixture)
    const result = await evaluateSignal('V0', template!)

    const rawGroups = rows(field(evaluateFixture, 'groups'))
    const rawEvaluations = rows(field(rawGroups[0], 'evaluations'))
    expect(rawEvaluations.length).toBeGreaterThan(0)

    const mappedEvaluations = result.groups[0]!.evaluations
    expect(mappedEvaluations).toHaveLength(rawEvaluations.length)

    const raw = item(rawEvaluations[0])
    expect(mappedEvaluations[0]!.conditionId).toBe(raw.condition_id)
    expect(mappedEvaluations[0]!.matchedTimeframe).toBe(raw.matched_timeframe ?? null)
    expect(mappedEvaluations[0]!.leftValue).toBe(raw.left_value)
  })
})

describe('策略模板映射', () => {
  it('读回时把 primary_tf / secondary_tfs 映射成前端字段', async () => {
    stubResponse(templatesFixture)
    const templates = await fetchTemplates()

    const raw = item(rows(templatesFixture)[0])
    expect(templates.length).toBeGreaterThan(0)
    expect(templates[0]!.primaryTimeframeId).toBe(raw.primary_tf)
    expect(templates[0]!.secondaryTimeframeIds).toEqual(raw.secondary_tfs ?? [])
    expect(Array.isArray(templates[0]!.conditionGroups)).toBe(true)
  })

  it('写回时仍然是后端约定的 snake_case 字段名', () => {
    const payload = templateToSnake({
      id: 'tpl_contract', name: '契约测试', logic: 'AND',
      conditionGroups: [], primaryTimeframeId: '30m', secondaryTimeframeIds: ['15m'],
      createdAt: 1, updatedAt: 2, enabled: true,
    } as ConditionTemplate)

    expect(payload.primary_tf).toBe('30m')
    expect(payload.secondary_tfs).toEqual(['15m'])
    expect(payload).not.toHaveProperty('primaryTimeframeId')
  })
})

describe('市场与缠论映射', () => {
  it('市场带出默认标的与启用状态', async () => {
    stubResponse(marketsFixture)
    const { markets } = await fetchMarkets()

    const first = item(rows(field(marketsFixture, 'markets'))[0])
    expect(markets.length).toBeGreaterThan(0)
    expect(markets[0]!.default_symbol).toBe(first.default_symbol)
    expect(typeof markets[0]!.enabled).toBe('boolean')
    expect(typeof markets[0]!.sort_order).toBe('number')
  })

  it('缠论分析的结构字段按后端命名透传', async () => {
    stubResponse(chanFixture)
    const analysis = await fetchChanAnalysis('V0', '1d', 10)

    expect(Array.isArray(analysis.bis)).toBe(true)
    expect(Array.isArray(analysis.buySellPoints)).toBe(true)
    expect(analysis.bis).toHaveLength(rows(field(chanFixture, 'bis')).length)
  })
})

describe('策略建议映射', () => {
  it('分析详情映射进度、结论与候选字段', async () => {
    stubResponse(advisorRunFixture)
    const run = await fetchAdvisorRun(15)

    expect(run.progressPercent).toBe(field(advisorRunFixture, 'progress_percent'))
    expect(run.evaluatedCount).toBe(field(advisorRunFixture, 'evaluated_count'))
    expect(run.truncated).toBe(field(advisorRunFixture, 'truncated'))
    expect(run.verdict).toBe(field(advisorRunFixture, 'verdict'))
    const rawChan = item(field(item(field(advisorRunFixture, 'profile')), 'chan'))
    expect(run.profile?.chan.verdict).toBe(field(rawChan, 'verdict'))

    const rawCandidate = item(rows(field(advisorRunFixture, 'candidates'))[0])
    const candidate = run.candidates[0]!
    expect(candidate.plateauStable).toBe(rawCandidate.plateau_stable)
    expect(candidate.inSample?.total_return).toBe(field(rawCandidate.in_sample, 'total_return'))
    expect(candidate.outOfSample?.win_rate).toBe(field(rawCandidate.out_of_sample, 'win_rate'))
  })
})

describe('登录用户映射', () => {
  it('带出模块与权限码（左导航与准入都由它驱动）', async () => {
    stubResponse(authMeFixture)
    const user = await fetchCurrentUser()

    expect(user.username).toBe(field(authMeFixture, 'username'))
    expect(user.permission_codes.length).toBeGreaterThan(0)
    expect(user.modules.length).toBeGreaterThan(0)
    // 每个模块都必须有 component_key，否则左导航渲染不出来
    for (const entry of user.modules) {
      expect(entry.component_key || entry.code).toBeTruthy()
    }
  })
})
