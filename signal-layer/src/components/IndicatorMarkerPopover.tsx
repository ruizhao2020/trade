import type { IndicatorMarkerDetail } from '../core/types.ts'
import type { RefObject } from 'react'

interface Props {
  detail: IndicatorMarkerDetail
  left: number
  top: number
  onClose: () => void
  popupRef: RefObject<HTMLDivElement | null>
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 14 14" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <path d="m3.5 3.5 7 7m0-7-7 7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  )
}

export function IndicatorMarkerPopover({ detail, left, top, onClose, popupRef }: Props) {
  return (
    <div
      ref={popupRef}
      role="dialog"
      aria-label={`${detail.title}详情`}
      className="absolute z-30 w-[300px] max-h-[340px] overflow-y-auto rounded-lg border border-[var(--border-accent)] bg-[rgba(19,23,31,0.97)] shadow-[0_18px_55px_rgba(0,0,0,0.5)] backdrop-blur-md"
      style={{ left, top }}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <div className="sticky top-0 z-10 flex items-start gap-3 px-4 py-3 border-b border-[var(--border-primary)] bg-[rgba(19,23,31,0.96)]">
        <span className="mt-1 w-2 h-2 rounded-sm shrink-0" style={{ backgroundColor: detail.accentColor }} />
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold text-[var(--text-primary)]">{detail.title}</div>
          {detail.subtitle && <div className="mt-0.5 text-[10px] text-[var(--text-muted)]">{detail.subtitle}</div>}
        </div>
        <button
          type="button"
          aria-label="关闭指标详情"
          onClick={onClose}
          className="w-7 h-7 -mt-1 -mr-1 rounded-md flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
        >
          <CloseIcon />
        </button>
      </div>

      <div className="px-4 py-3">
        <dl className="grid grid-cols-[76px_minmax(0,1fr)] gap-x-3 gap-y-2">
          {detail.fields.map(field => (
            <div key={`${field.label}:${field.value}`} className="contents">
              <dt className="text-[10px] text-[var(--text-muted)]">{field.label}</dt>
              <dd className="text-[11px] font-mono text-[var(--text-secondary)] text-right break-words">{field.value}</dd>
            </div>
          ))}
        </dl>

        {detail.reasons && detail.reasons.length > 0 && (
          <section className="mt-3 pt-3 border-t border-[var(--border-primary)]">
            <div className="mb-2 text-[10px] font-medium text-[var(--text-secondary)]">判定依据</div>
            <ol className="space-y-1.5">
              {detail.reasons.map((reason, index) => (
                <li key={`${index}:${reason}`} className="flex gap-2 text-[10px] leading-4 text-[var(--text-muted)]">
                  <span className="font-mono shrink-0" style={{ color: detail.accentColor }}>{index + 1}</span>
                  <span>{reason}</span>
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>
    </div>
  )
}
