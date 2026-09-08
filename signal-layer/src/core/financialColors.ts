export const PROFIT_COLOR_CLASS = 'text-[var(--accent-red)]'
export const LOSS_COLOR_CLASS = 'text-[var(--accent-green)]'
export const FLAT_COLOR_CLASS = 'text-[var(--text-muted)]'

/** 国内行情习惯：上涨/盈利为红色，下跌/亏损为绿色，持平为中性色。 */
export function financialValueColorClass(value: number | undefined): string {
  if (value === undefined || value === 0) return FLAT_COLOR_CLASS
  return value > 0 ? PROFIT_COLOR_CLASS : LOSS_COLOR_CLASS
}
