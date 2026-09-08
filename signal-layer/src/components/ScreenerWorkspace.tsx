import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { runScreener, type ScreenerMatch } from '../api/screener.ts'
import { fetchTemplates } from '../api/template.ts'
import { useAppStore } from '../store/useAppStore.ts'

interface Props {
  selectedSymbol: string
  selectedName: string
  chart: ReactNode
  onSelectSymbol: (symbol: string, name: string) => void
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
  const [universe, setUniverse] = useState('all')
  const [scanning, setScanning] = useState(false)
  const [progress, setProgress] = useState({ done: 0, total: 0 })
  const [results, setResults] = useState<ScreenerMatch[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (templates.length > 0) return
    fetchTemplates()
      .then((list) => {
        list.forEach((template) => addTemplate(template))
        if (!activeTemplateId && list[0]) setActiveTemplateId(list[0].id)
      })
      .catch(() => {})
  }, [activeTemplateId, addTemplate, setActiveTemplateId, templates.length])

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
      const limit = universe === 'all' ? 24 : 16
      setProgress({ done: 0, total: limit })
      const response = await runScreener(activeTemplate, { market: 'stock', limit, minProgress: 1, concurrency: 4 })
      setResults(response.results)
      setProgress({ done: response.scannedCount, total: response.scannedCount })
      const first = response.results[0]
      if (first) onSelectSymbol(first.item.symbol, first.item.name)
    } catch (scanError) {
      setError(scanError instanceof Error ? scanError.message : '选股失败')
    } finally {
      setScanning(false)
    }
  }

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
        <div>
          <label className="block text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)] mb-1.5">股票池</label>
          <select
            value={universe}
            onChange={(event) => setUniverse(event.target.value)}
            className="w-full h-9 px-3 rounded-md border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[12px] text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
          >
            <option value="all">沪深 A 股 · 前 24 个</option>
            <option value="watchlist">自选范围 · 前 16 个</option>
          </select>
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

      <section className="flex-1 min-w-[280px] flex flex-col bg-[var(--bg-primary)]">
        <div className="h-12 px-4 flex items-center gap-3 border-b border-[var(--border-primary)] shrink-0">
          <span className="text-[12px] font-semibold">{results.length} 个标的匹配</span>
          {progress.total > 0 && <span className="text-[10px] text-[var(--text-muted)]">已扫描 {progress.total} 个标的</span>}
        </div>
        <div className="flex-1 overflow-auto">
          <table className="w-full min-w-[460px] border-collapse">
            <thead className="sticky top-0 bg-[var(--bg-secondary)] z-10">
              <tr className="text-left text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
                <th className="font-medium px-4 py-2.5 border-b border-[var(--border-primary)]">标的</th>
                <th className="font-medium px-3 py-2.5 border-b border-[var(--border-primary)]">匹配度</th>
                <th className="font-medium px-3 py-2.5 border-b border-[var(--border-primary)]">状态</th>
                <th className="font-medium px-3 py-2.5 border-b border-[var(--border-primary)]">行业</th>
              </tr>
            </thead>
            <tbody>
              {results.map(({ item, isReady, progressPercent }) => {
                const selected = selectedSymbol === item.symbol
                return (
                  <tr
                    key={item.symbol}
                    onClick={() => onSelectSymbol(item.symbol, item.name)}
                    className={`cursor-pointer transition-colors ${selected ? 'bg-[rgba(108,140,255,0.08)] shadow-[inset_2px_0_0_var(--accent)]' : 'hover:bg-[var(--bg-tertiary)]/50'}`}
                  >
                    <td className="px-4 py-3 border-b border-[var(--border-primary)]">
                      <div className="text-[12px] font-medium">{item.name}</div>
                      <div className="text-[10px] font-mono text-[var(--text-muted)] mt-0.5">{item.symbol}</div>
                    </td>
                    <td className="px-3 py-3 border-b border-[var(--border-primary)] font-mono text-[12px] text-[var(--accent-green)]">{progressPercent}%</td>
                    <td className="px-3 py-3 border-b border-[var(--border-primary)] text-[11px] text-[var(--text-secondary)]">{isReady ? '信号就绪' : '部分满足'}</td>
                    <td className="px-3 py-3 border-b border-[var(--border-primary)] text-[11px] text-[var(--text-muted)]">{item.industry || '—'}</td>
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

      <aside className="w-[300px] xl:w-[360px] shrink-0 border-l border-[var(--border-primary)] bg-[var(--bg-primary)] flex flex-col min-w-0">
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
  )
}
