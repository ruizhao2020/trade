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
        context.strokeStyle = color
        context.lineWidth = 1
        context.strokeRect(x, top, width, height)

        context.font = '10px sans-serif'
        context.textAlign = 'left'
        context.textBaseline = 'bottom'
        context.fillStyle = color
        context.fillText(`合理价格 · ${zone.foldCount}折`, x + 4, Math.max(12, top - 3))
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
