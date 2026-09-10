import { api, setAccessToken } from './client.ts'

export interface AuthModule {
  id: number
  code: string
  name: string
  icon: string
  component_key: string
  route_path: string
  api_prefixes: string
  api_permission: string
  sort_order: number
  enabled: boolean
  visible: boolean
}

export interface AuthUser {
  id: number
  username: string
  email?: string
  display_name: string
  enabled: boolean
  role_codes: string[]
  permission_codes: string[]
  modules: AuthModule[]
}

interface TokenResponse {
  access_token: string
  token_type: string
  expires_at: number
  user: AuthUser
}

export async function login(username: string, password: string) {
  const result = await api.post<TokenResponse>('/auth/login', { username, password })
  setAccessToken(result.access_token)
  return result.user
}

export async function register(username: string, password: string, displayName: string) {
  const result = await api.post<TokenResponse>('/auth/register', {
    username,
    password,
    display_name: displayName,
  })
  setAccessToken(result.access_token)
  return result.user
}

export const fetchCurrentUser = () => api.get<AuthUser>('/auth/me')
export const logout = () => setAccessToken(null)
export const changePassword = (currentPassword: string, newPassword: string) =>
  api.put<void>('/auth/password', { current_password: currentPassword, new_password: newPassword })
