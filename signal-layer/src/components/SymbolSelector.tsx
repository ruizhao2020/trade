/**
 * ============================================================================
 * 品种/标的切换选择器
 * ============================================================================
 *
 * 交互流程：先选「品种」（股票/期货），再选「标的」（搜索下拉）。
 * 选中标的后回调通知父组件刷新图表。
 *
 * 样式遵循全局暗色主题（CSS 变量 var(--xxx)）。
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { fetchSymbols, type SymbolItem } from '../api/symbol.ts'

interface Props {
  /** 当前品种类型 */
  market: 'stock' | 'futures'
  /** 当前标的 symbol */
  symbol: string
  /** 当前标的名称（用于展示） */
  symbolName: string
  /** 品种变更回调 */
  onMarketChange: (market: 'stock' | 'futures') => void
  /** 标的变更回调 */
  onSymbolChange: (symbol: string, name: string) => void
}

export function SymbolSelector({ market, symbol, symbolName, onMarketChange, onSymbolChange }: Props) {
  const [keyword, setKeyword] = useState('')
  const [options, setOptions] = useState<SymbolItem[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const selectorRef = useRef<HTMLDivElement>(null)

  /** 加载标的列表。keyword 作为参数传入，避免闭包捕获旧值 */
  const loadSymbols = useCallback(async (kw?: string) => {
    setLoading(true)
    try {
      const resp = await fetchSymbols(market, kw || undefined, 50)
      setOptions(resp.symbols)
    } catch (e) {
      console.error('加载标的列表失败:', e)
      setOptions([])
    } finally {
      setLoading(false)
    }
  }, [market])

  const handleMarketSelect = (nextMarket: 'stock' | 'futures') => {
    setKeyword('')
    setOptions([])
    setOpen(false)
    onMarketChange(nextMarket)
  }

  // keyword 变化时，防抖 300ms 后搜索（用最新 keyword）
  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadSymbols(keyword)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [keyword, loadSymbols])

  // 输入只更新 keyword，由 useEffect 负责防抖搜索
  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    setKeyword(e.target.value)
  }

  const handleSelect = (item: SymbolItem) => {
    onSymbolChange(item.symbol, item.name)
    setOpen(false)
    setKeyword('')
  }

  // 点击外部关闭下拉
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (selectorRef.current && !selectorRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div className="flex items-center gap-2.5 relative shrink-0" ref={selectorRef}>
      {/* 品种选择 */}
      <div className="h-9 flex items-center gap-0.5 bg-[var(--bg-primary)] border border-[var(--border-primary)] rounded-md p-0.5 shrink-0">
        {(['stock', 'futures'] as const).map(m => (
          <button
            key={m}
            onClick={() => handleMarketSelect(m)}
            className={`h-7 text-[12px] px-3 rounded font-medium transition-colors duration-150 ${
              market === m
                ? 'bg-[var(--bg-surface)] text-[var(--text-primary)]'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            {m === 'stock' ? '股票' : '期货'}
          </button>
        ))}
      </div>

      {/* 标的搜索选择 */}
      <div className="relative shrink-0">
        <input
          value={keyword}
          onChange={handleInput}
          onFocus={() => setOpen(true)}
          placeholder={symbolName ? `${symbolName}  ${symbol}` : '搜索代码或名称...'}
          aria-label="搜索并选择标的"
          className="w-64 h-9 text-[12px] px-3 rounded-md bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-primary)] outline-none focus:border-[var(--accent)] placeholder:text-[var(--text-secondary)]"
        />
        {open && (
          <div
            className="absolute top-full left-0 mt-2 w-[360px] max-h-[360px] overflow-y-auto overscroll-contain rounded-md border border-[var(--border-accent)] bg-[var(--bg-surface)] shadow-2xl z-[100]"
            onWheel={(event) => event.stopPropagation()}
          >
            {loading ? (
              <div className="px-4 py-5 text-[12px] text-[var(--text-muted)] text-center">加载中...</div>
            ) : options.length === 0 ? (
              <div className="px-4 py-5 text-[12px] text-[var(--text-muted)] text-center">无匹配结果</div>
            ) : (
              options.map(item => (
                <button
                  key={item.symbol}
                  onClick={() => handleSelect(item)}
                  className={`w-full min-h-11 text-left px-4 py-2.5 hover:bg-[var(--bg-tertiary)] transition-colors flex items-center gap-3 border-b border-[var(--border-primary)] last:border-b-0 ${
                    item.symbol === symbol ? 'bg-[rgba(108,140,255,0.08)]' : ''
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full shrink-0 ${item.symbol === symbol ? 'bg-[var(--accent)]' : 'border border-[var(--text-muted)]'}`} />
                  <span className="flex-1 min-w-0">
                    <span className="block text-[12px] font-medium text-[var(--text-primary)] truncate">{item.name}</span>
                    <span className="block text-[10px] text-[var(--text-muted)] mt-0.5 truncate">{item.industry || item.exchange || item.market}</span>
                  </span>
                  <span className="text-[var(--text-secondary)] font-mono text-[11px] shrink-0">{item.symbol}</span>
                </button>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}
