import type { ReactNode } from 'react'
import { SymbolSelector } from './SymbolSelector.tsx'
import { SUPPORTED_TIMEFRAME_IDS } from '../core/constants.ts'
import type { SupportedTimeframeId } from '../core/constants.ts'

interface Props {
  title: string
  market: string
  symbol: string
  symbolName: string
  timeframe: SupportedTimeframeId
  onMarketChange: (market: string) => void
  onSymbolChange: (symbol: string, name: string) => void
  onTimeframeChange: (timeframe: SupportedTimeframeId) => void
  trailing?: ReactNode
}

export function WorkbenchHeader({
  title,
  market,
  symbol,
  symbolName,
  timeframe,
  onMarketChange,
  onSymbolChange,
  onTimeframeChange,
  trailing,
}: Props) {
  return (
    <header className="relative z-40 min-h-14 flex flex-wrap items-center gap-3 px-4 py-2 bg-[var(--bg-secondary)] border-b border-[var(--border-primary)] shrink-0 select-none overflow-visible">
      <h1 className="text-[15px] font-semibold text-[var(--text-primary)] tracking-tight whitespace-nowrap">{title}</h1>
      <span className="h-5 w-px bg-[var(--border-primary)] shrink-0" />
      <SymbolSelector
        market={market}
        symbol={symbol}
        symbolName={symbolName}
        onMarketChange={onMarketChange}
        onSymbolChange={onSymbolChange}
      />
      <span className="h-6 w-px bg-[var(--border-accent)] mx-1 shrink-0" aria-hidden="true" />
      <div className="flex items-center gap-2 shrink-0" aria-label="周期选择">
        {SUPPORTED_TIMEFRAME_IDS.map((tf) => (
          <button
            key={tf}
            type="button"
            onClick={() => onTimeframeChange(tf)}
            className={`h-8 min-w-11 px-3 rounded-md border text-[11px] font-mono transition-colors duration-150 ${
              timeframe === tf
                ? 'border-[var(--border-accent)] bg-[var(--bg-surface)] text-[var(--text-primary)]'
                : 'border-[var(--border-primary)] bg-[var(--bg-primary)] text-[var(--text-muted)] hover:border-[var(--border-accent)] hover:text-[var(--text-secondary)]'
            }`}
          >
            {tf === '1d' ? '日线' : tf}
          </button>
        ))}
      </div>
      <div className="flex-1" />
      {trailing}
    </header>
  )
}
