import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  Time,
} from 'lightweight-charts'
import type { CanvasRenderingTarget2D } from 'fancy-canvas'
import type { ChanClassification } from '../core/types.ts'

/** 分支画在最后一根 K 线右侧多远（像素）。 */
const BRANCH_LENGTH_PX = 96

export interface ClassificationBranch {
  label: string
  price: number
  color: string
  /** 再往后一层的分类（同样画成路径） */
  children: ClassificationChild[]
}

export interface ClassificationChild {
  label: string
  price: number
  color: string
}

/** 由完全分类结果换算成三条可绘制的分支（价格 + 颜色）。 */
export function buildClassificationBranches(classification: ChanClassification): ClassificationBranch[] {
  const { zhongshuHigh, zhongshuLow } = classification
  if (zhongshuHigh === undefined || zhongshuLow === undefined) return []
  const height = zhongshuHigh - zhongshuLow
  const branches: ClassificationBranch[] = [
    { label: '向上延续', price: zhongshuHigh + height, color: '#ff5b62', children: [] },
    { label: '中枢扩展', price: (zhongshuHigh + zhongshuLow) / 2, color: '#8b93a7', children: [] },
    { label: '向下转折', price: zhongshuLow - height, color: '#2fc58d', children: [] },
  ]
  const byKey: Record<string, ClassificationBranch> = {
    continue_up: branches[0]!,
    range: branches[1]!,
    reverse_down: branches[2]!,
  }
  for (const scenario of classification.scenarios) {
    const branch = byKey[scenario.key]
    if (!branch) continue
    const children = scenario.children ?? []
    const spread = height * 0.35
    branch.children = children.map((item, index) => ({
      label: item.label,
      // 子分支围绕父分支的目标价展开
      price: branch.price + (children.length === 1 ? 0 : (index - (children.length - 1) / 2) * spread),
      color: branch.color,
    }))
  }
  return branches
}

class ClassificationRenderer implements IPrimitivePaneRenderer {
  private readonly chart: IChartApi
  private readonly series: ISeriesApi<'Candlestick'>
  private readonly lastTime: number
  private readonly lastPrice: number
  private readonly branches: ClassificationBranch[]

  constructor(
    chart: IChartApi,
    series: ISeriesApi<'Candlestick'>,
    lastTime: number,
    lastPrice: number,
    branches: ClassificationBranch[],
  ) {
    this.chart = chart
    this.series = series
    this.lastTime = lastTime
    this.lastPrice = lastPrice
    this.branches = branches
  }

  draw(target: CanvasRenderingTarget2D): void {
    if (this.branches.length === 0) return
    target.useMediaCoordinateSpace((scope) => {
      const context = scope.context
      const startX = this.chart.timeScale().timeToCoordinate((this.lastTime / 1000) as Time)
      const startY = this.series.priceToCoordinate(this.lastPrice)
      if (startX === null || startY === null) return

      const endX = startX + BRANCH_LENGTH_PX
      for (const branch of this.branches) {
        const endY = this.series.priceToCoordinate(branch.price)
        if (endY === null) continue

        context.strokeStyle = branch.color
        context.fillStyle = branch.color
        context.lineWidth = 1.5
        context.setLineDash([5, 4])
        context.beginPath()
        context.moveTo(startX, startY)
        context.lineTo(endX, endY)
        context.stroke()
        context.setLineDash([])

        // 箭头
        const angle = Math.atan2(endY - startY, endX - startX)
        const size = 6
        context.beginPath()
        context.moveTo(endX, endY)
        context.lineTo(endX - size * Math.cos(angle - 0.45), endY - size * Math.sin(angle - 0.45))
        context.lineTo(endX - size * Math.cos(angle + 0.45), endY - size * Math.sin(angle + 0.45))
        context.closePath()
        context.fill()

        // 标签
        context.font = '11px ui-monospace, SFMono-Regular, Menlo, monospace'
        context.fillText(branch.label, endX + 6, endY + 4)

        // 再往后的分类：从当前分支末端继续画出子路径
        const childEndX = endX + 72
        for (const child of branch.children) {
          const childY = this.series.priceToCoordinate(child.price)
          if (childY === null) continue
          context.strokeStyle = child.color
          context.fillStyle = child.color
          context.lineWidth = 1
          context.setLineDash([3, 3])
          context.beginPath()
          context.moveTo(endX, endY)
          context.lineTo(childEndX, childY)
          context.stroke()
          context.setLineDash([])

          const childAngle = Math.atan2(childY - endY, childEndX - endX)
          const childSize = 5
          context.beginPath()
          context.moveTo(childEndX, childY)
          context.lineTo(
            childEndX - childSize * Math.cos(childAngle - 0.45),
            childY - childSize * Math.sin(childAngle - 0.45),
          )
          context.lineTo(
            childEndX - childSize * Math.cos(childAngle + 0.45),
            childY - childSize * Math.sin(childAngle + 0.45),
          )
          context.closePath()
          context.fill()

          context.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace'
          context.fillText(child.label, childEndX + 5, childY + 4)
        }
      }
    })
  }
}

class ClassificationPaneView implements IPrimitivePaneView {
  private readonly rendererInstance: ClassificationRenderer

  constructor(rendererInstance: ClassificationRenderer) {
    this.rendererInstance = rendererInstance
  }

  renderer(): IPrimitivePaneRenderer | null {
    return this.rendererInstance
  }
}

/** 在原图上画出后续走势的完全分类分支。 */
export class ClassificationPrimitive implements ISeriesPrimitive<Time> {
  private readonly views: IPrimitivePaneView[]

  constructor(
    chart: IChartApi,
    series: ISeriesApi<'Candlestick'>,
    lastTime: number,
    lastPrice: number,
    branches: ClassificationBranch[],
  ) {
    this.views = [new ClassificationPaneView(
      new ClassificationRenderer(chart, series, lastTime, lastPrice, branches),
    )]
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views
  }
}
