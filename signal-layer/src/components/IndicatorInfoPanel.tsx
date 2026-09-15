import type { ChanAnalysis, ChanRenderOptions, IndicatorDisplay, IndicatorResult, RawKline } from '../core/types.ts'
import { financialValueColorClass } from '../core/financialColors.ts'
import { volumeClassStyle } from '../core/volumeIndicator.ts'
import { findProfileSnapshot } from '../core/profileData.ts'

interface Props {
  collapsed: boolean
  onToggle: () => void
  klineData: RawKline[]
  analysis?: ChanAnalysis
  chanOptions: ChanRenderOptions
  indicators: IndicatorDisplay[]
  results: IndicatorResult[]
  cursorTime?: number | null
}

function formatNumber(value: number | undefined, digits = 2) {
  if (value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

function Chevron({ collapsed }: { collapsed: boolean }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={`w-4 h-4 transition-transform ${collapsed ? 'rotate-180' : ''}`} aria-hidden="true">
      <path d="m6 3 5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IndicatorInfoPanel({
  collapsed,
  onToggle,
  klineData,
  analysis,
  chanOptions,
  indicators,
  results,
  cursorTime,
}: Props) {
  const latest = klineData.at(-1)
  const previous = klineData.at(-2)
  const change = latest && previous ? ((latest.close - previous.close) / previous.close) * 100 : undefined
  const chipResult = results.find(result => result.type === 'chip_distribution')
  const chipSnapshot = findProfileSnapshot(chipResult?.profileData, cursorTime)
  const chipMetrics = chipSnapshot?.metrics ?? chipResult?.values[0]
  const chipTimeLabel = chipSnapshot
    ? new Date(chipSnapshot.time).toLocaleString('zh-CN', {
        month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
      })
    : ''
  const latestIndicatorValues: Array<{ key: string; label: string; value?: number; text?: string }> = results.flatMap((result) => {
    const last = result.values.at(-1)
    if (!last) return []
    if (result.type === 'chip_distribution') return []
    const plotValues = result.render.plots.slice(0, 2).map((plot) => ({
      key: `${result.type}-${plot.field}`,
      label: plot.label || `${result.type.toUpperCase()} ${plot.field}`,
      value: last[plot.field],
    }))
    if (result.type !== 'volume') return plotValues
    return [
      ...plotValues,
      { key: 'volume-ratio', label: '相邻量比', value: last.ratio },
      { key: 'volume-class', label: '量能分类', text: volumeClassStyle(last.volume_class).label },
    ]
  }).slice(0, 6)

  if (collapsed) {
    return (
      <aside className="w-11 shrink-0 border-l border-[var(--border-primary)] bg-[var(--bg-secondary)] flex justify-center pt-2">
        <button type="button" onClick={onToggle} aria-label="展开数据详情" className="w-8 h-8 rounded-md border border-[var(--border-primary)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]">
          <Chevron collapsed />
        </button>
      </aside>
    )
  }

  return (
    <aside className="w-[286px] shrink-0 border-l border-[var(--border-primary)] bg-[var(--bg-secondary)] flex flex-col overflow-hidden">
      <div className="h-12 px-4 border-b border-[var(--border-primary)] flex items-center gap-2 shrink-0">
        <span className="text-[12px] font-semibold text-[var(--text-secondary)]">数据详情</span>
        <div className="flex-1" />
        <button type="button" onClick={onToggle} aria-label="收起数据详情" className="w-8 h-8 rounded-md border border-[var(--border-primary)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]">
          <Chevron collapsed={false} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4">
        <section className="py-4 border-b border-[var(--border-primary)]">
          <div className="flex items-baseline gap-2">
            <span className="text-[22px] font-mono font-semibold tracking-tight">{formatNumber(latest?.close)}</span>
            <span className={`text-[11px] font-mono ${financialValueColorClass(change)}`}>
              {change === undefined ? '—' : `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`}
            </span>
          </div>
          <div className="text-[10px] text-[var(--text-muted)] mt-1">最新收盘数据</div>
          <div className="grid grid-cols-2 gap-x-5 gap-y-2 mt-4 text-[11px]">
            <div className="flex justify-between"><span className="text-[var(--text-muted)]">开盘</span><span className="font-mono">{formatNumber(latest?.open)}</span></div>
            <div className="flex justify-between"><span className="text-[var(--text-muted)]">最高</span><span className="font-mono">{formatNumber(latest?.high)}</span></div>
            <div className="flex justify-between"><span className="text-[var(--text-muted)]">最低</span><span className="font-mono">{formatNumber(latest?.low)}</span></div>
            <div className="flex justify-between"><span className="text-[var(--text-muted)]">成交量</span><span className="font-mono">{formatNumber(latest?.volume, 0)}</span></div>
          </div>
        </section>

        {chipMetrics && (
          <section className="py-4 border-b border-[var(--border-primary)]">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[11px] font-semibold text-[var(--text-secondary)]">筹码分布</span>
              <span className="text-[10px] text-[var(--text-muted)]">{chipTimeLabel || `近${formatNumber(chipMetrics.valid_turnover_days, 0)}日估算`}</span>
            </div>
            <div className="space-y-2 text-[11px]">
              <div className="flex justify-between"><span className="text-[var(--text-muted)]">主筹码峰</span><span className="font-mono text-[#e7c66b]">{formatNumber(chipMetrics.peak_price)}</span></div>
              <div className="flex justify-between"><span className="text-[var(--text-muted)]">平均成本</span><span className="font-mono">{formatNumber(chipMetrics.average_cost)}</span></div>
              <div className="flex justify-between"><span className="text-[var(--text-muted)]">获利盘</span><span className="font-mono text-[var(--accent-red)]">{formatNumber(chipMetrics.profit_ratio)}%</span></div>
              <div className="flex justify-between"><span className="text-[var(--text-muted)]">70%成本区间</span><span className="font-mono">{formatNumber(chipMetrics.range70_low)}–{formatNumber(chipMetrics.range70_high)}</span></div>
              <div className="flex justify-between"><span className="text-[var(--text-muted)]">70%集中度</span><span className="font-mono">{formatNumber(chipMetrics.concentration70)}%</span></div>
              <div className="flex justify-between"><span className="text-[var(--text-muted)]">90%成本区间</span><span className="font-mono">{formatNumber(chipMetrics.range90_low)}–{formatNumber(chipMetrics.range90_high)}</span></div>
              <div className="flex justify-between"><span className="text-[var(--text-muted)]">90%集中度</span><span className="font-mono">{formatNumber(chipMetrics.concentration90)}%</span></div>
              <div className="flex justify-between"><span className="text-[var(--text-muted)]">数据覆盖</span><span className="font-mono">{formatNumber(chipMetrics.coverage_ratio)}%</span></div>
              {chipMetrics.intraday_bars > 0 && <div className="flex justify-between"><span className="text-[var(--text-muted)]">分钟演进</span><span className="font-mono">{formatNumber(chipMetrics.intraday_bars, 0)} 根</span></div>}
            </div>
            <div className="mt-3 pt-3 border-t border-[var(--border-primary)] flex items-center gap-3 text-[10px] text-[var(--text-muted)]">
              <span className="flex items-center gap-1"><span className="w-2 h-2 bg-[rgba(108,140,255,0.8)]" />获利筹码</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 bg-[rgba(155,140,242,0.75)]" />套牢筹码</span>
            </div>
          </section>
        )}

        <section className="py-4 border-b border-[var(--border-primary)]">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">指标数值</span>
            <span className="text-[10px] font-mono text-[var(--text-muted)]">{indicators.length} 个图层</span>
          </div>
          {latestIndicatorValues.length > 0 ? (
            <div className="space-y-2">
              {latestIndicatorValues.map((item) => (
                <div key={item.key} className="flex items-center justify-between text-[11px]">
                  <span className="text-[var(--text-muted)] truncate pr-3">{item.label}</span>
                  <span className="font-mono text-[var(--text-primary)]">{item.text ?? formatNumber(item.value, 4)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[11px] text-[var(--text-muted)]">选择指标后显示最新数值</div>
          )}
        </section>

        <section className="py-4 border-b border-[var(--border-primary)]">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">缠论统计</span>
            <span className="text-[10px] font-mono text-[var(--text-muted)]">{chanOptions.zsLevel === 'duan' ? '段中枢' : '笔中枢'}</span>
          </div>
          <div className="space-y-2 text-[11px]">
            <div className="flex justify-between"><span className="text-[var(--text-muted)]">笔</span><span className="font-mono">{analysis?.bis.length ?? 0}</span></div>
            <div className="flex justify-between"><span className="text-[var(--text-muted)]">线段</span><span className="font-mono">{analysis?.duans.length ?? 0}</span></div>
            <div className="flex justify-between"><span className="text-[var(--text-muted)]">中枢</span><span className="font-mono">{chanOptions.zsLevel === 'duan' ? analysis?.duanZhongshus.length ?? 0 : analysis?.zhongshus.length ?? 0}</span></div>
            <div className="flex justify-between"><span className="text-[var(--text-muted)]">背驰</span><span className="font-mono">{analysis?.divergences.length ?? 0}</span></div>
            <div className="flex justify-between"><span className="text-[var(--text-muted)]">买卖点</span><span className="font-mono">{analysis?.buySellPoints.length ?? 0}</span></div>
          </div>
        </section>
      </div>
    </aside>
  )
}
