import type {
  IChartApi,
  IPanePrimitive,
  IPanePrimitivePaneView,
  IPrimitivePaneRenderer,
  ISeriesApi,
  Time,
} from 'lightweight-charts'
import type { CanvasRenderingTarget2D } from 'fancy-canvas'

export interface DilunZoneRegion {
  id: number
  startTime: number
  endTime: number
  low: number
  high: number
  foldCount: number
  mature: boolean
  /** 带上的文字。不传则用帝论的默认文案（该 primitive 最早为帝论结构而写）。 */
  label?: string
  /** 虚线边框：被扫荡/失效的区用它区分于仍在聚集的区 */
  dashed?: boolean
  /** 已被拿走的比例 0..1，从 fillFromTop 决定的那一侧往里填 */
  fillRatio?: number
  fillFromTop?: boolean
}

class DilunZoneRenderer implements IPrimitivePaneRenderer {
  private readonly chart: IChartApi
  private readonly candleSeries: ISeriesApi<'Candlestick'>
  private readonly zones: DilunZoneRegion[]

  constructor(
    chart: IChartApi,
    candleSeries: ISeriesApi<'Candlestick'>,
    zones: DilunZoneRegion[],
  ) {
    this.chart = chart
    this.candleSeries = candleSeries
    this.zones = zones
  }

  draw(target: CanvasRenderingTarget2D): void {
    const timeScale = this.chart.timeScale()
    target.useMediaCoordinateSpace(({ context }) => {
      for (const zone of this.zones) {
        const x1 = timeScale.timeToCoordinate(zone.startTime / 1000 as Time)
        const x2 = timeScale.timeToCoordinate(zone.endTime / 1000 as Time)
        const yHigh = this.candleSeries.priceToCoordinate(zone.high)
        const yLow = this.candleSeries.priceToCoordinate(zone.low)
        if (x1 === null || x2 === null || yHigh === null || yLow === null) continue
        const x = Math.min(x1, x2)
        const width = Math.max(Math.abs(x2 - x1), 2)
        const top = Math.min(yHigh, yLow)
        const height = Math.max(Math.abs(yLow - yHigh), 1)
        const color = zone.mature ? '#9b8cf2' : '#6c8cff'

        context.fillStyle = zone.mature ? 'rgba(155,140,242,0.10)' : 'rgba(108,140,255,0.08)'
        context.fillRect(x, top, width, height)

        // 已消耗比例：从被扫荡的那一侧往里填，表示这块流动性被拿走了多少。
        // 未消耗（fillRatio 0/未定义）时不画，帝论那套用法也不受影响。
        const fillRatio = zone.fillRatio === undefined ? 0 : Math.min(Math.max(zone.fillRatio, 0), 1)
        if (fillRatio > 0) {
          const fillHeight = Math.max(height * fillRatio, 1)
          const fillTop = zone.fillFromTop ? top : top + height - fillHeight
          context.fillStyle = zone.mature ? 'rgba(155,140,242,0.38)' : 'rgba(108,140,255,0.30)'
          context.fillRect(x, fillTop, width, fillHeight)
        }

        context.strokeStyle = color
        context.lineWidth = 1
        // 被扫荡的区用虚线边框：一眼区分"还在聚集"与"已经被拿走"
        if (zone.dashed) context.setLineDash([4, 3])
        context.strokeRect(x, top, width, height)
        context.setLineDash([])

        context.font = '10px sans-serif'
        context.textAlign = 'left'
        context.textBaseline = 'bottom'
        context.fillStyle = color
        context.fillText(zone.label ?? `合理价格 · ${zone.foldCount}折`, x + 4, Math.max(12, top - 3))
      }
    })
  }
}

class DilunZonePaneView implements IPanePrimitivePaneView {
  private readonly rendererInstance: DilunZoneRenderer

  constructor(chart: IChartApi, candleSeries: ISeriesApi<'Candlestick'>, zones: DilunZoneRegion[]) {
    this.rendererInstance = new DilunZoneRenderer(chart, candleSeries, zones)
  }

  renderer(): IPrimitivePaneRenderer | null {
    return this.rendererInstance
  }
}

export class DilunZonePrimitive implements IPanePrimitive {
  private readonly views: IPanePrimitivePaneView[]

  constructor(chart: IChartApi, candleSeries: ISeriesApi<'Candlestick'>, zones: DilunZoneRegion[]) {
    this.views = [new DilunZonePaneView(chart, candleSeries, zones)]
  }

  paneViews(): readonly IPanePrimitivePaneView[] {
    return this.views
  }
}
