import { useEffect, useRef, useState } from 'react'
import { createChart, CandlestickSeries, ColorType, CrosshairMode } from 'lightweight-charts'
import type { IChartApi, ISeriesApi, MouseEventParams, Time } from 'lightweight-charts'
import type { RawKline, ChanAnalysis, ChanRenderOptions, IndicatorMarkerDetail, IndicatorResult } from '../core/types.ts'
import { ChanRenderer } from './ChanRenderer.ts'
import { IndicatorRenderer } from './IndicatorRenderer.ts'
import { IndicatorMarkerPopover } from '../components/IndicatorMarkerPopover.tsx'
import { placeMarkerDetailPopup, type MarkerDetailProvider } from './markerDetails.ts'

interface Props {
  /** K线数据 */
  klineData: RawKline[]
  /** 缠论分析结果(可选,由父组件传入) */
  chanAnalysis?: ChanAnalysis
  /** 缠论渲染选项(可选) */
  chanOptions?: ChanRenderOptions
  /** 指标计算结果(可选) */
  indicatorResults?: IndicatorResult[]
  onCursorTimeChange?: (time: number | null) => void
  chanDetailFeatures?: string[]
  snapshotRequestId?: number
  onSnapshot?: (dataUrl: string) => void
}

/**
 * 改造后的 Chart 组件:单周期 + LWC 原生 series + ChanRenderer 缠论叠加
 *
 * 简化点:
 *   1) 删除 Canvas 自绘层 - 改用 LWC 原生 CandlestickSeries
 *   2) 删除多周期图层逻辑 - 单周期
 *   3) 缠论叠加交给 ChanRenderer
 */
export function Chart({ klineData, chanAnalysis, chanOptions, indicatorResults, onCursorTimeChange, chanDetailFeatures, snapshotRequestId, onSnapshot }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const popupRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const chanRendererRef = useRef<ChanRenderer | null>(null)
  const indicatorRendererRef = useRef<IndicatorRenderer | null>(null)
  const detailProvidersRef = useRef<MarkerDetailProvider[]>([])
  const onCursorTimeChangeRef = useRef(onCursorTimeChange)
  const [markerPopup, setMarkerPopup] = useState<{
    detail: IndicatorMarkerDetail
    left: number
    top: number
  } | null>(null)

  useEffect(() => {
    onCursorTimeChangeRef.current = onCursorTimeChange
  }, [onCursorTimeChange])

  // 初始化图表(只创建一次)
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0c0f15' },
        textColor: '#70798a',
      },
      grid: { vertLines: { color: '#1b202a' }, horzLines: { color: '#1b202a' } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#252b37' },
      timeScale: {
        borderColor: '#252b37',
        timeVisible: true,
        secondsVisible: false,
      },
      // 缩放与平移交互(LWC v5 顶层配置)
      handleScroll: {
        mouseWheel: true,       // 滚轮横向滚动
        pressedMouseMove: true, // 按住拖拽平移
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      handleScale: {
        mouseWheel: true,        // 滚轮缩放
        pinch: true,             // 触屏捏合缩放
        axisPressedMouseMove: true,  // 在坐标轴上拖拽缩放选区
        axisDoubleClickReset: true,  // 双击坐标轴重置视图
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    })
    chartRef.current = chart
    candleRef.current = chart.addSeries(CandlestickSeries, {
      // 国内行情配色：阳线红、阴线绿。
      upColor: '#ff5b62',
      downColor: '#2fc58d',
      borderUpColor: '#ff5b62',
      borderDownColor: '#2fc58d',
      wickUpColor: '#ff5b62',
      wickDownColor: '#2fc58d',
    })
    chanRendererRef.current = new ChanRenderer(chart, candleRef.current)
    indicatorRendererRef.current = new IndicatorRenderer(chart, candleRef.current)
    detailProvidersRef.current = [chanRendererRef.current]

    const handleChartClick = (param: MouseEventParams<Time>) => {
      const objectId = param.hoveredInfo?.objectId ?? param.hoveredObjectId
      const markerId = typeof objectId === 'string' ? objectId : undefined
      const detail = markerId
        ? detailProvidersRef.current
          .map(provider => provider.getMarkerDetail(markerId))
          .find((item): item is IndicatorMarkerDetail => Boolean(item))
        : undefined

      if (!detail || !param.point || !containerRef.current) {
        setMarkerPopup(null)
        return
      }

      const position = placeMarkerDetailPopup(
        param.point,
        { width: containerRef.current.clientWidth, height: containerRef.current.clientHeight },
      )
      setMarkerPopup(current => current?.detail.id === detail.id
        ? null
        : { detail, ...position })
    }
    chart.subscribeClick(handleChartClick)
    let cursorFrame: number | null = null
    const handleCrosshairMove = (param: MouseEventParams<Time>) => {
      const time = typeof param.time === 'number' ? param.time * 1000 : null
      indicatorRendererRef.current?.setProfileTime(time)
      if (cursorFrame !== null) window.cancelAnimationFrame(cursorFrame)
      cursorFrame = window.requestAnimationFrame(() => {
        onCursorTimeChangeRef.current?.(time)
        cursorFrame = null
      })
    }
    chart.subscribeCrosshairMove(handleCrosshairMove)

    const ro = new ResizeObserver(() => {
      if (!containerRef.current || !chartRef.current) return
      chartRef.current.applyOptions({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
      })
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.unsubscribeClick(handleChartClick)
      chart.unsubscribeCrosshairMove(handleCrosshairMove)
      if (cursorFrame !== null) window.cancelAnimationFrame(cursorFrame)
      chanRendererRef.current?.destroy()
      indicatorRendererRef.current?.destroy()
      chart.remove()
      chartRef.current = null
      candleRef.current = null
      chanRendererRef.current = null
      indicatorRendererRef.current = null
      detailProvidersRef.current = []
    }
  }, [])

  useEffect(() => {
    if (!markerPopup) return
    const closeOutside = (event: PointerEvent) => {
      const target = event.target as Node
      if (popupRef.current?.contains(target) || containerRef.current?.contains(target)) return
      setMarkerPopup(null)
    }
    document.addEventListener('pointerdown', closeOutside)
    return () => document.removeEventListener('pointerdown', closeOutside)
  }, [markerPopup])

  // K线数据更新
  useEffect(() => {
    if (!candleRef.current || klineData.length === 0) return
    candleRef.current.setData(
      klineData.map(k => ({
        time: k.openTime / 1000 as Time,
        open: k.open, high: k.high, low: k.low, close: k.close,
      }))
    )
    chartRef.current?.timeScale().fitContent()
  }, [klineData])

  // 缠论渲染
  useEffect(() => {
    if (!chanRendererRef.current) return
    if (chanAnalysis && chanOptions) {
      chanRendererRef.current.render(chanAnalysis, chanOptions, chanDetailFeatures)
    } else {
      chanRendererRef.current.clear()
    }
  }, [chanAnalysis, chanOptions, chanDetailFeatures])

  // 指标渲染
  useEffect(() => {
    if (!indicatorRendererRef.current) return
    if (indicatorResults && indicatorResults.length > 0) {
      indicatorRendererRef.current.render(indicatorResults)
    } else {
      indicatorRendererRef.current.clear()
    }
  }, [indicatorResults])

  useEffect(() => {
    if (!snapshotRequestId || !chartRef.current || !onSnapshot) return
    const frame = window.requestAnimationFrame(() => {
      onSnapshot(chartRef.current!.takeScreenshot().toDataURL('image/png'))
    })
    return () => window.cancelAnimationFrame(frame)
  }, [snapshotRequestId, onSnapshot])

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="absolute inset-0" />
      {markerPopup && (
        <IndicatorMarkerPopover
          detail={markerPopup.detail}
          left={markerPopup.left}
          top={markerPopup.top}
          onClose={() => setMarkerPopup(null)}
          popupRef={popupRef}
        />
      )}
      {/* 重置视图按钮:一键回到全量视图 */}
      <button
        onClick={() => chartRef.current?.timeScale().fitContent()}
        className="absolute top-2 right-2 z-10 px-2.5 py-1.5 text-[11px] font-mono rounded-md bg-[var(--bg-tertiary)]/90 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-surface)] border border-[var(--border-primary)] transition-colors"
        title="重置视图(双击时间轴也可重置)"
      >
        重置视图
      </button>
    </div>
  )
}
