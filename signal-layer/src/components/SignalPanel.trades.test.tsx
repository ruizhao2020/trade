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
    useAppStore.setState({ templates: [template()], activeTemplateId: 'tpl_hold', templateSignals: {} })
  })

  it('持仓上限为 0 时显示「不限」', async () => {
    render(<SignalPanel symbol="V0" />)
    await act(async () => { await Promise.resolve() })

    expect(screen.getByText('持仓上限')).toBeInTheDocument()
    expect(screen.getByText('不限')).toBeInTheDocument()
  })

  it('设置了持仓上限就显示根数，止损止盈即使都关闭也看得见这条规则', async () => {
    useAppStore.setState({ templates: [template({ maxHoldBars: 30 })], activeTemplateId: 'tpl_hold' })
    render(<SignalPanel symbol="V0" />)
    await act(async () => { await Promise.resolve() })

    expect(screen.getByText('30 根K线到期平仓')).toBeInTheDocument()
    // 止损/止盈都是「关闭」，但这不代表没有出场规则——这正是之前回测里凭空冒出
    // 「策略卖」时界面上看不到的那条规则。
    expect(screen.getAllByText('关闭')).toHaveLength(2)
  })

  it('交易明细逐笔写出出场原因（到期平仓不能显示成裸的英文 timeout）', async () => {
    await runAndShowTrades()

    expect(screen.getByText('到期平仓')).toBeInTheDocument()
    expect(screen.getByText('止损')).toBeInTheDocument()
    expect(screen.queryByText('timeout')).not.toBeInTheDocument()
    expect(screen.queryByText('stop_loss')).not.toBeInTheDocument()
  })
})
