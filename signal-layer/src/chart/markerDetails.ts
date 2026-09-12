import type { BuySellPoint, Divergence, IndicatorMarkerDetail } from '../core/types.ts'
import type { SeriesMarker, Time } from 'lightweight-charts'

const BUY_SELL_LABELS: Record<string, string> = {
  buy1: '一买', buy2: '二买', buy3: '三买',
  sell1: '一卖', sell2: '二卖', sell3: '三卖',
}

export interface MarkerDetailProvider {
  getMarkerDetail(markerId: string): IndicatorMarkerDetail | undefined
}

export function divergenceMarkerId(item: Divergence): string {
  return `chan:divergence:${item.time}:${item.index}`
}

export function divergenceMarkerLabel(item: Divergence): string {
  return item.type === 'bottom' ? '[底背驰]' : '[顶背驰]'
}

function numberText(value: number): string {
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 4 }).format(value)
}

function dateTimeText(epochMs: number): string {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(epochMs))
}

export function buildDivergenceMarkerDetail(
  item: Divergence,
  buySellPoints: BuySellPoint[],
): IndicatorMarkerDetail {
  const isBottom = item.type === 'bottom'
  const linkedPoint = buySellPoints.find(point => point.divergenceIndex === item.index)
  const decay = Math.max(0, (1 - item.strengthRatio) * 100)

  return {
    id: divergenceMarkerId(item),
    title: isBottom ? '底背驰' : '顶背驰',
    subtitle: `${item.kind === 'consolidation' ? '盘整背驰' : item.kind} · 笔级别`,
    accentColor: isBottom ? '#48c7e8' : '#d77dff',
    fields: [
      { label: '发生时间', value: dateTimeText(item.time) },
      { label: '标记价格', value: numberText(item.price) },
      { label: '所属中枢', value: `中枢 ${item.zhongshuIndex}` },
      { label: '对比笔', value: `笔 ${item.referenceBiIndex}` },
      { label: '离开笔', value: `笔 ${item.currentBiIndex}` },
      { label: '力度对比', value: `${numberText(item.referencePower)} → ${numberText(item.currentPower)}` },
      { label: '力度衰减', value: `${decay.toFixed(2)}%` },
      { label: '确认状态', value: item.confirmed ? '已确认' : '待确认' },
      ...(linkedPoint ? [{ label: '对应信号', value: BUY_SELL_LABELS[linkedPoint.type] ?? linkedPoint.type }] : []),
    ],
    reasons: item.reasons,
  }
}

export function placeMarkerDetailPopup(
  point: { x: number; y: number },
  container: { width: number; height: number },
  popup = { width: 300, height: 340 },
): { left: number; top: number } {
  const gap = 14
  const padding = 12
  const preferredLeft = point.x + gap + popup.width <= container.width - padding
    ? point.x + gap
    : point.x - popup.width - gap
  const preferredTop = point.y + gap + popup.height <= container.height - padding
    ? point.y + gap
    : point.y - popup.height - gap

  return {
    left: Math.max(padding, Math.min(preferredLeft, container.width - popup.width - padding)),
    top: Math.max(padding, Math.min(preferredTop, container.height - popup.height - padding)),
  }
}

function markerPriority(markerId: string | undefined): number {
  if (markerId?.startsWith('chan:bi-point:')) return 1
  if (markerId?.startsWith('chan:duan-point:')) return 2
  if (markerId?.startsWith('chan:divergence:')) return 3
  if (markerId?.startsWith('chan:buy-sell:')) return 4
  return 5
}

/** 将同一时间、同一价格、同一方向的标记按固定顺序沿竖直方向错开。 */
export function arrangeSeriesMarkersVertically(markers: SeriesMarker<Time>[]): SeriesMarker<Time>[] {
  type PriceMarker = SeriesMarker<Time> & { price: number }
  const groups = new Map<string, PriceMarker[]>()
  const passthrough: SeriesMarker<Time>[] = []

  for (const marker of markers) {
    const markerPrice = marker.price
    if (typeof markerPrice !== 'number' || !Number.isFinite(markerPrice)) {
      passthrough.push(marker)
      continue
    }
    const side = marker.position === 'atPriceTop' ? 'top' : marker.position === 'atPriceBottom' ? 'bottom' : ''
    if (!side) {
      passthrough.push(marker)
      continue
    }
    const key = `${String(marker.time)}:${side}:${markerPrice.toPrecision(12)}`
    const group = groups.get(key) ?? []
    group.push(marker as PriceMarker)
    groups.set(key, group)
  }

  const arranged = [...passthrough]
  for (const group of groups.values()) {
    const sorted = [...group].sort((a, b) => markerPriority(a.id) - markerPriority(b.id))
    const anchor = sorted[0].price
    const direction = sorted[0].position === 'atPriceTop' ? 1 : -1
    const step = Math.max(Math.abs(anchor) * 0.008, 0.01)
    sorted.forEach((marker, index) => {
      arranged.push({ ...marker, price: anchor + direction * step * (index + 1) })
    })
  }
  return arranged
}
