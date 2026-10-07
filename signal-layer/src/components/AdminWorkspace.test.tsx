import { render, screen } from '@testing-library/react'
import { fireEvent } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AuthUser } from '../api/auth.ts'
import { approveUser, deleteUser, fetchModules, fetchPermissions, fetchRoles, fetchUsers, fetchNotificationChannelsForAdmin, fetchNotificationTemplatesForAdmin, fetchPublicIndicatorPolicies, fetchPublicIndicatorFeaturePolicies, fetchIndicatorRuntimeSettings, rejectUser } from '../api/admin.ts'
import { AdminWorkspace } from './AdminWorkspace.tsx'

vi.mock('../api/admin.ts', () => ({
  fetchUsers: vi.fn(), fetchRoles: vi.fn(), fetchModules: vi.fn(), fetchPermissions: vi.fn(),
  fetchNotificationChannelsForAdmin: vi.fn(), fetchNotificationTemplatesForAdmin: vi.fn(),
  fetchPublicIndicatorPolicies: vi.fn(), fetchPublicIndicatorFeaturePolicies: vi.fn(),
  fetchIndicatorRuntimeSettings: vi.fn(), approveUser: vi.fn(), rejectUser: vi.fn(), deleteUser: vi.fn(),
  createModule: vi.fn(), createRole: vi.fn(), updateModule: vi.fn(), updateRole: vi.fn(),
  updateUserRoles: vi.fn(), createNotificationChannelForAdmin: vi.fn(),
  updateNotificationChannelForAdmin: vi.fn(), deleteNotificationChannelForAdmin: vi.fn(),
  updateNotificationTemplateForAdmin: vi.fn(), updatePublicIndicatorPolicy: vi.fn(),
  updatePublicIndicatorFeaturePolicy: vi.fn(), createPublicIndicatorFeaturePolicy: vi.fn(),
  updateIndicatorRuntimeSettings: vi.fn(),
}))

const admin: AuthUser = {
  id: 1, username: 'admin', display_name: '系统管理员', enabled: true, status: 'active',
  role_codes: ['admin'], permission_codes: ['admin.users'], modules: [],
}

function user(overrides: Partial<AuthUser>): AuthUser {
  return {
    id: 2, username: 'newbie', display_name: '新用户', enabled: true, status: 'pending',
    role_codes: ['member'], permission_codes: ['indicators.view'], modules: [], ...overrides,
  }
}

describe('系统管理 · 用户审核', () => {
  let confirmSpy: ReturnType<typeof vi.fn>
  beforeEach(() => {
    vi.mocked(fetchRoles).mockResolvedValue([
      { id: 1, code: 'admin', name: '管理员', description: '', built_in: true, enabled: true, registration_default: false, permission_codes: [] },
      { id: 2, code: 'member', name: '普通用户', description: '', built_in: true, enabled: true, registration_default: true, permission_codes: [] },
      { id: 3, code: 'researcher', name: '研究用户', description: '', built_in: true, enabled: true, registration_default: false, permission_codes: [] },
    ])
    vi.mocked(fetchModules).mockResolvedValue([])
    vi.mocked(fetchPermissions).mockResolvedValue([])
    vi.mocked(fetchNotificationChannelsForAdmin).mockResolvedValue([])
    vi.mocked(fetchNotificationTemplatesForAdmin).mockResolvedValue([])
    vi.mocked(fetchPublicIndicatorPolicies).mockResolvedValue([])
    vi.mocked(fetchPublicIndicatorFeaturePolicies).mockResolvedValue([])
    vi.mocked(fetchIndicatorRuntimeSettings).mockResolvedValue({ divergence_power_ratio: 0.7 })
    vi.mocked(approveUser).mockReset()
    vi.mocked(rejectUser).mockReset()
    vi.mocked(deleteUser).mockReset()
    // happy-dom 不提供 window.confirm，需要显式装上。
    confirmSpy = vi.fn().mockReturnValue(true)
    vi.stubGlobal('confirm', confirmSpy)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('待审核用户排在最前并标出状态', async () => {
    vi.mocked(fetchUsers).mockResolvedValue([
      user({ id: 3, username: 'old_active', display_name: '老用户', status: 'active', role_codes: ['researcher'] }),
      user({ id: 4, username: 'waiting', display_name: '待审者' }),
    ])

    render(<AdminWorkspace currentUser={admin} onModulesChanged={vi.fn()} />)

    const names = await screen.findAllByText(/老用户|待审者/)
    expect(names[0]).toHaveTextContent('待审者')
    expect(screen.getByText('待审核')).toBeInTheDocument()
    expect(screen.getByText('1 待审核')).toBeInTheDocument()
  })

  it('点通过调用审核接口并更新该行状态', async () => {
    vi.mocked(fetchUsers).mockResolvedValue([user({ id: 4, username: 'waiting', display_name: '待审者' })])
    vi.mocked(approveUser).mockResolvedValue(
      user({ id: 4, username: 'waiting', display_name: '待审者', status: 'active', role_codes: ['researcher'] }),
    )

    render(<AdminWorkspace currentUser={admin} onModulesChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: '通过' }))

    expect(approveUser).toHaveBeenCalledWith(4)
    // 通过后该行不再有待审按钮，状态变成已通过
    await screen.findByText('已通过')
    expect(screen.queryByRole('button', { name: '拒绝' })).not.toBeInTheDocument()
  })

  it('点拒绝调用拒绝接口', async () => {
    vi.mocked(fetchUsers).mockResolvedValue([user({ id: 4, username: 'waiting', display_name: '待审者' })])
    vi.mocked(rejectUser).mockResolvedValue(
      user({ id: 4, username: 'waiting', display_name: '待审者', status: 'rejected' }),
    )

    render(<AdminWorkspace currentUser={admin} onModulesChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: '拒绝' }))

    expect(rejectUser).toHaveBeenCalledWith(4)
    await screen.findByText('已拒绝')
  })

  it('待审核行提示需要授予含私有权限的角色', async () => {
    vi.mocked(fetchUsers).mockResolvedValue([user({ id: 4, username: 'waiting', display_name: '待审者' })])

    render(<AdminWorkspace currentUser={admin} onModulesChanged={vi.fn()} />)

    expect(await screen.findByText(/否则登录后只能看到公开的指标页/)).toBeInTheDocument()
  })
})

describe('系统管理 · 删除用户', () => {
  let confirmSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.mocked(fetchRoles).mockResolvedValue([
      { id: 2, code: 'member', name: '普通用户', description: '', built_in: true, enabled: true, registration_default: true, permission_codes: [] },
    ])
    vi.mocked(fetchModules).mockResolvedValue([])
    vi.mocked(fetchPermissions).mockResolvedValue([])
    vi.mocked(fetchNotificationChannelsForAdmin).mockResolvedValue([])
    vi.mocked(fetchNotificationTemplatesForAdmin).mockResolvedValue([])
    vi.mocked(fetchPublicIndicatorPolicies).mockResolvedValue([])
    vi.mocked(fetchPublicIndicatorFeaturePolicies).mockResolvedValue([])
    vi.mocked(fetchIndicatorRuntimeSettings).mockResolvedValue({ divergence_power_ratio: 0.7 })
    vi.mocked(deleteUser).mockReset()
    confirmSpy = vi.fn().mockReturnValue(true)
    vi.stubGlobal('confirm', confirmSpy)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('确认后调用删除接口并把该行移出列表', async () => {
    vi.mocked(fetchUsers).mockResolvedValue([
      user({ id: 4, username: 'doomed', display_name: '待删用户', status: 'active', role_codes: ['member'] }),
    ])
    vi.mocked(deleteUser).mockResolvedValue(undefined)

    render(<AdminWorkspace currentUser={admin} onModulesChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: '删除用户 doomed' }))

    await vi.waitFor(() => expect(deleteUser).toHaveBeenCalledWith(4))
    await vi.waitFor(() => expect(screen.queryByText('待删用户')).not.toBeInTheDocument())
  })

  it('确认框里说明了会连带删除的数据，并提示改用停用', async () => {
    vi.mocked(fetchUsers).mockResolvedValue([
      user({ id: 4, username: 'doomed', display_name: '待删用户', status: 'active', role_codes: ['member'] }),
    ])

    render(<AdminWorkspace currentUser={admin} onModulesChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: '删除用户 doomed' }))

    const message = confirmSpy.mock.calls[0][0] as string
    expect(message).toContain('@doomed')
    expect(message).toContain('无法恢复')
    expect(message).toContain('启用开关')
  })

  it('取消确认时不调用删除接口', async () => {
    vi.mocked(fetchUsers).mockResolvedValue([
      user({ id: 4, username: 'doomed', display_name: '待删用户', status: 'active', role_codes: ['member'] }),
    ])
    confirmSpy.mockReturnValue(false)

    render(<AdminWorkspace currentUser={admin} onModulesChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: '删除用户 doomed' }))

    expect(deleteUser).not.toHaveBeenCalled()
    expect(screen.getByText('待删用户')).toBeInTheDocument()
  })

  it('自己那一行没有删除按钮，保留启用开关', async () => {
    vi.mocked(fetchUsers).mockResolvedValue([
      user({ id: 1, username: 'admin', display_name: '系统管理员', status: 'active', role_codes: ['admin'] }),
    ])

    render(<AdminWorkspace currentUser={admin} onModulesChanged={vi.fn()} />)

    await screen.findByText('系统管理员')
    expect(screen.queryByRole('button', { name: /删除用户/ })).not.toBeInTheDocument()
    // 停用能力仍在（当前用户显示为只读状态文字）
    expect(screen.getByText('已启用')).toBeInTheDocument()
  })

  it('删除失败时显示服务端原因', async () => {
    vi.mocked(fetchUsers).mockResolvedValue([
      user({ id: 4, username: 'doomed', display_name: '待删用户', status: 'active', role_codes: ['member'] }),
    ])
    vi.mocked(deleteUser).mockRejectedValue(new Error('不能删除最后一个管理员'))

    render(<AdminWorkspace currentUser={admin} onModulesChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: '删除用户 doomed' }))

    expect(await screen.findByText('不能删除最后一个管理员')).toBeInTheDocument()
    expect(screen.getByText('待删用户')).toBeInTheDocument()
  })
})
