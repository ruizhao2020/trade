import { describe, expect, it } from 'vitest'
import {
  buildStrategyChanOptions,
  collectStrategyIndicatorsForTimeframe,
  templateUsesChanIndicator,
} from './strategyIndicators.ts'
import { ConditionOperator } from './types.ts'
import type { ChanRenderOptions, Condition, ConditionGroup, ConditionTemplate, ConditionValue } from './types.ts'

const baseOptions: ChanRenderOptions = {
  showFenxing: true,
  showBi: false,
  showDuan: false,
  showZhongshu: false,
  showZhongshuAxis: false,
  showBuySellPoints: false,
  zsLevel: 'bi',
}

function condition(left: ConditionValue, timeframeId?: string, id = 'condition-1'): Condition {
  return {
    id,
    name: '',
    left,
    operator: ConditionOperator.GreaterThan,
    right: { source: 'constant', value: 0 },
    timeframeId,
    enabled: true,
  }
}

function group(...conditions: Condition[]): ConditionGroup {
  return { id: `group-${conditions[0]?.id ?? 'empty'}`, name: '趋势确认', conditions }
}

function template(entry: ConditionGroup[], exit: ConditionGroup[] = []): ConditionTemplate {
  return {
    id: 'template-1',
    name: '测试策略',
    logic: 'AND',
    conditionGroups: entry,
    primaryTimeframeId: '1d',
    secondaryTimeframeIds: ['30m'],
    createdAt: 0,
    updatedAt: 0,
    enabled: true,
    tradeParams: {
      stopLossType: 'atr', stopLossValue: 1.5,
      takeProfitType: 'rr_ratio', takeProfitValue: 2,
      positionType: 'fixed_pct', positionValue: 10,
      exitConditions: exit,
      exitLogic: 'OR',
    },
  }
}

describe('strategy indicator dependencies by timeframe', () => {
  it('shows only MA5 on daily and only MACD on 30m', () => {
    const target = template([group(
      condition({ source: 'indicator', indicatorType: 'ma', params: { period: 5 }, field: 'value' }, '1d', 'ma5'),
      condition({ source: 'indicator', indicatorType: 'macd', params: { fast: 12, slow: 26, signal: 9 }, field: 'histogram' }, '30m', 'macd'),
    )])
    expect(collectStrategyIndicatorsForTimeframe(target, '1d')).toEqual([{ type: 'ma', params: { period: 5 } }])
    expect(collectStrategyIndicatorsForTimeframe(target, '30m')).toEqual([{ type: 'macd', params: { fast: 12, slow: 26, signal: 9 } }])
  })

  it('deduplicates equal parameters and retains different parameters', () => {
    const target = template([group(
      condition({ source: 'indicator', indicatorType: 'ma', params: { period: 5 }, field: 'value' }, '1d', 'ma5-a'),
      condition({ source: 'indicator', indicatorType: 'ma', params: { period: 5 }, field: 'value' }, '1d', 'ma5-b'),
      condition({ source: 'indicator', indicatorType: 'ma', params: { period: 20 }, field: 'value' }, '1d', 'ma20'),
    )])
    expect(collectStrategyIndicatorsForTimeframe(target, '1d')).toHaveLength(2)
  })

  it('honors explicit timeframe wrappers independently for each side', () => {
    const target = template([group({
      ...condition({ source: 'price', field: 'close' }, '1d'),
      right: {
        source: 'timeframe',
        timeframeId: '30m',
        inner: { source: 'indicator', indicatorType: 'rsi', params: { period: 14 }, field: 'value' },
      },
    })])
    expect(collectStrategyIndicatorsForTimeframe(target, '1d')).toEqual([])
    expect(collectStrategyIndicatorsForTimeframe(target, '30m')).toEqual([{ type: 'rsi', params: { period: 14 } }])
  })

  it.each(['buy1', 'buy2', 'buy3', 'sell1', 'sell2', 'sell3'])('enables chan for %s only at its timeframe', (property) => {
    const target = template([group(condition({ source: 'chan', element: 'buySellPoint', property }, '30m'))])
    expect(templateUsesChanIndicator(target, '1d')).toBe(false)
    expect(templateUsesChanIndicator(target, '30m')).toBe(true)
    expect(buildStrategyChanOptions(baseOptions, target, '30m')).toMatchObject({
      showBi: true,
      showDuan: true,
      showZhongshu: true,
      showBuySellPoints: true,
    })
  })

  it('detects chan in exit conditions only at the exit timeframe', () => {
    const exit = group(condition({ source: 'chan', element: 'zhongshu' }, '30m', 'exit'))
    const target = template([group(condition({ source: 'price', field: 'close' }, '1d'))], [exit])
    expect(templateUsesChanIndicator(target, '1d')).toBe(false)
    expect(templateUsesChanIndicator(target, '30m')).toBe(true)
  })

  it('ignores disabled conditions', () => {
    const disabled = condition({ source: 'chan', element: 'bi' }, '1d')
    disabled.enabled = false
    const target = template([group(disabled)])
    expect(templateUsesChanIndicator(target, '1d')).toBe(false)
    expect(collectStrategyIndicatorsForTimeframe(target, '1d')).toEqual([])
  })
})
