import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { runScreener } from '../api/screener.ts'
import type { ConditionTemplate } from '../core/types.ts'
import { useAppStore } from '../store/useAppStore.ts'
import { ScreenerWorkspace } from './ScreenerWorkspace.tsx'

vi.mock('../api/template.ts', () => ({
  fetchTemplates: vi.fn().mockResolvedValue([{
    id: 'strategy-1',
    name: '测试策略',
    description: '',
    logic: 'AND',
    conditionGroups: [],
    primaryTimeframeId: '1d',
    secondaryTimeframeIds: [],
    enabled: true,
    createdAt: 1,
    updatedAt: 1,
  }]),
}))

vi.mock('../api/symbol.ts', () => ({
  fetchMarkets: vi.fn().mockResolvedValue({
    markets: [{ id: 'stock', name: '股票', description: '', default_symbol: '000001_sz', default_symbol_name: '平安银行', enabled: true, sort_order: 10 }],
  }),
}))

vi.mock('../api/screener.ts', () => ({
  runScreener: vi.fn(),
}))

describe('ScreenerWorkspace pending selections', () => {
  beforeEach(() => {
    useAppStore.setState({ templates: [], activeTemplateId: null })
    vi.mocked(runScreener).mockReset()
  })

  it('does not select the first strategy or market automatically', async () => {
    render(
      <ScreenerWorkspace
        selectedSymbol=""
        selectedName=""
        chart={<div>图表占位</div>}
        onSelectSymbol={vi.fn()}
        strategyTimeframes={['1d']}
        activeTimeframe="1d"
        onTimeframeChange={vi.fn()}
      />,
    )

    await waitFor(() => expect(screen.getByRole('option', { name: '测试策略' })).toBeInTheDocument())
    const selectors = screen.getAllByRole('combobox')
    expect(selectors[0]).toHaveValue('')
    expect(selectors[1]).toHaveValue('')
    expect(useAppStore.getState().activeTemplateId).toBeNull()
    expect(screen.getByRole('button', { name: '请选择策略' })).toBeDisabled()
  })

  it('aborts the active request when stop screening is clicked', async () => {
    const active = {
      id: 'strategy-stop', name: '停止测试', logic: 'AND', conditionGroups: [],
      primaryTimeframeId: '1d', secondaryTimeframeIds: [], enabled: true, createdAt: 1, updatedAt: 1,
    } as ConditionTemplate
    useAppStore.setState({ templates: [active], activeTemplateId: active.id })
    vi.mocked(runScreener).mockImplementation((_template, options) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    }))
    render(
      <ScreenerWorkspace
        selectedSymbol="" selectedName="" chart={<div>图表占位</div>}
        onSelectSymbol={vi.fn()} strategyTimeframes={['1d']}
        activeTimeframe="1d" onTimeframeChange={vi.fn()}
      />,
    )

    await waitFor(() => expect(screen.getByRole('option', { name: '股票' })).toBeInTheDocument())
    fireEvent.change(screen.getAllByRole('combobox')[1]!, { target: { value: 'stock' } })
    fireEvent.click(screen.getByRole('button', { name: '开始选股' }))
    const stopButton = await screen.findByRole('button', { name: /停止选股/ })
    fireEvent.click(stopButton)

    await waitFor(() => expect(screen.getByText(/已停止，已扫描/)).toBeInTheDocument())
    expect(vi.mocked(runScreener).mock.calls[0]?.[1]?.signal?.aborted).toBe(true)
  })

  it('renders switchable tabs for every strategy timeframe and its own indicators', () => {
    const active = {
      id: 'strategy-multi', name: '多周期策略', logic: 'AND', enabled: true, createdAt: 1, updatedAt: 1,
      primaryTimeframeId: '1d', secondaryTimeframeIds: ['30m'],
      conditionGroups: [{ id: 'group', conditions: [
        {
          id: 'ma5', name: '', enabled: true, timeframeId: '1d', operator: 'gt',
          left: { source: 'indicator', indicatorType: 'ma', params: { period: 5 }, field: 'value' },
          right: { source: 'constant', value: 0 },
        },
        {
          id: 'buy1', name: '', enabled: true, timeframeId: '30m', operator: 'gt',
          left: { source: 'chan', element: 'buySellPoint', property: 'buy1' },
          right: { source: 'constant', value: 0 },
        },
      ] }],
    } as ConditionTemplate
    const onTimeframeChange = vi.fn()
    useAppStore.setState({ templates: [active], activeTemplateId: active.id })

    render(
      <ScreenerWorkspace
        selectedSymbol="000001_sz" selectedName="平安银行" chart={<div>图表占位</div>}
        onSelectSymbol={vi.fn()} strategyTimeframes={['1d', '30m']}
        activeTimeframe="1d" onTimeframeChange={onTimeframeChange}
      />,
    )

    expect(screen.getByRole('button', { name: '日线 · MA5' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '30分钟 · 缠论' }))
    expect(onTimeframeChange).toHaveBeenCalledWith('30m')
  })
})
