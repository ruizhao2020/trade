import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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
  })

  it('does not select the first strategy or market automatically', async () => {
    render(
      <ScreenerWorkspace
        selectedSymbol=""
        selectedName=""
        chart={<div>图表占位</div>}
        onSelectSymbol={vi.fn()}
      />,
    )

    await waitFor(() => expect(screen.getByRole('option', { name: '测试策略' })).toBeInTheDocument())
    const selectors = screen.getAllByRole('combobox')
    expect(selectors[0]).toHaveValue('')
    expect(selectors[1]).toHaveValue('')
    expect(useAppStore.getState().activeTemplateId).toBeNull()
    expect(screen.getByRole('button', { name: '请选择策略' })).toBeDisabled()
  })
})
