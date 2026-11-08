import type { BuySellPoint, Divergence, IndicatorMarkerDetail, IndicatorResult, ChanClassification } from '../core/types.ts'
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

export function buySellMarkerId(point: BuySellPoint): string {
  return `chan:buy-sell:${point.type}:${point.time}:${point.biIndex}`
}

export function buySellMarkerLabel(point: BuySellPoint): string {
  return `[${BUY_SELL_LABELS[point.type] ?? point.type}]`
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

export function buildBuySellMarkerDetail(point: BuySellPoint): IndicatorMarkerDetail {
  const label = BUY_SELL_LABELS[point.type] ?? point.type
  const isBuy = point.type.startsWith('buy')
  const reasonLabel: Record<string, string> = {
    bottom_divergence: '底背驰确认',
    top_divergence: '顶背驰确认',
  }
  return {
    id: buySellMarkerId(point),
    title: label,
    subtitle: `${isBuy ? '买点' : '卖点'} · ${point.confirmed ? '已确认' : '待确认'}`,
    accentColor: isBuy ? '#36c995' : '#ff6b72',
    fields: [
      { label: '发生时间', value: dateTimeText(point.time) },
      { label: '标记价格', value: numberText(point.price) },
      { label: '所属中枢', value: point.zhongshuIndex === undefined ? '—' : `中枢 ${point.zhongshuIndex}` },
      { label: '对应笔', value: `笔 ${point.biIndex}` },
      { label: '确认状态', value: point.confirmed ? '已确认' : '待确认' },
      { label: '信号强度', value: numberText(point.strength) },
      ...(point.reason ? [{ label: '触发依据', value: reasonLabel[point.reason] ?? point.reason }] : []),
    ],
  }
}

/**
 * 点击某根 K 线时，若该根上有「量价」形态触发，构造详情浮窗数据。
 *
 * 只认带 rule 的标记：其他指标的标记没有口径文本，不参与这个弹窗。
 * 同一根上多个形态同时成立时，按标记顺序取第一个作标题，其余列进"同时成立"。
 * "信号 N 号"里的 N 是形态的对外编号（1 起、只增不改），用于交流时指认信号。
 *
 * 纯函数，便于单测（见 markerDetails.test.ts）。
 */
export function buildFormMarkerDetail(
  result: IndicatorResult,
  timeSeconds: number,
  field?: string,
): IndicatorMarkerDetail | undefined {
  const formMarkers = (result.render?.markers ?? []).filter((marker) => marker.rule)
  if (formMarkers.length === 0) return undefined

  const row = result.values.find((value) => Math.round(value.time / 1000) === timeSeconds)
  if (!row) return undefined

  const fired = formMarkers.filter(
    (marker) => Boolean(row[marker.field]) && (!field || marker.field === field),
  )
  if (fired.length === 0) return undefined

  const numbers = formSignalNumbers(result)
  const sequenceOf = (markerField: string) => numbers.get(`${markerField}:${Math.round(row.time / 1000)}`)
  const primary = fired[0]!
  const isBuy = Number(row[primary.field]) > 0
  const fields = [
    { label: '时间', value: dateText(row.time) },
    { label: '相对量能', value: numberText(row.relative_volume) },
    { label: '当日涨幅', value: pctText(row.change_pct) },
    { label: '距高点回撤', value: magnitudeText(row.drawdown_pct) },
    { label: '成交量', value: numberText(row.volume) },
    { label: '量能基线', value: numberText(row.baseline) },
  ]
  if (fired.length > 1) {
    fields.push({
      label: '同时成立',
      value: fired.slice(1).map((marker) => {
        const number = sequenceOf(marker.field)
        return number ? `${marker.buyLabel} #${number}` : marker.buyLabel
      }).join('、'),
    })
  }

  return {
    id: `${result.type}:${primary.field}:${timeSeconds}`,
    title: isBuy ? primary.buyLabel : primary.sellLabel,
    subtitle: `信号 ${sequenceOf(primary.field) ? `#${sequenceOf(primary.field)}` : '—'} · ${isBuy ? '买入侧' : '顶部预警'}`,
    accentColor: isBuy ? '#ff5b62' : '#2fc58d',
    fields,
    reasonsTitle: '计算口径',
    reasons: [fillRule(primary.rule ?? '', result.params)],
  }
}

/** 把口径模板里的 {param} 换成实际参数——改了参数，弹窗里的说明也跟着变。 */
export function fillRule(rule: string, params: Record<string, number>): string {
  return rule.replace(/\{(\w+)\}/g, (match, key: string) => {
    const value = params[key]
    return value === undefined ? match : String(value)
  })
}

/**
 * 形态标记的自增编号：在当前图的数据范围内，按时间先后、同一根再按形态顺序，
 * 每个触发占一个号（同一根上两个形态算两个号）。
 *
 * 键是 `字段:秒级时间`，用于给图上的标记文字和弹窗取号。
 */
export function formSignalNumbers(result: IndicatorResult): Map<string, number> {
  const formMarkers = (result.render?.markers ?? []).filter((marker) => marker.rule)
  const numbers = new Map<string, number>()
  let sequence = 0
  for (const value of result.values) {
    const timeSeconds = Math.round(value.time / 1000)
    for (const marker of formMarkers) {
      if (!value[marker.field]) continue
      numbers.set(`${marker.field}:${timeSeconds}`, ++sequence)
    }
  }
  return numbers
}

/** 约定：带弹窗的指标文字用中括号包起来；有自增编号时写成 `[12. 放量突破]`。 */
export function popupMarkerLabel(label: string, hasPopup: boolean, sequence?: number): string {
  if (!hasPopup) return label
  return sequence ? `[${sequence}. ${label}]` : `[${label}]`
}

/** 指标形态标记的 id：点击时据此找回具体是哪一根、哪一个形态。 */
export function formMarkerId(resultType: string, field: string, timeSeconds: number): string {
  return `form:${resultType}:${field}:${timeSeconds}`
}

export interface FormMarkerRef {
  resultType: string
  field: string
  timeSeconds: number
}

/** 解析标记 id；不是形态标记（如缠论的 chan: 前缀）时返回 undefined。 */
export function parseFormMarkerId(markerId: string): FormMarkerRef | undefined {
  const parts = markerId.split(':')
  if (parts[0] !== 'form' || parts.length < 4) return undefined
  const [, resultType, field] = parts
  const timeSeconds = Number(parts[3])
  if (!resultType || !field || !Number.isFinite(timeSeconds)) return undefined
  return { resultType, field, timeSeconds }
}

function pctText(value: number | undefined): string {
  if (value === undefined || value === null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

/** 幅度（如回撤）不是涨跌，不带正负号。 */
function magnitudeText(value: number | undefined): string {
  if (value === undefined || value === null || !Number.isFinite(value)) return '—'
  return `${value.toFixed(2)}%`
}

function dateText(epochMs: number): string {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(epochMs))
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

function markerOffset(markerId: string | undefined): number {
  // 第一层比原来的 0.65 缩短约三分之一；后续层级留出完整间隔，
  // 保证笔端点、段端点、背驰和买卖点不会互相覆盖。
  if (markerId?.startsWith('chan:bi-point:')) return 0.43
  if (markerId?.startsWith('chan:duan-point:')) return 1.55
  if (markerId?.startsWith('chan:divergence:')) return 2.8
  if (markerId?.startsWith('chan:buy-sell:')) return 4.1
  return 5.3
}

function markerPixelOffset(markerId: string | undefined): number {
  // 固定像素层级可避免价格区间或缩放比例变化后重新发生重叠。
  // 笔端点距离 K 线为 8px；每个后续层至少预留 24px，覆盖图标与文字高度。
  if (markerId?.startsWith('chan:bi-point:')) return 8
  if (markerId?.startsWith('chan:duan-point:')) return 34
  if (markerId?.startsWith('chan:divergence:')) return 60
  if (markerId?.startsWith('chan:buy-sell:')) return 88
  return 116
}

export interface MarkerCoordinateAdapter {
  priceToCoordinate(price: number): number | null
  coordinateToPrice(coordinate: number): number | null
}

/** 将同一根 K 线、同一侧的标记按固定层级沿竖直方向错开。 */
export function arrangeSeriesMarkersVertically(markers: SeriesMarker<Time>[], coordinates?: MarkerCoordinateAdapter): SeriesMarker<Time>[] {
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
    // 以同一根 K 线和同一侧为一组：不同算法可能产生极小的价格误差，
    // 仍应视为同一点进行垂直排布，避免文字互相覆盖。
    const key = `${String(marker.time)}:${side}`
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
    sorted.forEach((marker) => {
      const anchorCoordinate = coordinates?.priceToCoordinate(anchor)
      if (anchorCoordinate !== undefined && anchorCoordinate !== null && coordinates) {
        const pixelDirection = marker.position === 'atPriceTop' ? -1 : 1
        const price = coordinates.coordinateToPrice(anchorCoordinate + pixelDirection * markerPixelOffset(marker.id))
        arranged.push({ ...marker, price: price ?? marker.price })
      } else {
        arranged.push({ ...marker, price: anchor + direction * step * markerOffset(marker.id) })
      }
    })
  }
  return arranged
}


const CLASSIFICATION_MARKER_ID = 'chan:classification'

export function classificationMarkerId(): string {
  return CLASSIFICATION_MARKER_ID
}

export function classificationMarkerLabel(): string {
  return '[完全分类]'
}

export function buildClassificationDetail(classification: ChanClassification): IndicatorMarkerDetail {
  const positionLabel = {
    above: '中枢上方', inside: '中枢内', below: '中枢下方', unknown: '未知',
  }[classification.position]
  return {
    id: CLASSIFICATION_MARKER_ID,
    title: '走势完全分类',
    subtitle: `当前价 ${classification.lastClose ?? '—'} · ${positionLabel}`,
    accentColor: '#e7c66b',
    fields: [
      { label: '中枢上沿', value: classification.zhongshuHigh === undefined ? '—' : String(classification.zhongshuHigh) },
      { label: '中枢下沿', value: classification.zhongshuLow === undefined ? '—' : String(classification.zhongshuLow) },
      { label: '当前位置', value: positionLabel },
    ],
    reasons: classification.scenarios.map((item) => (
      `${item.active ? '● ' : '○ '}${item.label}：${item.condition} → ${item.implication}`
    )),
    reasonsTitle: '后续走势的完全分类（● 已满足前提）',
  }
}
