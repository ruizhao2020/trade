import type { IndicatorProfileData, IndicatorProfileSnapshot } from './types.ts'

/** 返回指定K线时刻或其之前最近的价格分布快照；空时间返回最新快照。 */
export function findProfileSnapshot(
  profile: IndicatorProfileData | undefined,
  time: number | null | undefined,
): IndicatorProfileSnapshot | undefined {
  const snapshots = profile?.snapshots
  if (!snapshots || snapshots.length === 0) return undefined
  if (time === null || time === undefined) return snapshots.at(-1)
  let low = 0
  let high = snapshots.length - 1
  let match = -1
  while (low <= high) {
    const middle = Math.floor((low + high) / 2)
    if (snapshots[middle]!.time <= time) {
      match = middle
      low = middle + 1
    } else {
      high = middle - 1
    }
  }
  return match >= 0 ? snapshots[match] : snapshots[0]
}
