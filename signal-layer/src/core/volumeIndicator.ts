export const VOLUME_CLASS_STYLES: Record<number, { label: string; color: string }> = {
  0: { label: '常规', color: '#596477' },
  1: { label: '缩量', color: '#758195' },
  2: { label: '增量', color: '#596477' },
  3: { label: '倍量', color: '#e7b75f' },
  4: { label: '三倍量', color: '#b989f5' },
  5: { label: '多倍量', color: '#ff6b72' },
}

export const VOLUME_LEGEND = [0, 1, 2, 3, 4, 5].map(code => ({
  code,
  followsPrice: code === 0 || code === 2,
  ...VOLUME_CLASS_STYLES[code]!,
}))

export function volumeClassStyle(value: number | undefined, isUp?: boolean) {
  const code = value === undefined || !Number.isFinite(value) ? 0 : Math.trunc(value)
  const style = VOLUME_CLASS_STYLES[code] ?? VOLUME_CLASS_STYLES[0]!
  if ((code === 0 || code === 2) && isUp !== undefined) {
    return { ...style, color: isUp ? '#ff5b62' : '#2fc58d' }
  }
  return style
}
