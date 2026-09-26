import { useState } from 'react'
import { login, register } from '../api/auth.ts'
import type { AuthUser } from '../api/auth.ts'

export function LoginScreen({ onAuthenticated, onGuest }: { onAuthenticated: (user: AuthUser) => void; onGuest?: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const user = mode === 'login'
        ? await login(username, password)
        : await register(username, password, displayName)
      onAuthenticated(user)
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : String(submitError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="h-full w-full flex items-center justify-center bg-[var(--bg-primary)] relative overflow-hidden">
      <div className="absolute inset-0 opacity-60" style={{ background: 'radial-gradient(circle at 50% 0%, rgba(108,140,255,.18), transparent 38%), linear-gradient(rgba(255,255,255,.018) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.018) 1px, transparent 1px)', backgroundSize: 'auto, 32px 32px, 32px 32px' }} />
      <form onSubmit={submit} className="relative w-[420px] rounded-2xl border border-[var(--border-accent)] bg-[rgba(18,21,28,.96)] p-9 shadow-[0_28px_80px_rgba(0,0,0,.48)]">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-[var(--accent)] text-white flex items-center justify-center shadow-[0_10px_30px_rgba(108,140,255,.22)]">
            <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5"><path d="M3 15 7.5 5l3.2 6L17 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </div>
          <div><div className="text-[14px] font-semibold tracking-tight">SignalLayer</div><div className="text-[11px] text-[var(--text-muted)] uppercase tracking-[0.14em]">Strategy Workspace</div></div>
        </div>
        <h1 className="text-[24px] leading-tight font-semibold tracking-tight">{mode === 'login' ? '欢迎回来' : '创建账户'}</h1>
        <p className="mt-2 text-[12px] text-[var(--text-muted)]">{mode === 'login' ? '登录后继续管理指标、策略与选股任务' : '注册后将自动获得系统配置的默认角色'}</p>
        <div className="mt-7 space-y-5">
          {mode === 'register' && <label className="block"><span className="block mb-2 text-[12px] text-[var(--text-secondary)]">显示名称</span><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="用于界面展示" className="w-full h-11 px-3.5 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-primary)] text-[13px] outline-none focus:border-[var(--accent)] placeholder:text-[var(--text-muted)]" /></label>}
          <label className="block"><span className="block mb-2 text-[12px] text-[var(--text-secondary)]">用户名</span><input autoFocus value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} autoComplete="username" placeholder="请输入用户名" className="w-full h-11 px-3.5 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-primary)] text-[13px] outline-none focus:border-[var(--accent)] placeholder:text-[var(--text-muted)]" /></label>
          <label className="block"><span className="block mb-2 text-[12px] text-[var(--text-secondary)]">密码</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder={mode === 'login' ? '请输入密码' : '至少 8 位'} className="w-full h-11 px-3.5 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-primary)] text-[13px] outline-none focus:border-[var(--accent)] placeholder:text-[var(--text-muted)]" /></label>
        </div>
        {error && <div className="mt-5 px-3 py-2.5 rounded-lg border border-[rgba(255,107,114,.2)] bg-[rgba(255,107,114,.07)] text-[11px] text-[var(--accent-red)] break-words">{error}</div>}
        <button disabled={submitting} className="mt-7 w-full h-11 rounded-lg bg-[var(--accent)] text-white text-[13px] font-semibold shadow-[0_8px_24px_rgba(108,140,255,.18)] hover:bg-[var(--accent-hover)] disabled:opacity-50">{submitting ? '请稍候…' : mode === 'login' ? '登录' : '注册并登录'}</button>
        <div className="mt-6 pt-5 border-t border-[var(--border-primary)] text-center space-y-3"><button type="button" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }} className="block w-full text-[12px] text-[var(--text-muted)] hover:text-[var(--text-primary)]">{mode === 'login' ? '还没有账户？创建账户' : '已有账户？返回登录'}</button>{mode === 'login' && onGuest && <button type="button" onClick={onGuest} className="block w-full text-[11px] text-[var(--accent)] hover:text-[var(--text-primary)]">无需登录，先查看指标</button>}</div>
      </form>
    </div>
  )
}
