import { useCallback, useEffect, useState } from 'react'
import type { AuthModule, AuthUser } from '../api/auth.ts'
import {
  createModule, createRole, fetchModules, fetchPermissions, fetchRoles, fetchUsers,
  updateModule, updateRole, updateUserRoles, fetchNotificationChannelsForAdmin,
  fetchNotificationTemplatesForAdmin, createNotificationChannelForAdmin,
  updateNotificationChannelForAdmin, deleteNotificationChannelForAdmin,
  updateNotificationTemplateForAdmin,
  fetchPublicIndicatorPolicies, fetchPublicIndicatorFeaturePolicies,
  updatePublicIndicatorPolicy, updatePublicIndicatorFeaturePolicy,
  createPublicIndicatorFeaturePolicy,
  fetchIndicatorRuntimeSettings, updateIndicatorRuntimeSettings,
} from '../api/admin.ts'
import type { AdminNotificationChannel, AdminNotificationTemplate, IndicatorRuntimeSettings, PermissionItem, PublicIndicatorFeaturePolicy, PublicIndicatorPolicy, RoleItem } from '../api/admin.ts'

type Tab = 'users' | 'roles' | 'modules' | 'indicator-settings' | 'public-display' | 'notifications'

function Toggle({ value, onChange, disabled = false }: { value: boolean; onChange: (value: boolean) => void; disabled?: boolean }) {
  return <button type="button" disabled={disabled} aria-pressed={value} onClick={() => onChange(!value)} className={`w-10 h-5 rounded-full p-0.5 transition-colors disabled:opacity-35 disabled:cursor-not-allowed ${value ? 'bg-[var(--accent)]' : 'bg-[var(--border-accent)]'}`}><span className={`block w-4 h-4 rounded-full bg-white transition-transform ${value ? 'translate-x-5' : ''}`} /></button>
}

const NOTIFICATION_EVENT_LABEL: Record<string, string> = {
  screener_completed: '定时选股完成', screener_failed: '定时选股失败', entry: '策略建仓',
  exit: '策略清仓', stop_loss: '触发止损', take_profit: '触发止盈', scheduled: '策略定时快照',
}

function IndicatorSettingsPanel({ settings, onChange }: { settings: IndicatorRuntimeSettings; onChange: (value: IndicatorRuntimeSettings) => void }) {
  const [value, setValue] = useState(settings.divergence_power_ratio)
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)

  async function save() {
    if (!(value > 0 && value < 1)) { setMessage('阈值必须大于0且小于1'); return }
    setSaving(true); setMessage('')
    try {
      const next = await updateIndicatorRuntimeSettings({ divergence_power_ratio: value })
      onChange(next); setMessage('已保存并立即生效')
    } catch (error) {
      setMessage(error instanceof Error ? error.message.replace(/^Error:\s*/, '') : '保存失败')
    } finally { setSaving(false) }
  }

  return <div className="max-w-4xl mx-auto"><section className="p-6 rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)]"><h2 className="text-[13px] font-semibold">缠论参数</h2><p className="mt-1 text-[11px] text-[var(--text-muted)]">修改后立即参与新一次缠论计算，并使用独立缓存。</p><div className="mt-5 max-w-xl p-4 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-tertiary)]"><div className="text-[12px] font-medium">背驰力度阈值</div><div className="mt-1 text-[10px] leading-5 text-[var(--text-muted)]">仅当“当前笔力度 &lt; 参考笔力度 × 阈值”时确认背驰。默认0.7；刚好等于阈值不算背驰。</div><div className="mt-4 flex items-center gap-3"><input aria-label="背驰力度阈值" type="number" min="0.01" max="0.99" step="0.01" value={value} onChange={(event) => setValue(Number(event.target.value))} className="w-28 h-10 px-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] text-[13px] font-mono outline-none focus:border-[var(--accent)]" /><span className="text-[11px] text-[var(--text-muted)]">当前笔 / 参考笔</span><button type="button" disabled={saving} onClick={() => void save()} className="ml-auto h-10 px-4 rounded-lg bg-[var(--accent)] text-white text-[11px] disabled:opacity-50">{saving ? '保存中…' : '保存参数'}</button></div>{message && <div role="status" className={`mt-3 text-[11px] ${message.startsWith('已保存') ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>{message}</div>}</div></section></div>
}

function NotificationAdminPanel({
  channels, templates, onReload, onChannelsChange, onTemplatesChange,
}: {
  channels: AdminNotificationChannel[]
  templates: AdminNotificationTemplate[]
  onReload: () => Promise<void>
  onChannelsChange: (channels: AdminNotificationChannel[]) => void
  onTemplatesChange: (templates: AdminNotificationTemplate[]) => void
}) {
  const [channelType, setChannelType] = useState<'wecom' | 'feishu' | 'browser'>('wecom')
  const [channelName, setChannelName] = useState('交易提醒群')
  const [webhook, setWebhook] = useState('')
  const [saving, setSaving] = useState(false)
  const [actionMessage, setActionMessage] = useState('')

  async function addChannel() {
    if (!channelName.trim()) { setActionMessage('请填写渠道名称'); return }
    if (channelType !== 'browser' && !webhook.trim()) { setActionMessage('企业微信和飞书需要填写 Webhook 地址'); return }
    setSaving(true)
    setActionMessage('')
    try {
      const item = await createNotificationChannelForAdmin({ name: channelName.trim(), channel_type: channelType, webhook_url: webhook.trim() || undefined, is_shared: true })
      onChannelsChange([...channels, item]); setWebhook(''); setActionMessage('渠道已发布')
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message.replace(/^Error:\s*/, '') : '渠道发布失败')
    } finally { setSaving(false) }
  }

  return <div className="max-w-6xl mx-auto space-y-4">
    <section className="p-5 rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] shadow-[0_8px_24px_rgba(0,0,0,.08)]">
      <div><div className="text-[13px] font-semibold">推送渠道</div><p className="mt-1 text-[11px] text-[var(--text-muted)]">Webhook 只在此处维护，普通用户只能选择已发布的渠道。</p></div>
      <div className="mt-4 grid grid-cols-[1fr_150px_1.5fr_auto] gap-2"><input value={channelName} onChange={(event) => setChannelName(event.target.value)} placeholder="渠道名称" className="h-9 px-3 rounded-md bg-[var(--bg-tertiary)] border border-[var(--border-primary)] text-[11px] outline-none focus:border-[var(--accent)]" /><select value={channelType} onChange={(event) => setChannelType(event.target.value as typeof channelType)} className="h-9 px-3 rounded-md bg-[var(--bg-tertiary)] border border-[var(--border-primary)] text-[11px]"><option value="wecom">企业微信</option><option value="feishu">飞书</option><option value="browser">浏览器通知</option></select><input value={webhook} onChange={(event) => setWebhook(event.target.value)} disabled={channelType === 'browser'} placeholder={channelType === 'browser' ? '浏览器无需 Webhook' : 'Webhook 地址'} className="h-9 px-3 rounded-md bg-[var(--bg-tertiary)] border border-[var(--border-primary)] text-[11px] outline-none disabled:opacity-40" /><button type="button" disabled={saving} onClick={() => void addChannel()} className="h-9 px-4 rounded-md bg-[var(--accent)] text-white text-[11px] disabled:opacity-50">{saving ? '发布中…' : '发布渠道'}</button></div>
      {actionMessage && <div role="status" className="mt-2 text-[11px] text-[var(--accent)]">{actionMessage}</div>}
      <div className="mt-4 divide-y divide-[var(--border-primary)]">{channels.map((channel) => <div key={channel.id} className="py-3 flex items-center gap-3"><span className={`w-2 h-2 rounded-full ${channel.enabled ? 'bg-[var(--accent-green)]' : 'bg-[var(--text-muted)]'}`} /><div className="flex-1"><div className="text-[12px]">{channel.name}</div><div className="text-[10px] text-[var(--text-muted)] mt-1">{channel.channel_type === 'wecom' ? '企业微信' : channel.channel_type === 'feishu' ? '飞书' : '浏览器'} · {channel.webhook_url_masked || '无 Webhook'}</div></div><Toggle value={channel.enabled} onChange={(enabled) => void updateNotificationChannelForAdmin(channel.id, { enabled }).then((next) => onChannelsChange(channels.map((item) => item.id === next.id ? next : item)))} /><button type="button" onClick={() => void deleteNotificationChannelForAdmin(channel.id).then(() => onChannelsChange(channels.filter((item) => item.id !== channel.id)))} className="text-[11px] text-[var(--text-muted)] hover:text-[var(--accent-red)]">删除</button></div>)}</div>
    </section>
    <section className="p-5 rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] shadow-[0_8px_24px_rgba(0,0,0,.08)]"><div><div className="text-[13px] font-semibold">消息模板</div><p className="mt-1 text-[11px] text-[var(--text-muted)]">模板变量会在任务执行时自动替换，例如 {'{{symbol}}'}、{'{{price}}'}、{'{{screen_results}}'}。</p></div><div className="mt-4 space-y-3">{templates.map((template) => <TemplateEditor key={template.id} template={template} onChange={(next) => onTemplatesChange(templates.map((item) => item.id === next.id ? next : item))} onSaved={onReload} />)}</div></section>
  </div>
}

function TemplateEditor({ template, onChange, onSaved }: { template: AdminNotificationTemplate; onChange: (template: AdminNotificationTemplate) => void; onSaved: () => Promise<void> }) {
  const [content, setContent] = useState(template.content)
  const [name, setName] = useState(template.name)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  async function save() {
    setSaving(true); setMessage('')
    try {
      const next = await updateNotificationTemplateForAdmin(template.id, { name, content })
      onChange(next); await onSaved(); setMessage('已保存')
    } catch (error) { setMessage(error instanceof Error ? error.message.replace(/^Error:\s*/, '') : '保存失败') } finally { setSaving(false) }
  }
  return <div className="p-3 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-primary)]"><div className="flex items-center gap-3"><input value={name} onChange={(event) => setName(event.target.value)} className="flex-1 h-8 px-2 rounded-md bg-[var(--bg-secondary)] border border-[var(--border-primary)] text-[11px]" /><span className="text-[10px] text-[var(--text-muted)]">{NOTIFICATION_EVENT_LABEL[template.event_type] || template.event_type}</span><Toggle value={template.enabled} onChange={(enabled) => void updateNotificationTemplateForAdmin(template.id, { enabled }).then((next) => { onChange(next); return onSaved() }).catch((error) => setMessage(error instanceof Error ? error.message.replace(/^Error:\s*/, '') : '更新失败'))} /></div><textarea value={content} onChange={(event) => setContent(event.target.value)} className="mt-2 w-full min-h-24 p-2 rounded-md bg-[var(--bg-secondary)] border border-[var(--border-primary)] text-[11px] leading-5 outline-none focus:border-[var(--accent)]" /><div className="mt-2 flex items-center justify-end gap-3">{message && <span role="status" className={`text-[10px] ${message === '已保存' ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>{message}</span>}<button type="button" disabled={saving} onClick={() => void save()} className="h-7 px-3 rounded-md bg-[var(--accent)] text-white text-[10px] disabled:opacity-50">{saving ? '保存中…' : '保存模板'}</button></div></div>
}

function PublicDisplayPanel({ indicators, features, onIndicatorsChange, onFeaturesChange }: { indicators: PublicIndicatorPolicy[]; features: PublicIndicatorFeaturePolicy[]; onIndicatorsChange: (items: PublicIndicatorPolicy[]) => void; onFeaturesChange: (items: PublicIndicatorFeaturePolicy[]) => void }) {
  const [expandedTypes, setExpandedTypes] = useState<string[]>([])
  const updateIndicator = async (item: PublicIndicatorPolicy, values: Partial<PublicIndicatorPolicy>) => {
    const next = await updatePublicIndicatorPolicy(item.id, values)
    onIndicatorsChange(indicators.map((candidate) => candidate.id === next.id ? next : candidate))
    if (values.public_visible === false) {
      onFeaturesChange(features.map((feature) => feature.indicator_type === item.indicator_type
        ? { ...feature, public_visible: false, show_details: false }
        : feature))
    }
  }
  const updateFeature = async (item: PublicIndicatorFeaturePolicy, values: Partial<PublicIndicatorFeaturePolicy>) => {
    const next = await updatePublicIndicatorFeaturePolicy(item.id, values)
    onFeaturesChange(features.map((candidate) => candidate.id === next.id ? next : candidate))
  }
  const featuresFor = (indicatorType: string) => features.filter((item) => item.indicator_type === indicatorType)
  const toggleExpanded = (indicatorType: string) => setExpandedTypes((current) => current.includes(indicatorType)
    ? current.filter((item) => item !== indicatorType)
    : [...current, indicatorType])
  const addFeature = async (indicatorType: string) => {
    const featureCode = window.prompt('子功能编码，例如 divergence 或 histogram')?.trim()
    if (!featureCode) return
    const displayName = window.prompt('公开显示名称')?.trim()
    if (!displayName) return
    const next = await createPublicIndicatorFeaturePolicy({ indicator_type: indicatorType, feature_code: featureCode, display_name: displayName })
    onFeaturesChange([...features, next])
  }
  return <div className="max-w-6xl mx-auto space-y-5">
    <div className="px-4 py-3 rounded-lg border border-[rgba(108,140,255,.25)] bg-[rgba(108,140,255,.06)] text-[11px] leading-5 text-[var(--text-secondary)]">新增指标及其线条、标记会被自动发现，并默认保持私有。点击主指标展开子指标；关闭主指标后，全部子指标会同步关闭。</div>
    <section className="rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] overflow-hidden">
      <div className="px-5 py-4 border-b border-[var(--border-primary)] text-[13px] font-semibold">公开指标</div>
      <div className="divide-y divide-[var(--border-primary)]">
        {indicators.map((item) => {
          const expanded = expandedTypes.includes(item.indicator_type)
          const childFeatures = featuresFor(item.indicator_type)
          return <div key={item.id}>
            <div className="min-h-14 px-5 py-3 flex items-center gap-5">
              <button type="button" onClick={() => toggleExpanded(item.indicator_type)} className="min-w-0 flex-1 flex items-center gap-2 text-left">
                <svg viewBox="0 0 12 12" fill="none" className={`w-3 h-3 shrink-0 text-[var(--text-muted)] transition-transform ${expanded ? 'rotate-90' : ''}`} aria-hidden="true"><path d="m4 2.5 4 3.5-4 3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
                <span className="text-[12px] font-semibold text-[var(--text-primary)]">{item.display_name}</span>
                <code className="text-[9px] text-[var(--text-muted)]">{item.indicator_type}</code>
                {childFeatures.length > 0 && <span className="text-[9px] text-[var(--text-muted)]">{childFeatures.filter((feature) => feature.public_visible).length}/{childFeatures.length} 子项</span>}
              </button>
              <div className="flex items-center gap-8 shrink-0">
                <label className="flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">公开显示<Toggle value={item.public_visible} onChange={(public_visible) => void updateIndicator(item, { public_visible })} /></label>
                <label className="flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">显示参数<Toggle disabled={!item.public_visible} value={item.show_parameters} onChange={(show_parameters) => void updateIndicator(item, { show_parameters })} /></label>
                <label className="flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">显示详情<Toggle disabled={!item.public_visible} value={item.show_details} onChange={(show_details) => void updateIndicator(item, { show_details })} /></label>
                <label className="flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">信号标记<Toggle disabled={!item.public_visible} value={item.show_markers} onChange={(show_markers) => void updateIndicator(item, { show_markers })} /></label>
              </div>
            </div>
            {expanded && <div className="px-5 pb-4 ml-5">
              <div className="flex items-center gap-3 mb-3"><span className="text-[10px] text-[var(--text-muted)]">公开名称</span><input defaultValue={item.display_name} onBlur={(event) => { if (event.target.value !== item.display_name) void updateIndicator(item, { display_name: event.target.value }) }} className="h-8 w-56 px-2 rounded-md border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[11px]" /><button type="button" onClick={() => void addFeature(item.indicator_type)} className="ml-auto h-7 px-3 rounded-md border border-[var(--border-primary)] text-[10px] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]">添加子指标</button></div>
              <div className="rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] divide-y divide-[var(--border-primary)]">
                {childFeatures.length === 0 && <div className="px-4 py-3 text-[10px] text-[var(--text-muted)]">该指标暂无可单独配置的子指标</div>}
                {childFeatures.map((feature) => <div key={feature.id} className="min-h-12 px-4 py-2 flex items-center gap-5">
                  <div className="min-w-0 flex-1"><input defaultValue={feature.display_name} onBlur={(event) => { if (event.target.value !== feature.display_name) void updateFeature(feature, { display_name: event.target.value }) }} className="h-8 w-56 max-w-full px-2 rounded-md border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[11px]" /><code className="ml-2 text-[9px] text-[var(--text-muted)]">{feature.feature_code}</code></div>
                  <div className="flex items-center gap-8 shrink-0">
                    <label className="flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">公开显示<Toggle disabled={!item.public_visible} value={feature.public_visible} onChange={(public_visible) => void updateFeature(feature, { public_visible })} /></label>
                    <label className="flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">显示详情<Toggle disabled={!item.public_visible || !feature.public_visible} value={feature.show_details} onChange={(show_details) => void updateFeature(feature, { show_details })} /></label>
                  </div>
                </div>)}
              </div>
            </div>}
          </div>
        })}
      </div>
    </section>
  </div>
}

export function AdminWorkspace({ currentUser, onModulesChanged }: { currentUser: AuthUser; onModulesChanged: () => void }) {
  const [tab, setTab] = useState<Tab>('users')
  const [users, setUsers] = useState<AuthUser[]>([])
  const [roles, setRoles] = useState<RoleItem[]>([])
  const [modules, setModules] = useState<AuthModule[]>([])
  const [permissions, setPermissions] = useState<PermissionItem[]>([])
  const [notificationChannels, setNotificationChannels] = useState<AdminNotificationChannel[]>([])
  const [notificationTemplates, setNotificationTemplates] = useState<AdminNotificationTemplate[]>([])
  const [publicIndicators, setPublicIndicators] = useState<PublicIndicatorPolicy[]>([])
  const [publicIndicatorFeatures, setPublicIndicatorFeatures] = useState<PublicIndicatorFeaturePolicy[]>([])
  const [indicatorSettings, setIndicatorSettings] = useState<IndicatorRuntimeSettings>({ divergence_power_ratio: 0.7 })
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [nextUsers, nextRoles, nextModules, nextPermissions, nextChannels, nextTemplates, nextPublicIndicators, nextPublicFeatures, nextIndicatorSettings] = await Promise.all([
        fetchUsers(), fetchRoles(), fetchModules(), fetchPermissions(), fetchNotificationChannelsForAdmin(), fetchNotificationTemplatesForAdmin(), fetchPublicIndicatorPolicies(), fetchPublicIndicatorFeaturePolicies(), fetchIndicatorRuntimeSettings(),
      ])
      setUsers(nextUsers); setRoles(nextRoles); setModules(nextModules); setPermissions(nextPermissions); setNotificationChannels(nextChannels); setNotificationTemplates(nextTemplates); setPublicIndicators(nextPublicIndicators); setPublicIndicatorFeatures(nextPublicFeatures); setIndicatorSettings(nextIndicatorSettings); setError('')
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
      <div className="h-14 px-7 flex items-center border-b border-[var(--border-primary)] bg-[var(--bg-secondary)]">
        <div className="inline-flex items-center gap-1.5 p-1 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)] shadow-[0_4px_14px_rgba(0,0,0,.08)]" role="tablist" aria-label="系统管理页签">
          {([['users', '用户管理'], ['roles', '角色权限'], ['modules', '模块配置'], ['indicator-settings', '指标参数'], ['public-display', '公开展示'], ['notifications', '通知配置']] as const).map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)} className={`h-9 px-5 rounded-md text-[12px] font-medium transition-all ${tab === key ? 'bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-[0_2px_8px_rgba(0,0,0,.16)] ring-1 ring-[var(--border-accent)]' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'}`}>{label}</button>)}
        </div>
      </div>
      <div className="flex-1 overflow-auto p-7">
        {error && <div className="max-w-6xl mx-auto mb-5 px-4 py-3 rounded-lg border border-[rgba(255,107,114,.2)] bg-[rgba(255,107,114,.06)] text-[11px] text-[var(--accent-red)]">{error}</div>}
        {tab === 'users' && <div className="max-w-6xl mx-auto space-y-3">{users.map((user) => <div key={user.id} className="grid grid-cols-[220px_1fr_100px] gap-5 items-center p-5 rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] shadow-[0_8px_24px_rgba(0,0,0,.08)]"><div><div className="text-[13px] font-semibold">{user.display_name || user.username}{user.id === currentUser.id && <span className="ml-2 px-1.5 py-0.5 rounded bg-[rgba(108,140,255,.1)] text-[9px] font-medium text-[var(--accent)]">当前用户</span>}</div><div className="mt-1 text-[11px] text-[var(--text-muted)]">@{user.username}</div></div><div className="flex flex-wrap gap-2">{roles.map((role) => <button key={role.code} disabled={user.id === currentUser.id} onClick={() => void toggleUserRole(user, role.code)} className={`px-3 h-8 rounded-md border text-[11px] disabled:opacity-50 disabled:cursor-not-allowed ${user.role_codes.includes(role.code) ? 'border-[var(--accent)] text-[#b9c9ff] bg-[rgba(108,140,255,.1)]' : 'border-[var(--border-primary)] text-[var(--text-muted)] hover:border-[var(--border-accent)]'}`}>{role.name}</button>)}</div><div className="flex justify-end">{user.id === currentUser.id ? <span className="text-[10px] text-[var(--text-muted)]">已启用</span> : <Toggle value={user.enabled} onChange={(enabled) => void updateUserRoles(user.id, user.role_codes, enabled).then(load)} />}</div></div>)}</div>}

        {tab === 'roles' && <div className="max-w-6xl mx-auto space-y-4"><button onClick={() => { const code = window.prompt('角色编码（英文）'); const name = code && window.prompt('角色名称'); if (code && name) void createRole({ code, name, description: '' }).then(load) }} className="h-9 px-4 mb-1 rounded-lg bg-[var(--accent)] text-white text-[12px] font-medium hover:bg-[var(--accent-hover)]">新建角色</button>{roles.map((role) => <section key={role.id} className="p-5 rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] shadow-[0_8px_24px_rgba(0,0,0,.08)]"><div className="flex items-center gap-3"><div className="text-[13px] font-semibold">{role.name}</div><code className="text-[10px] text-[var(--text-muted)]">{role.code}</code>{role.built_in && <span className="px-1.5 py-0.5 rounded bg-[rgba(240,163,90,.08)] text-[9px] text-[var(--accent-orange)]">内置</span>}<div className="flex-1"/>{role.code === 'admin' ? <span className="text-[10px] text-[var(--text-muted)]">始终启用</span> : <Toggle value={role.enabled} onChange={(enabled) => void updateRole(role.id, { enabled }).then(load)} />}</div><label className="mt-3 flex items-center gap-2 text-[11px] text-[var(--text-secondary)]"><input type="checkbox" checked={role.registration_default} onChange={() => void updateRole(role.id, { registration_default: !role.registration_default }).then(load)} className="accent-[var(--accent)]" />设为新用户注册默认角色{role.registration_default && <span className="text-[10px] text-[var(--accent)]">（当前默认）</span>}</label><div className="mt-5 grid grid-cols-2 xl:grid-cols-3 gap-2.5">{permissions.map((permission) => <label key={permission.code} className={`min-h-10 flex items-center gap-2.5 px-3 py-2 rounded-lg border border-transparent bg-[var(--bg-tertiary)] text-[11px] ${role.code === 'admin' ? 'opacity-55' : 'hover:border-[var(--border-accent)]'}`}><input type="checkbox" disabled={role.code === 'admin'} checked={role.permission_codes.includes(permission.code)} onChange={() => void toggleRolePermission(role, permission.code)} className="accent-[var(--accent)]" /><span>{permission.name}</span><code className="ml-auto text-[9px] text-[var(--text-muted)]">{permission.code}</code></label>)}</div></section>)}</div>}

        {tab === 'modules' && (
          <div className="max-w-6xl mx-auto space-y-4">
            <button onClick={() => { const code = window.prompt('模块编码（英文）'); const name = code && window.prompt('模块名称'); if (code && name) void createModule({ code, name, component_key: code, icon: 'module' }).then(() => { void load(); onModulesChanged() }) }} className="h-9 px-4 mb-1 rounded-lg bg-[var(--accent)] text-white text-[12px] font-medium hover:bg-[var(--accent-hover)]">添加模块</button>
            {modules.map((module) => (
              <section key={module.id} className="p-5 rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)] shadow-[0_8px_24px_rgba(0,0,0,.08)]">
                <div className="grid grid-cols-[1fr_160px_auto_auto_auto] gap-5 items-center">
                  <div><div className="text-[13px] font-semibold">{module.name}</div><code className="mt-1 block text-[10px] text-[var(--text-muted)]">{module.code}</code></div>
                  <label className="text-[11px] text-[var(--text-muted)]">排序<input type="number" value={module.sort_order} onChange={(event) => void updateModule(module.id, { sort_order: Number(event.target.value) }).then(() => { void load(); onModulesChanged() })} className="ml-2 w-16 h-9 px-2 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-primary)] text-[12px]" /></label>
                  <label className="flex items-center gap-2.5 text-[11px] text-[var(--text-secondary)]">显示<Toggle value={module.visible} onChange={(visible) => void updateModule(module.id, { visible }).then(() => { void load(); onModulesChanged() })} /></label>
                  <label className="flex items-center gap-2.5 text-[11px] text-[var(--text-secondary)]">启用<Toggle value={module.enabled} onChange={(enabled) => void updateModule(module.id, { enabled }).then(() => { void load(); onModulesChanged() })} /></label>
                  <label className="flex items-center gap-2.5 text-[11px] text-[var(--text-secondary)]">允许未登录<Toggle value={module.public_access} onChange={(public_access) => void updateModule(module.id, { public_access }).then(() => { void load(); onModulesChanged() })} /></label>
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
        {tab === 'indicator-settings' && <IndicatorSettingsPanel settings={indicatorSettings} onChange={setIndicatorSettings} />}

        {tab === 'notifications' && <NotificationAdminPanel channels={notificationChannels} templates={notificationTemplates} onReload={load} onChannelsChange={setNotificationChannels} onTemplatesChange={setNotificationTemplates} />}
        {tab === 'public-display' && <PublicDisplayPanel indicators={publicIndicators} features={publicIndicatorFeatures} onIndicatorsChange={setPublicIndicators} onFeaturesChange={setPublicIndicatorFeatures} />}
      </div>
    </div>
  )
}
