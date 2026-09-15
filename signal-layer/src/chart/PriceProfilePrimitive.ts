import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
} from 'lightweight-charts'
import type { CanvasRenderingTarget2D } from 'fancy-canvas'

export interface PriceProfilePoint {
  price: number
  weight: number
  isProfit: boolean
}

export const MIN_VISIBLE_PROFILE_WEIGHT = 1e-8

export function hasVisibleProfileWeight(point: PriceProfilePoint): boolean {
  return Number.isFinite(point.weight) && point.weight > MIN_VISIBLE_PROFILE_WEIGHT
}

interface PriceProfileOptions {
  currentPrice: number
  peakPrice: number
  averageCost: number
}

class PriceProfileRenderer implements IPrimitivePaneRenderer {
  private readonly series: ISeriesApi<'Candlestick'>
  private readonly points: PriceProfilePoint[]
  private readonly options: PriceProfileOptions

  constructor(
    series: ISeriesApi<'Candlestick'>,
    points: PriceProfilePoint[],
    options: PriceProfileOptions,
  ) {
    this.series = series
    this.points = points
    this.options = options
  }

  draw(target: CanvasRenderingTarget2D): void {
    if (this.points.length === 0) return
    const maxWeight = Math.max(
      ...this.points.filter(hasVisibleProfileWeight).map(point => point.weight),
      0,
    )
    if (maxWeight <= 0) return

    target.useMediaCoordinateSpace(scope => {
      const context = scope.context
      const xEnd = scope.mediaSize.width - 8
      const maxWidth = Math.min(150, scope.mediaSize.width * 0.24)
      const coordinates = this.points.map(point => this.series.priceToCoordinate(point.price))

      for (let index = 0; index < this.points.length; index += 1) {
        const point = this.points[index]!
        if (!hasVisibleProfileWeight(point)) continue
        const y = coordinates[index]
        if (y === null) continue
        const previousY = coordinates[Math.max(0, index - 1)]
        const nextY = coordinates[Math.min(coordinates.length - 1, index + 1)]
        const binHeight = Math.max(
          1.5,
          Math.min(6, Math.abs((nextY ?? y) - (previousY ?? y)) / 2 || 2),
        )
        const width = point.weight / maxWeight * maxWidth
        context.fillStyle = point.isProfit ? 'rgba(108,140,255,0.58)' : 'rgba(155,140,242,0.48)'
        context.fillRect(xEnd - width, y - binHeight / 2, width, binHeight)

        if (Math.abs(point.price - this.options.peakPrice) < 1e-6) {
          context.strokeStyle = '#e7c66b'
          context.lineWidth = 1
          context.strokeRect(xEnd - width, y - binHeight / 2, width, binHeight)
        }
      }

      const averageY = this.series.priceToCoordinate(this.options.averageCost)
      if (averageY !== null) {
        context.strokeStyle = 'rgba(231,198,107,0.9)'
        context.lineWidth = 1
        context.setLineDash([4, 3])
        context.beginPath()
        context.moveTo(xEnd - maxWidth, averageY)
        context.lineTo(xEnd, averageY)
        context.stroke()
        context.setLineDash([])
      }

      const currentY = this.series.priceToCoordinate(this.options.currentPrice)
      if (currentY !== null) {
        context.fillStyle = 'rgba(12,15,21,0.82)'
        context.fillRect(xEnd - maxWidth, currentY - 9, 46, 15)
        context.fillStyle = '#a7afbd'
        context.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace'
        context.fillText('筹码峰', xEnd - maxWidth + 4, currentY + 2)
      }
    })
  }
}

class PriceProfilePaneView implements IPrimitivePaneView {
  private readonly rendererInstance: PriceProfileRenderer

  constructor(
    series: ISeriesApi<'Candlestick'>,
    points: PriceProfilePoint[],
    options: PriceProfileOptions,
  ) {
    this.rendererInstance = new PriceProfileRenderer(series, points, options)
  }

  renderer(): IPrimitivePaneRenderer | null {
    return this.rendererInstance
  }
}

export class PriceProfilePrimitive implements ISeriesPrimitive<Time> {
  private readonly views: IPrimitivePaneView[]
  private readonly points: PriceProfilePoint[]
  private readonly options: PriceProfileOptions
  private requestUpdate?: () => void

  constructor(
    series: ISeriesApi<'Candlestick'>,
    points: PriceProfilePoint[],
    options: PriceProfileOptions,
  ) {
    this.points = points
    this.options = options
    this.views = [new PriceProfilePaneView(series, this.points, this.options)]
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.requestUpdate = param.requestUpdate
  }

  detached(): void {
    this.requestUpdate = undefined
  }

  setSnapshot(points: PriceProfilePoint[], options: PriceProfileOptions): void {
    this.points.splice(0, this.points.length, ...points)
    Object.assign(this.options, options)
    this.requestUpdate?.()
  }
}
