import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BacktestResult } from '../api/signal.ts'
import type { ConditionTemplate } from '../core/types.ts'
import { useAppStore } from '../store/useAppStore.ts'
import { SignalPanel } from './SignalPanel.tsx'

vi.mock('../api/template.ts', () => ({
  fetchTemplates: vi.fn(async () => []),
  createTemplate: vi.fn(),
  deleteTemplate: vi.fn(),
  updateTemplate: vi.fn(),
}))
vi.mock('../api/signal.ts', async () => {
  const actual = await vi.importActual<typeof import('../api/signal.ts')>('../api/signal.ts')
  return { ...actual, evaluateSignal: vi.fn(), runBacktest: vi.fn() }
})

const { runBacktest } = await import('../api/signal.ts')
const { fetchTemplates } = await import('../api/template.ts')

/** store 与"服务端"必须给同一份列表：面板会拿服务端列表整体替换本地列表，
 *  两处不一致时模板会被这次替换清空（这正是修复跨账号残留的行为）。 */
function seedTemplates(list: ConditionTemplate[]) {
  vi.mocked(fetchTemplates).mockResolvedValue(list)
  useAppStore.setState({ templates: list, templatesLoaded: true, activeTemplateId: list[0]?.id ?? null, templateSignals: {} })
}

function template(overrides: Partial<ConditionTemplate['tradeParams']> = {}): ConditionTemplate {
  return {
    id: 'tpl_hold', name: '测试策略', logic: 'AND', conditionGroups: [],
    primaryTimeframeId: '1d', secondaryTimeframeIds: [],
    createdAt: 1, updatedAt: 1, enabled: true,
    tradeParams: {
      stopLossType: 'none', stopLossValue: 0,
      takeProfitType: 'none', takeProfitValue: 0,
      maxHoldBars: 0, exitConditions: [], exitLogic: 'AND',
      ...overrides,
    },
  }
}

const backtest: BacktestResult = {
  templateId: 'tpl_hold', symbol: 'V0', timeframe: '1d',
  totalTrades: 2, winTrades: 1, winRate: 50, totalReturn: 3, avgReturn: 1.5,
  maxDrawdown: 2, profitFactor: 1.2, payoffRatio: 1, suggestedPosition: 10,
  openPosition: null,
  trades: [
    { entryTime: 1, exitTime: 2, entryPrice: 10, exitPrice: 10.5, pnlPct: 5, exitReason: 'timeout' },
    { entryTime: 3, exitTime: 4, entryPrice: 10, exitPrice: 9.5, pnlPct: -5, exitReason: 'stop_loss' },
  ],
}

/** 打开回测视图并跑一次回测，让「交易明细」渲染出来。 */
async function runAndShowTrades() {
  render(<SignalPanel symbol="V0" />)
  await act(async () => { await Promise.resolve() })
  fireEvent.click(screen.getByRole('button', { name: '回测' }))
  fireEvent.click(screen.getByRole('button', { name: '运行回测' }))
  await act(async () => { await Promise.resolve() })
}

describe('SignalPanel 卖出与风控 / 交易明细', () => {
  beforeEach(() => {
    vi.mocked(runBacktest).mockReset()
    vi.mocked(runBacktest).mockResolvedValue(backtest)
    seedTemplates([template()])
  })

  it('持仓上限为 0 时显示「不限」', async () => {
    render(<SignalPanel symbol="V0" />)
    await act(async () => { await Promise.resolve() })

    expect(screen.getByText('持仓上限')).toBeInTheDocument()
    expect(screen.getByText('不限')).toBeInTheDocument()
  })

  it('设置了持仓上限就显示根数，止损止盈即使都关闭也看得见这条规则', async () => {
    seedTemplates([template({ maxHoldBars: 30 })])
    render(<SignalPanel symbol="V0" />)
    await act(async () => { await Promise.resolve() })

    expect(screen.getByText('30 根K线到期平仓')).toBeInTheDocument()
    // 止损/止盈都是「关闭」，但这不代表没有出场规则——这正是之前回测里凭空冒出
    // 「策略卖」时界面上看不到的那条规则。
    expect(screen.getAllByText('关闭')).toHaveLength(2)
  })

  it('仍持仓时显示「持有中」行与浮动盈亏，并说明不计入统计', async () => {
    vi.mocked(runBacktest).mockResolvedValue({
      ...backtest,
      totalTrades: 0, trades: [], winRate: 0, totalReturn: 0,
      openPosition: {
        entryTime: 1, entryPrice: 7.97, side: 'long',
        barsHeld: 400, lastTime: 2, lastPrice: 4.06, pnlPct: -49.06,
      },
    })
    await runAndShowTrades()

    // 表头同时说清"已完成 0 笔"和"还有 1 笔持有中"
    expect(screen.getByText('0 笔交易 · 1 笔持有中')).toBeInTheDocument()
    expect(screen.getByText('持有中')).toBeInTheDocument()
    // 入场价 → 最新价（没有卖出价可写）
    expect(screen.getByText('7.97 → 4.06')).toBeInTheDocument()
    expect(screen.getByText('-49.06%')).toBeInTheDocument()
    expect(screen.getByText(/已持有 400 根K线.*未计入上面的胜率与累计收益/)).toBeInTheDocument()
  })

  it('没有持仓时不出现「持有中」', async () => {
    await runAndShowTrades()

    expect(screen.queryByText('持有中')).not.toBeInTheDocument()
    expect(screen.getByText('2 笔交易')).toBeInTheDocument()
  })

  it('交易明细逐笔写出出场原因（到期平仓不能显示成裸的英文 timeout）', async () => {
    await runAndShowTrades()

    expect(screen.getByText('到期平仓')).toBeInTheDocument()
    expect(screen.getByText('止损')).toBeInTheDocument()
    expect(screen.queryByText('timeout')).not.toBeInTheDocument()
    expect(screen.queryByText('stop_loss')).not.toBeInTheDocument()
  })
})
