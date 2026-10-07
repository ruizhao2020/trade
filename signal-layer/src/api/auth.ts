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
  public_access: boolean
}

/** 准入审核状态：pending 待审核 / active 已通过 / rejected 已拒绝。 */
export type UserStatus = 'pending' | 'active' | 'rejected'

export const USER_STATUS_LABEL: Record<UserStatus, string> = {
  pending: '待审核',
  active: '已通过',
  rejected: '已拒绝',
}

export interface AuthUser {
  id: number
  username: string
  email?: string
  display_name: string
  enabled: boolean
  status: UserStatus
  created_at?: string
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

/** 注册结果：不再直接下发令牌，账号需管理员审核通过后才能登录。 */
export interface RegisterResult {
  status: UserStatus
  message: string
  username: string
  display_name: string
}

export async function login(username: string, password: string) {
  const result = await api.post<TokenResponse>('/auth/login', { username, password })
  setAccessToken(result.access_token)
  return result.user
}

export async function register(username: string, password: string, displayName: string) {
  return api.post<RegisterResult>('/auth/register', {
    username,
    password,
    display_name: displayName,
  })
}

export const fetchCurrentUser = () => api.get<AuthUser>('/auth/me')
export const logout = () => setAccessToken(null)
export const changePassword = (currentPassword: string, newPassword: string) =>
  api.put<void>('/auth/password', { current_password: currentPassword, new_password: newPassword })
