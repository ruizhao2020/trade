import { describe, expect, it } from 'vitest'
import {
  financialValueColorClass,
  FLAT_COLOR_CLASS,
  LOSS_COLOR_CLASS,
  PROFIT_COLOR_CLASS,
} from './financialColors.ts'

describe('financial value colors', () => {
  it('uses red for profit and rising values', () => {
    expect(financialValueColorClass(1.25)).toBe(PROFIT_COLOR_CLASS)
  })

  it('uses green for loss and falling values', () => {
    expect(financialValueColorClass(-1.25)).toBe(LOSS_COLOR_CLASS)
  })

  it('uses a neutral color for flat or missing values', () => {
    expect(financialValueColorClass(0)).toBe(FLAT_COLOR_CLASS)
    expect(financialValueColorClass(undefined)).toBe(FLAT_COLOR_CLASS)
  })
})
