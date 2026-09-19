import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchChanAnalysis } from '../api/chan.ts'
import { calculateIndicators } from '../api/indicator.ts'
import { fetchKlines } from '../api/kline.ts'
import type { FrontendKlineResponse } from '../api/kline.ts'
import { fetchPublicSiteConfig } from '../api/site.ts'
import { Chart } from '../chart/Chart.tsx'
import { IndicatorInfoPanel } from '../components/IndicatorInfoPanel.tsx'
import { IndicatorWorkbenchToolbar } from '../components/IndicatorWorkbenchToolbar.tsx'
import { WorkbenchHeader } from '../components/WorkbenchHeader.tsx'
import type { ChanAnalysis, ChanRenderOptions, IndicatorDisplay, IndicatorResult, RawKline } from '../core/types.ts'
import type { SupportedTimeframeId } from '../core/constants.ts'

const BASE_CHAN_OPTIONS: ChanRenderOptions = {
  showFenxing: false, showBi: false, showDuan: false, showZhongshu: false,
  showZhongshuAxis: true, showBuySellPoints: false, showDivergences: false,
  biColor: '#e7c66b', duanColor: '#6c8cff', zhongshuColor: '#9b8cf2', zsLevel: 'bi',
}

function PublicRail() {
  return <nav className="w-[72px] shrink-0 border-r border-[var(--border-primary)] bg-[var(--bg-nav)] flex flex-col items-center px-2 py-3 select-none"><div className="w-9 h-9 rounded-lg bg-[var(--accent)] text-white flex items-center justify-center mb-4"><svg viewBox="0 0 20 20" fill="none" className="w-5 h-5" aria-label="SignalLayer"><path d="M3 15 7.5 5l3.2 6L17 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg></div><div className="relative w-full h-14 rounded-md flex flex-col items-center justify-center gap-1 bg-[rgba(108,140,255,0.11)] text-[#b9c9ff]"><span className="absolute left-0 top-3 bottom-3 w-0.5 rounded-r bg-[var(--accent)]" /><svg viewBox="0 0 20 20" fill="none" className="w-[18px] h-[18px]" aria-hidden="true"><path d="M3 15.5 7 9l3 3 5-8 2 3M3 17h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg><span className="text-[11px]">指标</span></div></nav>
}

function ChartStage({ loading, error, klines, analysis, options, indicators, onCursor, detailFeatures, emptyMessage }: { loading: boolean; error: string | null; klines: RawKline[]; analysis: ChanAnalysis | null; options: ChanRenderOptions; indicators: IndicatorResult[]; onCursor: (time: number | null) => void; detailFeatures: string[]; emptyMessage: string }) {
  return <div className="flex-1 relative min-w-0 min-h-0 bg-[var(--chart-background)]">{loading ? <div className="absolute inset-0 grid place-items-center text-[12px] text-[var(--text-muted)]">加载中…</div> : error ? <div className="absolute inset-0 grid place-items-center text-[12px] text-[var(--accent-red)]">{error}</div> : klines.length ? <Chart klineData={klines} chanAnalysis={analysis ?? undefined} chanOptions={options} indicatorResults={indicators} onCursorTimeChange={onCursor} chanDetailFeatures={detailFeatures} /> : <div className="absolute inset-0 grid place-items-center text-[12px] text-[var(--text-muted)]">{emptyMessage}</div>}</div>
}

export function PublicApp() {
  const [timeframe, setTimeframe] = useState<SupportedTimeframeId>('1d')
  const [market, setMarket] = useState('')
  const [symbol, setSymbol] = useState('')
  const [symbolName, setSymbolName] = useState('')
  const [klines, setKlines] = useState<RawKline[]>([])
  const [analysis, setAnalysis] = useState<ChanAnalysis | null>(null)
  const [selected, setSelected] = useState<IndicatorDisplay[]>([])
  const [results, setResults] = useState<IndicatorResult[]>([])
  const [chanOptions, setChanOptions] = useState(BASE_CHAN_OPTIONS)
  const [visibleChanFeatures, setVisibleChanFeatures] = useState<string[]>([])
  const [detailChanFeatures, setDetailChanFeatures] = useState<string[]>([])
  const [chanFeatureLabels, setChanFeatureLabels] = useState<Record<string, string>>({})
  const [visibleIndicatorDetails, setVisibleIndicatorDetails] = useState<string[]>([])
  const [collapsed, setCollapsed] = useState(false)
  const [cursorTime, setCursorTime] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [marketDataStatus, setMarketDataStatus] = useState<Pick<FrontendKlineResponse, 'toTime' | 'stale' | 'refreshFailed' | 'statusMessage'> | null>(null)
  const [refreshNonce, setRefreshNonce] = useState(0)
  const forceRefreshRef = useRef(false)

  useEffect(() => {
    void fetchPublicSiteConfig().then((config) => {
      const chanFeatures = config.indicator_features.filter((item) => item.indicator_type === 'chan')
      const chanVisible = config.indicators.find((item) => item.indicator_type === 'chan')?.public_visible !== false
      const visible = chanVisible ? chanFeatures.filter((item) => item.public_visible).map((item) => item.feature_code) : []
      setVisibleChanFeatures(visible)
      setDetailChanFeatures(chanFeatures.filter((item) => item.public_visible && item.show_details).map((item) => item.feature_code))
      setChanFeatureLabels(Object.fromEntries(chanFeatures.map((item) => [item.feature_code, item.display_name])))
      setVisibleIndicatorDetails(config.indicators.filter((item) => item.public_visible && item.show_details).map((item) => item.indicator_type))
      setChanOptions((current) => ({
        ...current, showFenxing: visible.includes('fenxing'), showBi: visible.includes('bi'),
        showDuan: visible.includes('duan'), showZhongshu: visible.includes('zhongshu'),
        showDivergences: visible.includes('divergence'), showBuySellPoints: visible.includes('buy_sell_points'),
      }))
    }).catch(() => setVisibleChanFeatures(['bi', 'duan', 'zhongshu']))
  }, [])
  useEffect(() => {
    if (!market || !symbol) return
    let cancelled = false
    const forceRefresh = forceRefreshRef.current
    forceRefreshRef.current = false
    Promise.resolve().then(() => { if (!cancelled) { setLoading(true); setError(null); setMarketDataStatus(null) } })
    const request = forceRefresh
      ? fetchKlines(symbol, timeframe, 500, true).then(async (bars) => [
          bars,
          await fetchChanAnalysis(symbol, timeframe, 500, true),
        ] as const)
      : Promise.all([fetchKlines(symbol, timeframe, 500), fetchChanAnalysis(symbol, timeframe, 500)])
    request
      .then(([bars, chan]) => { if (!cancelled) { setKlines(bars.data as RawKline[]); setAnalysis(chan); setMarketDataStatus(bars) } })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [market, symbol, timeframe, refreshNonce])
  useEffect(() => {
    if (!selected.length || !klines.length) { Promise.resolve().then(() => setResults([])); return }
    let cancelled = false
    void calculateIndicators(symbol, timeframe, selected.map((item) => ({ type: item.type, params: item.params })), 500)
      .then((next) => { if (!cancelled) setResults(next) }).catch(() => { if (!cancelled) setResults([]) })
    return () => { cancelled = true }
  }, [selected, klines, symbol, timeframe])

  const handleMarket = useCallback((next: string) => { setMarket(next); setSymbol(''); setSymbolName(''); setKlines([]); setAnalysis(null); setResults([]); setMarketDataStatus(null); setError(null); setLoading(false); setCursorTime(null) }, [])
  const handleRefresh = useCallback(() => {
    forceRefreshRef.current = true
    setRefreshNonce((value) => value + 1)
  }, [])
  const headerProps = useMemo(() => ({ market, symbol, symbolName, timeframe, onMarketChange: handleMarket, onSymbolChange: (next: string, name: string) => { setSymbol(next); setSymbolName(name); setCursorTime(null) }, onTimeframeChange: (next: SupportedTimeframeId) => { setTimeframe(next); setCursorTime(null) } }), [handleMarket, market, symbol, symbolName, timeframe])

  const dataStatusBadge = marketDataStatus?.stale ? <span title={marketDataStatus.statusMessage || undefined} className="h-7 px-2.5 rounded-md border border-[rgba(240,163,90,.35)] bg-[rgba(240,163,90,.08)] flex items-center text-[10px] text-[var(--accent-orange)] whitespace-nowrap">数据截至 {marketDataStatus.toTime ? new Date(marketDataStatus.toTime).toLocaleDateString('zh-CN') : '未知'}{marketDataStatus.refreshFailed ? ' · 更新失败' : ' · 暂无更新'}</span> : null

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
      <span className="text-[10px] font-mono">刷新</span>
    </button>
  )
  return <div className="flex h-full w-full overflow-hidden bg-[var(--bg-primary)]"><PublicRail /><main className="flex-1 min-w-0 flex flex-col overflow-hidden"><WorkbenchHeader title="指标分析" {...headerProps} trailing={<div className="flex items-center gap-2">{dataStatusBadge}{refreshButton}</div>} /><IndicatorWorkbenchToolbar selectedIndicators={selected} onIndicatorChange={setSelected} chanOptions={chanOptions} onChanChange={setChanOptions} analysis={analysis ?? undefined} visibleChanFeatures={visibleChanFeatures} chanFeatureLabels={chanFeatureLabels} /><div className="flex flex-1 min-h-0 overflow-hidden"><ChartStage loading={loading} error={error} klines={klines} analysis={analysis} options={chanOptions} indicators={results} onCursor={setCursorTime} detailFeatures={detailChanFeatures} emptyMessage={!market ? '请选择市场' : !symbol ? '请选择标的' : '暂无行情数据'} /><IndicatorInfoPanel collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)} klineData={klines} analysis={analysis ?? undefined} chanOptions={chanOptions} indicators={selected} results={results} cursorTime={cursorTime} visibleChanFeatures={visibleChanFeatures} visibleIndicatorDetails={visibleIndicatorDetails} /></div></main></div>
}
