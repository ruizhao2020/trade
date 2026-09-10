import { useEffect, useRef, useState } from 'react'
import { SignalState } from '../core/types.ts'
import type { Condition } from '../core/types.ts'
import { useAppStore } from '../store/useAppStore.ts'
import { financialValueColorClass } from '../core/financialColors.ts'
import {
  createTemplate,
  deleteTemplate as deleteTemplateApi,
  fetchTemplates,
  updateTemplate as updateTemplateApi,
} from '../api/template.ts'
import { evaluateSignal, runBacktest } from '../api/signal.ts'
import type { BacktestResult } from '../api/signal.ts'
import { LayerControls } from './LayerControls.tsx'
import { TemplateEditor } from './TemplateEditor.tsx'

const STATE_LABEL: Record<string, string> = {
  idle: '尚未评估',
  evaluating: '评估中',
  partial: '部分满足',
  ready: '信号就绪',
}

const STATE_COLOR: Record<string, string> = {
  idle: 'var(--text-muted)',
  evaluating: 'var(--accent)',
  partial: 'var(--accent-orange)',
  ready: 'var(--accent-green)',
}

const CHAN_SIGNAL_LABEL: Record<string, string> = {
  buy1: '1买', buy2: '2买', buy3: '3买', sell1: '1卖', sell2: '2卖', sell3: '3卖',
}

const PRICE_FIELD_LABEL: Record<string, string> = {
  close: '收盘价', high: '最高价', low: '最低价', open: '开盘价', volume: '成交量',
}

const STOP_LOSS_UNIT: Record<string, string> = { atr: ' 倍平均真实波幅', fixed_pct: '%', swing_low: ' 近期低点' }
const TAKE_PROFIT_UNIT: Record<string, string> = { atr: ' 倍平均真实波幅', fixed_pct: '%', rr_ratio: ' 倍风险收益' }

interface Props {
  symbol?: string
  embedded?: boolean
  showLayers?: boolean
  onEvaluated?: (symbol: string) => void
  onBacktestResult?: (result: BacktestResult) => void
}

function conditionLabel(condition: Condition) {
  if (condition.name) return condition.name
  const left = condition.left
  if (left.source === 'chan' && left.element === 'buySellPoint') return CHAN_SIGNAL_LABEL[left.property ?? ''] ?? '买卖点'
  if (left.source === 'chan' && left.element === 'divergence') return left.property === 'top' ? '顶背驰' : left.property === 'bottom' ? '底背驰' : '背驰'
  if (left.source === 'chan' && left.element === 'bi') return '笔数'
  if (left.source === 'chan' && left.element === 'zhongshu') return '中枢数'
  if (left.source === 'price') return PRICE_FIELD_LABEL[left.field] ?? left.field
  if (left.source === 'indicator') return left.indicatorType.toUpperCase()
  return '策略条件'
}

function PlusIcon() {
  return <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5" aria-hidden="true"><path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
}

function PencilIcon() {
  return <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5" aria-hidden="true"><path d="m3 10.8.5-2.5 6-6a1.4 1.4 0 0 1 2 2l-6 6-2.5.5Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" /></svg>
}

function MoreIcon() {
  return <svg viewBox="0 0 14 14" fill="currentColor" className="w-3.5 h-3.5" aria-hidden="true"><circle cx="3" cy="7" r="1" /><circle cx="7" cy="7" r="1" /><circle cx="11" cy="7" r="1" /></svg>
}

function ChevronIcon({ open }: { open: boolean }) {
  return <svg viewBox="0 0 12 12" fill="none" className={`w-3 h-3 text-[var(--text-muted)] transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true"><path d="m3 5 3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
}

export function SignalPanel({ symbol = '300843_sz', embedded = false, showLayers = true, onEvaluated, onBacktestResult }: Props) {
  const [showEditor, setShowEditor] = useState(false)
  const [editTemplateId, setEditTemplateId] = useState<string | null>(null)
  const [layersExpanded, setLayersExpanded] = useState(true)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [evaluating, setEvaluating] = useState(false)
  const [backtesting, setBacktesting] = useState(false)
  const [templateAction, setTemplateAction] = useState(false)
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null)
  const [panelView, setPanelView] = useState<'live' | 'backtest'>('live')
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)

  const activeTemplateId = useAppStore((state) => state.activeTemplateId)
  const templates = useAppStore((state) => state.templates)
  const templateSignals = useAppStore((state) => state.templateSignals)
  const addStoreTemplate = useAppStore((state) => state.addTemplate)
  const deleteStoreTemplate = useAppStore((state) => state.deleteTemplate)
  const updateStoreTemplate = useAppStore((state) => state.updateTemplate)
  const setActiveTemplateId = useAppStore((state) => state.setActiveTemplateId)
  const setTemplateSignal = useAppStore((state) => state.setTemplateSignal)

  useEffect(() => {
    fetchTemplates()
      .then((list) => list.forEach((template) => {
        const exists = useAppStore.getState().templates.some((item) => item.id === template.id)
        if (exists) updateStoreTemplate(template.id, template)
        else addStoreTemplate(template)
      }))
      .catch((error) => console.error('[SL:SIGNAL] failed to load templates:', error))
  }, [addStoreTemplate, updateStoreTemplate])

  useEffect(() => {
    if (!menuOpen) return
    const closeMenu = (event: MouseEvent) => {
      const target = event.target as Node
      if (!menuRef.current?.contains(target) && !menuButtonRef.current?.contains(target)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', closeMenu)
    return () => document.removeEventListener('mousedown', closeMenu)
  }, [menuOpen])

  const activeTemplate = templates.find((template) => template.id === activeTemplateId)
  const activeSignal = activeTemplateId ? templateSignals[activeTemplateId] : undefined
  const editTemplate = editTemplateId ? templates.find((template) => template.id === editTemplateId) : undefined
  const displayedState = activeTemplate && !activeTemplate.enabled ? 'disabled' : activeSignal?.state ?? 'idle'
  const displayedStateLabel = displayedState === 'disabled' ? '策略已停用' : STATE_LABEL[displayedState]
  const displayedStateColor = displayedState === 'disabled' ? 'var(--text-muted)' : STATE_COLOR[displayedState]

  async function handleEvaluate() {
    if (!activeTemplate) return
    setPanelView('live')
    setEvaluating(true)
    try {
      const signal = await evaluateSignal(symbol, activeTemplate)
      setTemplateSignal(activeTemplate.id, signal)
      onEvaluated?.(symbol)
    } catch (error: unknown) {
      console.error('[SL:SIGNAL] evaluate failed:', error)
    } finally {
      setEvaluating(false)
    }
  }

  async function handleBacktest() {
    if (!activeTemplate) return
    setPanelView('backtest')
    setBacktesting(true)
    setBacktestResult(null)
    try {
      const result = await runBacktest(symbol, activeTemplate, 300)
      setBacktestResult(result)
      onBacktestResult?.(result)
    } catch (error: unknown) {
      console.error('[SL:SIGNAL] backtest failed:', error)
    } finally {
      setBacktesting(false)
    }
  }

  async function handleCopyTemplate() {
    if (!activeTemplate) return
    setTemplateAction(true)
    setMenuOpen(false)
    try {
      const now = Date.now()
      const copied = await createTemplate({ ...activeTemplate, id: `tpl_${now}`, name: `${activeTemplate.name} 副本`, createdAt: now, updatedAt: now })
      addStoreTemplate(copied)
      setActiveTemplateId(copied.id)
    } catch (error: unknown) {
      console.error('[SL:SIGNAL] copy template failed:', error)
    } finally {
      setTemplateAction(false)
    }
  }

  async function handleToggleTemplate() {
    if (!activeTemplate) return
    setTemplateAction(true)
    setMenuOpen(false)
    try {
      const updated = await updateTemplateApi(activeTemplate.id, { ...activeTemplate, enabled: !activeTemplate.enabled })
      updateStoreTemplate(activeTemplate.id, updated)
    } catch (error: unknown) {
      console.error('[SL:SIGNAL] toggle template failed:', error)
    } finally {
      setTemplateAction(false)
    }
  }

  async function handleDeleteTemplate() {
    if (!activeTemplate || !window.confirm(`确认删除策略“${activeTemplate.name}”？`)) return
    setTemplateAction(true)
    setMenuOpen(false)
    try {
      await deleteTemplateApi(activeTemplate.id)
      deleteStoreTemplate(activeTemplate.id)
      setActiveTemplateId(null)
    } catch (error: unknown) {
      console.error('[SL:SIGNAL] delete template failed:', error)
    } finally {
      setTemplateAction(false)
    }
  }

  const openNewTemplate = () => {
    setEditTemplateId(null)
    setShowEditor(true)
  }
  const openEditTemplate = () => {
    if (!activeTemplate) return
    setEditTemplateId(activeTemplate.id)
    setShowEditor(true)
  }

  const management = (
    <div className="relative px-3 py-3 border-b border-[var(--border-primary)] shrink-0">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">策略模板</span>
        <div className="flex items-center gap-2">
          {activeTemplate && <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${activeTemplate.enabled ? 'bg-[rgba(54,201,149,0.10)] text-[var(--accent-green)]' : 'bg-[var(--bg-tertiary)] text-[var(--text-muted)]'}`}>{activeTemplate.enabled ? '已启用' : '已停用'}</span>}
          <span className="text-[10px] font-mono text-[var(--text-muted)]">{templates.length} 个</span>
        </div>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_34px_34px_34px] gap-1.5">
        <select
          value={activeTemplateId ?? ''}
          onChange={(event) => {
            setActiveTemplateId(event.target.value || null)
            setPanelView('live')
            setBacktestResult(null)
          }}
          className="min-w-0 h-9 px-3 rounded-md border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[12px] text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
        >
          <option value="">选择策略...</option>
          {templates.map((template) => <option key={template.id} value={template.id}>{template.name}{template.enabled ? '' : '（已停用）'}</option>)}
        </select>
        <button type="button" onClick={openNewTemplate} aria-label="新建策略" className="h-9 rounded-md border border-[var(--border-primary)] flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"><PlusIcon /></button>
        <button type="button" onClick={openEditTemplate} disabled={!activeTemplate} aria-label="编辑当前策略" className="h-9 rounded-md border border-[var(--border-primary)] flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] disabled:opacity-30"><PencilIcon /></button>
        <button ref={menuButtonRef} type="button" onClick={() => setMenuOpen((open) => !open)} disabled={!activeTemplate} aria-label="更多策略操作" aria-expanded={menuOpen} className="h-9 rounded-md border border-[var(--border-primary)] flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] disabled:opacity-30"><MoreIcon /></button>
      </div>

      {menuOpen && activeTemplate && (
        <div ref={menuRef} className="absolute z-30 top-[82px] right-3 w-36 p-1 rounded-md border border-[var(--border-accent)] bg-[var(--bg-surface)] shadow-2xl">
          <button type="button" onClick={handleCopyTemplate} disabled={templateAction} className="w-full h-8 px-2 rounded text-left text-[11px] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]">复制策略</button>
          <button type="button" onClick={handleToggleTemplate} disabled={templateAction} className="w-full h-8 px-2 rounded text-left text-[11px] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]">{activeTemplate.enabled ? '停用策略' : '启用策略'}</button>
          <button type="button" onClick={handleDeleteTemplate} disabled={templateAction} className="w-full h-8 px-2 rounded text-left text-[11px] text-[var(--accent-red)] hover:bg-[var(--bg-tertiary)]">删除策略</button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-1 p-0.5 mt-3 rounded-md border border-[var(--border-primary)]">
        <button type="button" onClick={() => setPanelView('live')} className={`h-8 rounded text-[11px] transition-colors ${panelView === 'live' ? 'bg-[var(--bg-surface)] text-[var(--text-primary)]' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}`}>实时信号</button>
        <button type="button" onClick={() => setPanelView('backtest')} className={`h-8 rounded text-[11px] transition-colors ${panelView === 'backtest' ? 'bg-[var(--bg-surface)] text-[var(--text-primary)]' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}`}>回测</button>
      </div>
    </div>
  )

  const liveView = activeTemplate && (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="px-3 py-3 border-b border-[var(--border-primary)]">
        <div className={`p-3 rounded-md border-l-[3px] ${activeSignal ? 'bg-[var(--bg-primary)]' : 'bg-[var(--bg-tertiary)]/40'}`} style={{ borderLeftColor: displayedStateColor }}>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: displayedStateColor }} />
            <span className="text-[12px] font-semibold" style={{ color: displayedStateColor }}>{evaluating ? '评估中' : displayedStateLabel}</span>
            <span className="ml-auto text-[11px] font-mono text-[var(--text-muted)]">{activeSignal ? `${activeSignal.progressPercent}%` : '—'}</span>
          </div>
          {activeSignal?.state === SignalState.Partial && <div className="h-1 mt-2 rounded-full bg-[var(--bg-tertiary)] overflow-hidden"><div className="h-full bg-[var(--accent-orange)]" style={{ width: `${activeSignal.progressPercent}%` }} /></div>}
          <div className="mt-1.5 text-[10px] text-[var(--text-muted)]">{!activeTemplate.enabled ? '启用后才能运行实时评估和参与选股' : activeSignal ? '条件结果已同步到右侧图表' : '运行评估后显示当前标的的策略状态'}</div>
        </div>
      </div>

      <div className="px-3 py-3">
        <div className="flex items-center gap-2 mb-2"><span className="text-[11px] font-semibold">入场条件</span><span className="px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[10px] text-[var(--text-muted)]">{activeTemplate.logic === 'AND' ? '全部满足' : '满足任一组'}</span></div>
        {activeTemplate.conditionGroups.map((group, groupIndex) => (
          <div key={`${activeTemplate.id}:entry:${group.id}:${groupIndex}`} className="mb-3 last:mb-0">
            <div className="flex items-center gap-2 mb-1.5"><span className="text-[10px] tracking-wider text-[var(--text-muted)]">{group.name?.trim() || `条件组 ${groupIndex + 1}`}</span><span className="h-px flex-1 bg-[var(--border-primary)]" /></div>
            {group.conditions.filter((condition) => condition.enabled).map((condition, conditionIndex) => {
              const evaluation = activeSignal?.groups[groupIndex]?.evaluations.find((item) => item.conditionId === condition.id)
              return (
                <div key={`${activeTemplate.id}:entry:${groupIndex}:${condition.id}:${conditionIndex}`} className="min-h-10 px-2 py-1.5 mb-1 rounded-md bg-[var(--bg-tertiary)]/55 flex items-center gap-2">
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${evaluation?.satisfied ? 'bg-[var(--accent-green)]' : 'bg-[var(--text-muted)]'}`} />
                  <span className="flex-1 min-w-0"><span className="block truncate text-[11px] text-[var(--text-secondary)]">{conditionLabel(condition)}</span><span className="block text-[10px] font-mono text-[var(--text-muted)]">{condition.timeframeId ?? activeTemplate.primaryTimeframeId}</span></span>
                  {evaluation && <span className={`text-[10px] font-mono ${evaluation.satisfied ? 'text-[var(--accent-green)]' : 'text-[var(--text-muted)]'}`}>{evaluation.leftValue.toFixed(2)}</span>}
                </div>
              )
            })}
          </div>
        ))}

        <div className="flex items-center gap-2 mt-4 mb-2"><span className="text-[11px] font-semibold">出场与仓位</span><span className="ml-auto text-[10px] text-[var(--text-muted)]">{activeTemplate.tradeParams ? (activeTemplate.tradeParams.exitLogic === 'AND' ? '全部满足' : '满足任一组') : '止盈/止损'}</span></div>
        {activeTemplate.tradeParams ? (
          <div className="grid grid-cols-3 gap-px overflow-hidden rounded-md bg-[var(--border-primary)]">
            <div className="bg-[var(--bg-tertiary)] p-2"><span className="block text-[10px] text-[var(--text-muted)]">止损</span><span className="block mt-1 text-[11px] font-mono">{activeTemplate.tradeParams.stopLossValue}{STOP_LOSS_UNIT[activeTemplate.tradeParams.stopLossType] ?? ''}</span></div>
            <div className="bg-[var(--bg-tertiary)] p-2"><span className="block text-[10px] text-[var(--text-muted)]">止盈</span><span className="block mt-1 text-[11px] font-mono">{activeTemplate.tradeParams.takeProfitValue}{TAKE_PROFIT_UNIT[activeTemplate.tradeParams.takeProfitType] ?? ''}</span></div>
            <div className="bg-[var(--bg-tertiary)] p-2"><span className="block text-[10px] text-[var(--text-muted)]">仓位</span><span className="block mt-1 text-[11px] font-mono">{activeTemplate.tradeParams.positionValue}%</span></div>
          </div>
        ) : <div className="text-[11px] text-[var(--text-muted)]">未配置风控参数</div>}
      </div>

      <div className="sticky bottom-0 p-3 mt-auto border-t border-[var(--border-primary)] bg-[var(--bg-secondary)] flex gap-2">
        <button type="button" onClick={handleBacktest} disabled={backtesting} className="h-9 px-3 rounded-md border border-[var(--border-primary)] text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] disabled:opacity-40">{backtesting ? '回测中...' : '运行回测'}</button>
        <button type="button" onClick={handleEvaluate} disabled={evaluating || !activeTemplate.enabled} className="h-9 flex-1 rounded-md bg-[var(--accent)] text-white text-[11px] font-medium hover:bg-[var(--accent-hover)] disabled:opacity-40">{evaluating ? '评估中...' : '重新评估'}</button>
      </div>
    </div>
  )

  const backtestView = activeTemplate && (
    <div className="flex-1 min-h-0 overflow-y-auto px-3 py-3">
      {backtesting && <div className="h-40 flex items-center justify-center text-[11px] text-[var(--text-muted)]">正在运行回测...</div>}
      {!backtesting && !backtestResult && <div className="h-40 flex flex-col items-center justify-center gap-3 text-[11px] text-[var(--text-muted)]"><span>尚未生成回测结果</span><button type="button" onClick={handleBacktest} className="h-8 px-3 rounded-md bg-[var(--accent)] text-white">运行回测</button></div>}
      {backtestResult && (
        <>
          <div className="flex items-center justify-between mb-3"><span className="text-[11px] font-semibold">最近 300 根 K 线</span><span className="text-[10px] text-[var(--text-muted)]">{backtestResult.totalTrades} 笔交易</span></div>
          <div className="grid grid-cols-2 gap-1.5">
            <div className="rounded-md bg-[var(--bg-tertiary)] p-2.5"><span className="block text-[10px] text-[var(--text-muted)]">累计收益</span><span className={`block mt-1 text-[15px] font-mono ${financialValueColorClass(backtestResult.totalReturn)}`}>{backtestResult.totalReturn}%</span></div>
            <div className="rounded-md bg-[var(--bg-tertiary)] p-2.5"><span className="block text-[10px] text-[var(--text-muted)]">最大回撤</span><span className={`block mt-1 text-[15px] font-mono ${financialValueColorClass(-backtestResult.maxDrawdown)}`}>-{backtestResult.maxDrawdown}%</span></div>
            <div className="rounded-md bg-[var(--bg-tertiary)] p-2.5"><span className="block text-[10px] text-[var(--text-muted)]">胜率</span><span className="block mt-1 text-[15px] font-mono">{backtestResult.winRate}%</span></div>
            <div className="rounded-md bg-[var(--bg-tertiary)] p-2.5"><span className="block text-[10px] text-[var(--text-muted)]">盈亏因子</span><span className="block mt-1 text-[15px] font-mono">{backtestResult.profitFactor}</span></div>
          </div>
          {backtestResult.trades.length > 0 && <div className="mt-4"><div className="text-[11px] font-semibold mb-2">交易明细</div>{backtestResult.trades.map((trade, index) => <div key={`${trade.entryTime}-${index}`} className="grid grid-cols-[24px_1fr_auto] gap-2 py-2 border-b border-[var(--border-primary)] text-[10px]"><span className="text-[var(--text-muted)]">#{index + 1}</span><span className="font-mono text-[var(--text-secondary)]">{trade.entryPrice} → {trade.exitPrice}</span><span className={`font-mono ${financialValueColorClass(trade.pnlPct)}`}>{trade.pnlPct >= 0 ? '+' : ''}{trade.pnlPct}%</span></div>)}</div>}
          <button type="button" onClick={handleBacktest} className="w-full h-9 mt-4 rounded-md bg-[var(--accent)] text-white text-[11px] font-medium">重新回测</button>
        </>
      )}
    </div>
  )

  const panelContent = (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-secondary)]" style={{ width: embedded ? '100%' : 280 }}>
      {!embedded && <div className="h-10 px-4 flex items-center border-b border-[var(--border-primary)] text-[11px] font-semibold text-[var(--text-muted)]">策略</div>}
      {showLayers && <div className="border-b border-[var(--border-primary)]"><button type="button" onClick={() => setLayersExpanded((open) => !open)} className="w-full px-4 py-2.5 flex items-center justify-between text-[11px] text-[var(--text-muted)] hover:bg-[var(--bg-tertiary)]/50"><span>图层</span><ChevronIcon open={layersExpanded} /></button>{layersExpanded && <LayerControls />}</div>}
      {management}
      {!activeTemplate && <div className="flex-1 flex flex-col items-center justify-center gap-3 px-5 text-center"><span className="w-10 h-10 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center text-[var(--text-muted)]"><PlusIcon /></span><span className="text-[11px] text-[var(--text-muted)]">选择一个策略，或新建策略开始评估</span><button type="button" onClick={openNewTemplate} className="h-8 px-3 rounded-md border border-[var(--border-primary)] text-[11px] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]">新建策略</button></div>}
      {panelView === 'live' ? liveView : backtestView}
      {showEditor && <TemplateEditor template={editTemplate} onClose={() => { setShowEditor(false); setEditTemplateId(null) }} />}
    </div>
  )

  if (embedded) return panelContent

  return (
    <>
      <div className="hidden md:flex flex-col h-full border-l border-[var(--border-primary)]" style={{ width: 280 }}>{panelContent}</div>
      <div className="md:hidden">
        <button type="button" onClick={() => setMobileOpen((open) => !open)} className="fixed bottom-4 right-4 z-40 w-11 h-11 rounded-full bg-[var(--accent)] text-white shadow-lg flex items-center justify-center"><PlusIcon /></button>
        {mobileOpen && <div className="fixed inset-0 z-30 bg-black/50" onClick={() => setMobileOpen(false)}><div className="absolute bottom-0 left-0 right-0 bg-[var(--bg-secondary)] rounded-t-xl max-h-[75vh] overflow-y-auto border-t border-[var(--border-primary)]" onClick={(event) => event.stopPropagation()}>{panelContent}</div></div>}
      </div>
    </>
  )
}
