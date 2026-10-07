import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SweepGlossary, SweepSwatch } from './SweepLegend.tsx'

const BULL = '#FF2E93'
const BEAR = '#00E5C0'

describe('SSL / BSL 释义', () => {
  it('紧凑图例两侧都有可读名称，并用调用方给的颜色', () => {
    const { container } = render(
      <div>
        <SweepSwatch side="ssl" color={BULL} />
        <SweepSwatch side="bsl" color={BEAR} />
      </div>,
    )

    expect(screen.getByRole('img', { name: 'SSL SWEEP：卖方流动性被扫，看涨' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'BSL SWEEP：买方流动性被扫，看跌' })).toBeInTheDocument()
    // 颜色必须来自传参（接口的 render.markers），不能组件内部再写死一份
    const fills = Array.from(container.querySelectorAll('path')).map((el) => el.getAttribute('fill'))
    expect(fills).toEqual([BULL, BEAR])
  })

  it('释义图同时画出看涨与看跌两侧', () => {
    render(<SweepGlossary bullColor={BULL} bearColor={BEAR} />)

    expect(screen.getByRole('img', { name: /SSL SWEEP：影线跌破低点后收回，看涨/ })).toBeInTheDocument()
    expect(screen.getByText('SSL SWEEP · 看涨')).toBeInTheDocument()
    expect(screen.getByText('BSL SWEEP · 看跌')).toBeInTheDocument()
    // 虚线标注的"低点/高点"是这张图的关键：流动性就挂在这些水平外侧
    expect(screen.getByText('低点')).toBeInTheDocument()
    expect(screen.getByText('高点')).toBeInTheDocument()
  })

  it('文字解释讲清了"谁挂的单、为什么被扫、为什么反向"', () => {
    const { container } = render(<SweepGlossary bullColor={BULL} bearColor={BEAR} />)
    const text = container.textContent ?? ''

    // 只写"SSL 看涨"等于没解释，这三层必须都在
    expect(text).toMatch(/卖方流动性.*低点下方.*多头止损/)
    expect(text).toMatch(/买方流动性.*高点上方.*空头止损/)
    expect(text).toMatch(/影线越过这些水平.*收盘又回到内侧/)
    expect(text).toMatch(/大资金想建仓.*主动把价格推向/)
    expect(text).toMatch(/SSL 被扫.*看涨反转/)
    expect(text).toMatch(/BSL 被扫.*看跌反转/)
    // 说明标记挂在被扫价位上（这正是改用 marker 的原因）
    expect(text).toMatch(/标记挂在「被扫的那个价位」上/)
    // 正文是纯文本渲染，不能留 Markdown 记号（会原样显示星号）
    expect(text).not.toContain('**')
  })
})
