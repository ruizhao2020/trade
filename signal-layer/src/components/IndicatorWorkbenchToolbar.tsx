import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchIndicatorList } from '../api/indicator.ts'
import type { ChanAnalysis, ChanRenderOptions, IndicatorDisplay, IndicatorInfo } from '../core/types.ts'
import { getMaPeriodColor, MA_PERIODS } from '../core/indicatorColors.ts'
import { VOLUME_LEGEND } from '../core/volumeIndicator.ts'

interface Props {
  selectedIndicators: IndicatorDisplay[]
  onIndicatorChange: (indicators: IndicatorDisplay[]) => void
  chanOptions: ChanRenderOptions
  onChanChange: (options: ChanRenderOptions) => void
  analysis?: ChanAnalysis
  visibleChanFeatures?: string[]
  chanFeatureLabels?: Record<string, string>
}

type ChanToggleKey = 'showFenxing' | 'showBi' | 'showDuan' | 'showZhongshu' | 'showDivergences' | 'showBuySellPoints'

const CHAN_ITEMS: { key: ChanToggleKey; label: string; color: string; count: (analysis?: ChanAnalysis) => number }[] = [
  { key: 'showFenxing', label: '分型', color: '#f59e0b', count: (analysis) => analysis?.fenxings.length ?? 0 },
  { key: 'showBi', label: '笔', color: '#e7c66b', count: (analysis) => analysis?.bis.length ?? 0 },
  { key: 'showDuan', label: '线段', color: '#6c8cff', count: (analysis) => analysis?.duans.length ?? 0 },
  { key: 'showZhongshu', label: '中枢', color: '#9b8cf2', count: (analysis) => analysis?.zhongshus.length ?? 0 },
  { key: 'showDivergences', label: '背驰', color: '#56c7e8', count: (analysis) => analysis?.divergences.length ?? 0 },
  { key: 'showBuySellPoints', label: '买卖点', color: '#36c995', count: (analysis) => analysis?.buySellPoints.length ?? 0 },
]

const PARAM_LABELS: Record<string, string> = {
  shrink_max: '缩量上限',
  increase_min: '增量起点',
  double_min: '倍量起点',
  triple_min: '三倍量起点',
  multiple_min: '多倍量起点',
  bins: '价格档位',
  lookback: '回看天数',
  min_turnover_days: '最少有效天数',
}

function Toggle({ enabled, label, onClick }: { enabled: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={enabled}
      onClick={onClick}
      className={`relative w-9 h-5 rounded-full transition-colors duration-150 ${enabled ? 'bg-[var(--accent)]' : 'bg-[var(--border-accent)]'}`}
    >
      <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform duration-150 ${enabled ? 'translate-x-[18px]' : 'translate-x-0.5'}`} />
    </button>
  )
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 14 14" fill="none" className="w-3 h-3" aria-hidden="true">
      <path d="m3.5 3.5 7 7m0-7-7 7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  )
}

export function IndicatorWorkbenchToolbar({
  selectedIndicators,
  onIndicatorChange,
  chanOptions,
  onChanChange,
  analysis,
  visibleChanFeatures,
  chanFeatureLabels,
}: Props) {
  const [available, setAvailable] = useState<IndicatorInfo[]>([])
  const [activeType, setActiveType] = useState('ma')
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerButtonRef = useRef<HTMLButtonElement>(null)
  const pickerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchIndicatorList().then(setAvailable).catch(() => setAvailable([]))
  }, [])

  useEffect(() => {
    if (!pickerOpen) return
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node
      if (!pickerRef.current?.contains(target) && !pickerButtonRef.current?.contains(target)) {
        setPickerOpen(false)
      }
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPickerOpen(false)
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [pickerOpen])

  const maInfo = available.find((item) => item.type === 'ma')
  const selectedTypes = useMemo(
    () => new Set(selectedIndicators.map((item) => item.type)),
    [selectedIndicators],
  )
  const activeIndicator = selectedIndicators.find((item) => item.type === activeType)
  const activeInfo = available.find((item) => item.type === activeType)
  const maCount = selectedIndicators.filter((item) => item.type === 'ma').length
  const chanFeatureCode: Record<ChanToggleKey, string> = {
    showFenxing: 'fenxing', showBi: 'bi', showDuan: 'duan', showZhongshu: 'zhongshu',
    showDivergences: 'divergence', showBuySellPoints: 'buy_sell_points',
  }
  const visibleChanItems = visibleChanFeatures
    ? CHAN_ITEMS.filter((item) => visibleChanFeatures.includes(chanFeatureCode[item.key]))
    : CHAN_ITEMS
  const chanCount = visibleChanItems.filter((item) => Boolean(chanOptions[item.key])).length
  const chanEnabled = chanCount > 0

  function toggleMa(period: number) {
    const exists = selectedIndicators.some((item) => item.type === 'ma' && item.params.period === period)
    if (exists) {
      onIndicatorChange(selectedIndicators.filter((item) => !(item.type === 'ma' && item.params.period === period)))
      return
    }
    if (!maInfo) return
    onIndicatorChange([
      ...selectedIndicators,
      {
        type: 'ma',
        params: { ...maInfo.default_params, period },
        window: maInfo.render.window,
        color: getMaPeriodColor(period),
      },
    ])
  }

  function setIndicatorEnabled(info: IndicatorInfo, enabled: boolean) {
    if (!enabled) {
      onIndicatorChange(selectedIndicators.filter((item) => item.type !== info.type))
      return
    }
    if (selectedTypes.has(info.type)) return
    onIndicatorChange([
      ...selectedIndicators,
      {
        type: info.type,
        params: { ...info.default_params },
        window: info.render.window,
        color: info.render.plots[0]?.color,
      },
    ])
  }

  function updateActiveParam(key: string, value: number) {
    onIndicatorChange(selectedIndicators.map((item) => (
      item === activeIndicator ? { ...item, params: { ...item.params, [key]: value } } : item
    )))
  }

  function toggleChanMaster() {
    const enabled = !chanEnabled
    onChanChange({
      ...chanOptions,
      showFenxing: false,
      showBi: enabled,
      showDuan: enabled,
      showZhongshu: enabled,
      showZhongshuAxis: enabled,
      showBuySellPoints: visibleChanFeatures ? enabled && visibleChanFeatures.includes('buy_sell_points') : enabled,
      showDivergences: visibleChanFeatures ? enabled && visibleChanFeatures.includes('divergence') : enabled,
    })
  }

  const mainIndicators = selectedIndicators
    .filter((item, index, all) => item.type !== 'ma' && all.findIndex((candidate) => candidate.type === item.type) === index)

  return (
    <div className="relative shrink-0 bg-[var(--bg-secondary)] border-b border-[var(--border-primary)]">
      <div className="min-h-11 px-4 py-1.5 flex items-center gap-1.5 overflow-x-auto">
        <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)] mr-1 shrink-0">主指标</span>
        <div className={`h-9 rounded-md flex items-center shrink-0 overflow-hidden transition-colors ${activeType === 'ma' ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)] shadow-[inset_0_-2px_0_var(--accent)]' : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'}`}>
          <button type="button" onClick={() => setActiveType('ma')} className="h-9 px-3 flex items-center gap-2 text-[12px]">
            <span className="w-2 h-2 rounded-full bg-[var(--accent-orange)]" />
            MA
            <span className="font-mono text-[10px] text-[var(--text-muted)]">{maCount}</span>
          </button>
          {maCount > 0 && (
            <button type="button" aria-label="关闭 MA" onClick={() => onIndicatorChange(selectedIndicators.filter((item) => item.type !== 'ma'))} className="w-8 h-9 border-l border-[var(--border-primary)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--accent-red)] hover:bg-[var(--bg-surface)]">
              <CloseIcon />
            </button>
          )}
        </div>
        <div className={`h-9 rounded-md flex items-center shrink-0 overflow-hidden transition-colors ${activeType === 'chan' ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)] shadow-[inset_0_-2px_0_var(--accent)]' : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'}`}>
          <button type="button" onClick={() => setActiveType('chan')} className="h-9 px-3 flex items-center gap-2 text-[12px]">
            <span className="w-2 h-2 rounded-full bg-[#e7c66b]" />
            缠论
            <span className="font-mono text-[10px] text-[var(--text-muted)]">{chanCount}</span>
          </button>
          {chanEnabled && (
            <button type="button" aria-label="关闭缠论" onClick={toggleChanMaster} className="w-8 h-9 border-l border-[var(--border-primary)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--accent-red)] hover:bg-[var(--bg-surface)]">
              <CloseIcon />
            </button>
          )}
        </div>

        {mainIndicators.map((display) => {
          const info = available.find((item) => item.type === display.type)
          return (
            <div key={display.type} className={`h-9 rounded-md flex items-center shrink-0 overflow-hidden transition-colors ${activeType === display.type ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)] shadow-[inset_0_-2px_0_var(--accent)]' : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'}`}>
              <button type="button" onClick={() => setActiveType(display.type)} className="h-9 px-3 flex items-center gap-2 text-[12px]">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: display.color ?? info?.render.plots[0]?.color ?? 'var(--accent)' }} />
                {info?.name ?? display.type.toUpperCase()}
              </button>
              <button
                type="button"
                aria-label={`关闭${info?.name ?? display.type}`}
                onClick={() => {
                  onIndicatorChange(selectedIndicators.filter((item) => item.type !== display.type))
                  if (activeType === display.type) setActiveType('ma')
                }}
                className="w-8 h-9 border-l border-[var(--border-primary)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--accent-red)] hover:bg-[var(--bg-surface)]"
              >
                <CloseIcon />
              </button>
            </div>
          )
        })}

        <button
          ref={pickerButtonRef}
          type="button"
          onClick={() => setPickerOpen((open) => !open)}
          className="h-9 px-3 rounded-md border border-[var(--border-primary)] text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--border-accent)] shrink-0"
        >
          + 添加指标
        </button>
      </div>

      <div className="min-h-11 px-4 py-1.5 flex items-center gap-2 flex-wrap border-t border-[var(--border-primary)] bg-[var(--bg-primary)]/40">
        {activeType === 'ma' && (
          <>
            <span className="text-[10px] text-[var(--text-muted)] mr-1">MA 子指标</span>
            {MA_PERIODS.map((period) => {
              const enabled = selectedIndicators.some((item) => item.type === 'ma' && item.params.period === period)
              return (
                <button
                  key={period}
                  type="button"
                  aria-pressed={enabled}
                  onClick={() => toggleMa(period)}
                  disabled={!maInfo}
                  className={`h-7 px-2.5 rounded border flex items-center gap-1.5 text-[11px] font-mono transition-colors disabled:opacity-40 ${enabled ? 'border-[var(--accent)] bg-[rgba(108,140,255,0.11)] text-[#b9c9ff]' : 'border-[var(--border-primary)] text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}`}
                >
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: getMaPeriodColor(period) }} />
                  MA{period}
                </button>
              )
            })}
          </>
        )}

        {activeType === 'chan' && (
          <>
            <span className="text-[10px] text-[var(--text-muted)] mr-1">缠论子指标</span>
            {visibleChanItems.map((item) => {
              const enabled = Boolean(chanOptions[item.key])
              const count = item.key === 'showZhongshu' && chanOptions.zsLevel === 'duan'
                ? analysis?.duanZhongshus.length ?? 0
                : item.count(analysis)
              return (
                <button
                  key={item.key}
                  type="button"
                  aria-pressed={enabled}
                  onClick={() => onChanChange({ ...chanOptions, [item.key]: !enabled })}
                  className={`h-7 px-2.5 rounded border flex items-center gap-1.5 text-[11px] transition-colors ${enabled ? 'border-[var(--border-accent)] bg-[var(--bg-tertiary)] text-[var(--text-primary)]' : 'border-[var(--border-primary)] text-[var(--text-muted)]'}`}
                >
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: enabled ? item.color : 'transparent', border: `1px solid ${item.color}` }} />
                  {chanFeatureLabels?.[chanFeatureCode[item.key]] ?? item.label}
                  {count > 0 && <span className="font-mono text-[10px] text-[var(--text-muted)]">{count}</span>}
                </button>
              )
            })}
            <span className="ml-auto text-[10px] text-[var(--text-muted)]">中枢级别</span>
            <select
              value={chanOptions.zsLevel}
              onChange={(event) => onChanChange({ ...chanOptions, zsLevel: event.target.value as 'bi' | 'duan' })}
              className="h-7 px-2 rounded border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[11px] text-[var(--text-secondary)] outline-none"
            >
              <option value="bi">笔中枢</option>
              <option value="duan">段中枢</option>
            </select>
            <Toggle enabled={chanEnabled} label="显示缠论" onClick={toggleChanMaster} />
          </>
        )}

        {activeType !== 'ma' && activeType !== 'chan' && activeInfo && (
          <>
            <span className="text-[10px] text-[var(--text-muted)] mr-1">{activeInfo.name} 参数</span>
            {activeType === 'volume' && (
              <div className="flex items-center gap-1.5 mr-2 pr-2 border-r border-[var(--border-primary)]">
                {VOLUME_LEGEND.map(item => (
                  <span key={item.code} className="h-6 px-1.5 rounded border border-[var(--border-primary)] flex items-center gap-1 text-[10px] text-[var(--text-muted)] whitespace-nowrap">
                    {item.followsPrice ? (
                      <span className="w-2 h-2 border border-[var(--border-accent)] grid grid-cols-2 overflow-hidden">
                        <span className="bg-[#ff5b62]" />
                        <span className="bg-[#2fc58d]" />
                      </span>
                    ) : (
                      <span className="w-2 h-2 border" style={{ borderColor: item.color }} />
                    )}
                    {item.label}
                  </span>
                ))}
              </div>
            )}
            {Object.entries(activeIndicator?.params ?? activeInfo.default_params).map(([key, value]) => (
              <label key={key} className="flex items-center gap-1.5 text-[10px] text-[var(--text-muted)]">
                {PARAM_LABELS[key] ?? key}
                <input
                  type="number"
                  value={value}
                  onChange={(event) => updateActiveParam(key, Number(event.target.value))}
                  disabled={!activeIndicator}
                  className="w-16 h-7 px-2 rounded border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[11px] font-mono text-[var(--text-primary)] outline-none focus:border-[var(--accent)] disabled:opacity-40"
                />
              </label>
            ))}
            <span className="ml-auto text-[10px] text-[var(--text-muted)]">显示</span>
            <Toggle
              enabled={Boolean(activeIndicator)}
              label={`显示${activeInfo.name}`}
              onClick={() => setIndicatorEnabled(activeInfo, !activeIndicator)}
            />
          </>
        )}
      </div>

      {pickerOpen && (
        <div ref={pickerRef} className="absolute z-30 top-[46px] left-36 w-64 max-h-80 overflow-y-auto py-1 rounded-md border border-[var(--border-accent)] bg-[var(--bg-surface)] shadow-2xl">
          {available.map((info) => {
            const selected = info.type === 'ma' ? maCount > 0 : selectedTypes.has(info.type)
            return (
              <button
                key={info.type}
                type="button"
                onClick={() => {
                  if (info.type === 'ma') {
                    setActiveType('ma')
                  } else {
                    setIndicatorEnabled(info, true)
                    setActiveType(info.type)
                  }
                  setPickerOpen(false)
                }}
                className="w-full px-3 py-2 flex items-center gap-2 text-left hover:bg-[var(--bg-tertiary)]"
              >
                <span className={`w-2 h-2 rounded-full ${selected ? 'bg-[var(--accent)]' : 'border border-[var(--text-muted)]'}`} />
                <span className="flex-1 text-[11px] text-[var(--text-secondary)]">{info.name}</span>
                {selected && <span className="text-[10px] font-mono text-[var(--text-muted)]">ON</span>}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
