import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { login, register } from '../api/auth.ts'
import { LoginScreen } from './LoginScreen.tsx'

vi.mock('../api/auth.ts', () => ({
  login: vi.fn(),
  register: vi.fn(),
}))

const baseUser = {
  id: 1, username: 'reader', display_name: '读者', enabled: true, status: 'active' as const,
  role_codes: ['researcher'], permission_codes: ['private.access'], modules: [],
}

describe('LoginScreen 注册审核', () => {
  beforeEach(() => {
    vi.mocked(login).mockReset()
    vi.mocked(register).mockReset()
  })

  it('注册成功后停在等待审核页，不进入工作区', async () => {
    const onAuthenticated = vi.fn()
    vi.mocked(register).mockResolvedValue({
      status: 'pending',
      message: '注册已提交，请等待管理员审核通过后登录',
      username: 'newbie',
      display_name: '新用户',
    })

    render(<LoginScreen onAuthenticated={onAuthenticated} />)

    fireEvent.click(screen.getByText('还没有账户？创建账户'))
    fireEvent.change(screen.getByPlaceholderText('用于界面展示'), { target: { value: '新用户' } })
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'newbie' } })
    fireEvent.change(screen.getByPlaceholderText('至少 8 位'), { target: { value: 'Probe12345!' } })
    fireEvent.click(screen.getByRole('button', { name: '提交注册申请' }))

    expect(await screen.findByText('等待管理员审核')).toBeInTheDocument()
    expect(screen.getByText('注册已提交，请等待管理员审核通过后登录')).toBeInTheDocument()
    expect(screen.getByText('待审核')).toBeInTheDocument()
    // 关键：注册不再直接把人送进工作区
    expect(onAuthenticated).not.toHaveBeenCalled()
  })

  it('等待审核页可以退回登录', async () => {
    vi.mocked(register).mockResolvedValue({
      status: 'pending', message: '等待审核', username: 'newbie', display_name: '新用户',
    })

    render(<LoginScreen onAuthenticated={vi.fn()} />)
    fireEvent.click(screen.getByText('还没有账户？创建账户'))
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'newbie' } })
    fireEvent.change(screen.getByPlaceholderText('至少 8 位'), { target: { value: 'Probe12345!' } })
    fireEvent.click(screen.getByRole('button', { name: '提交注册申请' }))
    await screen.findByText('等待管理员审核')

    fireEvent.click(screen.getByRole('button', { name: '返回登录' }))

    expect(screen.getByRole('button', { name: '登录' })).toBeInTheDocument()
  })

  it('登录被拒时原样显示后端给出的审核原因', async () => {
    vi.mocked(login).mockRejectedValue(new Error('账号审核未通过，请联系管理员'))

    render(<LoginScreen onAuthenticated={vi.fn()} />)
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'rejected_user' } })
    fireEvent.change(screen.getByPlaceholderText('请输入密码'), { target: { value: 'Probe12345!' } })
    fireEvent.click(screen.getByRole('button', { name: '登录' }))

    // 不能退化成"用户名或密码错误"：否则用户无法判断是在等审核还是密码错了
    expect(await screen.findByText('账号审核未通过，请联系管理员')).toBeInTheDocument()
  })

  it('登录成功才回调 onAuthenticated', async () => {
    const onAuthenticated = vi.fn()
    vi.mocked(login).mockResolvedValue(baseUser)

    render(<LoginScreen onAuthenticated={onAuthenticated} />)
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'reader' } })
    fireEvent.change(screen.getByPlaceholderText('请输入密码'), { target: { value: 'Probe12345!' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '登录' }))
    })

    expect(onAuthenticated).toHaveBeenCalledWith(baseUser)
  })
})
