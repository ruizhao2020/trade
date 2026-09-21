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
  label?: string
}

export interface VolumeBoxLegendItem {
  label: string
  color: string
}

class VolumeBoxRenderer implements IPrimitivePaneRenderer {
  private readonly chart: IChartApi
  private readonly series: ISeriesApi<'Histogram'>
  private readonly points: VolumeBoxPoint[]
  private readonly legendItems: VolumeBoxLegendItem[]

  constructor(
    chart: IChartApi,
    series: ISeriesApi<'Histogram'>,
    points: VolumeBoxPoint[],
    legendItems: VolumeBoxLegendItem[],
  ) {
    this.chart = chart
    this.series = series
    this.points = points
    this.legendItems = legendItems
  }

  draw(target: CanvasRenderingTarget2D): void {
    const timeScale = this.chart.timeScale()
    const barWidth = Math.max(3, Math.min(timeScale.options().barSpacing * 0.78, 18))
    target.useMediaCoordinateSpace(scope => {
      const context = scope.context
      context.font = '10px sans-serif'
      context.textBaseline = 'middle'
      context.textAlign = 'left'
      let legendX = 8
      for (const item of this.legendItems) {
        context.strokeStyle = item.color
        context.lineWidth = 1.2
        context.strokeRect(legendX, 8, 10, 10)
        context.fillStyle = item.color
        context.fillText(item.label, legendX + 15, 13)
        legendX += 15 + context.measureText(item.label).width + 16
      }
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
        if (point.label) {
          context.font = '9px sans-serif'
          context.textAlign = 'center'
          context.textBaseline = 'bottom'
          const labelWidth = context.measureText(point.label).width + 6
          const labelY = Math.max(14, top - 3)
          context.fillStyle = 'rgba(17, 22, 31, 0.88)'
          context.fillRect(x - labelWidth / 2, labelY - 12, labelWidth, 12)
          context.fillStyle = point.color
          context.fillText(point.label, x, labelY)
        }
      }
    })
  }
}

class VolumeBoxPaneView implements IPrimitivePaneView {
  private readonly rendererInstance: VolumeBoxRenderer

  constructor(chart: IChartApi, series: ISeriesApi<'Histogram'>, points: VolumeBoxPoint[], legendItems: VolumeBoxLegendItem[]) {
    this.rendererInstance = new VolumeBoxRenderer(chart, series, points, legendItems)
  }

  renderer(): IPrimitivePaneRenderer | null {
    return this.rendererInstance
  }
}

export class VolumeBoxPrimitive implements ISeriesPrimitive<Time> {
  private readonly views: IPrimitivePaneView[]

  constructor(chart: IChartApi, series: ISeriesApi<'Histogram'>, points: VolumeBoxPoint[], legendItems: VolumeBoxLegendItem[] = []) {
    this.views = [new VolumeBoxPaneView(chart, series, points, legendItems)]
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views
  }
}
