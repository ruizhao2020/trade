export const VOLUME_CLASS_STYLES: Record<number, { label: string; color: string }> = {
  0: { label: '常规', color: '#596477' },
  1: { label: '缩量', color: '#758195' },
  2: { label: '增量', color: '#596477' },
  3: { label: '倍量', color: '#e7b75f' },
  4: { label: '三倍量', color: '#b989f5' },
  5: { label: '多倍量', color: '#ff6b72' },
}

export const VOLUME_SHAPE_STYLES: Record<number, { label: string; color: string }> = {
  0: { label: '常规', color: '#596477' },
  1: { label: '高量柱', color: '#56c7e8' },
  2: { label: '低量柱', color: '#8f9caf' },
  3: { label: '平量柱', color: '#6c8cff' },
  4: { label: '梯量柱', color: '#e7b75f' },
  5: { label: '连续缩量', color: '#9b8cf2' },
}

export const VOLUME_UP_COLOR = '#ff5b62'
export const VOLUME_DOWN_COLOR = '#2fc58d'
export const GENERAL_PILLAR_COLOR = '#6c8cff'
export const GOLDEN_PILLAR_COLOR = '#e7c66b'

export const VOLUME_LEGEND = [0, 1, 2, 3, 4, 5].map(code => ({
  code,
  followsPrice: code === 0 || code === 2,
  ...VOLUME_CLASS_STYLES[code]!,
}))

export const VOLUME_SHAPE_LEGEND = [1, 2, 3, 4, 5].map(code => ({
  code,
  followsPrice: false,
  ...VOLUME_SHAPE_STYLES[code]!,
}))

export function volumeClassStyle(value: number | undefined, isUp?: boolean) {
  const code = value === undefined || !Number.isFinite(value) ? 0 : Math.trunc(value)
  const style = VOLUME_CLASS_STYLES[code] ?? VOLUME_CLASS_STYLES[0]!
  if ((code === 0 || code === 2) && isUp !== undefined) {
    return { ...style, color: isUp ? '#ff5b62' : '#2fc58d' }
  }
  return style
}

export function volumeShapeStyle(value: number | undefined) {
  const code = value === undefined || !Number.isFinite(value) ? 0 : Math.trunc(value)
  return VOLUME_SHAPE_STYLES[code] ?? VOLUME_SHAPE_STYLES[0]!
}

export function volumeBarStyle(classValue: number | undefined, shapeValue: number | undefined, isUp?: boolean) {
  const classCode = classValue === undefined || !Number.isFinite(classValue) ? 0 : Math.trunc(classValue)
  // 倍量及以上优先突出；普通/增量/缩量再使用基础量柱形态配色。
  if (classCode >= 3) return volumeClassStyle(classCode, isUp)
  const shapeCode = shapeValue === undefined || !Number.isFinite(shapeValue) ? 0 : Math.trunc(shapeValue)
  if (shapeCode > 0) return volumeShapeStyle(shapeCode)
  return volumeClassStyle(classCode, isUp)
}

export function volumeBarColor(isUp: boolean) {
  return isUp ? VOLUME_UP_COLOR : VOLUME_DOWN_COLOR
}

/**
 * 这条柱状序列要不要按当日阴阳着红绿。
 *
 * 判据取**数据**而不是指标名：只要画的是 `volume` 柱、且行里带了 `is_up`
 * 标志，就逐根上色——成交量、量柱结构、量价都是这么输出的。
 *
 * 这里曾经写死成两个指标 type（`volume` / `volume_structure`），于是新加的
 * 量价画出来的量柱是一片灰：加指标的人不会想起来还有这么个列表要改。
 */
export function isVolumeBarSeries(plotField: string, values: Record<string, number>[]): boolean {
  return plotField === 'volume' && values.some(value => Number.isFinite(value.is_up))
}

/** 自己就带红绿成交量柱的指标：它们会画量能副图，不需要再叠一个普通「成交量」。 */
const SELF_CONTAINED_VOLUME_PANES = new Set(['volume_structure', 'volume_price'])

/**
 * 判断某个指标是否该因为"已经有人在画量能副图"而跳过。
 *
 * 只影响画图：同一个标的上同时开「量柱结构 / 量价」和普通「成交量」时，
 * 会出现两个几乎一样的量能副图，所以只画前者那个。计算与数据详情不受影响，
 * 两个指标的数值照样都在。
 */
export function shouldSkipVolumePane(indicatorType: string, allTypes: string[]): boolean {
  if (indicatorType !== 'volume') return false
  return allTypes.some(type => SELF_CONTAINED_VOLUME_PANES.has(type))
}
