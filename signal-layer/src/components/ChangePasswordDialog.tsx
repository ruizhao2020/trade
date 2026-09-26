import { useState } from 'react'
import { changePassword } from '../api/auth.ts'

export function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (newPassword !== confirmPassword) {
      setError('两次输入的新密码不一致')
      return
    }
    setSaving(true)
    setError('')
    try {
      await changePassword(currentPassword, newPassword)
      onClose()
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : String(submitError))
    } finally {
      setSaving(false)
    }
  }

  const inputClass = 'w-full h-11 px-3.5 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-primary)] text-[13px] outline-none focus:border-[var(--accent)]'
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <form onSubmit={submit} onClick={(event) => event.stopPropagation()} className="relative w-[420px] rounded-2xl border border-[var(--border-accent)] bg-[var(--bg-secondary)] p-7 shadow-[0_28px_80px_rgba(0,0,0,.5)]">
        <div className="flex items-start justify-between"><div><h2 className="text-[18px] font-semibold tracking-tight">修改密码</h2><p className="mt-1.5 text-[11px] text-[var(--text-muted)]">修改后请使用新密码登录，至少 8 位</p></div><button type="button" onClick={onClose} aria-label="关闭" className="w-8 h-8 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]">×</button></div>
        <div className="mt-6 space-y-5">
          <label className="block"><span className="block mb-2 text-[12px] text-[var(--text-secondary)]">当前密码</span><input type="password" autoFocus autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required className={inputClass} /></label>
          <label className="block"><span className="block mb-2 text-[12px] text-[var(--text-secondary)]">新密码</span><input type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required minLength={8} className={inputClass} /></label>
          <label className="block"><span className="block mb-2 text-[12px] text-[var(--text-secondary)]">确认新密码</span><input type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required minLength={8} className={inputClass} /></label>
        </div>
        {error && <div className="mt-5 px-3 py-2 rounded-lg bg-[rgba(255,107,114,.07)] text-[11px] text-[var(--accent-red)]">{error}</div>}
        <div className="mt-7 pt-5 border-t border-[var(--border-primary)] flex justify-end gap-2"><button type="button" onClick={onClose} className="h-10 px-5 rounded-lg text-[12px] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]">取消</button><button disabled={saving} className="h-10 px-5 rounded-lg bg-[var(--accent)] text-white text-[12px] font-medium hover:bg-[var(--accent-hover)] disabled:opacity-50">{saving ? '保存中…' : '确认修改'}</button></div>
      </form>
    </div>
  )
}
