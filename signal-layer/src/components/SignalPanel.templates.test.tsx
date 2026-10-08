import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConditionTemplate } from '../core/types.ts'
import { useAppStore } from '../store/useAppStore.ts'
import { SignalPanel } from './SignalPanel.tsx'

vi.mock('../api/template.ts', () => ({
  fetchTemplates: vi.fn(),
  createTemplate: vi.fn(),
  deleteTemplate: vi.fn(),
  updateTemplate: vi.fn(),
}))
vi.mock('../api/signal.ts', () => ({
  evaluateSignal: vi.fn(),
  runBacktest: vi.fn(),
}))

const { fetchTemplates } = await import('../api/template.ts')

function template(id: string, name: string): ConditionTemplate {
  return {
    id, name, logic: 'AND', conditionGroups: [],
    primaryTimeframeId: '1d', secondaryTimeframeIds: [],
    createdAt: 1, updatedAt: 1, enabled: true,
    tradeParams: {
      stopLossType: 'none', stopLossValue: 0,
      takeProfitType: 'none', takeProfitValue: 0,
      maxHoldBars: 0, exitConditions: [], exitLogic: 'AND',
    },
  }
}

/**
 * 跨账号残留的回归：store 是模块级单例，换账号不会重建。
 * 之前服务端列表是"逐条合并"进 store 的，于是 test 账号的策略在 admin 的下拉里
 * 一直留着；选中它点编辑，后端按归属人返回 404（界面上是英文 Template not found）。
 */
describe('SignalPanel 策略模板列表 = 服务端列表', () => {
  beforeEach(() => {
    vi.mocked(fetchTemplates).mockReset()
    // 上一个账号（test）留在内存里的策略
    useAppStore.setState({
      templates: [template('tpl_other', '布林通道均线策略')],
      templatesLoaded: true,
      activeTemplateId: 'tpl_other',
      templateSignals: { tpl_other: { state: 'ready' } as never },
    })
  })

  it('当前账号列表里没有的模板会被剔除，选中态一并清空', async () => {
    vi.mocked(fetchTemplates).mockResolvedValue([template('tpl_mine', '我的策略')])

    render(<SignalPanel symbol="V0" />)
    await act(async () => { await Promise.resolve() })

    expect(screen.getByRole('option', { name: '我的策略' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: '布林通道均线策略' })).not.toBeInTheDocument()
    expect(useAppStore.getState().templates.map((t) => t.id)).toEqual(['tpl_mine'])
    // 选中的是别人的策略：清掉，否则「编辑当前策略」会打到一个不属于自己的 id 上
    expect(useAppStore.getState().activeTemplateId).toBeNull()
    expect(useAppStore.getState().templateSignals).toEqual({})
  })

  it('服务端返回空列表时列表清空（不能保留旧列表）', async () => {
    vi.mocked(fetchTemplates).mockResolvedValue([])

    render(<SignalPanel symbol="V0" />)
    await act(async () => { await Promise.resolve() })

    expect(screen.queryByRole('option', { name: '布林通道均线策略' })).not.toBeInTheDocument()
    expect(useAppStore.getState().templates).toEqual([])
  })
})
