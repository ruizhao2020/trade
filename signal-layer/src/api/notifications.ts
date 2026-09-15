import { api } from './client'

export type NotificationChannelType = 'browser' | 'wecom' | 'feishu'
export type NotificationEventType = 'entry' | 'exit' | 'stop_loss' | 'take_profit' | 'scheduled' | 'screener_completed' | 'screener_failed'

export interface NotificationChannel {
  id: number
  name: string
  channel_type: NotificationChannelType
  webhook_url_masked?: string | null
  enabled: boolean
  is_shared: boolean
  can_manage: boolean
}

export interface StrategyMonitor {
  id: number
  template_id: string
  template_name: string
  timeframe: string
  symbol: string
  symbol_name: string
  channel_ids: number[]
  enabled: boolean
  poll_interval_seconds: number
  last_checked_at?: string | null
  last_bar_time?: number | null
  in_position: boolean
  entry_price?: number | null
  stop_loss_price?: number | null
  take_profit_price?: number | null
  schedule_enabled: boolean
  schedule_time: string
  schedule_weekdays: number[]
  event_types: string[]
}

export interface NotificationEvent {
  id: number
  monitor_id: number
  event_type: NotificationEventType
  symbol: string
  symbol_name: string
  template_name: string
  timeframe: string
  bar_time: number
  price: number
  title: string
  content: string
  delivery_status: Record<string, string>
  is_read: boolean
  created_at: string
}

export async function fetchNotificationChannels() {
  return api.get<NotificationChannel[]>('/notifications/channels')
}

export async function createNotificationChannel(payload: { name: string; channel_type: NotificationChannelType; webhook_url?: string; enabled?: boolean }) {
  return api.post<NotificationChannel>('/notifications/channels', payload)
}

export async function deleteNotificationChannel(id: number) {
  return api.delete(`/notifications/channels/${id}`)
}

export async function testNotificationChannel(id: number) {
  return api.post<{ status: string }>(`/notifications/channels/${id}/test`, {})
}

export async function fetchAdminNotificationChannels() {
  return api.get<NotificationChannel[]>('/notifications/admin/channels')
}

export async function createAdminNotificationChannel(payload: { name: string; channel_type: NotificationChannelType; webhook_url?: string; enabled?: boolean; is_shared?: boolean }) {
  return api.post<NotificationChannel>('/notifications/admin/channels', payload)
}

export async function updateAdminNotificationChannel(id: number, payload: { name?: string; webhook_url?: string; enabled?: boolean }) {
  return api.put<NotificationChannel>(`/notifications/admin/channels/${id}`, payload)
}

export async function deleteAdminNotificationChannel(id: number) {
  return api.delete(`/notifications/admin/channels/${id}`)
}

export interface NotificationTemplateConfig {
  id: number
  event_type: string
  name: string
  content: string
  enabled: boolean
}

export async function fetchNotificationTemplates() {
  return api.get<NotificationTemplateConfig[]>('/notifications/admin/templates')
}

export async function updateNotificationTemplate(id: number, payload: { name?: string; content?: string; enabled?: boolean }) {
  return api.put<NotificationTemplateConfig>(`/notifications/admin/templates/${id}`, payload)
}

export async function fetchStrategyMonitors() {
  return api.get<StrategyMonitor[]>('/notifications/monitors')
}

export async function createStrategyMonitor(payload: { template_id: string; symbol: string; symbol_name?: string; channel_ids: number[]; event_types?: string[]; poll_interval_seconds?: number; enabled?: boolean; schedule_enabled?: boolean; schedule_time?: string; schedule_weekdays?: number[] }) {
  return api.post<StrategyMonitor>('/notifications/monitors', payload)
}

export async function updateStrategyMonitor(id: number, payload: Partial<Pick<StrategyMonitor, 'enabled' | 'channel_ids' | 'symbol_name' | 'event_types' | 'poll_interval_seconds' | 'schedule_enabled' | 'schedule_time' | 'schedule_weekdays'>> & { reset_position?: boolean }) {
  return api.put<StrategyMonitor>(`/notifications/monitors/${id}`, payload)
}

export async function deleteStrategyMonitor(id: number) {
  return api.delete(`/notifications/monitors/${id}`)
}

export interface ScreenerSchedule {
  id: number
  template_id: string
  template_name: string
  market: 'stock' | 'futures'
  universe_limit: number
  min_progress: number
  schedule_time: string
  schedule_weekdays: number[]
  channel_ids: number[]
  enabled: boolean
  last_run_at?: string | null
  last_result_count: number
  last_error?: string | null
}

export async function fetchScreenerSchedules() {
  return api.get<ScreenerSchedule[]>('/notifications/screener-schedules')
}

export async function createScreenerSchedule(payload: { template_id: string; market: 'stock' | 'futures'; universe_limit: number; min_progress: number; schedule_time: string; schedule_weekdays: number[]; channel_ids: number[]; enabled?: boolean }) {
  return api.post<ScreenerSchedule>('/notifications/screener-schedules', payload)
}

export async function updateScreenerSchedule(id: number, payload: Partial<Pick<ScreenerSchedule, 'market' | 'universe_limit' | 'min_progress' | 'schedule_time' | 'schedule_weekdays' | 'channel_ids' | 'enabled'>>) {
  return api.put<ScreenerSchedule>(`/notifications/screener-schedules/${id}`, payload)
}

export async function deleteScreenerSchedule(id: number) {
  return api.delete(`/notifications/screener-schedules/${id}`)
}

export async function fetchNotificationEvents(unreadOnly = false) {
  return api.get<NotificationEvent[]>('/notifications/events', { unread_only: String(unreadOnly), limit: '100' })
}

export async function markNotificationEventsRead(ids?: number[]) {
  return api.post<{ updated: number }>('/notifications/events/read', { ids: ids ?? null })
}
