import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchMarkets, fetchSymbols } from '../api/symbol.ts'
import { SymbolSelector } from './SymbolSelector.tsx'

vi.mock('../api/symbol.ts', () => ({
  fetchMarkets: vi.fn(),
  fetchSymbols: vi.fn(),
}))

describe('SymbolSelector pending state', () => {
  beforeEach(() => {
    vi.mocked(fetchMarkets).mockResolvedValue({
      markets: [
        { id: 'stock', name: '股票', description: '', default_symbol: '000001_sz', default_symbol_name: '平安银行', enabled: true, sort_order: 10 },
      ],
    })
    vi.mocked(fetchSymbols).mockResolvedValue({ market: 'stock', symbols: [], total: 0, count: 0 })
  })

  it('starts with market and symbol unselected', () => {
    render(<SymbolSelector market="" symbol="" symbolName="" onMarketChange={vi.fn()} onSymbolChange={vi.fn()} />)

    expect(screen.getByLabelText('选择市场')).toHaveValue('')
    expect(screen.getByLabelText('搜索并选择标的')).toBeDisabled()
    expect(screen.getByPlaceholderText('请先选择市场')).toBeInTheDocument()
    expect(fetchSymbols).not.toHaveBeenCalled()
  })

  it('keeps the symbol pending after a market is selected', () => {
    const onMarketChange = vi.fn()
    const onSymbolChange = vi.fn()
    render(<SymbolSelector market="" symbol="" symbolName="" onMarketChange={onMarketChange} onSymbolChange={onSymbolChange} />)

    fireEvent.change(screen.getByLabelText('选择市场'), { target: { value: 'stock' } })

    expect(onMarketChange).toHaveBeenCalledWith('stock')
    expect(onSymbolChange).toHaveBeenCalledWith('', '')
  })
})
