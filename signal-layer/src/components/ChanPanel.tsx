/**
 * 缠论控制面板 - 让用户控制各缠论元素的显示/隐藏
 */

import type { ChanAnalysis, ChanRenderOptions, ZhongshuLevel } from '../core/types.ts'

interface Props {
  options: ChanRenderOptions
  onChange: (options: ChanRenderOptions) => void
  analysis?: ChanAnalysis
}

interface ToggleItem {
  key: keyof ChanRenderOptions
  label: string
  color: string
  count?: number
}

export function ChanPanel({ options, onChange, analysis }: Props) {
  // 中枢数量根据级别动态显示
  const zsCount = options.zsLevel === 'duan'
    ? analysis?.duanZhongshus.length
    : analysis?.zhongshus.length

  const items: ToggleItem[] = [
    { key: 'showFenxing', label: '分型', color: '#f59e0b', count: analysis?.fenxings.length },
    { key: 'showBi', label: '笔', color: '#fbbf24', count: analysis?.bis.length },
    { key: 'showDuan', label: '线段', color: '#3b82f6', count: analysis?.duans.length },
    { key: 'showZhongshu', label: '中枢', color: '#8b5cf6', count: zsCount },
    { key: 'showZhongshuAxis', label: '中枢中轴', color: '#8b5cf6' },
    { key: 'showDivergences', label: '背驰', color: '#56c7e8', count: analysis?.divergences.length },
    { key: 'showBuySellPoints', label: '买卖点', color: '#10b981', count: analysis?.buySellPoints.length },
  ]

  const toggle = (key: keyof ChanRenderOptions) => {
    onChange({ ...options, [key]: !options[key] })
  }

  const setZsLevel = (level: ZhongshuLevel) => {
    onChange({ ...options, zsLevel: level })
  }

  return (
    <div className="flex items-center gap-1 px-3 py-2 bg-[var(--bg-secondary)] border-b border-[var(--border-primary)] overflow-x-auto">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)] mr-2 shrink-0">
        缠论
      </span>
      {items.map((item) => {
        const enabled = options[item.key] as boolean
        return (
          <button
            key={item.key}
            onClick={() => toggle(item.key)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium transition-all duration-150 shrink-0 ${
              enabled
                ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)]'
                : 'bg-transparent text-[var(--text-muted)] hover:bg-[var(--bg-tertiary)]/50'
            }`}
            style={enabled ? { boxShadow: `inset 0 -2px 0 ${item.color}` } : {}}
          >
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{
                backgroundColor: enabled ? item.color : 'transparent',
                border: `1px solid ${item.color}`,
              }}
            />
            {item.label}
            {item.count !== undefined && item.count > 0 && (
              <span className="text-[10px] text-[var(--text-muted)] font-mono">
                {item.count}
              </span>
            )}
          </button>
        )
      })}

      {/* 中枢级别切换:笔中枢 vs 段中枢 */}
      <div className="flex items-center gap-0.5 ml-2 pl-2 border-l border-[var(--border-primary)] shrink-0">
        <span className="text-[10px] text-[var(--text-muted)] mr-1">中枢级别</span>
        {(['bi', 'duan'] as const).map(level => {
          const active = options.zsLevel === level
          const label = level === 'bi' ? '笔' : '段'
          return (
            <button
              key={level}
              onClick={() => setZsLevel(level)}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors duration-150 ${
                active
                  ? 'bg-[var(--accent)] text-white'
                  : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
            >
              {label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
