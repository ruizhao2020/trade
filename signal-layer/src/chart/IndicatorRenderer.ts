/**
 * ============================================================================
 * 指标通用渲染器
 * ============================================================================
 *
 * 核心思想:根据后端返回的 RenderSpec 自动创建 LWC Series,前端永远不用改。
 *
 * 工作流程:
 *   1. Chart 组件收到 IndicatorResult[]
 *   2. 遍历每个 result,查 render.window 决定画在主图还是子图
 *   3. 遍历 render.plots,根据 plot.type 创建对应的 LineSeries / HistogramSeries
 *   4. 从 result.values 取 plot.field 对应的数据,setData
 *
 * 新增指标时前端零改动 —— 后端只要返回正确的 render 描述,就能自动画出来。
 */

import type { IChartApi, ISeriesApi, Time, ISeriesMarkersPluginApi, SeriesMarker } from 'lightweight-charts'
import { LineSeries, HistogramSeries, createSeriesMarkers } from 'lightweight-charts'
import type { IndicatorResult, RenderSpec } from '../core/types.ts'

interface CreatedSeries {
  indicatorKey: string
  series: Array<ISeriesApi<'Line'> | ISeriesApi<'Histogram'>>
  markerPlugins: ISeriesMarkersPluginApi<Time>[]
  paneIndex: number
}

export class IndicatorRenderer {
  private chart: IChartApi
  private candleSeries: ISeriesApi<'Candlestick'>
  private created: CreatedSeries[] = []
  private subPaneCount = 1

  constructor(chart: IChartApi, candleSeries: ISeriesApi<'Candlestick'>) {
    this.chart = chart
    this.candleSeries = candleSeries
  }

  /**
   * 渲染所有指标
   * - 先清理旧 series,再根据新结果重新创建
   * - 支持增量更新(同 key 的指标复用 series)
   */
  render(results: IndicatorResult[]) {
    // 简单策略:全量重建。后续可优化为增量对比
    this.clear()

    for (const result of results) {
      if (!result.render || result.values.length === 0) continue
      this._renderOne(result)
    }
  }

  /** 清理所有已创建的 series */
  clear() {
    for (const item of this.created) {
      for (const s of item.series) {
        try { this.chart.removeSeries(s) } catch { /* already removed */ }
      }
      for (const mp of item.markerPlugins) {
        try { mp.detach() } catch { /* already detached */ }
      }
    }
    this.created = []
    this.subPaneCount = 1
  }

  /** 渲染单个指标 */
  private _renderOne(result: IndicatorResult) {
    const render: RenderSpec = result.render
    const key = this._makeKey(result)
    const paneIndex = render.window === 'main' ? 0 : this._allocSubPane()

    const series: Array<ISeriesApi<'Line'> | ISeriesApi<'Histogram'>> = []
    const markerPlugins: ISeriesMarkersPluginApi<Time>[] = []

    for (const plot of render.plots) {
      if (plot.type === 'marker') continue
      const data = result.values
        .map(v => ({
          time: (v.time / 1000) as Time,
          value: v[plot.field],
        }))
        .filter(d => d.value !== undefined && d.value !== null && !Number.isNaN(d.value))

      if (data.length === 0) continue

      if (plot.type === 'line') {
        const s = this.chart.addSeries(LineSeries, {
          color: plot.color,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        }, paneIndex)
        s.setData(data)
        series.push(s)
      } else if (plot.type === 'histogram') {
        const s = this.chart.addSeries(HistogramSeries, {
          color: plot.color,
          priceLineVisible: false,
          lastValueVisible: false,
        }, paneIndex)
        s.setData(data)
        series.push(s)
      }
    }

    if (render.markers && render.window === 'main') {
      for (const ms of render.markers) {
        const markers: SeriesMarker<Time>[] = []
        for (const v of result.values) {
          const val = v[ms.field]
          if (!val || val === 0) continue
          const isBuy = val > 0
          const position = isBuy ? 'belowBar' as const : 'aboveBar' as const
          const labelIndex = ms.labelIndexField ? v[ms.labelIndexField] : undefined
          const labelTagCode = ms.labelTagField ? v[ms.labelTagField] : undefined
          const labelTag = labelTagCode !== undefined && Number.isFinite(labelTagCode)
            ? ms.labelTags?.[Math.trunc(labelTagCode)]
            : undefined
          const label = `${isBuy ? ms.buyLabel : ms.sellLabel}${labelIndex !== undefined && Number.isFinite(labelIndex) ? Math.trunc(labelIndex) : ''}${labelTag ? ` · ${labelTag}` : ''}`
          const markerBase = {
            time: (v.time / 1000) as Time,
            color: isBuy ? ms.buyColor : ms.sellColor,
            shape: isBuy ? 'arrowUp' as const : 'arrowDown' as const,
            text: label,
            size: ms.size ?? 2,
          }
          const markerPrice = ms.priceField ? v[ms.priceField] : undefined
          if (markerPrice !== undefined && Number.isFinite(markerPrice)) {
            markers.push({
              ...markerBase,
              position: isBuy ? 'atPriceBottom' : 'atPriceTop',
              price: markerPrice,
            })
          } else {
            // 透明占位标记先参与原生堆叠，使所有买卖箭头与对应 K 线保持一致的屏幕间距。
            if (ms.spacing && ms.spacing > 0) {
              markers.push({
                time: markerBase.time,
                position,
                color: 'rgba(0, 0, 0, 0)',
                shape: 'circle',
                size: ms.spacing,
              })
            }
            markers.push({
              ...markerBase,
              position,
            })
          }
        }
        if (markers.length > 0) {
          const mp = createSeriesMarkers(this.candleSeries, markers)
          markerPlugins.push(mp)
        }
      }
    }

    if (series.length > 0 || markerPlugins.length > 0) {
      this.created.push({ indicatorKey: key, series, markerPlugins, paneIndex })
    }
  }

  /** 生成指标唯一 key,如 "ma:period=5" */
  private _makeKey(result: IndicatorResult): string {
    const params = Object.entries(result.params)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${k}=${v}`)
      .join(',')
    return `${result.type}:${params}`
  }

  /**
   * 分配子图索引。
   * 策略:每个 sub 指标独占一个子图,便于不同指标分开看。
   * 后续可优化为同类型指标共用子图。
   */
  private _allocSubPane(): number {
    return this.subPaneCount++
  }

  destroy() {
    this.clear()
  }
}
