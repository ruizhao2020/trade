import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { fetchIndicatorList } from '../api/indicator.ts'
import type { ChanRenderOptions, IndicatorInfo } from '../core/types.ts'
import { IndicatorWorkbenchToolbar } from './IndicatorWorkbenchToolbar.tsx'

vi.mock('../api/indicator.ts', () => ({ fetchIndicatorList: vi.fn() }))

const ZONE: IndicatorInfo = {
  type: 'liquidity_zone',
  name: '流动性聚集区',
  description: '',
  default_params: { span: 5, atr_len: 14, eq_atr: 0.35, min_touches: 2, max_zones: 4 },
  render: { window: 'main', plots: [], markers: [] },
  outputs: [],
}

const CHAN_OPTIONS: ChanRenderOptions = {
  showFenxing: false, showBi: false, showDuan: false, showZhongshu: false,
  showBuySellPoints: false, showDivergences: false, showZhongshuAxis: false, zsLevel: 'bi',
}

function renderToolbar() {
  return render(
    <IndicatorWorkbenchToolbar
      selectedIndicators={[{ type: 'liquidity_zone', params: { ...ZONE.default_params }, window: 'main' }]}
      onIndicatorChange={vi.fn()}
      chanOptions={CHAN_OPTIONS}
      onChanChange={vi.fn()}
      visibleChanFeatures={[]}
      chanFeatureLabels={{}}
    />,
  )
}

describe('流动性聚集区的参数面板', () => {
  it('选中后显示三种状态的图例，且能弹出完整状态图示', async () => {
    vi.mocked(fetchIndicatorList).mockResolvedValue([ZONE])
    renderToolbar()

    // 切到该指标（点指标条）
    fireEvent.click(await screen.findByRole('button', { name: '流动性聚集区' }))

    // 紧凑图例：三种方框形态各自有可读名称
    expect(await screen.findByRole('img', { name: '聚集中的方框：实线 + 填满' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '被扫荡的方框：虚线 + 填充按剩余比例递减' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '完全扫荡的方框：虚线 + 不填充' })).toBeInTheDocument()

    // 信息图标 → 弹出完整图示
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '聚集区状态图示' }))
    const tooltip = screen.getByRole('tooltip')
    expect(tooltip).toBeInTheDocument()
    expect(screen.getByText('生成 → 聚集')).toBeInTheDocument()
    expect(screen.getByText(/填充比例 = 1 − 越界幅度 ÷ 区带高度/)).toBeInTheDocument()
  })

  it('每个参数旁都有信息图标，点击弹出该参数的含义', async () => {
    vi.mocked(fetchIndicatorList).mockResolvedValue([ZONE])
    renderToolbar()
    fireEvent.click(await screen.findByRole('button', { name: '流动性聚集区' }))

    // 参数面板里的每个参数都应有说明按钮（参数名取自 PARAM_LABELS）
    // 参数标签必须是中文，不能把英文 key 直接摆到界面上
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '摆动窗口说明' })).toBeInTheDocument()
    })
    for (const label of ['摆动窗口说明', 'ATR周期说明', '等高容差说明', '最少触碰说明', '最大方框数说明']) {
      expect(screen.getByRole('button', { name: label }), `${label} 缺失`).toBeInTheDocument()
    }

    fireEvent.click(screen.getByRole('button', { name: '等高容差说明' }))
    expect(screen.getByRole('tooltip')).toHaveTextContent(/等高\/等低容差 = ATR × 这个倍数/)
    expect(screen.getByRole('tooltip')).toHaveTextContent(/精确相等几乎不出现/)
  })

  it('流动性扫荡反转：显示 SSL/BSL 图例，点开是含义解释', async () => {
    vi.mocked(fetchIndicatorList).mockResolvedValue([
      { ...ZONE, type: 'liquidity_sweep', name: '流动性扫荡反转', default_params: { piv_len: 8, atr_len: 14 } },
    ])
    render(
      <IndicatorWorkbenchToolbar
        selectedIndicators={[{ type: 'liquidity_sweep', params: { piv_len: 8, atr_len: 14 }, window: 'main' }]}
        onIndicatorChange={vi.fn()}
        chanOptions={CHAN_OPTIONS}
        onChanChange={vi.fn()}
        visibleChanFeatures={[]}
        chanFeatureLabels={{}}
      />,
    )

    fireEvent.click(await screen.findByRole('button', { name: '流动性扫荡反转' }))
    // 图上标记写着英文缩写，参数行里要能直接读到它们的含义
    expect(await screen.findByRole('img', { name: 'SSL SWEEP：卖方流动性被扫，看涨' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'BSL SWEEP：买方流动性被扫，看跌' })).toBeInTheDocument()

    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'SSL / BSL 含义说明' }))
    const tooltip = screen.getByRole('tooltip')
    expect(tooltip).toHaveTextContent('卖方流动性')
    expect(tooltip).toHaveTextContent('买方流动性')
    expect(tooltip).toHaveTextContent('看涨反转')
    expect(tooltip).toHaveTextContent('看跌反转')
  })

  it('其他指标不显示聚集区图例', async () => {
    vi.mocked(fetchIndicatorList).mockResolvedValue([
      { ...ZONE, type: 'macd', name: 'MACD', default_params: { fast: 12, slow: 26, signal: 9 } },
    ])
    render(
      <IndicatorWorkbenchToolbar
        selectedIndicators={[{ type: 'macd', params: { fast: 12, slow: 26, signal: 9 }, window: 'sub' }]}
        onIndicatorChange={vi.fn()}
        chanOptions={CHAN_OPTIONS}
        onChanChange={vi.fn()}
        visibleChanFeatures={[]}
        chanFeatureLabels={{}}
      />,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'MACD' }))
    expect(screen.queryByRole('img', { name: '聚集中的方框：实线 + 填满' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '聚集区状态图示' })).not.toBeInTheDocument()
  })
})
