import { describe, expect, it } from 'vitest'
import type { PlotSpec } from '../core/types.ts'
import { buildZoneBoxes, fillHeightRatio, isZonePlot } from './zoneBoxes.ts'

const ACTIVE = '#6c8cff'
const SWEPT = '#9b8cf2'

function plot(field: string, color = ACTIVE, label = '聚集区1'): PlotSpec {
  return { field, type: 'zone', color, label }
}

/** 造一个槽位的连续行：consumed/from_top 只在末行给终值（后端就是这么回填的）。 */
function rowsFor(
  slot: number,
  range: [number, number],
  low: number,
  high: number,
  options: { consumed?: number; fromTop?: boolean } = {},
) {
  const rows: Array<Record<string, unknown>> = []
  for (let time = 0; time < 10; time += 1) {
    if (time < range[0] || time > range[1]) {
      rows.push({ time })
      continue
    }
    const isLast = time === range[1]
    const consumed = isLast ? (options.consumed ?? 0) : 0
    rows.push({
      time,
      [`zone_${slot}_low`]: low,
      [`zone_${slot}_high`]: high,
      [`zone_${slot}_consumed`]: consumed,
      // 后端把"越过噪声门槛"单独标出来：虚线看它，不看填充比例
      [`zone_${slot}_swept`]: consumed > 0 ? 1 : 0,
      [`zone_${slot}_swept_from_top`]: options.fromTop ? 1 : 0,
    })
  }
  return rows
}

describe('流动性聚集区方框还原', () => {
  it('识别 zone 类型的 plot，且要求字段名符合 zone_{k}_low 约定', () => {
    expect(isZonePlot(plot('zone_1_low'))).toBe(true)
    expect(isZonePlot(plot('zone_1_high'))).toBe(false)
    expect(isZonePlot({ ...plot('zone_1_low'), type: 'line' })).toBe(false)
  })

  it('按字段出现的时间范围还原方框，边界取最后一行的值', () => {
    const boxes = buildZoneBoxes(rowsFor(1, [2, 6], 10, 11), [plot('zone_1_low')])

    expect(boxes).toHaveLength(1)
    expect(boxes[0]!.startTime).toBe(2)
    expect(boxes[0]!.endTime).toBe(6)
    expect(boxes[0]!.low).toBe(10)
    expect(boxes[0]!.high).toBe(11)
    expect(boxes[0]!.swept).toBe(false)
  })

  it('聚集阶段：实线且填满（流动性完整）', () => {
    const plain = buildZoneBoxes(rowsFor(1, [2, 9], 10, 11), [plot('zone_1_low')])[0]!

    expect(plain.swept).toBe(false)
    expect(plain.consumedRatio).toBe(0)
    expect(fillHeightRatio(plain)).toBe(1)
  })

  it('被扫荡：虚线，填充按剩余比例递减，从被扫荡那侧抽空', () => {
    const swept = buildZoneBoxes(
      rowsFor(1, [2, 6], 10, 11, { consumed: 0.4, fromTop: true }),
      [plot('zone_1_low', SWEPT, '聚集区1（已扫荡 40%）')],
    )[0]!

    expect(swept.swept).toBe(true)
    expect(swept.consumedRatio).toBeCloseTo(0.4)
    // 上沿被扫荡 → 上方抽空 → 填充留在下方
    expect(swept.fillFromTop).toBe(false)
    expect(fillHeightRatio(swept)).toBeCloseTo(0.6)
    expect(swept.label).toContain('已扫荡')
  })

  it('完全扫荡：虚线且不填充', () => {
    const boxes = buildZoneBoxes(
      rowsFor(2, [1, 5], 9, 9.5, { consumed: 1, fromTop: false }),
      [plot('zone_2_low', SWEPT)],
    )
    expect(boxes[0]!.swept).toBe(true)
    expect(fillHeightRatio(boxes[0]!)).toBe(0)
    // 下沿被扫荡 → 下方抽空 → 填充留在上方
    expect(boxes[0]!.fillFromTop).toBe(true)
  })

  it('多个槽位互不干扰，各自成框', () => {
    const values = Array.from({ length: 10 }, (_, time) => ({
      time,
      zone_1_low: time >= 1 && time <= 4 ? 10 : undefined,
      zone_1_high: time >= 1 && time <= 4 ? 10.5 : undefined,
      zone_1_consumed: 0,
      zone_1_from_top: 0,
      zone_2_low: time >= 6 && time <= 9 ? 20 : undefined,
      zone_2_high: time >= 6 && time <= 9 ? 20.5 : undefined,
      zone_2_consumed: 0,
      zone_2_swept: 0,
      zone_2_swept_from_top: 0,
    }))

    const boxes = buildZoneBoxes(values, [plot('zone_1_low'), plot('zone_2_low')])

    expect(boxes.map((box) => box.slot)).toEqual([1, 2])
    expect(boxes[0]!.low).toBe(10)
    expect(boxes[1]!.low).toBe(20)
  })

  it('没有数据的槽位不画框', () => {
    const boxes = buildZoneBoxes([{ time: 0 }, { time: 1 }], [plot('zone_1_low'), plot('zone_2_low')])
    expect(boxes).toEqual([])
  })

  it('字段残缺或区间非法时跳过该槽位，不画出一个坏框', () => {
    const broken = [
      { time: 0, zone_1_low: 10, zone_1_high: null, zone_1_consumed: 0, zone_1_from_top: 0 },
      { time: 1, zone_2_low: 10, zone_2_high: 10, zone_2_consumed: 0, zone_2_from_top: 0 },
    ]
    const boxes = buildZoneBoxes(broken, [plot('zone_1_low'), plot('zone_2_low')])
    // zone_1 缺 high、zone_2 上下沿相等 → 都不画
    expect(boxes).toEqual([])
  })

  it('填充比例被夹到 0..1，越界值不会画出框外的填充', () => {
    expect(fillHeightRatio({ consumedRatio: -0.5 })).toBe(1)   // 负数视为未消耗
    expect(fillHeightRatio({ consumedRatio: 1.7 })).toBe(0)    // 超额消耗视为抽空
    expect(fillHeightRatio({ consumedRatio: Number.NaN })).toBe(1)
  })
})
