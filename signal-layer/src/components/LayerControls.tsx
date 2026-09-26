import { useAppStore } from '../store/useAppStore.ts'

const TF_COLORS: Record<string, string> = {
  '5m': '#36c995', '30m': '#ffa726', '1d': '#ef5350',
}

export function LayerControls() {
  const layers = useAppStore((s) => s.layers)
  const timeframes = useAppStore((s) => s.timeframes)
  const toggleLayerVisibility = useAppStore((s) => s.toggleLayerVisibility)
  const setLayerOpacity = useAppStore((s) => s.setLayerOpacity)

  return (
    <div className="px-4 pb-2.5 pt-1 space-y-0.5">
      {layers.map((layer) => {
        const tf = timeframes.find((t) => t.id === layer.timeframeId)
        const label = tf?.label ?? layer.timeframeId
        const color = TF_COLORS[layer.timeframeId] ?? '#888'

        return (
          <div key={layer.timeframeId} className="flex items-center gap-2.5 h-7 group">
            <button
              onClick={() => toggleLayerVisibility(layer.timeframeId)}
              className="w-4 h-4 rounded-sm border shrink-0 flex items-center justify-center transition-all duration-150"
              style={{
                backgroundColor: layer.visible ? color : 'transparent',
                borderColor: layer.visible ? color : 'var(--border-accent)',
              }}
            >
              {layer.visible && (
                <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                  <path d="M1 4l2.5 2.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              )}
            </button>

            <span className={`text-[11px] w-12 shrink-0 font-mono transition-colors duration-150 ${
              layer.visible ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)]'
            }`}>
              {label}
            </span>

            <input
              type="range"
              min="0.05"
              max="1"
              step="0.05"
              value={layer.opacity}
              onChange={(e) => setLayerOpacity(layer.timeframeId, parseFloat(e.target.value))}
              disabled={!layer.visible}
              className="flex-1 h-1 rounded-full appearance-none cursor-pointer disabled:opacity-20 disabled:cursor-not-allowed"
              style={{
                background: layer.visible
                  ? `linear-gradient(to right, ${color} 0%, ${color} ${layer.opacity * 100}%, var(--bg-tertiary) ${layer.opacity * 100}%, var(--bg-tertiary) 100%)`
                  : 'var(--bg-tertiary)',
              }}
            />

            <span className={`text-[11px] w-8 text-right shrink-0 font-mono tabular-nums transition-colors duration-150 ${
              layer.visible ? 'text-[var(--text-secondary)]' : 'text-[var(--text-muted)]'
            }`}>
              {Math.round(layer.opacity * 100)}%
            </span>
          </div>
        )
      })}
    </div>
  )
}
