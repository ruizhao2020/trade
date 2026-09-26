import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Chart } from './chart/Chart.tsx'
import { IndicatorInfoPanel } from './components/IndicatorInfoPanel.tsx'
import { IndicatorWorkbenchToolbar } from './components/IndicatorWorkbenchToolbar.tsx'
import { ScreenerWorkspace } from './components/ScreenerWorkspace.tsx'
import { SignalPanel } from './components/SignalPanel.tsx'
import { WorkbenchHeader } from './components/WorkbenchHeader.tsx'
import { WorkspaceNav } from './components/WorkspaceNav.tsx'
import type { WorkspaceModule } from './components/WorkspaceNav.tsx'
import { fetchKlines } from './api/kline.ts'
import type { FrontendKlineResponse } from './api/kline.ts'
import { fetchChanAnalysis } from './api/chan.ts'
import { calculateIndicators } from './api/indicator.ts'
import { runBacktest } from './api/signal.ts'
import type { BacktestResult } from './api/signal.ts'
import type {
  ChanAnalysis,
  ChanRenderOptions,
  IndicatorDisplay,
  IndicatorResult,
  RawKline,
} from './core/types.ts'
import { useAppStore } from './store/useAppStore.ts'
import {
  buildStrategyChanOptions,
  collectStrategyTimeframes,
  collectStrategyIndicatorsForTimeframe,
  filterStrategyChanAnalysis,
  templateUsesChanIndicator,
} from './core/strategyIndicators.ts'
import { buildStrategyTradeMarkerResult } from './core/strategyMarkers.ts'
import { isSupportedTimeframeId, timeframeLabel } from './core/constants.ts'
import type { SupportedTimeframeId } from './core/constants.ts'
import { AdminWorkspace } from './components/AdminWorkspace.tsx'
import { LoginScreen } from './components/LoginScreen.tsx'
import { fetchCurrentUser, logout } from './api/auth.ts'
import type { AuthUser } from './api/auth.ts'
import { getAccessToken } from './api/client.ts'
import { ChangePasswordDialog } from './components/ChangePasswordDialog.tsx'
import { NotificationWorkspace } from './components/NotificationWorkspace.tsx'
import { ContentWorkspace } from './components/ContentWorkspace.tsx'

const DEFAULT_CHAN_OPTIONS: ChanRenderOptions = {
  showFenxing: false,
  showBi: false,
  showDuan: false,
  showZhongshu: false,
  showZhongshuAxis: true,
  showBuySellPoints: false,
  showDivergences: false,
  biColor: '#e7c66b',
  duanColor: '#6c8cff',
  zhongshuColor: '#9b8cf2',
  zsLevel: 'bi',
}

/** 行情加载遮罩：不卸载图表，只是盖在上层，保证切换标的/周期时不丢失画面上下文。 */
function ChartLoadingOverlay() {
  const [elapsedMs, setElapsedMs] = useState(0)
  useEffect(() => {
    const startedAt = Date.now()
    const timer = window.setInterval(() => setElapsedMs(Date.now() - startedAt), 200)
    return () => window.clearInterval(timer)
  }, [])
  const seconds = Math.floor(elapsedMs / 1000)
  return (
    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2.5 bg-[rgba(12,15,21,.76)] px-6">
      <div className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
        <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className="w-3.5 h-3.5 animate-spin">
          <path d="M14 8a6 6 0 1 1-1.76-4.24" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span>正在加载行情</span>
        <span className="font-mono tabular-nums text-[var(--text-muted)]">{seconds}s</span>
      </div>
      {seconds >= 5 && (
        <p className="max-w-[360px] text-center text-[11px] leading-5 text-[var(--text-muted)]">
          首次加载需要从数据源补齐历史行情，耗时可能较长；读取过的标的会明显更快。
        </p>
      )}
    </div>
  )
}

function ChartStage({
  loading,
  error,
  klineData,
  chanAnalysis,
  chanOptions,
  indicatorResults,
  onCursorTimeChange,
  onRetry,
  emptyMessage = '无数据',
}: {
  loading: boolean
  error: string | null
  klineData: RawKline[]
  chanAnalysis: ChanAnalysis | null
  chanOptions: ChanRenderOptions
  indicatorResults: IndicatorResult[]
  onCursorTimeChange?: (time: number | null) => void
  onRetry?: () => void
  emptyMessage?: string
}) {
  const hasData = klineData.length > 0
  return (
    <div className="flex-1 relative min-w-0 min-h-0 bg-[var(--chart-background)]">
      {/* 已有数据时始终保留图表，加载/报错都以覆盖层或横幅呈现 */}
      {hasData && (
        <Chart klineData={klineData} chanAnalysis={chanAnalysis ?? undefined} chanOptions={chanOptions} indicatorResults={indicatorResults} onCursorTimeChange={onCursorTimeChange} />
      )}
      {loading && <ChartLoadingOverlay />}
      {!loading && error && hasData && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 flex max-w-[520px] items-center gap-3 rounded-lg border border-[rgba(255,107,114,.28)] bg-[rgba(28,18,20,.94)] px-3 py-2">
          <span className="text-[11px] text-[var(--accent-red)]">刷新失败，当前显示上一次成功加载的数据：{error}</span>
          {onRetry && <button type="button" onClick={onRetry} className="shrink-0 text-[11px] text-[var(--accent)] hover:underline">重试</button>}
        </div>
      )}
      {!loading && error && !hasData && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center">
          <div className="text-[13px] text-[var(--accent-red)]">行情加载失败</div>
          <div className="max-w-md text-[12px] leading-5 text-[var(--text-secondary)]">{error}</div>
          {onRetry && <button type="button" onClick={onRetry} className="action-primary mt-1">重新加载</button>}
        </div>
      )}
      {!loading && !error && !hasData && (
        <div className="absolute inset-0 flex items-center justify-center text-[12px] text-[var(--text-muted)]">{emptyMessage}</div>
      )}
    </div>
  )
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function CollapseIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={`w-4 h-4 transition-transform ${collapsed ? 'rotate-180' : ''}`} aria-hidden="true">
      <path d="m10 3-5 5 5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function WorkbenchApp({ user, onLogout, onUserChange, onLogin }: { user: AuthUser; onLogout: () => void; onUserChange: (user: AuthUser) => void; onLogin?: () => void }) {
  const initialModule = user.modules[0]?.component_key || user.modules[0]?.code || ''
  const [activeModule, setActiveModule] = useState<WorkspaceModule>(initialModule)
  const [timeframe, setTimeframe] = useState<SupportedTimeframeId>('1d')
  const [market, setMarket] = useState('')
  const [symbol, setSymbol] = useState('')
  const [symbolName, setSymbolName] = useState('')
  const [klineData, setKlineData] = useState<RawKline[]>([])
  const [chanOptions, setChanOptions] = useState<ChanRenderOptions>(DEFAULT_CHAN_OPTIONS)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [indicatorError, setIndicatorError] = useState<string | null>(null)
  const [strategyIndicatorError, setStrategyIndicatorError] = useState<string | null>(null)
  const [strategyScanError, setStrategyScanError] = useState<string | null>(null)
  const [chanAnalysis, setChanAnalysis] = useState<ChanAnalysis | null>(null)
  const [selectedIndicators, setSelectedIndicators] = useState<IndicatorDisplay[]>([])
  const [indicatorResults, setIndicatorResults] = useState<IndicatorResult[]>([])
  const [strategyIndicatorResults, setStrategyIndicatorResults] = useState<{ key: string; results: IndicatorResult[] }>({ key: '', results: [] })
  const [indicatorInfoCollapsed, setIndicatorInfoCollapsed] = useState(false)
  const [strategyInfoCollapsed, setStrategyInfoCollapsed] = useState(false)
  const [backtestResult, setBacktestResult] = useState<{ key: string; result: BacktestResult } | null>(null)
  const [strategyTradeScan, setStrategyTradeScan] = useState<{ key: string; result: BacktestResult | null }>({ key: '', result: null })
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false)
  const [indicatorCursorTime, setIndicatorCursorTime] = useState<number | null>(null)
  const [marketDataStatus, setMarketDataStatus] = useState<Pick<FrontendKlineResponse, 'toTime' | 'stale' | 'refreshFailed' | 'statusMessage'> | null>(null)
  const [refreshNonce, setRefreshNonce] = useState(0)
  const forceRefreshRef = useRef(false)

  const templates = useAppStore((state) => state.templates)
  const activeTemplateId = useAppStore((state) => state.activeTemplateId)
  const activeTemplate = templates.find((template) => template.id === activeTemplateId)
  const allowedModules = user.modules.map((module) => module.component_key || module.code)
  const effectiveActiveModule = allowedModules.includes(activeModule) ? activeModule : allowedModules[0] ?? ''
  const strategyRequests = useMemo(
    () => collectStrategyIndicatorsForTimeframe(activeTemplate, timeframe),
    [activeTemplate, timeframe],
  )
  const strategyTimeframes = useMemo(
    () => collectStrategyTimeframes(activeTemplate).filter(isSupportedTimeframeId),
    [activeTemplate],
  )
  const strategyRequestKey = useMemo(
    () => `${symbol}:${timeframe}:${activeTemplateId ?? ''}:${JSON.stringify(strategyRequests)}`,
    [activeTemplateId, strategyRequests, symbol, timeframe],
  )
  const strategyTradeKey = symbol && activeTemplate ? `${symbol}:${activeTemplate.id}:${activeTemplate.updatedAt}` : ''
  const strategyUsesChan = useMemo(
    () => templateUsesChanIndicator(activeTemplate, timeframe),
    [activeTemplate, timeframe],
  )
  const strategyChanOptions = useMemo(
    () => buildStrategyChanOptions(chanOptions, activeTemplate, timeframe),
    [activeTemplate, chanOptions, timeframe],
  )
  const strategyChanAnalysis = useMemo(
    () => filterStrategyChanAnalysis(chanAnalysis, activeTemplate, timeframe),
    [activeTemplate, chanAnalysis, timeframe],
  )

  useEffect(() => {
    if (effectiveActiveModule !== 'screener' || strategyTimeframes.length === 0) return
    if (!strategyTimeframes.includes(timeframe)) {
      const nextTimeframe = strategyTimeframes[0]!
      Promise.resolve().then(() => setTimeframe(nextTimeframe))
    }
  }, [effectiveActiveModule, strategyTimeframes, timeframe])

  useEffect(() => {
    if (!market || !symbol) return
    let cancelled = false
    const forceRefresh = forceRefreshRef.current
    forceRefreshRef.current = false
    Promise.resolve().then(() => {
      if (!cancelled) {
        setLoading(true)
        setError(null)
        setMarketDataStatus(null)
      }
    })
    const requestSymbol = symbol
    const request = forceRefresh
      ? fetchKlines(requestSymbol, timeframe, 500, true).then(async (klineResponse) => [
          klineResponse,
          await fetchChanAnalysis(requestSymbol, timeframe, 500, true),
        ] as const)
      : Promise.all([
          fetchKlines(requestSymbol, timeframe, 500),
          fetchChanAnalysis(requestSymbol, timeframe, 500),
        ])
    request
      .then(([klineResponse, chanResponse]) => {
        if (cancelled) return
        setKlineData(klineResponse.data as RawKline[])
        setMarketDataStatus(klineResponse)
        setChanAnalysis(chanResponse)
      })
      .catch((loadError: unknown) => {
        if (!cancelled) setError(errorMessage(loadError))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [market, symbol, timeframe, refreshNonce])

  useEffect(() => {
    if (!symbol || selectedIndicators.length === 0 || klineData.length === 0) return
    let cancelled = false
    calculateIndicators(
      symbol,
      timeframe,
      selectedIndicators.map((indicator) => ({ type: indicator.type, params: indicator.params })),
      500,
    )
      .then((results) => {
        if (cancelled) return
        setIndicatorError(null)
        setIndicatorResults(results.map((result) => {
          const display = selectedIndicators.find((item) => (
            item.type === result.type
            && Object.entries(item.params).every(([key, value]) => result.params[key] === value)
          ))
          const color = display?.color
          if (!color || result.render.plots.length === 0) return result
          return { ...result, render: { ...result.render, plots: result.render.plots.map((plot, plotIndex) => plotIndex === 0 ? { ...plot, color } : plot) } }
        }))
      })
      .catch((loadError: unknown) => {
        if (!cancelled) {
          setIndicatorResults([])
          setIndicatorError(errorMessage(loadError))
        }
      })
    return () => { cancelled = true }
  }, [selectedIndicators, klineData, timeframe, market, symbol])

  useEffect(() => {
    if (!symbol || strategyRequests.length === 0 || klineData.length === 0) return
    let cancelled = false
    calculateIndicators(symbol, timeframe, strategyRequests, 500)
      .then((results) => {
        if (!cancelled) {
          setStrategyIndicatorError(null)
          setStrategyIndicatorResults({ key: strategyRequestKey, results })
        }
      })
      .catch((loadError: unknown) => {
        if (!cancelled) {
          setStrategyIndicatorResults({ key: strategyRequestKey, results: [] })
          setStrategyIndicatorError(errorMessage(loadError))
        }
      })
    return () => { cancelled = true }
  }, [strategyRequestKey, strategyRequests, klineData, symbol, timeframe])

  useEffect(() => {
    if (!symbol || !['strategy', 'screener'].includes(effectiveActiveModule) || !activeTemplate?.enabled || !strategyTradeKey) return
    let cancelled = false
    Promise.resolve().then(() => {
      if (!cancelled) {
        setStrategyTradeScan({ key: '', result: null })
        setBacktestResult(null)
      }
    })
    runBacktest(symbol, activeTemplate, 300)
      .then((result) => {
        if (!cancelled) {
          setStrategyScanError(null)
          setStrategyTradeScan({ key: strategyTradeKey, result })
        }
      })
      .catch((loadError: unknown) => {
        if (!cancelled) {
          setStrategyTradeScan({ key: strategyTradeKey, result: null })
          setStrategyScanError(errorMessage(loadError))
        }
      })
    return () => { cancelled = true }
  }, [effectiveActiveModule, activeTemplate, strategyTradeKey, symbol])

  const activeTradeResult = useMemo(() => {
    if (backtestResult?.key === strategyTradeKey) return backtestResult.result
    return strategyTradeScan.key === strategyTradeKey ? strategyTradeScan.result : null
  }, [backtestResult, strategyTradeKey, strategyTradeScan])
  const strategyTradeMarkers = useMemo(
    () => buildStrategyTradeMarkerResult(activeTradeResult, timeframe, klineData),
    [activeTradeResult, klineData, timeframe],
  )
  const visibleStrategyMarkerCount = strategyTradeMarkers[0]?.values.length ?? 0

  const strategyResults = useMemo(
    () => [
      ...(strategyRequests.length > 0 && strategyIndicatorResults.key === strategyRequestKey ? strategyIndicatorResults.results : []),
      ...strategyTradeMarkers,
    ],
    [strategyIndicatorResults, strategyRequestKey, strategyRequests.length, strategyTradeMarkers],
  )

  // 策略状态文案：失败必须与“确实没有买卖点”区分开，不能让用户把报错当成无信号
  const strategyStatus = strategyScanError
    ? { tone: 'error' as const, text: `策略买卖点计算失败：${strategyScanError}` }
    : strategyIndicatorError
      ? { tone: 'error' as const, text: `策略指标计算失败：${strategyIndicatorError}` }
      : !activeTemplate
        ? { tone: 'muted' as const, text: '未选择策略，选择后可查看买卖点' }
        : !activeTemplate.enabled
          ? { tone: 'muted' as const, text: '策略已停用，不会计算买卖点' }
          : strategyTradeScan.key !== strategyTradeKey
            ? { tone: 'muted' as const, text: '计算策略买卖点…' }
            : visibleStrategyMarkerCount > 0
              ? { tone: 'muted' as const, text: `当前图表已标注 ${visibleStrategyMarkerCount} 个策略买卖点` }
              : activeTradeResult?.trades.length
                ? { tone: 'muted' as const, text: '当前可视范围无策略买卖点' }
                : { tone: 'muted' as const, text: '当前策略暂无买卖点' }

  const handleMarketChange = useCallback((nextMarket: string) => {
    setIndicatorCursorTime(null)
    setMarket(nextMarket)
    setSymbol('')
    setSymbolName('')
    setKlineData([])
    setChanAnalysis(null)
    setIndicatorResults([])
    setIndicatorError(null)
    setStrategyIndicatorError(null)
    setStrategyScanError(null)
    setMarketDataStatus(null)
    setError(null)
    setLoading(false)
  }, [])
  const handleSymbolChange = useCallback((nextSymbol: string, nextName: string) => {
    setIndicatorCursorTime(null)
    setSymbol(nextSymbol)
    setSymbolName(nextName)
  }, [])
  const handleScreenSymbol = useCallback((nextSymbol: string, nextName: string, nextMarket: string) => {
    setIndicatorCursorTime(null)
    setMarket(nextMarket)
    setSymbol(nextSymbol)
    setSymbolName(nextName)
    const primary = activeTemplate?.primaryTimeframeId
    if (primary && isSupportedTimeframeId(primary)) setTimeframe(primary)
    else if (strategyTimeframes[0]) setTimeframe(strategyTimeframes[0])
  }, [activeTemplate, strategyTimeframes])
  const handleTimeframeChange = useCallback((nextTimeframe: SupportedTimeframeId) => {
    setIndicatorCursorTime(null)
    setTimeframe(nextTimeframe)
  }, [])
  const handleRefresh = useCallback(() => {
    forceRefreshRef.current = true
    setRefreshNonce((value) => value + 1)
  }, [])
  // 重试只重新触发一次读取，不强制绕过缓存（强制刷新代价很高）
  const handleRetry = useCallback(() => {
    setRefreshNonce((value) => value + 1)
  }, [])

  const headerProps = {
    market,
    symbol,
    symbolName,
    timeframe,
    onMarketChange: handleMarketChange,
    onSymbolChange: handleSymbolChange,
    onTimeframeChange: handleTimeframeChange,
  }
  const dataStatusBadge = marketDataStatus?.stale ? (
    <span title={marketDataStatus.statusMessage || undefined} className="h-7 px-2.5 rounded-md border border-[rgba(240,163,90,.35)] bg-[rgba(240,163,90,.08)] flex items-center text-[11px] text-[var(--accent-orange)] whitespace-nowrap">
      数据截至 {marketDataStatus.toTime ? new Date(marketDataStatus.toTime).toLocaleDateString('zh-CN') : '未知'}{marketDataStatus.refreshFailed ? ' · 更新失败' : ' · 暂无更新'}
    </span>
  ) : null

  const refreshButton = (
    <button
      type="button"
      onClick={handleRefresh}
      disabled={loading || !symbol}
      aria-label="刷新行情"
      title="强制刷新行情(绕过缓存)"
      className="h-7 px-2.5 rounded-md border border-[var(--border-primary)] bg-[var(--bg-primary)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:border-[var(--border-accent)] hover:bg-[var(--bg-tertiary)] transition-colors duration-150 flex items-center gap-1.5 shrink-0 disabled:opacity-60"
    >
      <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`}>
        <path d="M14 8a6 6 0 1 1-1.76-4.24" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M14 2v4h-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="text-[11px] font-mono">刷新</span>
    </button>
  )

  return (
    <div className="flex h-full w-full overflow-hidden bg-[var(--bg-primary)]">
      <WorkspaceNav active={effectiveActiveModule} onChange={setActiveModule} modules={user.modules} user={user} onLogout={onLogout} onChangePassword={() => setPasswordDialogOpen(true)} onLogin={onLogin} />
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden">
        {effectiveActiveModule === 'indicators' && (
          <>
            <WorkbenchHeader title="指标分析" {...headerProps} trailing={<div className="flex flex-wrap items-center gap-3">{refreshButton}{dataStatusBadge}{chanAnalysis && <div className="hidden xl:flex items-center gap-3 text-[11px] text-[var(--text-muted)] font-mono whitespace-nowrap">
                <span>笔 {chanAnalysis.bis.length}</span><span>段 {chanAnalysis.duans.length}</span><span>中枢 {chanOptions.zsLevel === 'duan' ? chanAnalysis.duanZhongshus.length : chanAnalysis.zhongshus.length}</span><span>背驰 {chanAnalysis.divergences.length}</span><span>买卖点 {chanAnalysis.buySellPoints.length}</span>
              </div>}</div>} />
            <IndicatorWorkbenchToolbar selectedIndicators={selectedIndicators} onIndicatorChange={setSelectedIndicators} chanOptions={chanOptions} onChanChange={setChanOptions} analysis={chanAnalysis ?? undefined} />
            {indicatorError && (
              <div className="h-8 px-4 flex items-center gap-2 border-b border-[rgba(255,107,114,.25)] bg-[rgba(255,107,114,.06)] shrink-0">
                <span className="text-[11px] text-[var(--accent-red)]">指标计算失败，图表未显示该指标：{indicatorError}</span>
              </div>
            )}
            <div className="flex flex-1 min-h-0 overflow-hidden">
              <ChartStage loading={loading} error={error} klineData={klineData} chanAnalysis={chanAnalysis} chanOptions={chanOptions} indicatorResults={selectedIndicators.length > 0 ? indicatorResults : []} onCursorTimeChange={setIndicatorCursorTime} onRetry={handleRetry} emptyMessage={!market ? '请选择市场' : !symbol ? '请选择标的' : '暂无行情数据'} />
              <IndicatorInfoPanel collapsed={indicatorInfoCollapsed} onToggle={() => setIndicatorInfoCollapsed((value) => !value)} klineData={klineData} analysis={chanAnalysis ?? undefined} chanOptions={chanOptions} indicators={selectedIndicators} results={selectedIndicators.length > 0 ? indicatorResults : []} cursorTime={indicatorCursorTime} />
            </div>
          </>
        )}

        {effectiveActiveModule === 'strategy' && (
          <>
            <WorkbenchHeader title="策略执行" {...headerProps} trailing={<div className="flex items-center gap-2">{dataStatusBadge}{refreshButton}</div>} />
            <div className="h-11 px-4 flex items-center gap-2 border-b border-[var(--border-primary)] bg-[var(--bg-secondary)] shrink-0 overflow-x-auto">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)] shrink-0">策略指标</span>
              {strategyUsesChan && <span className="h-7 px-2.5 rounded-md bg-[var(--bg-tertiary)] flex items-center text-[11px] text-[var(--text-secondary)] whitespace-nowrap">{timeframeLabel(timeframe)} · 缠论</span>}
              {strategyRequests.map((request) => <span key={`${request.type}:${JSON.stringify(request.params)}`} className="h-7 px-2.5 rounded-md bg-[var(--bg-tertiary)] flex items-center text-[11px] text-[var(--text-secondary)] whitespace-nowrap">{timeframeLabel(timeframe)} · {request.type.toUpperCase()}{Object.values(request.params).length > 0 ? ` ${Object.values(request.params).join('/')}` : ''}</span>)}
              {strategyRequests.length === 0 && !strategyUsesChan && <span className="text-[11px] text-[var(--text-muted)]">{activeTemplate ? `当前${timeframeLabel(timeframe)}级别无策略指标` : '选择策略后自动展示其引用指标'}</span>}
              <div className="flex-1" />{strategyStatus.tone === 'error'
                ? <span className="text-[11px] text-[var(--accent-red)]">{strategyStatus.text}</span>
                : <span className="text-[11px] text-[var(--text-muted)] whitespace-nowrap">{strategyStatus.text}</span>}
            </div>
            <div className="flex flex-1 min-h-0 overflow-hidden">
              <aside className={`${strategyInfoCollapsed ? 'w-11' : 'w-[310px]'} shrink-0 border-r border-[var(--border-primary)] bg-[var(--bg-secondary)] transition-[width] duration-200 overflow-hidden flex flex-col`}>
                <div className="h-11 px-2 flex items-center gap-2 border-b border-[var(--border-primary)] shrink-0">
                  <button type="button" onClick={() => setStrategyInfoCollapsed((value) => !value)} aria-label={strategyInfoCollapsed ? '展开策略信息' : '收起策略信息'} className="w-8 h-8 rounded-md border border-[var(--border-primary)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] shrink-0"><CollapseIcon collapsed={strategyInfoCollapsed} /></button>
                  {!strategyInfoCollapsed && <span className="text-[11px] font-semibold text-[var(--text-secondary)]">策略信息</span>}
                </div>
                {!strategyInfoCollapsed && <div className="flex-1 min-h-0"><SignalPanel embedded showLayers={false} symbol={symbol} onBacktestResult={(result) => setBacktestResult({ key: strategyTradeKey, result })} /></div>}
              </aside>
              <ChartStage loading={loading} error={error} klineData={klineData} chanAnalysis={strategyChanAnalysis} chanOptions={strategyChanOptions} indicatorResults={strategyResults} onRetry={handleRetry} emptyMessage={!market ? '请选择市场' : !symbol ? '请选择标的' : !activeTemplate ? '请选择策略' : '暂无行情数据'} />
            </div>
          </>
        )}

        {effectiveActiveModule === 'screener' && (
          <>
            <div className="h-14 px-4 flex items-center gap-3 border-b border-[var(--border-primary)] bg-[var(--bg-secondary)] shrink-0"><h1 className="text-[15px] font-semibold tracking-tight">策略选股</h1><span className="text-[11px] text-[var(--text-muted)]">使用已有策略批量评估候选标的</span></div>
            <ScreenerWorkspace
              selectedSymbol={symbol}
              selectedName={symbolName}
              onSelectSymbol={handleScreenSymbol}
              strategyTimeframes={strategyTimeframes}
              activeTimeframe={timeframe}
              onTimeframeChange={handleTimeframeChange}
              chart={<ChartStage loading={loading} error={error} klineData={klineData} chanAnalysis={strategyChanAnalysis} chanOptions={strategyChanOptions} indicatorResults={strategyResults} onRetry={handleRetry} emptyMessage="开始选股后，点击结果查看策略指标" />}
            />
          </>
        )}

        {effectiveActiveModule === 'admin' && (
          <AdminWorkspace currentUser={user} onModulesChanged={() => { void fetchCurrentUser().then(onUserChange) }} />
        )}

        {effectiveActiveModule === 'notifications' && <NotificationWorkspace />}

        {effectiveActiveModule === 'content' && <ContentWorkspace />}

        {!['indicators', 'strategy', 'screener', 'admin', 'notifications', 'content'].includes(effectiveActiveModule) && (
          <div className="flex-1 flex items-center justify-center text-[var(--text-muted)]">
            <div className="text-center"><div className="text-[14px] text-[var(--text-secondary)]">模块已配置</div><div className="mt-1 text-[11px]">页面组件尚未接入：{effectiveActiveModule}</div></div>
          </div>
        )}
      </main>
      {passwordDialogOpen && <ChangePasswordDialog onClose={() => setPasswordDialogOpen(false)} />}
    </div>
  )
}

function App() {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [initializing, setInitializing] = useState(() => Boolean(getAccessToken()))

  useEffect(() => {
    const handleUnauthorized = () => setUser(null)
    window.addEventListener('signal-layer:unauthorized', handleUnauthorized)
    if (getAccessToken()) {
      fetchCurrentUser().then(setUser).catch(() => logout()).finally(() => setInitializing(false))
    }
    return () => window.removeEventListener('signal-layer:unauthorized', handleUnauthorized)
  }, [])

  if (initializing) {
    return <div className="h-full flex items-center justify-center bg-[var(--bg-primary)] text-[var(--text-muted)]">正在验证登录状态…</div>
  }
  if (!user) return <LoginScreen onAuthenticated={setUser} />
  if (!user.permission_codes.includes('private.access')) {
    return <div className="h-full w-full grid place-items-center bg-[var(--bg-primary)]"><div className="w-[420px] p-7 rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] text-center"><div className="text-[15px] font-semibold">私有工作区权限未开通</div><p className="mt-2.5 text-[12px] leading-6 text-[var(--text-secondary)]">账户已创建，但当前角色还不能进入研究工作区。</p><p className="mt-1.5 text-[12px] leading-6 text-[var(--text-muted)]">请联系系统管理员，在“系统 → 用户管理”中把你的角色调整为研究用户或管理员，然后重新登录。</p><div className="mt-5 flex items-center justify-center gap-2"><button type="button" onClick={() => { void fetchCurrentUser().then(setUser).catch(() => { logout(); setUser(null) }) }} className="h-9 px-4 rounded-md border border-[var(--border-primary)] text-[12px] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]">我已开通，重新检查</button><button type="button" onClick={() => { logout(); setUser(null) }} className="h-9 px-4 rounded-md bg-[var(--accent)] text-white text-[12px]">返回登录</button></div></div></div>
  }
  return <WorkbenchApp user={user} onLogout={() => { logout(); setUser(null) }} onUserChange={setUser} />
}

export default App
