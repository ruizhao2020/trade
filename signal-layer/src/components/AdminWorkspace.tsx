import { useCallback, useEffect, useState } from 'react'
import type { AuthModule, AuthUser } from '../api/auth.ts'
import {
  createModule, createRole, fetchModules, fetchPermissions, fetchRoles, fetchUsers,
  updateModule, updateRole, updateUserRoles,
} from '../api/admin.ts'
import type { PermissionItem, RoleItem } from '../api/admin.ts'

type Tab = 'users' | 'roles' | 'modules'

function Toggle({ value, onChange }: { value: boolean; onChange: (value: boolean) => void }) {
  return <button type="button" aria-pressed={value} onClick={() => onChange(!value)} className={`w-10 h-5 rounded-full p-0.5 transition-colors ${value ? 'bg-[var(--accent)]' : 'bg-[var(--border-accent)]'}`}><span className={`block w-4 h-4 rounded-full bg-white transition-transform ${value ? 'translate-x-5' : ''}`} /></button>
}

export function AdminWorkspace({ currentUser, onModulesChanged }: { currentUser: AuthUser; onModulesChanged: () => void }) {
  const [tab, setTab] = useState<Tab>('users')
  const [users, setUsers] = useState<AuthUser[]>([])
  const [roles, setRoles] = useState<RoleItem[]>([])
  const [modules, setModules] = useState<AuthModule[]>([])
  const [permissions, setPermissions] = useState<PermissionItem[]>([])
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [nextUsers, nextRoles, nextModules, nextPermissions] = await Promise.all([
        fetchUsers(), fetchRoles(), fetchModules(), fetchPermissions(),
      ])
      setUsers(nextUsers); setRoles(nextRoles); setModules(nextModules); setPermissions(nextPermissions); setError('')
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError))
    }
  }, [])

  useEffect(() => {
    void Promise.resolve().then(load)
  }, [load])

  async function toggleUserRole(user: AuthUser, roleCode: string) {
    const next = user.role_codes.includes(roleCode)
      ? user.role_codes.filter((code) => code !== roleCode)
      : [...user.role_codes, roleCode]
    const updated = await updateUserRoles(user.id, next, user.enabled)
    setUsers((items) => items.map((item) => item.id === user.id ? updated : item))
  }

  async function toggleRolePermission(role: RoleItem, code: string) {
    const next = role.permission_codes.includes(code)
      ? role.permission_codes.filter((item) => item !== code)
      : [...role.permission_codes, code]
    const updated = await updateRole(role.id, { permission_codes: next })
    setRoles((items) => items.map((item) => item.id === role.id ? updated : item))
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col bg-[var(--bg-primary)]">
      <header className="h-16 px-7 flex items-center border-b border-[var(--border-primary)] bg-[var(--bg-secondary)]">
        <div><h1 className="text-[17px] font-semibold tracking-tight">系统管理</h1><p className="mt-0.5 text-[11px] text-[var(--text-muted)]">集中管理账户、角色权限和模块准入</p></div>
        <div className="ml-auto flex items-center gap-2 text-[10px] text-[var(--text-muted)]"><span className="px-2.5 py-1 rounded-md bg-[var(--bg-tertiary)]">{users.length} 用户</span><span className="px-2.5 py-1 rounded-md bg-[var(--bg-tertiary)]">{roles.length} 角色</span><span className="px-2.5 py-1 rounded-md bg-[var(--bg-tertiary)]">{modules.length} 模块</span></div>
      </header>
      <div className="h-12 px-7 flex items-center gap-1 border-b border-[var(--border-primary)] bg-[var(--bg-secondary)]">
        {([['users', '用户管理'], ['roles', '角色权限'], ['modules', '模块配置']] as const).map(([key, label]) => <button key={key} onClick={() => setTab(key)} className={`h-8 px-4 rounded-md text-[12px] font-medium transition-colors ${tab === key ? 'bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-sm' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'}`}>{label}</button>)}
      </div>
      <div className="flex-1 overflow-auto p-7">
        {error && <div className="max-w-6xl mx-auto mb-5 px-4 py-3 rounded-lg border border-[rgba(255,107,114,.2)] bg-[rgba(255,107,114,.06)] text-[11px] text-[var(--accent-red)]">{error}</div>}
        {tab === 'users' && <div className="max-w-6xl mx-auto space-y-3">{users.map((user) => <div key={user.id} className="grid grid-cols-[220px_1fr_100px] gap-5 items-center p-5 rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] shadow-[0_8px_24px_rgba(0,0,0,.08)]"><div><div className="text-[13px] font-semibold">{user.display_name || user.username}{user.id === currentUser.id && <span className="ml-2 px-1.5 py-0.5 rounded bg-[rgba(108,140,255,.1)] text-[9px] font-medium text-[var(--accent)]">当前用户</span>}</div><div className="mt-1 text-[11px] text-[var(--text-muted)]">@{user.username}</div></div><div className="flex flex-wrap gap-2">{roles.map((role) => <button key={role.code} disabled={user.id === currentUser.id} onClick={() => void toggleUserRole(user, role.code)} className={`px-3 h-8 rounded-md border text-[11px] disabled:opacity-50 disabled:cursor-not-allowed ${user.role_codes.includes(role.code) ? 'border-[var(--accent)] text-[#b9c9ff] bg-[rgba(108,140,255,.1)]' : 'border-[var(--border-primary)] text-[var(--text-muted)] hover:border-[var(--border-accent)]'}`}>{role.name}</button>)}</div><div className="flex justify-end">{user.id === currentUser.id ? <span className="text-[10px] text-[var(--text-muted)]">已启用</span> : <Toggle value={user.enabled} onChange={(enabled) => void updateUserRoles(user.id, user.role_codes, enabled).then(load)} />}</div></div>)}</div>}

        {tab === 'roles' && <div className="max-w-6xl mx-auto space-y-4"><button onClick={() => { const code = window.prompt('角色编码（英文）'); const name = code && window.prompt('角色名称'); if (code && name) void createRole({ code, name, description: '' }).then(load) }} className="h-9 px-4 mb-1 rounded-lg bg-[var(--accent)] text-white text-[12px] font-medium hover:bg-[var(--accent-hover)]">新建角色</button>{roles.map((role) => <section key={role.id} className="p-5 rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] shadow-[0_8px_24px_rgba(0,0,0,.08)]"><div className="flex items-center gap-3"><div className="text-[13px] font-semibold">{role.name}</div><code className="text-[10px] text-[var(--text-muted)]">{role.code}</code>{role.built_in && <span className="px-1.5 py-0.5 rounded bg-[rgba(240,163,90,.08)] text-[9px] text-[var(--accent-orange)]">内置</span>}<div className="flex-1"/>{role.code === 'admin' ? <span className="text-[10px] text-[var(--text-muted)]">始终启用</span> : <Toggle value={role.enabled} onChange={(enabled) => void updateRole(role.id, { enabled }).then(load)} />}</div><div className="mt-5 grid grid-cols-2 xl:grid-cols-3 gap-2.5">{permissions.map((permission) => <label key={permission.code} className={`min-h-10 flex items-center gap-2.5 px-3 py-2 rounded-lg border border-transparent bg-[var(--bg-tertiary)] text-[11px] ${role.code === 'admin' ? 'opacity-55' : 'hover:border-[var(--border-accent)]'}`}><input type="checkbox" disabled={role.code === 'admin'} checked={role.permission_codes.includes(permission.code)} onChange={() => void toggleRolePermission(role, permission.code)} className="accent-[var(--accent)]" /><span>{permission.name}</span><code className="ml-auto text-[9px] text-[var(--text-muted)]">{permission.code}</code></label>)}</div></section>)}</div>}

        {tab === 'modules' && (
          <div className="max-w-6xl mx-auto space-y-4">
            <button onClick={() => { const code = window.prompt('模块编码（英文）'); const name = code && window.prompt('模块名称'); if (code && name) void createModule({ code, name, component_key: code, icon: 'module' }).then(() => { void load(); onModulesChanged() }) }} className="h-9 px-4 mb-1 rounded-lg bg-[var(--accent)] text-white text-[12px] font-medium hover:bg-[var(--accent-hover)]">添加模块</button>
            {modules.map((module) => (
              <section key={module.id} className="p-5 rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] shadow-[0_8px_24px_rgba(0,0,0,.08)]">
                <div className="grid grid-cols-[1fr_160px_auto_auto] gap-5 items-center">
                  <div><div className="text-[13px] font-semibold">{module.name}</div><code className="mt-1 block text-[10px] text-[var(--text-muted)]">{module.code}</code></div>
                  <label className="text-[11px] text-[var(--text-muted)]">排序<input type="number" value={module.sort_order} onChange={(event) => void updateModule(module.id, { sort_order: Number(event.target.value) }).then(() => { void load(); onModulesChanged() })} className="ml-2 w-16 h-9 px-2 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-primary)] text-[12px]" /></label>
                  <label className="flex items-center gap-2.5 text-[11px] text-[var(--text-secondary)]">显示<Toggle value={module.visible} onChange={(visible) => void updateModule(module.id, { visible }).then(() => { void load(); onModulesChanged() })} /></label>
                  <label className="flex items-center gap-2.5 text-[11px] text-[var(--text-secondary)]">启用<Toggle value={module.enabled} onChange={(enabled) => void updateModule(module.id, { enabled }).then(() => { void load(); onModulesChanged() })} /></label>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-3">
                  <label className="text-[11px] text-[var(--text-muted)]">页面组件<input defaultValue={module.component_key} onBlur={(event) => void updateModule(module.id, { component_key: event.target.value }).then(() => { void load(); onModulesChanged() })} className="mt-1.5 w-full h-9 px-3 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-primary)] text-[11px] text-[var(--text-secondary)] outline-none focus:border-[var(--accent)]" /></label>
                  <label className="text-[11px] text-[var(--text-muted)]">API 前缀<input defaultValue={module.api_prefixes} onBlur={(event) => void updateModule(module.id, { api_prefixes: event.target.value }).then(load)} className="mt-1.5 w-full h-9 px-3 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-primary)] text-[11px] text-[var(--text-secondary)] outline-none focus:border-[var(--accent)]" /></label>
                  <label className="text-[11px] text-[var(--text-muted)]">准入权限<input defaultValue={module.api_permission} onBlur={(event) => void updateModule(module.id, { api_permission: event.target.value }).then(load)} className="mt-1.5 w-full h-9 px-3 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-primary)] text-[11px] text-[var(--text-secondary)] outline-none focus:border-[var(--accent)]" /></label>
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
