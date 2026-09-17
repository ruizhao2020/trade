import type { AuthModule, AuthUser } from '../api/auth.ts'

export type WorkspaceModule = string

interface Props {
  active: WorkspaceModule
  onChange: (module: WorkspaceModule) => void
  modules: AuthModule[]
  user: AuthUser
  onLogout: () => void
  onChangePassword: () => void
  onLogin?: () => void
  showAuthEntry?: boolean
}

function NavIcon({ type }: { type: string }) {
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
  if (type === 'settings') {
    return <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5"/><path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
  }
  if (type === 'bell' || type === 'notifications') {
    return <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M5.2 8.3a4.8 4.8 0 0 1 9.6 0v2.1c0 1.1.4 2.1 1.2 2.9H4c.8-.8 1.2-1.8 1.2-2.9V8.3Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/><path d="M8 16h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
  }
  if (type === 'file' || type === 'content') {
    return <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M5 2.8h6.2L15 6.6v10.6H5V2.8Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/><path d="M11 2.8v4h4M7.5 10h5M7.5 13h5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
  }
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M3 15.5 7 9l3 3 5-8 2 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3 17h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

export function WorkspaceNav({ active, onChange, modules, user, onLogout, onChangePassword, onLogin, showAuthEntry = true }: Props) {
  return (
    <nav className="w-[72px] shrink-0 border-r border-[var(--border-primary)] bg-[var(--bg-nav)] flex flex-col items-center px-2 py-3 select-none">
      <div className="w-9 h-9 rounded-lg bg-[var(--accent)] text-white flex items-center justify-center mb-4 shadow-[0_8px_24px_rgba(108,140,255,0.18)]">
        <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5" aria-label="SignalLayer">
          <path d="M3 15 7.5 5l3.2 6L17 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>

      <div className="w-full space-y-1" role="tablist" aria-label="主模块">
        {modules.map((item) => {
          const moduleKey = item.component_key || item.code
          const selected = active === moduleKey
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => onChange(moduleKey)}
              className={`relative w-full h-14 rounded-md flex flex-col items-center justify-center gap-1 transition-colors duration-150 ${
                selected
                  ? 'bg-[rgba(108,140,255,0.11)] text-[#b9c9ff]'
                  : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'
              }`}
            >
              {selected && <span className="absolute left-0 top-3 bottom-3 w-0.5 rounded-r bg-[var(--accent)]" />}
              <span className="w-[18px] h-[18px]"><NavIcon type={item.icon} /></span>
              <span className="text-[11px] truncate max-w-full">{item.name}</span>
            </button>
          )
        })}
      </div>
      <div className="mt-auto w-full pt-3 border-t border-[var(--border-primary)]">
        <div title={user.display_name || user.username} className="w-full flex justify-center mb-2">
          <span className="w-7 h-7 rounded-full bg-[rgba(108,140,255,.10)] border border-[rgba(108,140,255,.24)] flex items-center justify-center text-[11px] font-semibold text-[#b9c9ff]">{(user.display_name || user.username).slice(0, 1).toUpperCase()}</span>
        </div>
        {user.id !== 0 && <button type="button" onClick={onChangePassword} className="w-full h-7 rounded-md text-[10px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]">改密</button>}
        {(user.id !== 0 || showAuthEntry) && <button type="button" onClick={user.id === 0 ? onLogin : onLogout} className="w-full h-7 rounded-md text-[10px] text-[var(--text-muted)] hover:text-[var(--accent-red)] hover:bg-[var(--bg-tertiary)]">{user.id === 0 ? '登录 / 注册' : '退出'}</button>}
      </div>
    </nav>
  )
}
