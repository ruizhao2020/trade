import { createPortal } from 'react-dom'
import { useEffect, useRef, useState } from 'react'

interface Props {
  label?: string
  text: string
}

/** 参数旁的小信息按钮；点击显示说明，点击外部或再次点击关闭。 */
export function ParameterHint({ label, text }: Props) {
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<{ left: number; top: number }>({ left: 0, top: 0 })
  const rootRef = useRef<HTMLSpanElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  function toggle() {
    if (open) {
      setOpen(false)
      return
    }
    const rect = buttonRef.current?.getBoundingClientRect()
    if (rect) {
      const width = 280
      const estimatedHeight = 90
      const left = Math.min(Math.max(8, rect.left), Math.max(8, window.innerWidth - width - 8))
      const below = rect.bottom + 8
      const top = below + estimatedHeight <= window.innerHeight - 8
        ? below
        : Math.max(8, rect.top - estimatedHeight - 8)
      setPosition({ left, top })
    }
    setOpen(true)
  }

  useEffect(() => {
    if (!open) return
    const close = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [open])

  return (
    <span ref={rootRef} className="relative inline-flex items-center gap-1 align-middle">
      {label && <span>{label}</span>}
      <button
        type="button"
        ref={buttonRef}
        aria-label={`${label ?? '参数'}说明`}
        aria-expanded={open}
        onClick={toggle}
        className="w-4 h-4 rounded-full border border-[var(--border-accent)] text-[9px] leading-none text-[var(--accent)] hover:bg-[rgba(108,140,255,.12)] transition-colors"
      >
        i
      </button>
      {open && typeof document !== 'undefined' && createPortal(
        <span
          role="tooltip"
          style={{ left: position.left, top: position.top }}
          className="fixed z-[9999] w-[280px] p-3 rounded-lg border border-[var(--border-accent)] bg-[var(--bg-surface)] text-[12px] leading-5 text-[var(--text-secondary)] shadow-2xl"
        >
          {text}
        </span>,
        document.body,
      )}
    </span>
  )
}
