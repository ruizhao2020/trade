import { describe, expect, it } from 'vitest'
import { ConditionOperator } from '../core/types.ts'
import type { ConditionGroup, ConditionTemplate } from '../core/types.ts'
import { templateToSnake } from './template.ts'

function group(id: string, name: string): ConditionGroup {
  return {
    id,
    name,
    logic: 'OR',
    conditions: [{
      id: `${id}-condition`,
      name: '',
      left: { source: 'price', field: 'close' },
      operator: ConditionOperator.GreaterThan,
      right: { source: 'constant', value: 0 },
      enabled: true,
    }],
  }
}

describe('strategy persistence serialization', () => {
  it('sends editable entry and exit group names to the database API', () => {
    const strategy: ConditionTemplate = {
      id: 'strategy-1',
      name: '趋势策略',
      logic: 'AND',
      conditionGroups: [group('entry', '趋势确认')],
      primaryTimeframeId: '1d',
      secondaryTimeframeIds: ['30m'],
      createdAt: 1,
      updatedAt: 2,
      enabled: true,
      tradeParams: {
        stopLossType: 'atr', stopLossValue: 1.5,
        takeProfitType: 'rr_ratio', takeProfitValue: 2,
        exitConditions: [group('exit', '动能衰减离场')],
        exitLogic: 'OR',
      },
    }
    const serialized = templateToSnake(strategy)
    expect(serialized.condition_groups[0]?.name).toBe('趋势确认')
    expect(serialized.condition_groups[0]?.logic).toBe('OR')
    expect(serialized.trade_params?.exit_conditions[0]?.name).toBe('动能衰减离场')
    expect(serialized.trade_params?.exit_conditions[0]?.logic).toBe('OR')
  })
})
