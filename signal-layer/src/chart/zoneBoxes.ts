import type { PlotSpec } from '../core/types.ts'

/**
 * 流动性聚集区的方框（生成 → 聚集 → 被扫荡 → 消失）。
 *
 * 后端每个槽位给一组兄弟字段：`zone_{k}_low` / `_high` / `_consumed` / `_swept`
 * / `_swept_from_top`。这里把它们还原成一个方框：左右边界由字段出现的时间范围
 * 决定（后端已经按"生成处 → 被扫荡处"裁好，未被扫荡的延伸到最后一根），
 * 上下边界取该槽位最后一行的值（区带可能随枢轴合并微调，画最终定义）。
 *
 * **填充表示"流动性还在"**：
 * - 生成 / 聚集：实线框 + 填满
 * - 被扫荡：虚线框，填充按剩余比例递减，从被扫荡的那一侧开始抽空
 * - 完全扫荡：虚线框 + 不填充
 *
 * 为什么把这段逻辑单独放在这里：画布的绘制代码在这个仓库里测不到
 * （没有 canvas mock），所以把"哪些槽位要画、画多大、实线还是虚线、填充多少"
 * 这些判断挤到纯函数里，绘制层只负责照着画。
 */
export interface ZoneBox {
  slot: number
  label: string
  color: string
  startTime: number
  endTime: number
  low: number
  high: number
  /** 已被拿走的比例 0..1 */
  consumedRatio: number
  /** 填充（＝剩余流动性）应该从哪一侧起算：true 自上沿向下 */
  fillFromTop: boolean
  /** 已被扫荡（边框转虚线） */
  swept: boolean
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** 槽位字段前缀，如 `zone_3_low` → `zone_3_`。 */
function slotPrefix(field: string): string | null {
  const match = /^(zone_\d+)_low$/.exec(field)
  return match ? `${match[1]}_` : null
}

export function isZonePlot(plot: PlotSpec): boolean {
  return plot.type === 'zone' && slotPrefix(plot.field) !== null
}

export function buildZoneBoxes(
  values: Array<Record<string, unknown>>,
  plots: PlotSpec[],
): ZoneBox[] {
  const boxes: ZoneBox[] = []
  for (const plot of plots) {
    if (!isZonePlot(plot)) continue
    const prefix = slotPrefix(plot.field)!
    const slot = Number(prefix.slice('zone_'.length, -1))

    let firstIndex = -1
    let lastIndex = -1
    for (let index = 0; index < values.length; index += 1) {
      if (finiteNumber(values[index]?.[`${prefix}low`]) === null) continue
      if (firstIndex === -1) firstIndex = index
      lastIndex = index
    }
    if (firstIndex === -1) continue

    const head = values[firstIndex]!
    const tail = values[lastIndex]!
    const low = finiteNumber(tail[`${prefix}low`])
    const high = finiteNumber(tail[`${prefix}high`])
    const startTime = finiteNumber(head.time)
    const endTime = finiteNumber(tail.time)
    if (low === null || high === null || startTime === null || endTime === null) continue
    if (high <= low) continue

    const sweptFromTop = finiteNumber(tail[`${prefix}swept_from_top`]) === 1
    boxes.push({
      slot,
      label: plot.label,
      color: plot.color,
      startTime,
      endTime,
      low,
      high,
      consumedRatio: clamp01(finiteNumber(tail[`${prefix}consumed`]) ?? 0),
      // 填充是"剩下的流动性"，所以锚在**被扫荡方向的对面**：
      // 上沿被扫荡 → 上方被抽空 → 填充留在下方
      fillFromTop: !sweptFromTop,
      swept: finiteNumber(tail[`${prefix}swept`]) === 1,
    })
  }
  return boxes
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(Math.max(value, 0), 1)
}

/**
 * 方框内的填充高度占比 = **剩余**流动性比例 = 1 - 已被拿走比例。
 *
 * 单独抽出来是因为它是唯一会算错的地方：填充必须落在方框内部，方向要对，
 * 完全扫荡时必须恰好为 0（"扫荡后不填充颜色"）。
 */
export function fillHeightRatio(box: Pick<ZoneBox, 'consumedRatio'>): number {
  // 比例缺失或非法时按"未被消耗"处理：显示完整填充，而不是画一个空框
  const consumed = Number.isFinite(box.consumedRatio) ? clamp01(box.consumedRatio) : 0
  return 1 - consumed
}

