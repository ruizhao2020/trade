import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { runScreener, type ScreenerMatch } from '../api/screener.ts'
import { fetchTemplates } from '../api/template.ts'
import { useAppStore } from '../store/useAppStore.ts'
import { fetchMarkets, type MarketItem } from '../api/symbol.ts'

interface Props {
  selectedSymbol: string
  selectedName: string
  chart: ReactNode
  onSelectSymbol: (symbol: string, name: string, market: string) => void
}

function CollapseIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={`w-4 h-4 transition-transform ${collapsed ? 'rotate-180' : ''}`} aria-hidden="true">
      <path d="m10 3-5 5 5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function ScreenerWorkspace({ selectedSymbol, selectedName, chart, onSelectSymbol }: Props) {
  const templates = useAppStore((state) => state.templates)
  const activeTemplateId = useAppStore((state) => state.activeTemplateId)
  const addTemplate = useAppStore((state) => state.addTemplate)
  const setActiveTemplateId = useAppStore((state) => state.setActiveTemplateId)
  const [collapsed, setCollapsed] = useState(false)
  const [market, setMarket] = useState('stock')
  const [markets, setMarkets] = useState<MarketItem[]>([])
  const [targetCount, setTargetCount] = useState(10)
  const [scanning, setScanning] = useState(false)
  const [progress, setProgress] = useState({ done: 0, total: 0 })
  const [results, setResults] = useState<ScreenerMatch[]>([])
  const [error, setError] = useState<string | null>(null)
  const [resultWidth, setResultWidth] = useState(() => {
    const saved = Number(window.localStorage?.getItem('signal-layer-screener-result-width'))
    return Number.isFinite(saved) && saved >= 260 ? saved : 320
  })
  const [resizing, setResizing] = useState(false)
  const splitAreaRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (templates.length > 0) return
    fetchTemplates()
      .then((list) => {
        list.forEach((template) => addTemplate(template))
        if (!activeTemplateId && list[0]) setActiveTemplateId(list[0].id)
      })
      .catch(() => {})
  }, [activeTemplateId, addTemplate, setActiveTemplateId, templates.length])

  useEffect(() => {
    fetchMarkets().then((response) => setMarkets(response.markets)).catch(() => {})
  }, [])

  const activeTemplate = templates.find((template) => template.id === activeTemplateId) ?? templates[0]
  const conditionCount = useMemo(
    () => activeTemplate?.conditionGroups.reduce((total, group) => total + group.conditions.filter((condition) => condition.enabled).length, 0) ?? 0,
    [activeTemplate],
  )

  async function runScreen() {
    if (!activeTemplate) return
    setScanning(true)
    setError(null)
    setResults([])
    try {
      const maxCandidates = Math.min(2000, Math.max(100, targetCount * 50))
      const batchSize = 4
      let offset = 0
      let universeTotal = maxCandidates
      let matches: ScreenerMatch[] = []
      let firstSelected = false
      setProgress({ done: 0, total: maxCandidates })

      while (offset < Math.min(maxCandidates, universeTotal) && matches.length < targetCount) {
        const remaining = targetCount - matches.length
        const response = await runScreener(activeTemplate, {
          market,
          limit: Math.min(batchSize, maxCandidates - offset),
          offset,
          targetCount: remaining,
          minProgress: 1,
          concurrency: batchSize,
        })
        universeTotal = response.universeTotal
        offset += response.scannedCount
        const unique = new Map(matches.map((item) => [item.item.symbol, item]))
        response.results.forEach((item) => unique.set(item.item.symbol, item))
        matches = [...unique.values()]
          .sort((a, b) => Number(b.isReady) - Number(a.isReady) || b.progressPercent - a.progressPercent || a.item.symbol.localeCompare(b.item.symbol))
          .slice(0, targetCount)
        setResults(matches)
        setProgress({ done: offset, total: Math.min(maxCandidates, universeTotal) })

        if (!firstSelected && matches[0]) {
          firstSelected = true
          onSelectSymbol(matches[0].item.symbol, matches[0].item.name, matches[0].item.market)
        }
        if (response.scannedCount === 0) break
      }
      setProgress({ done: offset, total: offset })
    } catch (scanError) {
      setError(scanError instanceof Error ? scanError.message : '选股失败')
    } finally {
      setScanning(false)
    }
  }

  function startResize(event: React.PointerEvent<HTMLDivElement>) {
    event.preventDefault()
    const startX = event.clientX
    const startWidth = resultWidth
    const availableWidth = splitAreaRef.current?.clientWidth ?? 900
    const maxWidth = Math.max(260, availableWidth - 440)
    setResizing(true)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    const move = (moveEvent: PointerEvent) => {
      const next = Math.min(maxWidth, Math.max(260, startWidth + moveEvent.clientX - startX))
      setResultWidth(next)
    }
    const finish = () => {
      setResizing(false)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.removeEventListener('pointermove', move)
      document.removeEventListener('pointerup', finish)
    }
    document.addEventListener('pointermove', move)
    document.addEventListener('pointerup', finish)
  }

  useEffect(() => {
    window.localStorage?.setItem('signal-layer-screener-result-width', String(Math.round(resultWidth)))
  }, [resultWidth])

  const filters = (
    <div className="flex flex-col h-full min-h-0">
      <div className="px-4 pt-3 pb-4 space-y-3">
        <div>
          <label className="block text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">选股策略</label>
          <select
            value={activeTemplate?.id ?? ''}
            onChange={(event) => setActiveTemplateId(event.target.value || null)}
            className="w-full h-9 px-3 rounded-md border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[12px] text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
          >
            {templates.length === 0 && <option value="">暂无策略</option>}
            {templates.map((template) => <option key={template.id} value={template.id}>{template.name}{template.enabled ? '' : '（已停用）'}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-[1fr_88px] gap-2">
          <label className="block text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">市场
            <select value={market} onChange={(event) => setMarket(event.target.value)} className="mt-1.5 w-full h-9 px-3 rounded-md border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[12px] text-[var(--text-primary)] outline-none focus:border-[var(--accent)]">
              {markets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="block text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">选出数量
            <input type="number" min="1" max="100" value={targetCount} onChange={(event) => setTargetCount(Math.min(100, Math.max(1, Number(event.target.value) || 1)))} className="mt-1.5 w-full h-9 px-2 rounded-md border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[12px] font-mono text-[var(--text-primary)] outline-none focus:border-[var(--accent)]" />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-md border border-[var(--border-primary)] bg-[var(--bg-primary)] px-3 py-2">
            <div className="text-[10px] text-[var(--text-muted)]">信号周期</div>
            <div className="text-[12px] font-mono mt-0.5">{activeTemplate?.primaryTimeframeId ?? '—'}</div>
          </div>
          <div className="rounded-md border border-[var(--border-primary)] bg-[var(--bg-primary)] px-3 py-2">
            <div className="text-[10px] text-[var(--text-muted)]">条件数量</div>
            <div className="text-[12px] font-mono mt-0.5">{conditionCount}</div>
          </div>
        </div>
      </div>

      <div className="px-4 py-3 border-t border-[var(--border-primary)]">
        <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-2">筛选条件</div>
        <div className="space-y-2">
          {activeTemplate?.conditionGroups.flatMap((group) => group.conditions).filter((condition) => condition.enabled).slice(0, 5).map((condition) => (
            <div key={condition.id} className="flex items-start gap-2 text-[11px] text-[var(--text-secondary)]">
              <span className="w-1.5 h-1.5 mt-1.5 rounded-full bg-[var(--accent-green)] shrink-0" />
              <span className="line-clamp-2">{condition.name || '策略条件'}</span>
            </div>
          ))}
          {conditionCount === 0 && <div className="text-[11px] text-[var(--text-muted)]">当前策略没有启用条件</div>}
        </div>
      </div>

      <div className="mt-auto p-4 border-t border-[var(--border-primary)]">
        <button
          type="button"
          onClick={runScreen}
          disabled={!activeTemplate || !activeTemplate.enabled || scanning}
          className="w-full h-9 rounded-md bg-[var(--accent)] text-white text-[12px] font-medium hover:bg-[var(--accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {scanning ? `扫描中 ${progress.done}/${progress.total}` : activeTemplate && !activeTemplate.enabled ? '策略已停用' : '开始选股'}
        </button>
        {error && <div className="mt-2 text-[10px] text-[var(--accent-red)] break-all">{error}</div>}
      </div>
    </div>
  )

  return (
    <div className={`flex flex-1 min-h-0 overflow-hidden ${collapsed ? 'screen-filter-collapsed' : ''}`}>
      <aside className={`${collapsed ? 'w-11' : 'w-[220px] xl:w-[250px]'} shrink-0 border-r border-[var(--border-primary)] bg-[var(--bg-secondary)] flex flex-col transition-[width] duration-200 overflow-hidden`}>
        <div className="h-11 px-2 flex items-center gap-2 border-b border-[var(--border-primary)] shrink-0">
          <button type="button" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? '展开选股条件' : '收起选股条件'} className="w-8 h-8 rounded-md border border-[var(--border-primary)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] shrink-0">
            <CollapseIcon collapsed={collapsed} />
          </button>
          {!collapsed && <span className="text-[11px] font-semibold text-[var(--text-secondary)]">选股条件</span>}
        </div>
        {!collapsed && filters}
      </aside>

      <div ref={splitAreaRef} className="flex flex-1 min-w-0 overflow-hidden">
      <section className="shrink-0 min-w-0 flex flex-col bg-[var(--bg-primary)]" style={{ width: resultWidth }}>
        <div className="h-12 px-4 flex items-center gap-3 border-b border-[var(--border-primary)] shrink-0">
          <span className="text-[12px] font-semibold">{results.length} 个标的匹配</span>
          {progress.total > 0 && <span className="text-[10px] text-[var(--text-muted)]">{scanning ? `扫描中 ${progress.done}/${progress.total}，结果逐批返回` : `已扫描 ${progress.done} 个标的`}</span>}
        </div>
        <div className="flex-1 overflow-auto">
          <table className="w-full min-w-[260px] border-collapse">
            <thead className="sticky top-0 bg-[var(--bg-secondary)] z-10">
              <tr className="text-left text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
                <th className="font-medium px-4 py-2.5 border-b border-[var(--border-primary)]">标的</th>
                <th className="font-medium px-3 py-2.5 border-b border-[var(--border-primary)]">匹配度</th>
                <th className="font-medium px-3 py-2.5 border-b border-[var(--border-primary)]">状态</th>
              </tr>
            </thead>
            <tbody>
              {results.map(({ item, isReady, progressPercent }) => {
                const selected = selectedSymbol === item.symbol
                return (
                  <tr
                    key={item.symbol}
                    onClick={() => onSelectSymbol(item.symbol, item.name, item.market)}
                    className={`cursor-pointer transition-colors ${selected ? 'bg-[rgba(108,140,255,0.08)] shadow-[inset_2px_0_0_var(--accent)]' : 'hover:bg-[var(--bg-tertiary)]/50'}`}
                  >
                    <td className="px-4 py-3 border-b border-[var(--border-primary)]">
                      <div className="text-[12px] font-medium">{item.name}</div>
                      <div className="text-[10px] text-[var(--text-muted)] mt-0.5"><span className="font-mono">{item.symbol}</span>{item.industry && <span> · {item.industry}</span>}</div>
                    </td>
                    <td className="px-3 py-3 border-b border-[var(--border-primary)] font-mono text-[12px] text-[var(--accent-green)]">{progressPercent}%</td>
                    <td className="px-3 py-3 border-b border-[var(--border-primary)] text-[11px] text-[var(--text-secondary)]">{isReady ? '信号就绪' : '部分满足'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {!scanning && results.length === 0 && (
            <div className="h-full min-h-56 flex items-center justify-center text-[12px] text-[var(--text-muted)]">
              {activeTemplate ? '点击“开始选股”扫描当前股票池' : '请先创建或选择一个策略'}
            </div>
          )}
        </div>
      </section>

      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="调整选股列表和指标图宽度"
        onPointerDown={startResize}
        className={`group relative w-2 shrink-0 cursor-col-resize touch-none ${resizing ? 'bg-[rgba(108,140,255,.12)]' : 'bg-[var(--bg-secondary)]'}`}
      >
        <span className={`absolute inset-y-0 left-1/2 -translate-x-1/2 w-px transition-colors ${resizing ? 'bg-[var(--accent)]' : 'bg-[var(--border-primary)] group-hover:bg-[var(--accent)]'}`} />
        <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-1 h-10 rounded-full bg-[var(--border-accent)] group-hover:bg-[var(--accent)]" />
      </div>

      <aside className="flex-1 min-w-[440px] bg-[var(--bg-primary)] flex flex-col">
        <div className="h-12 px-4 flex items-center justify-between border-b border-[var(--border-primary)] shrink-0">
          <div>
            <div className="text-[12px] font-semibold">{selectedName}</div>
            <div className="text-[10px] font-mono text-[var(--text-muted)]">{selectedSymbol}</div>
          </div>
          <span className="text-[10px] text-[var(--text-muted)]">{activeTemplate?.name ?? '未选策略'}</span>
        </div>
        <div className="flex-1 relative min-h-0 flex">{chart}</div>
      </aside>
      </div>
    </div>
  )
}
