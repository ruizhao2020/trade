import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createTemplate, updateTemplate } from '../api/template.ts'
import { fetchIndicatorList } from '../api/indicator.ts'
import { TemplateEditor } from './TemplateEditor.tsx'

vi.mock('../api/template.ts', () => ({
  createTemplate: vi.fn(),
  updateTemplate: vi.fn(),
}))
vi.mock('../api/indicator.ts', () => ({
  fetchIndicatorList: vi.fn(),
}))

const created = {
  id: 'tpl_new', name: '测试策略', logic: 'AND' as const, conditionGroups: [],
  primaryTimeframeId: '30m', secondaryTimeframeIds: ['5m'],
  createdAt: 1, updatedAt: 1, enabled: true,
}

/** 渲染并放掉 fetchIndicatorList 的 promise，避免 act 警告 */
async function renderEditor() {
  render(<TemplateEditor onClose={vi.fn()} />)
  await act(async () => { await Promise.resolve() })
}

describe('TemplateEditor 周期设置', () => {
  beforeEach(() => {
    vi.mocked(fetchIndicatorList).mockResolvedValue([])
    vi.mocked(createTemplate).mockReset()
    vi.mocked(createTemplate).mockResolvedValue(created)
  })

  it('保存时带上所选的主周期与次级周期', async () => {
    await renderEditor()

    fireEvent.change(screen.getByLabelText('策略名称'), { target: { value: '测试策略' } })
    fireEvent.change(screen.getByLabelText('主周期'), { target: { value: '30m' } })
    // 次级周期只能选比主周期更细的：5分钟可以
    fireEvent.click(screen.getByRole('button', { name: '5分钟' }))
    fireEvent.click(screen.getByRole('button', { name: '保存策略' }))
    await act(async () => { await Promise.resolve() })

    const payload = await vi.mocked(createTemplate).mock.calls[0]?.[0]
    expect(payload?.primaryTimeframeId).toBe('30m')
    expect(payload?.secondaryTimeframeIds).toEqual(['5m'])
  })

  it('次级周期只允许选比主周期更细的级别', async () => {
    await renderEditor()

    // 主周期 30分钟：更粗的日线/60分钟与同级的 30分钟 都不可选
    fireEvent.change(screen.getByLabelText('主周期'), { target: { value: '30m' } })
    expect(screen.getByRole('button', { name: '日线' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '60分钟' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '30分钟' })).toBeDisabled()
    // 更细的 15分钟/5分钟 可选
    expect(screen.getByRole('button', { name: '15分钟' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '5分钟' })).toBeEnabled()
  })

  it('主周期是最细的 5分钟时没有可选的次级周期', async () => {
    await renderEditor()

    fireEvent.change(screen.getByLabelText('主周期'), { target: { value: '5m' } })

    for (const label of ['日线', '60分钟', '30分钟', '15分钟', '5分钟']) {
      expect(screen.getByRole('button', { name: label })).toBeDisabled()
    }
  })

  it('主周期改粗后，不再比它更细的次级周期会被剔除', async () => {
    await renderEditor()

    fireEvent.change(screen.getByLabelText('策略名称'), { target: { value: '测试策略' } })
    // 主周期日线时把 30分钟 选为次级
    fireEvent.click(screen.getByRole('button', { name: '30分钟' }))
    expect(screen.getByRole('button', { name: '30分钟' })).toHaveAttribute('aria-pressed', 'true')

    // 主周期改成 15分钟 后，30分钟 已不比主周期更细，应自动取消
    fireEvent.change(screen.getByLabelText('主周期'), { target: { value: '15m' } })
    expect(screen.getByRole('button', { name: '30分钟' })).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(screen.getByRole('button', { name: '保存策略' }))
    await act(async () => { await Promise.resolve() })

    expect(await vi.mocked(createTemplate).mock.calls[0]?.[0]).toMatchObject({
      primaryTimeframeId: '15m',
      secondaryTimeframeIds: [],
    })
  })
})

// ── 出场设置（止损/止盈）的选中一致性 ───────────────────────────────────

/** 找到止损/止盈下拉（它们的选项里含「关闭」）。 */
function riskSelects() {
  return Array.from(document.querySelectorAll('select')).filter((el) =>
    Array.from(el.options).some((o) => o.textContent?.trim() === '关闭')
    && Array.from(el.options).some((o) => o.value.startsWith('atr') || o.value.startsWith('rr_ratio')))
}

describe('TemplateEditor 出场设置', () => {
  beforeEach(() => {
    vi.mocked(fetchIndicatorList).mockResolvedValue([])
    vi.mocked(createTemplate).mockReset()
    vi.mocked(createTemplate).mockResolvedValue(created)
  })

  it('每个预设选项都能被如实选中（取整值不能被显示成「关闭」）', async () => {
    // 这是这次 bug 的回归护栏：选中值曾按 `type:2` 拼、选项却写成 `atr:2.0`，
    // 匹配不上时浏览器退回第一个选项，界面显示「关闭」而实际存的是「平均真实波幅 × 2.0」。
    const cases = [
      { stop_loss_type: 'atr', stop_loss_value: 2.0, expected: 'atr:2' },
      { stop_loss_type: 'atr', stop_loss_value: 1.5, expected: 'atr:1.5' },
      { stop_loss_type: 'atr', stop_loss_value: 3.0, expected: 'atr:3' },
      { stop_loss_type: 'fixed_pct', stop_loss_value: 5.0, expected: 'fixed_pct:5' },
      { stop_loss_type: 'swing_low', stop_loss_value: 0.0, expected: 'swing_low:0' },
      { stop_loss_type: 'none', stop_loss_value: 0.0, expected: 'none:0' },
    ] as const

    for (const item of cases) {
      const { unmount } = render(
        <TemplateEditor
          onClose={vi.fn()}
          template={{
            id: 'tpl_risk', name: '风控', logic: 'AND', conditionGroups: [], primaryTimeframeId: '1d',
            secondaryTimeframeIds: [], createdAt: 1, updatedAt: 1, enabled: true,
            tradeParams: {
              stopLossType: item.stop_loss_type, stopLossValue: item.stop_loss_value,
              takeProfitType: 'none', takeProfitValue: 0,
              maxHoldBars: 0,
              exitConditions: [], exitLogic: 'AND',
            },
          }}
        />,
      )
      await act(async () => { await Promise.resolve() })
      const [stopLoss] = riskSelects()
      expect(stopLoss!.value, `${item.stop_loss_type}:${item.stop_loss_value} 应选中 ${item.expected}`).toBe(item.expected)
      expect(stopLoss!.selectedIndex).toBeGreaterThan(-1)
      unmount()
    }
  })

  it('取值不在预设里时如实回显，不能显示成「关闭」', async () => {
    render(
      <TemplateEditor
        onClose={vi.fn()}
        template={{
          id: 'tpl_odd', name: '历史值', logic: 'AND', conditionGroups: [], primaryTimeframeId: '1d',
          secondaryTimeframeIds: [], createdAt: 1, updatedAt: 1, enabled: true,
          tradeParams: {
            stopLossType: 'atr', stopLossValue: 2.5,     // 预设里没有 2.5
            takeProfitType: 'none', takeProfitValue: 0,
            maxHoldBars: 0,
            exitConditions: [], exitLogic: 'AND',
          },
        }}
      />,
    )
    await act(async () => { await Promise.resolve() })

    const [stopLoss] = riskSelects()
    expect(stopLoss!.value).toBe('atr:2.5')
    expect(stopLoss!.options[stopLoss!.selectedIndex]?.textContent?.trim()).toContain('2.5')
    expect(stopLoss!.options[stopLoss!.selectedIndex]?.textContent?.trim()).not.toBe('关闭')
  })

  it('选择「关闭」后保存写入 none，而不是落回默认的 ATR×2', async () => {
    vi.mocked(updateTemplate).mockReset()
    vi.mocked(updateTemplate).mockResolvedValue(created)
    render(
      <TemplateEditor
        onClose={vi.fn()}
        template={{
          id: 'tpl_off', name: '关闭止损', logic: 'AND', conditionGroups: [], primaryTimeframeId: '1d',
          secondaryTimeframeIds: [], createdAt: 1, updatedAt: 1, enabled: true,
          tradeParams: {
            stopLossType: 'atr', stopLossValue: 2.0,     // 起点是 ATR×2（旧 bug 会让它显示成「关闭」）
            takeProfitType: 'none', takeProfitValue: 0,
            maxHoldBars: 0,
            exitConditions: [], exitLogic: 'AND',
          },
        }}
      />,
    )
    await act(async () => { await Promise.resolve() })

    fireEvent.change(screen.getByLabelText('策略名称'), { target: { value: '关闭止损' } })
    const [stopLoss] = riskSelects()
    fireEvent.change(stopLoss!, { target: { value: 'none:0' } })
    fireEvent.click(screen.getByRole('button', { name: '保存策略' }))
    await act(async () => { await Promise.resolve() })

    // 编辑已有模板走 update
    const payload = await vi.mocked(updateTemplate).mock.calls[0]?.[1]
    expect(payload?.tradeParams?.stopLossType).toBe('none')
    expect(payload?.tradeParams?.stopLossValue).toBe(0)
  })
})

// ── 持仓上限（到期平仓）────────────────────────────────────────────────
//
// 以前这个上限在回测里写死 100 根 K 线：用户把止损止盈都关掉、又没设出场条件，
// 回测照样会冒出「策略卖」。现在它必须来自显式配置，默认 0 = 不限。

describe('TemplateEditor 持仓上限', () => {
  beforeEach(() => {
    vi.mocked(fetchIndicatorList).mockResolvedValue([])
    vi.mocked(updateTemplate).mockReset()
    vi.mocked(updateTemplate).mockResolvedValue(created)
    vi.mocked(createTemplate).mockReset()
    vi.mocked(createTemplate).mockResolvedValue(created)
  })

  // 用 role 查询而不是 getByLabelText：外层 <label> 里还包着「参数说明」按钮，
  // 按钮会被同一个 label 文本关联上，getByLabelText 会命中两个元素。
  const holdInput = () => screen.getByRole('spinbutton', { name: '持仓上限' })

  function renderWithParams(tradeParams: Record<string, unknown>) {
    render(
      <TemplateEditor
        onClose={vi.fn()}
        template={{
          id: 'tpl_hold', name: '持仓上限', logic: 'AND', conditionGroups: [], primaryTimeframeId: '1d',
          secondaryTimeframeIds: [], createdAt: 1, updatedAt: 1, enabled: true,
          tradeParams: tradeParams as never,
        }}
      />,
    )
  }

  it('新建策略默认不限（0），并提示不会到期平仓', async () => {
    await renderEditor()

    const input = holdInput()
    expect(input).toHaveValue(0)
    expect(input).toHaveAttribute('min', '0')
    expect(screen.getByText(/不限 · 不设置到期平仓/)).toBeInTheDocument()
  })

  it('老模板没有 maxHoldBars 字段时按不限处理，不会显示空白', async () => {
    renderWithParams({
      stopLossType: 'none', stopLossValue: 0,
      takeProfitType: 'none', takeProfitValue: 0,
      exitConditions: [], exitLogic: 'AND',
    })
    await act(async () => { await Promise.resolve() })

    expect(holdInput()).toHaveValue(0)
  })

  it('填了上限就保存对应根数，并把说明改成到期平仓', async () => {
    await renderEditor()

    fireEvent.change(screen.getByLabelText('策略名称'), { target: { value: '持仓上限' } })
    fireEvent.change(holdInput(), { target: { value: '30' } })
    expect(screen.getByText(/持仓满 30 根K线仍未出场时按收盘价平仓/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '保存策略' }))
    await act(async () => { await Promise.resolve() })

    expect(await vi.mocked(createTemplate).mock.calls[0]?.[0]).toMatchObject({
      tradeParams: { maxHoldBars: 30 },
    })
  })

  it('负数/超上限/清空都被夹回合法范围', async () => {
    await renderEditor()
    const input = holdInput()

    // 先设一个合法值，让后续每次输入都真的改变状态（受控 number input 在
    // 状态没变时 DOM 值不一定会被 React 拉回，断言会变得不可靠）
    fireEvent.change(input, { target: { value: '30' } })
    expect(input).toHaveValue(30)

    fireEvent.change(input, { target: { value: '-5' } })
    expect(input).toHaveValue(0)

    fireEvent.change(input, { target: { value: '999999' } })
    expect(input).toHaveValue(5000)

    // 清空输入框：Number.parseInt('') 是 NaN，必须落回 0 而不是把 NaN 存进策略
    fireEvent.change(input, { target: { value: '' } })
    expect(input).toHaveValue(0)

    fireEvent.change(screen.getByLabelText('策略名称'), { target: { value: '夹取' } })
    fireEvent.click(screen.getByRole('button', { name: '保存策略' }))
    await act(async () => { await Promise.resolve() })

    expect(await vi.mocked(createTemplate).mock.calls[0]?.[0]).toMatchObject({
      tradeParams: { maxHoldBars: 0 },
    })
  })

  it('编辑已有模板时带出保存过的上限（回填不能丢）', async () => {
    renderWithParams({
      stopLossType: 'none', stopLossValue: 0,
      takeProfitType: 'none', takeProfitValue: 0,
      maxHoldBars: 45, exitConditions: [], exitLogic: 'AND',
    })
    await act(async () => { await Promise.resolve() })

    expect(holdInput()).toHaveValue(45)

    fireEvent.click(screen.getByRole('button', { name: '保存策略' }))
    await act(async () => { await Promise.resolve() })

    expect(await vi.mocked(updateTemplate).mock.calls[0]?.[1]).toMatchObject({
      tradeParams: { maxHoldBars: 45 },
    })
  })
})
