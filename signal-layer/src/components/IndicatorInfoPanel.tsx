import type { ChanAnalysis, ChanRenderOptions, IndicatorDisplay, IndicatorResult, RawKline } from '../core/types.ts'
import { financialValueColorClass } from '../core/financialColors.ts'

interface Props {
  collapsed: boolean
  onToggle: () => void
  klineData: RawKline[]
  analysis?: ChanAnalysis
  chanOptions: ChanRenderOptions
  indicators: IndicatorDisplay[]
  results: IndicatorResult[]
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
}: Props) {
  const latest = klineData.at(-1)
  const previous = klineData.at(-2)
  const change = latest && previous ? ((latest.close - previous.close) / previous.close) * 100 : undefined
  const latestIndicatorValues = results.flatMap((result) => {
    const last = result.values.at(-1)
    if (!last) return []
    return result.render.plots.slice(0, 2).map((plot) => ({
      key: `${result.type}-${plot.field}`,
      label: plot.label || `${result.type.toUpperCase()} ${plot.field}`,
      value: last[plot.field],
    }))
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
                  <span className="font-mono text-[var(--text-primary)]">{formatNumber(item.value, 4)}</span>
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
