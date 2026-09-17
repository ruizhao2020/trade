/**
 * 缠论元素 LWC 渲染器 (v5 API)
 *
 * 渲染策略:
 *   - 笔/线段: LineSeries
 *   - 中枢: IPanePrimitive (自定义 Canvas 绘制矩形 + 中轴虚线)
 *   - 分型/买卖点: createSeriesMarkers
 */

import type {
  IChartApi,
  ISeriesApi,
  IPanePrimitive,
  IPanePrimitivePaneView,
  IPrimitivePaneRenderer,
  Time,
  SeriesMarker,
  ISeriesMarkersPluginApi,
  Coordinate,
} from 'lightweight-charts'
import { LineSeries, createSeriesMarkers } from 'lightweight-charts'
import type { CanvasRenderingTarget2D } from 'fancy-canvas'
import type {
  ChanAnalysis,
  ChanRenderOptions,
  Fenxing,
  Zhongshu,
  BuySellPoint,
  Divergence,
  IndicatorMarkerDetail,
  Duan,
  Bi,
} from '../core/types.ts'
import { arrangeSeriesMarkersVertically, buildBuySellMarkerDetail, buildDivergenceMarkerDetail, buySellMarkerId, buySellMarkerLabel, divergenceMarkerId, divergenceMarkerLabel } from './markerDetails.ts'

class ZhongshuRenderer implements IPrimitivePaneRenderer {
  private readonly candleSeries: ISeriesApi<'Candlestick'>
  private readonly chart: IChartApi
  private readonly zhongshus: Zhongshu[]
  private readonly options: { color: string; showAxis: boolean }

  constructor(
    candleSeries: ISeriesApi<'Candlestick'>,
    chart: IChartApi,
    zhongshus: Zhongshu[],
    options: { color: string; showAxis: boolean }
  ) {
    this.candleSeries = candleSeries
    this.chart = chart
    this.zhongshus = zhongshus
    this.options = options
  }

  draw(target: CanvasRenderingTarget2D): void {
    if (this.zhongshus.length === 0) return
    const timeScale = this.chart.timeScale()

    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context
      for (const zs of this.zhongshus) {
        const x1 = timeScale.timeToCoordinate(zs.startTime / 1000 as Time)
        const x2 = timeScale.timeToCoordinate(zs.endTime / 1000 as Time)
        const yHigh = this.candleSeries.priceToCoordinate(zs.high)
        const yLow = this.candleSeries.priceToCoordinate(zs.low)
        if (x1 === null || x2 === null || yHigh === null || yLow === null) continue

        const x = Math.min(x1, x2)
        const w = Math.abs(x2 - x1)
        const yTop = Math.min(yHigh, yLow)
        const h = Math.abs(yHigh - yLow)

        const fillColor = zs.broken
          ? (zs.breakDirection === 'up' ? 'rgba(255,91,98,0.15)' : 'rgba(47,197,141,0.15)')
          : this.options.color + '33'
        ctx.fillStyle = fillColor
        ctx.fillRect(x, yTop, w, h)

        ctx.strokeStyle = zs.broken
          ? (zs.breakDirection === 'up' ? '#ff5b62' : '#2fc58d')
          : this.options.color
        ctx.lineWidth = 1
        ctx.strokeRect(x, yTop, w, h)

        if (this.options.showAxis) {
          const yMid = this.candleSeries.priceToCoordinate(zs.mid)
          if (yMid !== null) {
            ctx.strokeStyle = this.options.color + '88'
            ctx.lineWidth = 1
            ctx.setLineDash([4, 4])
            ctx.beginPath()
            ctx.moveTo(x, yMid)
            ctx.lineTo(x + w, yMid)
            ctx.stroke()
            ctx.setLineDash([])
          }
        }
      }
    })
  }
}

class ZhongshuPaneView implements IPanePrimitivePaneView {
  private readonly _renderer: ZhongshuRenderer

  constructor(
    candleSeries: ISeriesApi<'Candlestick'>,
    chart: IChartApi,
    zhongshus: Zhongshu[],
    options: { color: string; showAxis: boolean }
  ) {
    this._renderer = new ZhongshuRenderer(candleSeries, chart, zhongshus, options)
  }

  renderer(): IPrimitivePaneRenderer | null {
    return this._renderer
  }
}

class ZhongshuPrimitive implements IPanePrimitive {
  private readonly views: IPanePrimitivePaneView[]

  constructor(
    candleSeries: ISeriesApi<'Candlestick'>,
    chart: IChartApi,
    zhongshus: Zhongshu[],
    options: { color: string; showAxis: boolean }
  ) {
    this.views = [new ZhongshuPaneView(candleSeries, chart, zhongshus, options)]
  }

  paneViews(): readonly IPanePrimitivePaneView[] {
    return this.views
  }
}

function buildLineData(items: Array<{ startTime: number; startPrice: number; endTime: number; endPrice: number }>) {
  // 合并相邻笔/段端点:前一笔的 endTime 等于下一笔的 startTime,只保留一个点
  // 注意:段的 start/end 可能时间倒序(向下段起点是高点,晚于低点),
  // 所以每个 item 的两点按时间排序后加入
  const points: Array<{ time: number; value: number }> = []
  for (const item of items) {
    const startT = item.startTime / 1000
    const endT = item.endTime / 1000
    // 每个元素的两点按时间升序排列
    const segPts: Array<{ time: number; value: number }> =
      startT <= endT
        ? [
            { time: startT, value: item.startPrice },
            { time: endT, value: item.endPrice },
          ]
        : [
            { time: endT, value: item.endPrice },
            { time: startT, value: item.startPrice },
          ]
    for (const p of segPts) {
      if (points.length === 0 || points[points.length - 1].time !== p.time) {
        points.push(p)
      }
    }
  }
  // 再次去重保险:如果还有相同时间的点,只保留最后一个
  const seen = new Map<number, number>()
  for (const p of points) seen.set(p.time, p.value)
  return Array.from(seen.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([time, value]) => ({ time: time as Time, value }))
}

function buildBiIndexMarkers(bis: Array<{ index: number; direction: 'up' | 'down'; startTime: number; endTime: number; startPrice: number; endPrice: number }>): SeriesMarker<Time>[] {
  // 每个端点都标号,相邻笔共享端点编号,连续递增。
  // N 笔 -> N+1 个端点标号 (0, 1, 2, ..., N)
  // 笔 0 起点标 0;每笔终点标 i+1(笔 i 终点 = 笔 i+1 起点,共享同一标号)
  // 顶(高价)标上方 aboveBar;底(低价)标下方 belowBar
  const markers: SeriesMarker<Time>[] = []
  if (bis.length === 0) return markers

  // 第一笔起点(仅一次,后续笔的起点已被前一笔终点覆盖)
  const first = bis[0]
  markers.push({
    time: first.startTime / 1000 as Time,
    position: first.direction === 'up' ? 'atPriceBottom' : 'atPriceTop',
    price: first.startPrice,
    color: '#fbbf24',
    shape: 'circle',
    size: 0.8,
    id: `chan:bi-point:0:${first.startTime}`,
    text: '0',
  })

  // 每笔终点:编号 i+1
  bis.forEach((b, i) => {
    markers.push({
      time: b.endTime / 1000 as Time,
      position: b.direction === 'up' ? 'atPriceTop' : 'atPriceBottom',
      price: b.endPrice,
      color: '#fbbf24',
      shape: 'circle',
      size: 0.8,
      id: `chan:bi-point:${i + 1}:${b.endTime}`,
      text: `${i + 1}`,
    })
  })

  return markers
}

function buildDuanIndexMarkers(duans: Array<{ index: number; direction: 'up' | 'down'; startTime: number; endTime: number; startPrice: number; endPrice: number }>): SeriesMarker<Time>[] {
  const markers: SeriesMarker<Time>[] = []
  if (duans.length === 0) return markers

  const first = duans[0]
  markers.push({
    time: first.startTime / 1000 as Time,
    position: first.direction === 'up' ? 'atPriceBottom' : 'atPriceTop',
    price: first.startPrice,
    color: '#3b82f6',
    shape: 'square',
    size: 0.8,
    id: `chan:duan-point:0:${first.startTime}`,
    text: 'D0',
  })

  duans.forEach((d, i) => {
    markers.push({
      time: d.endTime / 1000 as Time,
      position: d.direction === 'up' ? 'atPriceTop' : 'atPriceBottom',
      price: d.endPrice,
      color: '#3b82f6',
      shape: 'square',
      size: 0.8,
      id: `chan:duan-point:${i + 1}:${d.endTime}`,
      text: `D${i + 1}`,
    })
  })

  return markers
}

interface FeatLine {
  t1: number
  p1: number
  t2: number
  p2: number
  color: string
  width: number
  dash: number[]
}

function buildFeatLines(duans: Duan[], bis: Bi[]): FeatLine[] {
  const lines: FeatLine[] = []
  for (const duan of duans) {
    const mergedSet = new Set(duan.mergedFeat?.map(m => m.bi) ?? [])
    for (const f of duan.featElements ?? []) {
      const bi = bis[f.bi]
      if (!bi) continue
      const isMerged = mergedSet.has(f.bi)
      lines.push({
        t1: bi.startTime, p1: f.first,
        t2: bi.endTime, p2: f.last,
        color: isMerged ? '#22c55e' : '#f97316',
        width: isMerged ? 2 : 1,
        dash: isMerged ? [6, 4] : [4, 4],
      })
    }
  }
  return lines
}

class FeatSequenceRenderer implements IPrimitivePaneRenderer {
  private readonly candleSeries: ISeriesApi<'Candlestick'>
  private readonly chart: IChartApi
  private readonly lines: FeatLine[]

  constructor(candleSeries: ISeriesApi<'Candlestick'>, chart: IChartApi, lines: FeatLine[]) {
    this.candleSeries = candleSeries
    this.chart = chart
    this.lines = lines
  }

  draw(target: CanvasRenderingTarget2D): void {
    if (this.lines.length === 0) return
    const timeScale = this.chart.timeScale()
    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context
      for (const line of this.lines) {
        const x1 = timeScale.timeToCoordinate(line.t1 / 1000 as Time)
        const x2 = timeScale.timeToCoordinate(line.t2 / 1000 as Time)
        const y1 = this.candleSeries.priceToCoordinate(line.p1)
        const y2 = this.candleSeries.priceToCoordinate(line.p2)
        if (x1 === null || x2 === null || y1 === null || y2 === null) continue
        ctx.strokeStyle = line.color
        ctx.lineWidth = line.width
        ctx.setLineDash(line.dash)
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
      }
      ctx.setLineDash([])
    })
  }
}

class FeatSequencePaneView implements IPanePrimitivePaneView {
  private readonly _renderer: FeatSequenceRenderer
  constructor(candleSeries: ISeriesApi<'Candlestick'>, chart: IChartApi, lines: FeatLine[]) {
    this._renderer = new FeatSequenceRenderer(candleSeries, chart, lines)
  }
  renderer(): IPrimitivePaneRenderer | null {
    return this._renderer
  }
}

class FeatSequencePrimitive implements IPanePrimitive {
  private readonly views: IPanePrimitivePaneView[]
  constructor(candleSeries: ISeriesApi<'Candlestick'>, chart: IChartApi, lines: FeatLine[]) {
    this.views = [new FeatSequencePaneView(candleSeries, chart, lines)]
  }
  paneViews(): readonly IPanePrimitivePaneView[] {
    return this.views
  }
}

function buildFenxingMarkers(fenxings: Fenxing[], chanKLineTimes: number[]): SeriesMarker<Time>[] {
  return fenxings.map(f => ({
    time: (chanKLineTimes[f.klineIndices[1]] ?? 0) / 1000 as Time,
    position: f.direction === 'top' ? 'atPriceTop' : 'atPriceBottom',
    price: f.price,
    color: f.direction === 'top' ? '#ef4444' : '#10b981',
    shape: f.direction === 'top' ? 'arrowDown' : 'arrowUp',
    text: f.direction === 'top' ? '顶' : '底',
  }))
}

function buildBuySellMarkers(points: BuySellPoint[]): SeriesMarker<Time>[] {
  const colorMap: Record<string, string> = {
    buy1: '#22c55e', buy2: '#16a34a', buy3: '#15803d',
    sell1: '#f87171', sell2: '#ef4444', sell3: '#dc2626',
  }
  return points.map(p => {
    const isBuy = p.type.startsWith('buy')
    return {
      time: p.time / 1000 as Time,
      position: isBuy ? 'atPriceBottom' : 'atPriceTop',
      price: p.price,
      color: colorMap[p.type] ?? '#fbbf24',
      shape: isBuy ? 'arrowUp' : 'arrowDown',
      size: 2,
      id: buySellMarkerId(p),
      text: buySellMarkerLabel(p),
    }
  })
}

function buildDivergenceMarkers(divergences: Divergence[]): SeriesMarker<Time>[] {
  return divergences.map(item => {
    const isBottom = item.type === 'bottom'
    return {
      time: item.time / 1000 as Time,
      position: isBottom ? 'atPriceBottom' : 'atPriceTop',
      price: item.price,
      color: isBottom ? '#48c7e8' : '#d77dff',
      shape: 'square',
      size: 1,
      id: divergenceMarkerId(item),
      text: divergenceMarkerLabel(item),
    }
  })
}

export class ChanRenderer {
  private lineSeriesList: ISeriesApi<'Line'>[] = []
  private primitives: IPanePrimitive[] = []
  private markersPlugin: ISeriesMarkersPluginApi<Time> | null = null
  private markerDetails = new Map<string, IndicatorMarkerDetail>()
  private readonly chart: IChartApi
  private readonly candleSeries: ISeriesApi<'Candlestick'>

  constructor(chart: IChartApi, candleSeries: ISeriesApi<'Candlestick'>) {
    this.chart = chart
    this.candleSeries = candleSeries
  }

  render(analysis: ChanAnalysis, options: ChanRenderOptions, detailFeatures?: string[]): void {
    this.clear()

    if (options.showBi && analysis.bis.length > 0) {
      const biSeries = this.chart.addSeries(LineSeries, {
        color: options.biColor ?? '#fbbf24',
        lineWidth: 1,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
      })
      biSeries.setData(buildLineData(analysis.bis))
      this.lineSeriesList.push(biSeries)
    }

    if (options.showDuan && analysis.duans.length > 0) {
      const duanSeries = this.chart.addSeries(LineSeries, {
        color: options.duanColor ?? '#3b82f6',
        lineWidth: 2,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
      })
      duanSeries.setData(buildLineData(analysis.duans))
      this.lineSeriesList.push(duanSeries)
    }

    if (options.showZhongshu) {
      // 根据 zsLevel 选择中枢数据:笔中枢(level="bi")或段中枢(level="duan")
      const zsList = options.zsLevel === 'duan' ? analysis.duanZhongshus : analysis.zhongshus
      if (zsList.length > 0) {
        const prim = new ZhongshuPrimitive(this.candleSeries, this.chart, zsList, {
          color: options.zhongshuColor ?? '#8b5cf6',
          showAxis: options.showZhongshuAxis,
        })
        const pane = this.chart.panes()[0]
        pane.attachPrimitive(prim)
        this.primitives.push(prim)
      }
    }

    const markers: SeriesMarker<Time>[] = []
    // 笔序号:在每笔终点标注序号,方便定位讨论
    if (options.showBi && analysis.bis.length > 0) {
      markers.push(...buildBiIndexMarkers(analysis.bis))
    }
    // 段序号:在每段终点标注序号(蓝色 D 前缀),与笔序号(黄色)区分
    if (options.showDuan && analysis.duans.length > 0) {
      markers.push(...buildDuanIndexMarkers(analysis.duans))
    }
    if (options.showDuan && analysis.duans.length > 0) {
      const featLines = buildFeatLines(analysis.duans, analysis.bis)
      if (featLines.length > 0) {
        const prim = new FeatSequencePrimitive(this.candleSeries, this.chart, featLines)
        const pane = this.chart.panes()[0]
        pane.attachPrimitive(prim)
        this.primitives.push(prim)
      }
    }
    if (options.showFenxing && analysis.fenxings.length > 0) {
      const chanKLineTimes = analysis.chanKLines.map(k => k.openTime)
      markers.push(...buildFenxingMarkers(analysis.fenxings, chanKLineTimes))
    }
    if (options.showDivergences && analysis.divergences.length > 0) {
      for (const item of detailFeatures?.includes('divergence') === false ? [] : analysis.divergences) {
        const detail = buildDivergenceMarkerDetail(item, analysis.buySellPoints)
        this.markerDetails.set(detail.id, detail)
      }
      markers.push(...buildDivergenceMarkers(analysis.divergences))
    }
    if (options.showBuySellPoints && analysis.buySellPoints.length > 0) {
      for (const item of detailFeatures?.includes('buy_sell_points') === false ? [] : analysis.buySellPoints) {
        const detail = buildBuySellMarkerDetail(item)
        this.markerDetails.set(detail.id, detail)
      }
      markers.push(...buildBuySellMarkers(analysis.buySellPoints))
    }
    const arrangedMarkers = arrangeSeriesMarkersVertically(markers, {
      priceToCoordinate: (price) => this.candleSeries.priceToCoordinate(price),
      coordinateToPrice: (coordinate) => this.candleSeries.coordinateToPrice(coordinate as Coordinate),
    })
      .sort((a, b) => (a.time as number) - (b.time as number))
    if (arrangedMarkers.length > 0) {
      this.markersPlugin = createSeriesMarkers(this.candleSeries, arrangedMarkers)
    }
  }

  clear(): void {
    this.markerDetails.clear()
    for (const s of this.lineSeriesList) {
      this.chart.removeSeries(s)
    }
    this.lineSeriesList = []

    if (this.primitives.length > 0) {
      const pane = this.chart.panes()[0]
      for (const p of this.primitives) {
        pane.detachPrimitive(p)
      }
      this.primitives = []
    }

    if (this.markersPlugin) {
      this.markersPlugin.detach()
      this.markersPlugin = null
    }
  }

  destroy(): void {
    this.clear()
  }

  getMarkerDetail(markerId: string): IndicatorMarkerDetail | undefined {
    return this.markerDetails.get(markerId)
  }
}
