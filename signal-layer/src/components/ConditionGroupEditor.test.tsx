import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ConditionOperator } from '../core/types.ts'
import type { ConditionGroup, IndicatorInfo } from '../core/types.ts'
import { ConditionGroupEditor } from './ConditionGroupEditor.tsx'

const maInfo: IndicatorInfo = {
  type: 'ma',
  name: '移动平均线',
  description: '均线',
  default_params: { period: 5 },
  render: {
    window: 'main',
    plots: [{ field: 'value', type: 'line', color: '#f0a35a', label: '均线' }],
  },
}

const volumeStructureInfo: IndicatorInfo = {
  type: 'volume_structure',
  name: '量柱结构',
  description: '关键量柱与黄金柱',
  default_params: { lookback: 20, key_ratio_min: 1.8, confirm_bars: 3, break_tolerance: 0 },
  outputs: [
    { field: 'key_pillar', label: '关键量柱出现' },
    { field: 'general_confirmed', label: '将军柱确认' },
    { field: 'golden_confirmed', label: '黄金柱确认' },
  ],
  render: {
    window: 'main',
    plots: [{ field: 'key_line', type: 'line', color: '#56c7e8', label: '关键量柱线' }],
  },
}

function maGroup(name: string, period: number): ConditionGroup {
  return {
    // 故意使用重复 ID，覆盖历史数据曾出现的情况。
    id: 'duplicate-group',
    name,
    conditions: [{
      id: 'duplicate-condition',
      name: '',
      left: { source: 'indicator', indicatorType: 'ma', params: { period }, field: 'value' },
      operator: ConditionOperator.GreaterThan,
      right: { source: 'constant', value: 0 },
      enabled: true,
    }],
  }
}

describe('ConditionGroupEditor condition isolation', () => {
  it('does not show a redundant output selector for a single-output indicator', () => {
    render(<ConditionGroupEditor groups={[maGroup('短期均线', 5)]} indicators={[maInfo]} onChange={vi.fn()} />)

    expect(screen.queryByLabelText('移动平均线 输出线')).not.toBeInTheDocument()
    expect(screen.getByLabelText('移动平均线 周期')).toHaveValue('5')
    expect(screen.getByRole('option', { name: '周期 120' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '周期 260' })).toBeInTheDocument()
  })

  it('supports unary MA direction conditions without a right-hand value', () => {
    const group = maGroup('长期趋势', 120)
    group.conditions[0] = { ...group.conditions[0]!, operator: ConditionOperator.Rising }

    render(<ConditionGroupEditor groups={[group]} indicators={[maInfo]} onChange={vi.fn()} />)

    expect(screen.getByLabelText('条件 1 运算符')).toHaveValue(ConditionOperator.Rising)
    expect(screen.getByRole('option', { name: '向上' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '向下' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '上转下' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '下转上' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '支撑' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '压制' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: '介于' })).not.toBeInTheDocument()
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
  })

  it.each([
    [ConditionOperator.TurnDown, '上转下'],
    [ConditionOperator.TurnUp, '下转上'],
  ])('renders %s as a unary MA reversal condition', (operator, label) => {
    const group = maGroup('均线拐点', 20)
    group.conditions[0] = { ...group.conditions[0]!, operator }

    render(<ConditionGroupEditor groups={[group]} indicators={[maInfo]} onChange={vi.fn()} />)

    expect(screen.getByLabelText('条件 1 运算符')).toHaveValue(operator)
    expect(screen.getByRole('option', { name: label })).toBeInTheDocument()
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
  })

  it('keeps MA periods independent between conditions in the same group', () => {
    const onChange = vi.fn()
    const first = maGroup('均线组合', 5)
    const secondCondition = {
      ...first.conditions[0]!,
      // 故意保留重复 ID，模拟旧策略数据。
      left: { source: 'indicator' as const, indicatorType: 'ma', params: { period: 20 }, field: 'value' },
    }
    const group = { ...first, conditions: [first.conditions[0]!, secondCondition] }

    render(<ConditionGroupEditor groups={[group]} indicators={[maInfo]} onChange={onChange} />)
    const periodInputs = screen.getAllByLabelText('移动平均线 周期')
    fireEvent.change(periodInputs[1]!, { target: { value: '60' } })

    const updated = onChange.mock.lastCall?.[0] as ConditionGroup[]
    expect(updated[0]!.conditions[0]!.left).toMatchObject({ params: { period: 5 } })
    expect(updated[0]!.conditions[1]!.left).toMatchObject({ params: { period: 60 } })
  })

  it('changes only the selected condition indicator parameters', () => {
    const onChange = vi.fn()
    render(<ConditionGroupEditor groups={[maGroup('短期均线', 5), maGroup('长期均线', 20)]} indicators={[maInfo]} onChange={onChange} />)
    const periodInputs = screen.getAllByLabelText('移动平均线 周期')
    fireEvent.change(periodInputs[1]!, { target: { value: '60' } })
    const updated = onChange.mock.lastCall?.[0] as ConditionGroup[]
    expect(updated[0]!.conditions[0]!.left).toMatchObject({ params: { period: 5 } })
    expect(updated[1]!.conditions[0]!.left).toMatchObject({ params: { period: 60 } })
  })

  it('changes only the selected group name even when IDs repeat', () => {
    const onChange = vi.fn()
    render(<ConditionGroupEditor groups={[maGroup('第一组', 5), maGroup('第二组', 20)]} indicators={[maInfo]} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('条件组 2 名称'), { target: { value: '趋势确认' } })
    const updated = onChange.mock.lastCall?.[0] as ConditionGroup[]
    expect(updated.map((group) => group.name)).toEqual(['第一组', '趋势确认'])
  })

  it('supports OR logic inside an individual condition group', () => {
    const onChange = vi.fn()
    render(<ConditionGroupEditor groups={[maGroup('均线支撑', 5)]} indicators={[maInfo]} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: '或 · 任一' }))
    const updated = onChange.mock.lastCall?.[0] as ConditionGroup[]
    expect(updated[0]?.logic).toBe('OR')
  })

  it.each([
    [ConditionOperator.Support, '支撑'],
    [ConditionOperator.Resistance, '压制'],
  ])('renders MA %s as a unary condition', (operator, label) => {
    const group = maGroup('均线作用', 5)
    group.conditions[0] = { ...group.conditions[0]!, operator }
    render(<ConditionGroupEditor groups={[group]} indicators={[maInfo]} onChange={vi.fn()} />)

    expect(screen.getByLabelText('条件 1 运算符')).toHaveValue(operator)
    expect(screen.getByRole('option', { name: label })).toBeInTheDocument()
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
  })

  it('allows strategy conditions to select non-plot indicator outputs', () => {
    const onChange = vi.fn()
    const group = maGroup('量柱确认', 5)
    group.conditions[0] = {
      ...group.conditions[0]!,
      left: {
        source: 'indicator', indicatorType: 'volume_structure',
        params: { ...volumeStructureInfo.default_params }, field: 'key_pillar',
      },
    }

    render(<ConditionGroupEditor groups={[group]} indicators={[maInfo, volumeStructureInfo]} onChange={onChange} />)
    const output = screen.getByLabelText('量柱结构 输出线')
    expect(output).toHaveValue('key_pillar')
    expect(screen.getByRole('option', { name: '黄金柱确认' })).toBeInTheDocument()

    fireEvent.change(output, { target: { value: 'golden_confirmed' } })
    const updated = onChange.mock.lastCall?.[0] as ConditionGroup[]
    expect(updated[0]!.conditions[0]!.left).toMatchObject({ field: 'golden_confirmed' })
  })
})

describe('ConditionGroupEditor 条件级别', () => {
  it('提供「主周期」与「次级周期」两个抽象级别，并标注具体级别归属', () => {
    render(
      <ConditionGroupEditor
        groups={[maGroup('短期均线', 5)]}
        indicators={[maInfo]}
        onChange={vi.fn()}
        primaryTimeframeId="1d"
        secondaryTimeframeIds={['60m', '30m']}
      />,
    )

    expect(screen.getByRole('option', { name: '主周期（日线）' })).toBeInTheDocument()
    // 次级周期选项把集合内的级别列出来
    expect(screen.getByRole('option', { name: '次级周期（60分钟 或 30分钟）' })).toBeEnabled()
    // 具体级别分别标注归属
    expect(screen.getByRole('option', { name: '日线（主周期）' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '60分钟（次级周期）' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '30分钟（次级周期）' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '15分钟' })).toBeInTheDocument()
  })

  it('没有声明次级周期时「次级周期」不可选', () => {
    render(
      <ConditionGroupEditor
        groups={[maGroup('短期均线', 5)]}
        indicators={[maInfo]}
        onChange={vi.fn()}
        primaryTimeframeId="1d"
        secondaryTimeframeIds={[]}
      />,
    )

    expect(screen.getByRole('option', { name: '次级周期（未设置）' })).toBeDisabled()
  })

  it('选择「次级周期」会把条件级别写成哨兵值', () => {
    const onChange = vi.fn()
    render(
      <ConditionGroupEditor
        groups={[maGroup('短期均线', 5)]}
        indicators={[maInfo]}
        onChange={onChange}
        primaryTimeframeId="1d"
        secondaryTimeframeIds={['30m']}
      />,
    )

    fireEvent.change(screen.getByLabelText('条件 1 级别'), { target: { value: 'secondary' } })

    const updated = onChange.mock.calls[0]?.[0]
    expect(updated?.[0]?.conditions[0]?.timeframeId).toBe('secondary')
  })
})

// ── 形态/事件型字段：不带数学比较 ────────────────────────────────────────

const sweepInfo: IndicatorInfo = {
  type: 'liquidity_sweep',
  name: '流动性扫荡反转',
  description: '扫荡信号',
  default_params: { piv_len: 8, atr_len: 14 },
  outputs: [
    { field: 'bull_signal', label: '看涨扫荡信号', kind: 'event' },
    { field: 'bear_signal', label: '看跌扫荡信号', kind: 'event' },
    { field: 'bull_level', label: '被扫的支撑水平' },
  ],
  render: { window: 'main', plots: [], markers: [] },
}

const maturityInfo: IndicatorInfo = {
  type: 'dilun_structure',
  name: '帝论·合理价格',
  description: '形态',
  default_params: { maturity_bars: 8 },
  outputs: [
    { field: 'zone_mature', label: '态势成熟', kind: 'event' },
    { field: 'zone_low', label: '合理价格下沿' },
  ],
  render: { window: 'main', plots: [], markers: [] },
}

function eventGroup(indicatorType: string, field: string): ConditionGroup {
  return {
    id: 'g-event',
    name: '事件条件',
    conditions: [{
      id: 'c-event',
      name: '',
      left: { source: 'indicator', indicatorType, params: {}, field },
      operator: ConditionOperator.NonZero,
      right: { source: 'constant', value: 0 },
      enabled: true,
    }],
  }
}

describe('形态/事件型字段的条件编辑', () => {
  it('事件型字段不显示运算符与右值，只提示「出现即成立」', () => {
    render(
      <ConditionGroupEditor
        groups={[eventGroup('liquidity_sweep', 'bull_signal')]}
        onChange={vi.fn()}
        indicators={[sweepInfo]}
      />,
    )

    expect(screen.getByText('出现即成立')).toBeInTheDocument()
    expect(screen.queryByLabelText(/运算符/)).not.toBeInTheDocument()
    // 右值输入框（固定值）也不该出现
    expect(screen.queryByPlaceholderText('数值')).not.toBeInTheDocument()
  })

  it('把字段切成事件型时，自动改为「成立」并归零右值', () => {
    const onChange = vi.fn()
    const group: ConditionGroup = {
      id: 'g-switch',
      name: '',
      conditions: [{
        id: 'c-switch', name: '',
        left: { source: 'indicator', indicatorType: 'liquidity_sweep', params: {}, field: 'bull_level' },
        operator: ConditionOperator.GreaterThan,
        right: { source: 'constant', value: 11 },
        enabled: true,
      }],
    }
    render(
      <ConditionGroupEditor groups={[group]} onChange={onChange} indicators={[sweepInfo]} />,
    )

    fireEvent.change(screen.getByLabelText('流动性扫荡反转 输出线'), { target: { value: 'bull_signal' } })

    const updated = onChange.mock.calls.at(-1)![0][0] as ConditionGroup
    expect(updated.conditions[0]!.operator).toBe(ConditionOperator.NonZero)
    expect(updated.conditions[0]!.right).toEqual({ source: 'constant', value: 0 })
  })

  it('从事件型切回连续量时，还原成比较运算而不是留下「成立」', () => {
    const onChange = vi.fn()
    const { rerender } = render(
      <ConditionGroupEditor
        groups={[eventGroup('liquidity_sweep', 'bull_signal')]}
        onChange={onChange}
        indicators={[sweepInfo]}
      />,
    )

    fireEvent.change(screen.getByLabelText('流动性扫荡反转 输出线'), { target: { value: 'bull_level' } })

    const updated = onChange.mock.calls.at(-1)![0][0] as ConditionGroup
    expect(updated.conditions[0]!.operator).toBe(ConditionOperator.GreaterThan)

    // onChange 是受控回调，界面要等父组件把新值传回来才会变——这里手动回灌验证往返
    rerender(
      <ConditionGroupEditor groups={[updated]} onChange={onChange} indicators={[sweepInfo]} />,
    )
    expect(screen.getByLabelText(/运算符/)).toBeInTheDocument()
    expect(screen.queryByText('出现即成立')).not.toBeInTheDocument()
  })

  it('态势成熟这类事件字段同样不显示运算符', () => {
    render(
      <ConditionGroupEditor
        groups={[eventGroup('dilun_structure', 'zone_mature')]}
        onChange={vi.fn()}
        indicators={[maturityInfo]}
      />,
    )

    expect(screen.getByText('出现即成立')).toBeInTheDocument()
    expect(screen.queryByLabelText(/运算符/)).not.toBeInTheDocument()
  })
})

// ── 布林带开口 / 收口 ───────────────────────────────────────────────────

const bollingerInfo: IndicatorInfo = {
  type: 'bollinger',
  name: '布林带',
  description: '通道指标',
  default_params: { period: 20, std: 2 },
  outputs: [
    { field: 'upper', label: '上轨' },
    { field: 'middle', label: '中轨' },
    { field: 'lower', label: '下轨' },
    { field: 'bandwidth', label: '带宽%' },
  ],
  render: { window: 'main', plots: [], markers: [] },
}

function bollingerGroup(operator: ConditionOperator): ConditionGroup {
  return {
    id: 'g-boll',
    name: '布林带',
    conditions: [{
      id: 'c-boll', name: '',
      left: { source: 'indicator', indicatorType: 'bollinger', params: {}, field: 'bandwidth' },
      operator,
      right: { source: 'constant', value: 0 },
      enabled: true,
    }],
  }
}

describe('布林带开口与收口', () => {
  it('带宽是可选字段，且能选到「向下」（收口）', () => {
    render(
      <ConditionGroupEditor groups={[bollingerGroup(ConditionOperator.Falling)]} onChange={vi.fn()} indicators={[bollingerInfo]} />,
    )

    const field = screen.getByLabelText('布林带 输出线') as HTMLSelectElement
    expect(Array.from(field.options).map((o) => o.textContent.trim())).toEqual(['上轨', '中轨', '下轨', '带宽%'])

    const operator = screen.getByLabelText('条件 1 运算符') as HTMLSelectElement
    expect(operator.value).toBe(ConditionOperator.Falling)
    // 收口＝带宽向下；开口＝带宽向上，两者都必须在可选运算符里
    const labels = Array.from(operator.options).map((o) => o.textContent.trim())
    expect(labels).toContain('向下')
    expect(labels).toContain('向上')
  })

  it('「向上」对非均线指标也可选（这是开口的表达方式）', () => {
    render(
      <ConditionGroupEditor groups={[bollingerGroup(ConditionOperator.Rising)]} onChange={vi.fn()} indicators={[bollingerInfo]} />,
    )

    const operator = screen.getByLabelText('条件 1 运算符') as HTMLSelectElement
    expect(operator.value).toBe(ConditionOperator.Rising)
    expect(Array.from(operator.options).map((o) => o.textContent.trim())).toContain('向上')
  })

  it('「支撑 / 压制」仍然只属于均线', () => {
    render(
      <ConditionGroupEditor groups={[bollingerGroup(ConditionOperator.GreaterThan)]} onChange={vi.fn()} indicators={[bollingerInfo]} />,
    )

    const labels = Array.from((screen.getByLabelText('条件 1 运算符') as HTMLSelectElement).options)
      .map((o) => o.textContent.trim())
    expect(labels).not.toContain('支撑')
    expect(labels).not.toContain('压制')
  })
})
