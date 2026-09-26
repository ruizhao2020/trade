import { act, fireEvent, render, screen } from '@testing-library/react'
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

  it('starts with market and symbol unselected', async () => {
    render(<SymbolSelector market="" symbol="" symbolName="" onMarketChange={vi.fn()} onSymbolChange={vi.fn()} />)

    expect(screen.getByLabelText('选择市场')).toHaveValue('')
    expect(screen.getByLabelText('搜索并选择标的')).toBeDisabled()
    expect(screen.getByPlaceholderText('请先选择市场')).toBeInTheDocument()

    // 放掉 300ms 防抖，确认未选择市场时确实不会去请求标的列表
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 350)) })
    expect(fetchSymbols).not.toHaveBeenCalled()
  })

  it('keeps the symbol pending after a market is selected', async () => {
    const onMarketChange = vi.fn()
    const onSymbolChange = vi.fn()
    render(<SymbolSelector market="" symbol="" symbolName="" onMarketChange={onMarketChange} onSymbolChange={onSymbolChange} />)

    // 市场目录改为只取自后端，需要等接口返回后选项才存在
    await screen.findByRole('option', { name: '股票' })
    fireEvent.change(screen.getByLabelText('选择市场'), { target: { value: 'stock' } })

    expect(onMarketChange).toHaveBeenCalledWith('stock')
    expect(onSymbolChange).toHaveBeenCalledWith('', '')
  })

  it('offers the backend default symbol as an explicit one-click choice', async () => {
    const onSymbolChange = vi.fn()
    render(<SymbolSelector market="stock" symbol="" symbolName="" onMarketChange={vi.fn()} onSymbolChange={onSymbolChange} />)

    fireEvent.focus(screen.getByLabelText('搜索并选择标的'))
    const defaultOption = await screen.findByRole('button', { name: /平安银行/ })

    // 默认标的只是快捷入口，仍由用户点击后才生效，不自动加载行情
    expect(onSymbolChange).not.toHaveBeenCalled()
    fireEvent.click(defaultOption)
    expect(onSymbolChange).toHaveBeenCalledWith('000001_sz', '平安银行')
  })

  it('shows a load failure instead of an empty result list', async () => {
    vi.mocked(fetchSymbols).mockRejectedValue(new Error('服务暂时不可用，请稍后重试'))
    render(<SymbolSelector market="stock" symbol="" symbolName="" onMarketChange={vi.fn()} onSymbolChange={vi.fn()} />)

    fireEvent.focus(screen.getByLabelText('搜索并选择标的'))

    expect(await screen.findByText('标的列表加载失败')).toBeInTheDocument()
    expect(screen.queryByText('无匹配结果')).not.toBeInTheDocument()
  })
})
