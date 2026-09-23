import { api } from './client.ts'
import type { AuthModule, AuthUser } from './auth.ts'

export interface PermissionItem {
  id: number
  code: string
  name: string
  description: string
  module_code?: string
}

export interface RoleItem {
  id: number
  code: string
  name: string
  description: string
  built_in: boolean
  enabled: boolean
  registration_default: boolean
  permission_codes: string[]
}

export const fetchUsers = () => api.get<AuthUser[]>('/admin/users')
export const fetchRoles = () => api.get<RoleItem[]>('/admin/roles')
export const fetchModules = () => api.get<AuthModule[]>('/admin/modules')
export const fetchPermissions = () => api.get<PermissionItem[]>('/admin/permissions')

export const updateUserRoles = (userId: number, roleCodes: string[], enabled: boolean) =>
  api.put<AuthUser>(`/admin/users/${userId}/roles`, { role_codes: roleCodes, enabled })

export const updateRole = (roleId: number, values: Partial<RoleItem>) =>
  api.put<RoleItem>(`/admin/roles/${roleId}`, values)

export const createRole = (values: { code: string; name: string; description: string; registration_default?: boolean }) =>
  api.post<RoleItem>('/admin/roles', { ...values, permission_codes: [], enabled: true, registration_default: values.registration_default ?? false })

export const updateModule = (moduleId: number, values: Partial<AuthModule>) =>
  api.put<AuthModule>(`/admin/modules/${moduleId}`, values)

export const createModule = (values: { code: string; name: string; component_key: string; icon: string }) =>
  api.post<AuthModule>('/admin/modules', { ...values, route_path: `/${values.code}`, api_prefixes: `/api/v1/${values.code}`, api_permission: `${values.code}.view`, sort_order: 50, enabled: true, visible: true, public_access: false })

export interface AdminNotificationChannel {
  id: number
  name: string
  channel_type: 'browser' | 'wecom' | 'feishu'
  webhook_url_masked?: string | null
  enabled: boolean
  is_shared: boolean
  can_manage: boolean
}

export interface AdminNotificationTemplate {
  id: number
  event_type: string
  name: string
  content: string
  enabled: boolean
}

export const fetchNotificationChannelsForAdmin = () => api.get<AdminNotificationChannel[]>('/notifications/admin/channels')
export const createNotificationChannelForAdmin = (values: { name: string; channel_type: 'browser' | 'wecom' | 'feishu'; webhook_url?: string; enabled?: boolean; is_shared?: boolean }) => api.post<AdminNotificationChannel>('/notifications/admin/channels', values)
export const updateNotificationChannelForAdmin = (id: number, values: { name?: string; webhook_url?: string; enabled?: boolean }) => api.put<AdminNotificationChannel>(`/notifications/admin/channels/${id}`, values)
export const deleteNotificationChannelForAdmin = (id: number) => api.delete(`/notifications/admin/channels/${id}`)
export const fetchNotificationTemplatesForAdmin = () => api.get<AdminNotificationTemplate[]>('/notifications/admin/templates')
export const updateNotificationTemplateForAdmin = (id: number, values: { name?: string; content?: string; enabled?: boolean }) => api.put<AdminNotificationTemplate>(`/notifications/admin/templates/${id}`, values)

export interface PublicIndicatorPolicy {
  id: number
  indicator_type: string
  display_name: string
  public_visible: boolean
  show_parameters: boolean
  show_details: boolean
  show_markers: boolean
  sort_order: number
}

export interface PublicIndicatorFeaturePolicy {
  id: number
  indicator_type: string
  feature_code: string
  display_name: string
  public_visible: boolean
  show_details: boolean
  sort_order: number
}

export const fetchPublicIndicatorPolicies = () => api.get<PublicIndicatorPolicy[]>('/admin/public-indicators')
export const updatePublicIndicatorPolicy = (id: number, values: Partial<PublicIndicatorPolicy>) => api.put<PublicIndicatorPolicy>(`/admin/public-indicators/${id}`, values)
export const fetchPublicIndicatorFeaturePolicies = () => api.get<PublicIndicatorFeaturePolicy[]>('/admin/public-indicator-features')
export const createPublicIndicatorFeaturePolicy = (values: { indicator_type: string; feature_code: string; display_name: string; public_visible?: boolean; show_details?: boolean; sort_order?: number }) => api.post<PublicIndicatorFeaturePolicy>('/admin/public-indicator-features', values)
export const updatePublicIndicatorFeaturePolicy = (id: number, values: Partial<PublicIndicatorFeaturePolicy>) => api.put<PublicIndicatorFeaturePolicy>(`/admin/public-indicator-features/${id}`, values)

export interface IndicatorRuntimeSettings {
  divergence_power_ratio: number
}

export const fetchIndicatorRuntimeSettings = () => api.get<IndicatorRuntimeSettings>('/admin/indicator-settings')
export const updateIndicatorRuntimeSettings = (values: IndicatorRuntimeSettings) => api.put<IndicatorRuntimeSettings>('/admin/indicator-settings', values)
