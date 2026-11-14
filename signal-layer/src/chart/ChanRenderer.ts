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
  KlineOverlap,
  BuySellPoint,
  Divergence,
  IndicatorMarkerDetail,
  Duan,
  Bi,
} from '../core/types.ts'
import { arrangeSeriesMarkersVertically, buildBuySellMarkerDetail, buildClassificationDetail, buildDivergenceMarkerDetail, buySellMarkerId, buySellMarkerLabel, classificationMarkerId, classificationMarkerLabel, divergenceMarkerId, divergenceMarkerLabel } from './markerDetails.ts'
import { ClassificationPrimitive, buildClassificationBranches } from './ClassificationPrimitive.ts'

class ZhongshuRenderer implements IPrimitivePaneRenderer {
  private readonly candleSeries: ISeriesApi<'Candlestick'>
  private readonly chart: IChartApi
  private readonly zhongshus: Zhongshu[]
  private readonly options: { color: string; showAxis: boolean; fillAlpha?: number; lineWidth?: number }

  constructor(
    candleSeries: ISeriesApi<'Candlestick'>,
    chart: IChartApi,
    zhongshus: Zhongshu[],
    options: { color: string; showAxis: boolean; fillAlpha?: number; lineWidth?: number }
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

        // 填充透明度与线宽可按调用方调整（K 线重叠级别需要更醒目）
        const alpha = Math.round((this.options.fillAlpha ?? 0.2) * 255).toString(16).padStart(2, '0')
        const fillColor = zs.broken
          ? (zs.breakDirection === 'up' ? 'rgba(255,91,98,0.15)' : 'rgba(47,197,141,0.15)')
          : this.options.color + alpha
        ctx.fillStyle = fillColor
        ctx.fillRect(x, yTop, w, h)

        ctx.strokeStyle = zs.broken
          ? (zs.breakDirection === 'up' ? '#ff5b62' : '#2fc58d')
          : this.options.color
        ctx.lineWidth = this.options.lineWidth ?? 1
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
    options: { color: string; showAxis: boolean; fillAlpha?: number; lineWidth?: number }
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
    options: { color: string; showAxis: boolean; fillAlpha?: number; lineWidth?: number }
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
    // 只画本段的特征元素：扫描确认分型时会越过段末，旧数据可能把这些笔也带进来
    const allowed = new Set(duan.biIndices ?? [])
    for (const f of duan.featElements ?? []) {
      if (!allowed.has(f.bi)) continue
      const bi = bis[f.bi]
      if (!bi) continue
      const isMerged = mergedSet.has(f.bi)
      lines.push({
        t1: bi.startTime, p1: f.first,
        t2: bi.endTime, p2: f.last,
        color: isMerged ? '#22c55e' : '#f97316',
        width: 3,
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
  // 特征序列画在笔线之上，否则 1px 虚线会和同路径的笔线重叠、被完全盖住
  zOrder(): 'top' {
    return 'top'
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

interface EndpointLabelPart {
  text: string
  color: string
}

interface EndpointLabel {
  time: number
  price: number
  side: 'above' | 'below'
  parts: EndpointLabelPart[]
}

/**
 * 笔序号与段端点的纯文字标注。
 *
 * - 笔序号用笔线颜色，段端点用段线颜色；不再使用圆点/方块图标。
 * - 同一时间、同一价格上的笔序号和 D 标记合并成一组，并排绘制（如 `16 D1`）。
 * - 不重叠的端点仍按方向放在价位上方或下方。
 */
function buildEndpointLabels(analysis: ChanAnalysis, options: ChanRenderOptions): EndpointLabel[] {
  interface RawLabel {
    text: string
    color: string
    side: 'above' | 'below'
    order: number
  }
  const groups = new Map<string, { time: number; price: number; labels: RawLabel[] }>()
  const add = (
    time: number, price: number, text: string, color: string, side: 'above' | 'below', order: number,
  ) => {
    const key = `${time}:${price.toFixed(6)}`
    const group = groups.get(key) ?? { time, price, labels: [] }
    group.labels.push({ text, color, side, order })
    groups.set(key, group)
  }

  if (options.showBi && analysis.bis.length > 0) {
    const color = options.biColor ?? '#e7c66b'
    const first = analysis.bis[0]
    add(first.startTime, first.startPrice, '0', color, first.direction === 'up' ? 'below' : 'above', 0)
    analysis.bis.forEach((bi, index) => {
      add(bi.endTime, bi.endPrice, `${index + 1}`, color, bi.direction === 'up' ? 'above' : 'below', 0)
    })
  }

  if (options.showDuan && analysis.duans.length > 0) {
    const color = options.duanColor ?? '#3b82f6'
    const first = analysis.duans[0]
    add(first.startTime, first.startPrice, 'D0', color, first.direction === 'up' ? 'below' : 'above', 1)
    analysis.duans.forEach((duan, index) => {
      add(duan.endTime, duan.endPrice, `D${index + 1}`, color, duan.direction === 'up' ? 'above' : 'below', 1)
    })
  }

  return [...groups.values()]
    .sort((a, b) => a.time - b.time)
    .map((group) => {
      const labels = [...group.labels].sort((a, b) => a.order - b.order)
      const anchor = labels.find((item) => item.order === 0) ?? labels[0]
      return {
        time: group.time,
        price: group.price,
        side: anchor.side,
        parts: labels.map(({ text, color }) => ({ text, color })),
      }
    })
}

class EndpointLabelRenderer implements IPrimitivePaneRenderer {
  private readonly chart: IChartApi
  private readonly series: ISeriesApi<'Candlestick'>
  private readonly labels: EndpointLabel[]

  constructor(chart: IChartApi, series: ISeriesApi<'Candlestick'>, labels: EndpointLabel[]) {
    this.chart = chart
    this.series = series
    this.labels = labels
  }

  draw(target: CanvasRenderingTarget2D): void {
    const timeScale = this.chart.timeScale()
    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context
      ctx.save()
      ctx.font = '600 12px -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif'
      ctx.textBaseline = 'middle'
      for (const label of this.labels) {
        const x = timeScale.timeToCoordinate(label.time / 1000 as Time)
        const y = this.series.priceToCoordinate(label.price)
        if (x === null || y === null) continue
        const widths = label.parts.map((part) => ctx.measureText(part.text).width)
        const separatorGap = 4
        const separatorWidth = 1
        const between = label.parts.length > 1 ? separatorGap * 2 + separatorWidth : 0
        const total = widths.reduce((sum, width) => sum + width, 0) + between * Math.max(0, label.parts.length - 1)
        const startX = Math.max(4, Math.min(x - total / 2, 1184 - total))
        const textY = Math.max(12, Math.min(label.side === 'above' ? y - 13 : y + 15, 842))
        let cursor = startX
        for (let i = 0; i < label.parts.length; i += 1) {
          const part = label.parts[i]
          ctx.lineWidth = 3
          ctx.strokeStyle = 'rgba(10, 13, 19, 0.95)'
          ctx.strokeText(part.text, cursor, textY)
          ctx.fillStyle = part.color
          ctx.fillText(part.text, cursor, textY)
          cursor += widths[i]
          if (i < label.parts.length - 1) {
            // 多标签之间用一根中性细竖线分隔，避免类别颜色互相干扰
            const lineX = cursor + separatorGap + separatorWidth / 2
            ctx.beginPath()
            ctx.moveTo(lineX, textY - 5)
            ctx.lineTo(lineX, textY + 5)
            ctx.strokeStyle = '#8b93a7'
            ctx.lineWidth = 1
            ctx.stroke()
            cursor += between
          }
        }
      }
      ctx.restore()
    })
  }
}

class EndpointLabelPaneView implements IPanePrimitivePaneView {
  private readonly _renderer: EndpointLabelRenderer

  constructor(chart: IChartApi, series: ISeriesApi<'Candlestick'>, labels: EndpointLabel[]) {
    this._renderer = new EndpointLabelRenderer(chart, series, labels)
  }

  renderer(): IPrimitivePaneRenderer | null {
    return this._renderer
  }

  // 端点文字画在 K 线/笔线/特征线之上
  zOrder(): 'top' {
    return 'top'
  }
}

class EndpointLabelPrimitive implements IPanePrimitive {
  private readonly views: IPanePrimitivePaneView[]

  constructor(chart: IChartApi, series: ISeriesApi<'Candlestick'>, labels: EndpointLabel[]) {
    this.views = [new EndpointLabelPaneView(chart, series, labels)]
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
  private analysis: ChanAnalysis | null = null
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
    this.analysis = analysis

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

    // 走势完全分类：从最后一根 K 线向右画出三条分支（箭头 + 标签）
    // 只有缠论图层里显式打开「完全分类」才画
    if (options.showClassification && analysis.classification && analysis.classification.scenarios.length > 0) {
      const last = analysis.bis[analysis.bis.length - 1]
      const lastZhongshu = analysis.zhongshus[analysis.zhongshus.length - 1]
      const lastTime = last?.endTime ?? lastZhongshu?.endTime
      const lastPrice = analysis.classification.lastClose
      const branches = buildClassificationBranches(analysis.classification)
      if (lastTime && lastPrice !== undefined && branches.length > 0) {
        const prim = new ClassificationPrimitive(this.chart, this.candleSeries, lastTime, lastPrice, branches)
        this.candleSeries.attachPrimitive(prim)
        this.primitives.push(prim)
      }
    }

    // K 线重叠级别：零缠口径的只读级别参考。独立于笔/中枢，序号偏移 10000
    // 避免与真实中枢编号混淆。按级别分组上色：重叠根数越多级别越高，颜色越醒目。
    if (options.showOverlaps && analysis.overlaps.length > 0) {
      const levels: Array<{ level: KlineOverlap['level']; color: string }> = [
        { level: 'sub1', color: '#f59e0b' },   // 长重叠（原「次级别」）
        { level: 'sub2', color: '#22d3ee' },   // 中重叠（原「次次级别」）
        { level: 'sub3', color: '#f472b6' },   // 短重叠（过渡区）
      ]
      const pane = this.chart.panes()[0]
      for (const group of levels) {
        const items = analysis.overlaps.filter((item) => item.level === group.level)
        if (items.length === 0) continue
        const overlapBoxes: Zhongshu[] = items.map((item, index) => ({
          index: 10000 + index,
          high: item.high,
          low: item.low,
          mid: (item.high + item.low) / 2,
          startTime: item.startTime,
          endTime: item.endTime,
          level: 'bi',
          broken: false,
          biIndices: [],
        }))
        const prim = new ZhongshuPrimitive(this.candleSeries, this.chart, overlapBoxes, {
          color: group.color,
          showAxis: false,
          fillAlpha: 0.30,
          lineWidth: 2,
        })
        pane.attachPrimitive(prim)
        this.primitives.push(prim)
      }
    }

    const markers: SeriesMarker<Time>[] = []
    // 走势完全分类：挂在最后一笔的终点，点击弹出后续分类；只在开关打开时显示
    if (options.showClassification && analysis.classification && analysis.classification.scenarios.length > 0) {
      const last = analysis.bis[analysis.bis.length - 1]
      const lastZhongshu = analysis.zhongshus[analysis.zhongshus.length - 1]
      const lastTime = last?.endTime ?? lastZhongshu?.endTime
      if (lastTime) {
        markers.push({
          time: (lastTime / 1000) as Time,
          position: 'aboveBar',
          color: '#e7c66b',
          shape: 'circle',
          text: classificationMarkerLabel(),
          id: classificationMarkerId(),
        })
      }
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
    // 笔序号 / 段端点：纯文字标注；重合时并排显示
    const endpointLabels = buildEndpointLabels(analysis, options)
    if (endpointLabels.length > 0) {
      const prim = new EndpointLabelPrimitive(this.chart, this.candleSeries, endpointLabels)
      const pane = this.chart.panes()[0]
      pane.attachPrimitive(prim)
      this.primitives.push(prim)
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
    if (markerId === classificationMarkerId() && this.analysis?.classification) {
      return buildClassificationDetail(this.analysis.classification)
    }
    return this.markerDetails.get(markerId)
  }
}
