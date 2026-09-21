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
