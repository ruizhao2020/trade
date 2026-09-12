import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  Time,
} from 'lightweight-charts'
import type { CanvasRenderingTarget2D } from 'fancy-canvas'

export interface VolumeBoxPoint {
  time: number
  value: number
  color: string
}

class VolumeBoxRenderer implements IPrimitivePaneRenderer {
  private readonly chart: IChartApi
  private readonly series: ISeriesApi<'Histogram'>
  private readonly points: VolumeBoxPoint[]

  constructor(
    chart: IChartApi,
    series: ISeriesApi<'Histogram'>,
    points: VolumeBoxPoint[],
  ) {
    this.chart = chart
    this.series = series
    this.points = points
  }

  draw(target: CanvasRenderingTarget2D): void {
    const timeScale = this.chart.timeScale()
    const barWidth = Math.max(3, Math.min(timeScale.options().barSpacing * 0.78, 18))
    target.useMediaCoordinateSpace(scope => {
      const context = scope.context
      for (const point of this.points) {
        const x = timeScale.timeToCoordinate(point.time / 1000 as Time)
        const yValue = this.series.priceToCoordinate(point.value)
        const yZero = this.series.priceToCoordinate(0)
        if (x === null || yValue === null || yZero === null) continue
        const top = Math.min(yValue, yZero)
        const height = Math.max(Math.abs(yZero - yValue), 1)
        context.strokeStyle = point.color
        context.lineWidth = 1.2
        context.strokeRect(x - barWidth / 2, top, barWidth, height)
      }
    })
  }
}

class VolumeBoxPaneView implements IPrimitivePaneView {
  private readonly rendererInstance: VolumeBoxRenderer

  constructor(chart: IChartApi, series: ISeriesApi<'Histogram'>, points: VolumeBoxPoint[]) {
    this.rendererInstance = new VolumeBoxRenderer(chart, series, points)
  }

  renderer(): IPrimitivePaneRenderer | null {
    return this.rendererInstance
  }
}

export class VolumeBoxPrimitive implements ISeriesPrimitive<Time> {
  private readonly views: IPrimitivePaneView[]

  constructor(chart: IChartApi, series: ISeriesApi<'Histogram'>, points: VolumeBoxPoint[]) {
    this.views = [new VolumeBoxPaneView(chart, series, points)]
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views
  }
}
