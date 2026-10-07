import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ZoneStateDiagram, ZoneStateSwatch } from './ZoneStateDiagram.tsx'

describe('流动性聚集区状态图示', () => {
  it('完整图示把三种状态都标出来', () => {
    render(<ZoneStateDiagram />)

    const diagram = screen.getByRole('img', { name: /填充表示流动性还在/ })
    expect(diagram).toBeInTheDocument()
    // 三个阶段说明必须都在图上，缺一个用户就读不懂虚线框了
    expect(screen.getByText('生成 → 聚集')).toBeInTheDocument()
    expect(screen.getByText('被扫荡（部分）')).toBeInTheDocument()
    expect(screen.getByText('消失（完全扫荡）')).toBeInTheDocument()
    // 核心是"填充＝还在、扫荡后抽空"，这三行是这张图要传达的内容
    expect(screen.getByText('实线框 + 填满')).toBeInTheDocument()
    expect(screen.getByText('虚线 + 填充递减')).toBeInTheDocument()
    expect(screen.getByText('虚线 + 不填充')).toBeInTheDocument()
    expect(screen.getByText(/填充比例 = 1 − 越界幅度 ÷ 区带高度/)).toBeInTheDocument()
    expect(screen.getByText(/方框右边界停在被扫荡那一刻/)).toBeInTheDocument()
  })

  it('紧凑图例的三种形态各自有可读的说明', () => {
    render(
      <div>
        <ZoneStateSwatch state="accumulating" />
        <ZoneStateSwatch state="swept" />
        <ZoneStateSwatch state="gone" />
      </div>,
    )

    expect(screen.getByRole('img', { name: '聚集中的方框：实线 + 填满' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '被扫荡的方框：虚线 + 填充按剩余比例递减' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '完全扫荡的方框：虚线 + 不填充' })).toBeInTheDocument()
  })

  it('聚集填满、部分扫荡留一半多、完全扫荡不填充', () => {
    const { container: accumulating } = render(<ZoneStateSwatch state="accumulating" />)
    // 底色 + 填充 + 实线边框（无 dash）
    expect(accumulating.querySelectorAll('rect')).toHaveLength(3)
    expect(accumulating.querySelector('rect[stroke-dasharray="4 3"]')).toBeNull()

    const { container: swept } = render(<ZoneStateSwatch state="swept" />)
    expect(swept.querySelector('rect[stroke-dasharray="4 3"]')).not.toBeNull()

    // 完全扫荡：只有底色 + 边框，没有填充块
    const { container: gone } = render(<ZoneStateSwatch state="gone" />)
    expect(gone.querySelectorAll('rect')).toHaveLength(2)
    expect(gone.querySelector('rect[stroke-dasharray="4 3"]')).not.toBeNull()
  })
})
