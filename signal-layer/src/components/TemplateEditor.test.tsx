import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createTemplate } from '../api/template.ts'
import { fetchIndicatorList } from '../api/indicator.ts'
import { TemplateEditor } from './TemplateEditor.tsx'

vi.mock('../api/template.ts', () => ({
  createTemplate: vi.fn(),
  updateTemplate: vi.fn(),
}))
vi.mock('../api/indicator.ts', () => ({
  fetchIndicatorList: vi.fn(),
}))

const created = {
  id: 'tpl_new', name: '测试策略', logic: 'AND' as const, conditionGroups: [],
  primaryTimeframeId: '30m', secondaryTimeframeIds: ['5m'],
  createdAt: 1, updatedAt: 1, enabled: true,
}

/** 渲染并放掉 fetchIndicatorList 的 promise，避免 act 警告 */
async function renderEditor() {
  render(<TemplateEditor onClose={vi.fn()} />)
  await act(async () => { await Promise.resolve() })
}

describe('TemplateEditor 周期设置', () => {
  beforeEach(() => {
    vi.mocked(fetchIndicatorList).mockResolvedValue([])
    vi.mocked(createTemplate).mockReset()
    vi.mocked(createTemplate).mockResolvedValue(created)
  })

  it('保存时带上所选的主周期与次级周期', async () => {
    await renderEditor()

    fireEvent.change(screen.getByLabelText('策略名称'), { target: { value: '测试策略' } })
    fireEvent.change(screen.getByLabelText('主周期'), { target: { value: '30m' } })
    // 次级周期只能选比主周期更细的：5分钟可以
    fireEvent.click(screen.getByRole('button', { name: '5分钟' }))
    fireEvent.click(screen.getByRole('button', { name: '保存策略' }))
    await act(async () => { await Promise.resolve() })

    const payload = await vi.mocked(createTemplate).mock.calls[0]?.[0]
    expect(payload?.primaryTimeframeId).toBe('30m')
    expect(payload?.secondaryTimeframeIds).toEqual(['5m'])
  })

  it('次级周期只允许选比主周期更细的级别', async () => {
    await renderEditor()

    // 主周期 30分钟：更粗的日线/60分钟与同级的 30分钟 都不可选
    fireEvent.change(screen.getByLabelText('主周期'), { target: { value: '30m' } })
    expect(screen.getByRole('button', { name: '日线' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '60分钟' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '30分钟' })).toBeDisabled()
    // 更细的 15分钟/5分钟 可选
    expect(screen.getByRole('button', { name: '15分钟' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '5分钟' })).toBeEnabled()
  })

  it('主周期是最细的 5分钟时没有可选的次级周期', async () => {
    await renderEditor()

    fireEvent.change(screen.getByLabelText('主周期'), { target: { value: '5m' } })

    for (const label of ['日线', '60分钟', '30分钟', '15分钟', '5分钟']) {
      expect(screen.getByRole('button', { name: label })).toBeDisabled()
    }
  })

  it('主周期改粗后，不再比它更细的次级周期会被剔除', async () => {
    await renderEditor()

    fireEvent.change(screen.getByLabelText('策略名称'), { target: { value: '测试策略' } })
    // 主周期日线时把 30分钟 选为次级
    fireEvent.click(screen.getByRole('button', { name: '30分钟' }))
    expect(screen.getByRole('button', { name: '30分钟' })).toHaveAttribute('aria-pressed', 'true')

    // 主周期改成 15分钟 后，30分钟 已不比主周期更细，应自动取消
    fireEvent.change(screen.getByLabelText('主周期'), { target: { value: '15m' } })
    expect(screen.getByRole('button', { name: '30分钟' })).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(screen.getByRole('button', { name: '保存策略' }))
    await act(async () => { await Promise.resolve() })

    expect(await vi.mocked(createTemplate).mock.calls[0]?.[0]).toMatchObject({
      primaryTimeframeId: '15m',
      secondaryTimeframeIds: [],
    })
  })
})
