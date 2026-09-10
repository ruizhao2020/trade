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

export const createRole = (values: { code: string; name: string; description: string }) =>
  api.post<RoleItem>('/admin/roles', { ...values, permission_codes: [], enabled: true })

export const updateModule = (moduleId: number, values: Partial<AuthModule>) =>
  api.put<AuthModule>(`/admin/modules/${moduleId}`, values)

export const createModule = (values: { code: string; name: string; component_key: string; icon: string }) =>
  api.post<AuthModule>('/admin/modules', { ...values, route_path: `/${values.code}`, api_prefixes: `/api/v1/${values.code}`, api_permission: `${values.code}.view`, sort_order: 50, enabled: true, visible: true })
