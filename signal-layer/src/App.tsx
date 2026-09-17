import { useCallback, useEffect, useMemo, useState } from 'react'
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
  collectStrategyIndicatorsForTimeframe,
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
  showBi: true,
  showDuan: true,
  showZhongshu: true,
  showZhongshuAxis: true,
  showBuySellPoints: true,
  showDivergences: true,
  biColor: '#e7c66b',
  duanColor: '#6c8cff',
  zhongshuColor: '#9b8cf2',
  zsLevel: 'bi',
}

function ChartStage({
  loading,
  error,
  klineData,
  chanAnalysis,
  chanOptions,
  indicatorResults,
  onCursorTimeChange,
}: {
  loading: boolean
  error: string | null
  klineData: RawKline[]
  chanAnalysis: ChanAnalysis | null
  chanOptions: ChanRenderOptions
  indicatorResults: IndicatorResult[]
  onCursorTimeChange?: (time: number | null) => void
}) {
  return (
    <div className="flex-1 relative min-w-0 min-h-0 bg-[var(--chart-background)]">
      {loading ? (
        <div className="absolute inset-0 flex items-center justify-center text-[var(--text-muted)] text-sm">加载中...</div>
      ) : error ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-[var(--text-muted)] text-sm gap-2 px-6 text-center">
          <div className="text-[var(--accent-red)]">后端连接失败</div>
          <div className="text-xs font-mono max-w-md break-all">{error}</div>
          <div className="text-xs mt-2">请确保后端已启动：<span className="font-mono">uvicorn app.main:app --port 8000</span></div>
        </div>
      ) : klineData.length === 0 ? (
        <div className="absolute inset-0 flex items-center justify-center text-[var(--text-muted)] text-sm">无数据</div>
      ) : (
        <Chart klineData={klineData} chanAnalysis={chanAnalysis ?? undefined} chanOptions={chanOptions} indicatorResults={indicatorResults} onCursorTimeChange={onCursorTimeChange} />
      )}
    </div>
  )
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
  const [market, setMarket] = useState('futures')
  const [symbol, setSymbol] = useState('RB0')
  const [symbolName, setSymbolName] = useState('螺纹钢连续')
  const [klineData, setKlineData] = useState<RawKline[]>([])
  const [chanOptions, setChanOptions] = useState<ChanRenderOptions>(DEFAULT_CHAN_OPTIONS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
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

  const templates = useAppStore((state) => state.templates)
  const activeTemplateId = useAppStore((state) => state.activeTemplateId)
  const activeTemplate = templates.find((template) => template.id === activeTemplateId)
  const allowedModules = user.modules.map((module) => module.component_key || module.code)
  const effectiveActiveModule = allowedModules.includes(activeModule) ? activeModule : allowedModules[0] ?? ''
  const strategyRequests = useMemo(
    () => collectStrategyIndicatorsForTimeframe(activeTemplate, timeframe),
    [activeTemplate, timeframe],
  )
  const strategyRequestKey = useMemo(
    () => `${symbol}:${timeframe}:${activeTemplateId ?? ''}:${JSON.stringify(strategyRequests)}`,
    [activeTemplateId, strategyRequests, symbol, timeframe],
  )
  const strategyTradeKey = activeTemplate ? `${symbol}:${activeTemplate.id}:${activeTemplate.updatedAt}` : ''
  const strategyUsesChan = useMemo(
    () => templateUsesChanIndicator(activeTemplate, timeframe),
    [activeTemplate, timeframe],
  )
  const strategyChanOptions = useMemo(
    () => buildStrategyChanOptions(chanOptions, activeTemplate, timeframe),
    [activeTemplate, chanOptions, timeframe],
  )

  useEffect(() => {
    let cancelled = false
    Promise.resolve().then(() => {
      if (!cancelled) {
        setLoading(true)
        setError(null)
        setMarketDataStatus(null)
      }
    })
    const requestSymbol = symbol
    Promise.all([fetchKlines(requestSymbol, timeframe, 500), fetchChanAnalysis(requestSymbol, timeframe, 500)])
      .then(([klineResponse, chanResponse]) => {
        if (cancelled) return
        setKlineData(klineResponse.data as RawKline[])
        setMarketDataStatus(klineResponse)
        setChanAnalysis(chanResponse)
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : String(loadError))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [market, symbol, timeframe])

  useEffect(() => {
    if (selectedIndicators.length === 0 || klineData.length === 0) return
    let cancelled = false
    calculateIndicators(
      symbol,
      timeframe,
      selectedIndicators.map((indicator) => ({ type: indicator.type, params: indicator.params })),
      500,
    )
      .then((results) => {
        if (cancelled) return
        setIndicatorResults(results.map((result, index) => {
          const color = selectedIndicators[index]?.color
          if (!color || result.render.plots.length === 0) return result
          return { ...result, render: { ...result.render, plots: result.render.plots.map((plot, plotIndex) => plotIndex === 0 ? { ...plot, color } : plot) } }
        }))
      })
      .catch(() => {
        if (!cancelled) setIndicatorResults([])
      })
    return () => { cancelled = true }
  }, [selectedIndicators, klineData, timeframe, market, symbol])

  useEffect(() => {
    if (strategyRequests.length === 0 || klineData.length === 0) return
    let cancelled = false
    calculateIndicators(symbol, timeframe, strategyRequests, 500)
      .then((results) => {
        if (!cancelled) setStrategyIndicatorResults({ key: strategyRequestKey, results })
      })
      .catch(() => {
        if (!cancelled) setStrategyIndicatorResults({ key: strategyRequestKey, results: [] })
      })
    return () => { cancelled = true }
  }, [strategyRequestKey, strategyRequests, klineData, symbol, timeframe])

  useEffect(() => {
    if (!['strategy', 'screener'].includes(effectiveActiveModule) || !activeTemplate?.enabled || !strategyTradeKey) return
    let cancelled = false
    runBacktest(symbol, activeTemplate, 300)
      .then((result) => {
        if (!cancelled) setStrategyTradeScan({ key: strategyTradeKey, result })
      })
      .catch(() => {
        if (!cancelled) setStrategyTradeScan({ key: strategyTradeKey, result: null })
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

  const handleMarketChange = useCallback((nextMarket: string) => {
    setIndicatorCursorTime(null)
    setMarket(nextMarket)
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
    if (activeTemplate && isSupportedTimeframeId(activeTemplate.primaryTimeframeId)) setTimeframe(activeTemplate.primaryTimeframeId)
  }, [activeTemplate])
  const handleTimeframeChange = useCallback((nextTimeframe: SupportedTimeframeId) => {
    setIndicatorCursorTime(null)
    setTimeframe(nextTimeframe)
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
    <span title={marketDataStatus.statusMessage || undefined} className="h-7 px-2.5 rounded-md border border-[rgba(240,163,90,.35)] bg-[rgba(240,163,90,.08)] flex items-center text-[10px] text-[var(--accent-orange)] whitespace-nowrap">
      数据截至 {marketDataStatus.toTime ? new Date(marketDataStatus.toTime).toLocaleDateString('zh-CN') : '未知'}{marketDataStatus.refreshFailed ? ' · 更新失败' : ' · 暂无更新'}
    </span>
  ) : null

  return (
    <div className="flex h-full w-full overflow-hidden bg-[var(--bg-primary)]">
      <WorkspaceNav active={effectiveActiveModule} onChange={setActiveModule} modules={user.modules} user={user} onLogout={onLogout} onChangePassword={() => setPasswordDialogOpen(true)} onLogin={onLogin} />
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden">
        {effectiveActiveModule === 'indicators' && (
          <>
            <WorkbenchHeader title="指标分析" {...headerProps} trailing={<div className="hidden xl:flex items-center gap-3">{dataStatusBadge}{chanAnalysis && <div className="flex items-center gap-3 text-[10px] text-[var(--text-muted)] font-mono whitespace-nowrap">
                <span>笔 {chanAnalysis.bis.length}</span><span>段 {chanAnalysis.duans.length}</span><span>中枢 {chanOptions.zsLevel === 'duan' ? chanAnalysis.duanZhongshus.length : chanAnalysis.zhongshus.length}</span><span>背驰 {chanAnalysis.divergences.length}</span><span>买卖点 {chanAnalysis.buySellPoints.length}</span>
              </div>}</div>} />
            <IndicatorWorkbenchToolbar selectedIndicators={selectedIndicators} onIndicatorChange={setSelectedIndicators} chanOptions={chanOptions} onChanChange={setChanOptions} analysis={chanAnalysis ?? undefined} />
            <div className="flex flex-1 min-h-0 overflow-hidden">
              <ChartStage loading={loading} error={error} klineData={klineData} chanAnalysis={chanAnalysis} chanOptions={chanOptions} indicatorResults={selectedIndicators.length > 0 ? indicatorResults : []} onCursorTimeChange={setIndicatorCursorTime} />
              <IndicatorInfoPanel collapsed={indicatorInfoCollapsed} onToggle={() => setIndicatorInfoCollapsed((value) => !value)} klineData={klineData} analysis={chanAnalysis ?? undefined} chanOptions={chanOptions} indicators={selectedIndicators} results={selectedIndicators.length > 0 ? indicatorResults : []} cursorTime={indicatorCursorTime} />
            </div>
          </>
        )}

        {effectiveActiveModule === 'strategy' && (
          <>
            <WorkbenchHeader title="策略执行" {...headerProps} trailing={dataStatusBadge} />
            <div className="h-11 px-4 flex items-center gap-2 border-b border-[var(--border-primary)] bg-[var(--bg-secondary)] shrink-0 overflow-x-auto">
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)] shrink-0">策略指标</span>
              {strategyUsesChan && <span className="h-7 px-2.5 rounded-md bg-[var(--bg-tertiary)] flex items-center text-[11px] text-[var(--text-secondary)] whitespace-nowrap">{timeframeLabel(timeframe)} · 缠论</span>}
              {strategyRequests.map((request) => <span key={`${request.type}:${JSON.stringify(request.params)}`} className="h-7 px-2.5 rounded-md bg-[var(--bg-tertiary)] flex items-center text-[11px] text-[var(--text-secondary)] whitespace-nowrap">{timeframeLabel(timeframe)} · {request.type.toUpperCase()}{Object.values(request.params).length > 0 ? ` ${Object.values(request.params).join('/')}` : ''}</span>)}
              {strategyRequests.length === 0 && !strategyUsesChan && <span className="text-[11px] text-[var(--text-muted)]">{activeTemplate ? `当前${timeframeLabel(timeframe)}级别无策略指标` : '选择策略后自动展示其引用指标'}</span>}
              <div className="flex-1" /><span className="text-[10px] text-[var(--text-muted)] whitespace-nowrap">{activeTemplate && !activeTemplate.enabled ? '策略已停用' : strategyTradeScan.key !== strategyTradeKey && activeTemplate ? '计算策略买卖点…' : visibleStrategyMarkerCount > 0 ? `当前图表已标注 ${visibleStrategyMarkerCount} 个策略买卖点` : activeTradeResult?.trades.length ? '当前可视范围无策略买卖点' : '当前策略暂无买卖点'}</span>
            </div>
            <div className="flex flex-1 min-h-0 overflow-hidden">
              <aside className={`${strategyInfoCollapsed ? 'w-11' : 'w-[310px]'} shrink-0 border-r border-[var(--border-primary)] bg-[var(--bg-secondary)] transition-[width] duration-200 overflow-hidden flex flex-col`}>
                <div className="h-11 px-2 flex items-center gap-2 border-b border-[var(--border-primary)] shrink-0">
                  <button type="button" onClick={() => setStrategyInfoCollapsed((value) => !value)} aria-label={strategyInfoCollapsed ? '展开策略信息' : '收起策略信息'} className="w-8 h-8 rounded-md border border-[var(--border-primary)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] shrink-0"><CollapseIcon collapsed={strategyInfoCollapsed} /></button>
                  {!strategyInfoCollapsed && <span className="text-[11px] font-semibold text-[var(--text-secondary)]">策略信息</span>}
                </div>
                {!strategyInfoCollapsed && <div className="flex-1 min-h-0"><SignalPanel embedded showLayers={false} symbol={symbol} onBacktestResult={(result) => setBacktestResult({ key: strategyTradeKey, result })} /></div>}
              </aside>
              <ChartStage loading={loading} error={error} klineData={klineData} chanAnalysis={chanAnalysis} chanOptions={strategyChanOptions} indicatorResults={strategyResults} />
            </div>
          </>
        )}

        {effectiveActiveModule === 'screener' && (
          <>
            <div className="h-14 px-4 flex items-center gap-3 border-b border-[var(--border-primary)] bg-[var(--bg-secondary)] shrink-0"><h1 className="text-[15px] font-semibold tracking-tight">策略选股</h1><span className="text-[11px] text-[var(--text-muted)]">使用已有策略批量评估候选标的</span></div>
            <ScreenerWorkspace selectedSymbol={symbol} selectedName={symbolName} onSelectSymbol={handleScreenSymbol} chart={<ChartStage loading={loading} error={error} klineData={klineData} chanAnalysis={chanAnalysis} chanOptions={strategyChanOptions} indicatorResults={strategyResults} />} />
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
    return <div className="h-full w-full grid place-items-center bg-[var(--bg-primary)]"><div className="w-[400px] p-7 rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] text-center"><div className="text-[15px] font-semibold">私有工作区权限未开通</div><p className="mt-2 text-[11px] leading-5 text-[var(--text-muted)]">账户已经创建，但需要管理员授予“研究用户”角色后才能进入完整工作区。</p><button type="button" onClick={() => { logout(); setUser(null) }} className="mt-5 h-9 px-4 rounded-md bg-[var(--accent)] text-white text-[12px]">返回登录</button></div></div>
  }
  return <WorkbenchApp user={user} onLogout={() => { logout(); setUser(null) }} onUserChange={setUser} />
}

export default App
