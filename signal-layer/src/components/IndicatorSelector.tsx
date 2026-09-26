import { useState, useEffect, useRef, useCallback } from 'react'
import type { IndicatorInfo, IndicatorDisplay } from '../core/types.ts'
import { fetchIndicatorList } from '../api/indicator.ts'

interface Props {
  selectedIndicators: IndicatorDisplay[]
  onChange: (indicators: IndicatorDisplay[]) => void
}

const DOT_PALETTE = [
  '#5B8DEF', '#34C759', '#FF9500', '#FF3B30',
  '#AF52DE', '#FFD60A', '#64D2FF', '#30D158',
]

function pickColor(info: IndicatorInfo, fallbackIdx: number): string {
  if (info.render.plots.length > 0) return info.render.plots[0].color
  return DOT_PALETTE[fallbackIdx % DOT_PALETTE.length]
}

export function IndicatorSelector({ selectedIndicators, onChange }: Props) {
  const [available, setAvailable] = useState<IndicatorInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerPos, setPickerPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 })

  const plusBtnRef = useRef<HTMLButtonElement>(null)
  const pickerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    fetchIndicatorList()
      .then((list) => {
        if (!cancelled) {
          setAvailable(list)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载失败')
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!pickerOpen) return
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      if (
        pickerRef.current && !pickerRef.current.contains(target) &&
        plusBtnRef.current && !plusBtnRef.current.contains(target)
      ) {
        setPickerOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [pickerOpen])

  const openPicker = useCallback(() => {
    if (plusBtnRef.current) {
      const rect = plusBtnRef.current.getBoundingClientRect()
      setPickerPos({ top: rect.bottom + 4, left: rect.left })
    }
    setPickerOpen(true)
  }, [])

  const toggle = useCallback((info: IndicatorInfo) => {
    const exists = selectedIndicators.find((i) => i.type === info.type)
    if (exists) {
      onChange(selectedIndicators.filter((i) => i.type !== info.type))
    } else {
      const display: IndicatorDisplay = {
        type: info.type,
        params: { ...info.default_params },
        window: info.render.window,
        color: pickColor(info, available.indexOf(info)),
      }
      onChange([...selectedIndicators, display])
    }
  }, [selectedIndicators, onChange, available])

  const isSelected = useCallback(
    (type: string) => selectedIndicators.some((i) => i.type === type),
    [selectedIndicators],
  )

  return (
    <div className="flex items-center gap-1 px-3 py-2 bg-[var(--bg-secondary)] border-b border-[var(--border-primary)] overflow-x-auto relative">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)] mr-2 shrink-0">
        指标
      </span>

      {selectedIndicators.map((indicator) => {
        const info = available.find((i) => i.type === indicator.type)
        const color = indicator.color
          ?? (info ? pickColor(info, available.indexOf(info)) : DOT_PALETTE[0])
        return (
          <button
            key={indicator.type}
            onClick={() => {
              onChange(selectedIndicators.filter((i) => i.type !== indicator.type))
            }}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium transition-all duration-150 shrink-0 bg-[var(--accent)]/15 text-[var(--accent)] hover:bg-[var(--accent)]/25"
            title={info?.description}
          >
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: color }}
            />
            {info?.name ?? indicator.type}
          </button>
        )
      })}

      <button
        ref={plusBtnRef}
        onClick={openPicker}
        className={`flex items-center justify-center w-6 h-6 rounded text-[11px] font-bold transition-all duration-150 shrink-0 ${
          pickerOpen
            ? 'bg-[var(--accent)] text-white'
            : 'bg-[var(--bg-tertiary)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'
        }`}
      >
        +
      </button>

      {loading && (
        <div className="flex items-center gap-1.5 ml-1 shrink-0">
          <div className="w-10 h-5 rounded-sm bg-[var(--bg-tertiary)] animate-pulse" />
          <div className="w-14 h-5 rounded-sm bg-[var(--bg-tertiary)] animate-pulse" />
          <div className="w-8 h-5 rounded-sm bg-[var(--bg-tertiary)] animate-pulse" />
        </div>
      )}

      {error && !loading && available.length === 0 && (
        <span className="text-[11px] text-[var(--accent-red)] shrink-0 ml-1">加载失败</span>
      )}

      {pickerOpen && (
        <div
          ref={pickerRef}
          className="fixed z-50 min-w-[180px] bg-[var(--bg-surface)] border border-[var(--border-primary)] rounded-lg shadow-xl overflow-hidden animate-fade-in"
          style={{ top: pickerPos.top, left: pickerPos.left }}
        >
          <div className="max-h-[280px] overflow-y-auto py-1">
            {available.length === 0 && !loading && (
              <div className="px-3 py-4 text-[11px] text-[var(--text-muted)] text-center">
                {error ? '加载失败' : '暂无可用指标'}
              </div>
            )}
            {available.map((info, idx) => {
              const selected = isSelected(info.type)
              const color = pickColor(info, idx)
              return (
                <button
                  key={info.type}
                  onClick={() => toggle(info)}
                  className={`flex items-center gap-2 w-full px-3 py-1.5 text-[11px] transition-colors duration-100 hover:bg-[var(--bg-tertiary)] ${
                    selected
                      ? 'text-[var(--accent)]'
                      : 'text-[var(--text-secondary)]'
                  }`}
                >
                  <span
                    className={`w-2 h-2 rounded-full shrink-0 transition-colors duration-150 ${
                      selected ? '' : 'opacity-40'
                    }`}
                    style={{
                      backgroundColor: selected ? color : 'transparent',
                      border: `1.5px solid ${color}`,
                    }}
                  />
                  <span className="flex-1 text-left font-medium">{info.name}</span>
                  {selected && (
                    <span className="text-[11px] font-mono text-[var(--accent)]">ON</span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
