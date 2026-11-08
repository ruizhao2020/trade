import type {
  AutoscaleInfo,
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  Time,
} from 'lightweight-charts'
import type { CanvasRenderingTarget2D } from 'fancy-canvas'
import type { ArrowSpec } from '../core/types.ts'

/** 箭头端点相对柱群峰的偏移，占指标值最大绝对值的比例，避免压住柱体。 */
export const ARROW_OFFSET_RATIO = 0.12

export interface ArrowPoint {
  x: number
  y: number
}

/**
 * 端点的纵坐标（指标值坐标）：顶背驰画在柱群上方，底背驰画在下方。
 * 偏移量由调用方按当前数据的量级给出，保证不同标的看起来一致。
 */
export function arrowEndpointValue(
  peakValue: number,
  direction: ArrowSpec['direction'],
  pad: number,
): number {
  return direction === 'top' ? peakValue + pad : peakValue - pad
}

/** 箭头头部的三个顶点：尖端落在 to 上，方向由 from → to 决定。 */
export function arrowHeadPoints(from: ArrowPoint, to: ArrowPoint, size = 7): [ArrowPoint, ArrowPoint, ArrowPoint] {
  const angle = Math.atan2(to.y - from.y, to.x - from.x)
  const spread = 0.45
  return [
    to,
    {
      x: to.x - size * Math.cos(angle - spread),
      y: to.y - size * Math.sin(angle - spread),
    },
    {
      x: to.x - size * Math.cos(angle + spread),
      y: to.y - size * Math.sin(angle + spread),
    },
  ]
}

/** 箭头偏移量：取箭头两端峰值的绝对值再乘一个比例。
 *
 * 不能拿整行 values 的最大绝对值——每行都带 `time`（毫秒级时间戳），
 * 那样偏移量会变成 1e11 量级，箭头端点和自动缩放都会落到图外。
 */
export function arrowPadOf(arrows: ArrowSpec[]): number {
  let maxAbs = 0
  for (const arrow of arrows) {
    maxAbs = Math.max(maxAbs, Math.abs(arrow.fromValue), Math.abs(arrow.toValue))
  }
  return maxAbs * ARROW_OFFSET_RATIO
}

class DivergenceArrowRenderer implements IPrimitivePaneRenderer {
  private readonly chart: IChartApi
  private readonly series: ISeriesApi<'Line'> | ISeriesApi<'Histogram'>
  private readonly arrows: ArrowSpec[]
  private readonly pad: number

  constructor(
    chart: IChartApi,
    series: ISeriesApi<'Line'> | ISeriesApi<'Histogram'>,
    arrows: ArrowSpec[],
    pad: number,
  ) {
    this.chart = chart
    this.series = series
    this.arrows = arrows
    this.pad = pad
  }

  draw(target: CanvasRenderingTarget2D): void {
    if (this.arrows.length === 0) return
    target.useMediaCoordinateSpace((scope) => {
      const context = scope.context
      const timeScale = this.chart.timeScale()

      for (const arrow of this.arrows) {
        const fromX = timeScale.timeToCoordinate((arrow.fromTime / 1000) as Time)
        const toX = timeScale.timeToCoordinate((arrow.toTime / 1000) as Time)
        if (fromX === null || toX === null) continue
        const fromY = this.series.priceToCoordinate(
          arrowEndpointValue(arrow.fromValue, arrow.direction, this.pad),
        )
        const toY = this.series.priceToCoordinate(
          arrowEndpointValue(arrow.toValue, arrow.direction, this.pad),
        )
        if (fromY === null || toY === null) continue

        const from = { x: fromX, y: fromY }
        const to = { x: toX, y: toY }

        context.strokeStyle = arrow.color
        context.fillStyle = arrow.color
        context.lineWidth = 1.2
        context.beginPath()
        context.moveTo(from.x, from.y)
        context.lineTo(to.x, to.y)
        context.stroke()

        const [tip, left, right] = arrowHeadPoints(from, to)
        context.beginPath()
        context.moveTo(tip.x, tip.y)
        context.lineTo(left.x, left.y)
        context.lineTo(right.x, right.y)
        context.closePath()
        context.fill()
      }
    })
  }
}

class DivergenceArrowPaneView implements IPrimitivePaneView {
  private readonly rendererInstance: DivergenceArrowRenderer

  constructor(
    chart: IChartApi,
    series: ISeriesApi<'Line'> | ISeriesApi<'Histogram'>,
    arrows: ArrowSpec[],
    pad: number,
  ) {
    this.rendererInstance = new DivergenceArrowRenderer(chart, series, arrows, pad)
  }
  renderer(): IPrimitivePaneRenderer | null {
    return this.rendererInstance
  }
}

/**
 * 副图跨 K 线箭头（MACD 柱群背驰：前群峰 → 后群峰）。
 *
 * 端点用值坐标，随缩放/平移自动跟随；箭头画在柱群峰之外，
 * 所以同时把这段高度并入自动缩放，否则会被副图的上/下边界裁掉。
 */
export class DivergenceArrowPrimitive implements ISeriesPrimitive<Time> {
  private readonly arrows: ArrowSpec[]
  private readonly pad: number
  private readonly views: IPrimitivePaneView[]

  constructor(
    chart: IChartApi,
    series: ISeriesApi<'Line'> | ISeriesApi<'Histogram'>,
    arrows: ArrowSpec[],
    pad: number,
  ) {
    this.arrows = arrows
    this.pad = pad
    this.views = [new DivergenceArrowPaneView(chart, series, arrows, pad)]
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views
  }

  autoscaleInfo(): AutoscaleInfo | null {
    if (this.arrows.length === 0) return null
    let minValue = Number.POSITIVE_INFINITY
    let maxValue = Number.NEGATIVE_INFINITY
    for (const arrow of this.arrows) {
      for (const value of [arrow.fromValue, arrow.toValue]) {
        const endpoint = arrowEndpointValue(value, arrow.direction, this.pad)
        minValue = Math.min(minValue, value, endpoint)
        maxValue = Math.max(maxValue, value, endpoint)
      }
    }
    if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) return null
    return { priceRange: { minValue, maxValue } }
  }
}
