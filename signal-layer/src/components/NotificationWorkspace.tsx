import { useEffect, useMemo, useRef, useState } from 'react'
import {
  createScreenerSchedule, createStrategyMonitor, deleteScreenerSchedule, deleteStrategyMonitor,
  fetchNotificationChannels, fetchNotificationEvents, fetchScreenerSchedules, fetchStrategyMonitors,
  markNotificationEventsRead, updateScreenerSchedule, updateStrategyMonitor,
} from '../api/notifications.ts'
import type { NotificationChannel, NotificationEvent, ScreenerSchedule, StrategyMonitor } from '../api/notifications.ts'
import { fetchTemplates } from '../api/template.ts'
import { useAppStore } from '../store/useAppStore.ts'

const EVENT_LABEL: Record<string, string> = { entry: '建仓', exit: '清仓', stop_loss: '止损', take_profit: '止盈', scheduled: '策略快照', screener_completed: '选股完成', screener_failed: '选股失败' }
const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

function CollapseIcon({ open }: { open: boolean }) {
  return <svg viewBox="0 0 16 16" fill="none" className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true"><path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
}

function ChannelPicker({ channels, value, onChange }: { channels: NotificationChannel[]; value: number[]; onChange: (ids: number[]) => void }) {
  if (channels.length === 0) return <div className="min-h-9 flex items-center px-3 rounded-md border border-[var(--border-primary)] text-[10px] text-[var(--text-muted)]">暂无可用渠道，请联系管理员配置</div>
  return <div className="min-h-9 flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 rounded-md border border-[var(--border-primary)] bg-[var(--bg-tertiary)]"><span className="w-full text-[10px] text-[var(--text-muted)]">可多选推送渠道</span>{channels.map((channel) => <label key={channel.id} className="inline-flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)] cursor-pointer"><input type="checkbox" checked={value.includes(channel.id)} onChange={() => onChange(value.includes(channel.id) ? value.filter((id) => id !== channel.id) : [...value, channel.id])} className="accent-[var(--accent)]" />{channel.name}</label>)}</div>
}

export function NotificationWorkspace() {
  const templates = useAppStore((s) => s.templates)
  const addTemplate = useAppStore((s) => s.addTemplate)
  const [channels, setChannels] = useState<NotificationChannel[]>([])
  const [monitors, setMonitors] = useState<StrategyMonitor[]>([])
  const [schedules, setSchedules] = useState<ScreenerSchedule[]>([])
  const [events, setEvents] = useState<NotificationEvent[]>([])
  const [templateId, setTemplateId] = useState('')
  const [symbol, setSymbol] = useState('')
  const [symbolName, setSymbolName] = useState('')
  const [monitorChannelIds, setMonitorChannelIds] = useState<number[]>([])
  const [screenChannelIds, setScreenChannelIds] = useState<number[]>([])
  const [eventTypes, setEventTypes] = useState<string[]>(['entry', 'exit', 'stop_loss', 'take_profit'])
  const [screenTime, setScreenTime] = useState('01:00')
  const [screenDays, setScreenDays] = useState<number[]>([1, 2, 3, 4, 5])
  const [screenLimit, setScreenLimit] = useState(50)
  const [screenMarket, setScreenMarket] = useState<'stock' | 'futures'>('stock')
  const [tab, setTab] = useState<'tasks' | 'events'>('tasks')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [monitorOpen, setMonitorOpen] = useState(true)
  const [screenerOpen, setScreenerOpen] = useState(true)
  const seenEvents = useRef(new Set<number>())

  const load = async () => {
    try {
      const [nextChannels, nextMonitors, nextSchedules, nextEvents] = await Promise.all([
        fetchNotificationChannels(), fetchStrategyMonitors(), fetchScreenerSchedules(), fetchNotificationEvents(false),
      ])
      setChannels(nextChannels); setMonitors(nextMonitors); setSchedules(nextSchedules); setEvents(nextEvents)
      nextEvents.forEach((event) => seenEvents.current.add(event.id))
    } catch (loadError) { setError(loadError instanceof Error ? loadError.message : '通知数据加载失败') }
  }
  useEffect(() => { const timer = window.setTimeout(() => { void load() }, 0); return () => window.clearTimeout(timer) }, [])
  useEffect(() => {
    if (templates.length) return
    void fetchTemplates().then((list) => { list.forEach(addTemplate); if (list[0]) setTemplateId(list[0].id) }).catch(() => {})
  }, [addTemplate, templates.length])
  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const next = await fetchNotificationEvents(true)
        for (const event of next) {
          if (seenEvents.current.has(event.id)) continue
          seenEvents.current.add(event.id)
          if ('Notification' in window && Notification.permission === 'granted') new Notification(event.title, { body: event.content })
        }
        if (next.length) setEvents((current) => [...next, ...current.filter((item) => !next.some((e) => e.id === item.id))])
      } catch { /* 后台轮询失败不打断页面 */ }
    }, 30000)
    return () => window.clearInterval(timer)
  }, [])

  const activeTemplate = useMemo(() => templates.find((item) => item.id === templateId), [templateId, templates])
  const toggleDay = (day: number, value: number[], setter: (value: number[]) => void) => setter(value.includes(day) ? value.filter((item) => item !== day) : [...value, day].sort())
  const toggleEvent = (event: string) => setEventTypes((current) => current.includes(event) ? current.filter((item) => item !== event) : [...current, event])
  const channelNames = (ids: number[]) => ids.map((id) => channels.find((channel) => channel.id === id)?.name).filter(Boolean).join('、') || '未选择渠道'
  const daysText = (days: number[]) => days.length ? days.map((day) => WEEKDAYS[day - 1]).join('、') : '每天'

  async function addMonitor() {
    if (!templateId || !symbol.trim() || !eventTypes.length) return
    setBusy(true); setError(null)
    try {
      const item = await createStrategyMonitor({ template_id: templateId, symbol: symbol.trim(), symbol_name: symbolName.trim(), channel_ids: monitorChannelIds, event_types: eventTypes as ('entry' | 'exit' | 'stop_loss' | 'take_profit')[] })
      setMonitors((current) => [item, ...current]); setSymbol(''); setSymbolName('')
    } catch (e) { setError(e instanceof Error ? e.message : '创建标的监控失败') } finally { setBusy(false) }
  }
  async function addScreenerSchedule() {
    if (!templateId) return
    setBusy(true); setError(null)
    try {
      const item = await createScreenerSchedule({ template_id: templateId, market: screenMarket, universe_limit: screenLimit, min_progress: 1, schedule_time: screenTime, schedule_weekdays: screenDays, channel_ids: screenChannelIds })
      setSchedules((current) => [item, ...current])
    } catch (e) { setError(e instanceof Error ? e.message : '创建定时选股任务失败') } finally { setBusy(false) }
  }
  async function markRead(event: NotificationEvent) {
    if (event.is_read) return
    await markNotificationEventsRead([event.id]).catch(() => {})
    setEvents((current) => current.map((item) => item.id === event.id ? { ...item, is_read: true } : item))
  }
  async function enableBrowserNotifications() { if ('Notification' in window) await Notification.requestPermission() }

  return <div className="flex-1 min-h-0 overflow-auto bg-[var(--bg-primary)] p-5 lg:p-7"><div className="max-w-6xl mx-auto space-y-5">
    <header className="flex items-start justify-between gap-4"><div><h1 className="text-[17px] font-semibold tracking-tight">通知中心</h1><p className="text-[11px] text-[var(--text-muted)] mt-1">管理个人推送任务；通知渠道和消息模板由管理员统一维护</p></div><button type="button" onClick={enableBrowserNotifications} className="h-8 px-3 rounded-md border border-[var(--border-primary)] text-[11px] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]">开启浏览器通知</button></header>
    {error && <div role="alert" className="rounded-md border border-[rgba(248,113,113,.25)] bg-[rgba(248,113,113,.06)] px-3 py-2 text-[11px] text-[var(--accent-red)]">{error}</div>}
    <div className="flex items-center gap-1 border-b border-[var(--border-primary)]"><button type="button" onClick={() => setTab('tasks')} className={`h-9 px-3 text-[12px] ${tab === 'tasks' ? 'text-[var(--text-primary)] border-b-2 border-[var(--accent)]' : 'text-[var(--text-muted)]'}`}>推送任务 <span className="text-[10px] ml-1">{monitors.length + schedules.length}</span></button><button type="button" onClick={() => setTab('events')} className={`h-9 px-3 text-[12px] ${tab === 'events' ? 'text-[var(--text-primary)] border-b-2 border-[var(--accent)]' : 'text-[var(--text-muted)]'}`}>通知记录 <span className="text-[10px] ml-1">{events.filter((event) => !event.is_read).length} 未读</span></button></div>
    {tab === 'events' ? <section className="rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] divide-y divide-[var(--border-primary)]">{events.length === 0 && <div className="px-4 py-10 text-center text-[11px] text-[var(--text-muted)]">暂无通知记录</div>}{events.map((event) => <button type="button" key={event.id} onClick={() => void markRead(event)} className={`w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-[var(--bg-tertiary)]/50 ${event.is_read ? '' : 'bg-[rgba(108,140,255,.05)]'}`}><span className={`mt-1.5 w-2 h-2 rounded-full ${event.event_type.includes('failed') || event.event_type === 'stop_loss' ? 'bg-[var(--accent-red)]' : event.event_type === 'entry' ? 'bg-[var(--accent-green)]' : 'bg-[var(--accent)]'}`} /><div className="flex-1 min-w-0"><div className="text-[12px] font-medium">{EVENT_LABEL[event.event_type] || event.title} · {event.symbol_name || event.symbol}</div><div className="mt-1 text-[11px] text-[var(--text-secondary)] whitespace-pre-line">{event.content}</div></div><time className="text-[10px] text-[var(--text-muted)] whitespace-nowrap">{new Date(event.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</time></button>)}</section> : <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-5">
      <div className="space-y-4"><section className="rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)]"><button type="button" onClick={() => setMonitorOpen((value) => !value)} className="w-full px-4 py-3 flex items-center justify-between"><div className="text-left"><h2 className="text-[12px] font-semibold">标的策略监控</h2><p className="text-[10px] text-[var(--text-muted)] mt-1">建仓、清仓、止损、止盈触发后推送</p></div><CollapseIcon open={monitorOpen} /></button>{monitorOpen && <div className="px-4 pb-4 space-y-3"><div className="grid grid-cols-1 md:grid-cols-3 gap-2"><select value={templateId} onChange={(event) => setTemplateId(event.target.value)} className="field"><option value="">选择策略</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}</select><input value={symbol} onChange={(event) => setSymbol(event.target.value)} placeholder="标的代码，如 RB0" className="field" /><input value={symbolName} onChange={(event) => setSymbolName(event.target.value)} placeholder="标的名称（可选）" className="field" /></div><div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-secondary)]"><span>触发事件</span>{['entry', 'exit', 'stop_loss', 'take_profit'].map((event) => <label key={event} className="inline-flex items-center gap-1.5"><input type="checkbox" checked={eventTypes.includes(event)} onChange={() => toggleEvent(event)} className="accent-[var(--accent)]" />{EVENT_LABEL[event]}</label>)}</div><div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-2"><ChannelPicker channels={channels} value={monitorChannelIds} onChange={setMonitorChannelIds} /><button type="button" disabled={busy || !activeTemplate || !symbol.trim()} onClick={() => void addMonitor()} className="action-primary">保存监控</button></div></div>}</section>{monitors.map((monitor) => <div key={monitor.id} className="px-4 py-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] flex items-center gap-3"><button type="button" onClick={() => void updateStrategyMonitor(monitor.id, { enabled: !monitor.enabled }).then((next) => setMonitors((items) => items.map((item) => item.id === next.id ? next : item)))} className={`w-8 h-4 rounded-full p-0.5 shrink-0 ${monitor.enabled ? 'bg-[var(--accent)]' : 'bg-[var(--bg-tertiary)]'}`}><span className={`block w-3 h-3 rounded-full bg-white ${monitor.enabled ? 'translate-x-4' : ''}`} /></button><div className="min-w-0 flex-1"><div className="text-[12px] font-medium">{monitor.template_name} · {monitor.symbol_name || monitor.symbol}</div><div className="text-[10px] text-[var(--text-muted)] mt-1">{monitor.timeframe} · {monitor.enabled ? '运行中' : '已停用'} · 触发：{(monitor.event_types || []).map((event) => EVENT_LABEL[event]).join('、')} · {monitor.channel_ids.length ? monitor.channel_ids.map((id) => channels.find((channel) => channel.id === id)?.name).filter(Boolean).join('、') : '未选择渠道'}</div></div><button type="button" onClick={() => void deleteStrategyMonitor(monitor.id).then(() => setMonitors((items) => items.filter((item) => item.id !== monitor.id)))} className="icon-button" aria-label="删除监控">×</button></div>)}</div>
      <div className="space-y-4"><section className="rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)]"><button type="button" onClick={() => setScreenerOpen((value) => !value)} className="w-full px-4 py-3 flex items-center justify-between"><div className="text-left"><h2 className="text-[12px] font-semibold">定时策略选股</h2><p className="text-[10px] text-[var(--text-muted)] mt-1">任务完成后发送命中结果和执行状态</p></div><CollapseIcon open={screenerOpen} /></button>{screenerOpen && <div className="px-4 pb-4 space-y-3"><select value={templateId} onChange={(event) => setTemplateId(event.target.value)} className="field"><option value="">选择策略</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}</select><div className="grid grid-cols-2 gap-2"><select value={screenMarket} onChange={(event) => setScreenMarket(event.target.value as 'stock' | 'futures')} className="field"><option value="stock">沪深 A 股</option><option value="futures">期货</option></select><input type="number" min="1" max="500" value={screenLimit} onChange={(event) => setScreenLimit(Number(event.target.value))} className="field" aria-label="扫描数量" /></div><div className="grid grid-cols-2 gap-2"><label className="text-[10px] text-[var(--text-muted)]">执行时间<input type="time" value={screenTime} onChange={(event) => setScreenTime(event.target.value)} className="field mt-1" /></label><div><span className="text-[10px] text-[var(--text-muted)]">推送渠道</span><ChannelPicker channels={channels} value={screenChannelIds} onChange={setScreenChannelIds} /></div></div><div className="flex items-center gap-1.5"><span className="text-[10px] text-[var(--text-muted)]">执行日</span>{WEEKDAYS.map((day, index) => <button type="button" key={day} onClick={() => toggleDay(index + 1, screenDays, setScreenDays)} className={`w-6 h-6 rounded-full border text-[10px] ${screenDays.includes(index + 1) ? 'border-[var(--accent)] text-[var(--accent)] bg-[rgba(108,140,255,.12)]' : 'border-[var(--border-primary)] text-[var(--text-muted)]'}`}>{day}</button>)}</div><button type="button" disabled={busy || !activeTemplate} onClick={() => void addScreenerSchedule()} className="action-primary w-full">保存并启用选股任务</button></div>}</section>{schedules.map((schedule) => <div key={schedule.id} className="px-4 py-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)]"><div className="flex items-center gap-3"><span className={`w-1.5 h-1.5 rounded-full ${schedule.enabled ? 'bg-[var(--accent-green)]' : 'bg-[var(--text-muted)]'}`} /><div className="flex-1 min-w-0"><div className="text-[12px] font-medium">{schedule.template_name} · {schedule.market === 'stock' ? '沪深 A 股' : '期货'}</div><div className="text-[10px] text-[var(--text-muted)] mt-1">每周{daysText(schedule.schedule_weekdays)} {schedule.schedule_time} · 前 {schedule.universe_limit} 个 · {channelNames(schedule.channel_ids)}</div>{schedule.last_error && <div className="text-[10px] text-[var(--accent-red)] mt-1">上次失败：{schedule.last_error}</div>}</div><button type="button" onClick={() => void updateScreenerSchedule(schedule.id, { enabled: !schedule.enabled }).then((next) => setSchedules((items) => items.map((item) => item.id === next.id ? next : item)))} className="text-[10px] text-[var(--text-muted)]">{schedule.enabled ? '停用' : '启用'}</button><button type="button" onClick={() => void deleteScreenerSchedule(schedule.id).then(() => setSchedules((items) => items.filter((item) => item.id !== schedule.id)))} className="icon-button" aria-label="删除选股任务">×</button></div><div className="text-[10px] text-[var(--text-muted)] mt-2">{schedule.last_run_at ? `上次执行：${new Date(schedule.last_run_at).toLocaleString('zh-CN')}` : '尚未执行'} · 命中 {schedule.last_result_count} 个</div></div>)}</div>
    </div>}
  </div></div>
}
