export type WorkspaceModule = 'indicators' | 'strategy' | 'screener'

interface Props {
  active: WorkspaceModule
  onChange: (module: WorkspaceModule) => void
}

const items: { id: WorkspaceModule; label: string; icon: 'chart' | 'strategy' | 'filter' }[] = [
  { id: 'indicators', label: '指标', icon: 'chart' },
  { id: 'strategy', label: '策略', icon: 'strategy' },
  { id: 'screener', label: '选股', icon: 'filter' },
]

function NavIcon({ type }: { type: 'chart' | 'strategy' | 'filter' }) {
  if (type === 'strategy') {
    return (
      <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <circle cx="5" cy="5" r="2" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="15" cy="15" r="2" stroke="currentColor" strokeWidth="1.5" />
        <path d="M5 7v2.2c0 1 .8 1.8 1.8 1.8h6.4c1 0 1.8.8 1.8 1.8V13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    )
  }
  if (type === 'filter') {
    return (
      <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M3 5h14M6 10h8M8.5 15h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M3 15.5 7 9l3 3 5-8 2 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3 17h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

export function WorkspaceNav({ active, onChange }: Props) {
  return (
    <nav className="w-[72px] shrink-0 border-r border-[var(--border-primary)] bg-[var(--bg-nav)] flex flex-col items-center px-2 py-3 select-none">
      <div className="w-9 h-9 rounded-lg bg-[var(--accent)] text-white flex items-center justify-center mb-4 shadow-[0_8px_24px_rgba(108,140,255,0.18)]">
        <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5" aria-label="SignalLayer">
          <path d="M3 15 7.5 5l3.2 6L17 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>

      <div className="w-full space-y-1" role="tablist" aria-label="主模块">
        {items.map((item) => {
          const selected = active === item.id
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => onChange(item.id)}
              className={`relative w-full h-14 rounded-md flex flex-col items-center justify-center gap-1 transition-colors duration-150 ${
                selected
                  ? 'bg-[rgba(108,140,255,0.11)] text-[#b9c9ff]'
                  : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'
              }`}
            >
              {selected && <span className="absolute left-0 top-3 bottom-3 w-0.5 rounded-r bg-[var(--accent)]" />}
              <span className="w-[18px] h-[18px]"><NavIcon type={item.icon} /></span>
              <span className="text-[11px]">{item.label}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
