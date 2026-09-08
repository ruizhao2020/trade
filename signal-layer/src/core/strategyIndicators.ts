import type { ChanRenderOptions, ConditionTemplate, ConditionValue } from './types.ts'

export interface StrategyIndicatorRequest {
  type: string
  params: Record<string, number>
}

function visitValue(
  value: ConditionValue | undefined,
  defaultTimeframe: string,
  visit: (inner: ConditionValue, timeframe: string) => void,
) {
  if (!value) return
  if (value.source === 'timeframe') {
    visitValue(value.inner, value.timeframeId, visit)
    return
  }
  visit(value, defaultTimeframe)
}

function visitTemplateValues(
  template: ConditionTemplate,
  visit: (value: ConditionValue, timeframe: string) => void,
) {
  const groups = [...template.conditionGroups, ...(template.tradeParams?.exitConditions ?? [])]
  groups.forEach((group) => group.conditions.forEach((condition) => {
    if (!condition.enabled) return
    const conditionTimeframe = condition.timeframeId || template.primaryTimeframeId
    visitValue(condition.left, conditionTimeframe, visit)
    visitValue(condition.right, conditionTimeframe, visit)
    visitValue(condition.right2, conditionTimeframe, visit)
  }))
}

export function collectStrategyIndicatorsForTimeframe(
  template: ConditionTemplate | undefined,
  timeframe: string,
): StrategyIndicatorRequest[] {
  if (!template) return []
  const found = new Map<string, StrategyIndicatorRequest>()
  visitTemplateValues(template, (value, valueTimeframe) => {
    if (valueTimeframe !== timeframe || value.source !== 'indicator') return
    const request = { type: value.indicatorType, params: value.params }
    const paramsKey = Object.entries(request.params).sort(([a], [b]) => a.localeCompare(b))
    found.set(`${request.type}:${JSON.stringify(paramsKey)}`, request)
  })
  return [...found.values()]
}

export function templateUsesChanIndicator(
  template: ConditionTemplate | undefined,
  timeframe: string,
): boolean {
  if (!template) return false
  let found = false
  visitTemplateValues(template, (value, valueTimeframe) => {
    if (valueTimeframe === timeframe && value.source === 'chan') found = true
  })
  return found
}

export function buildStrategyChanOptions(
  base: ChanRenderOptions,
  template: ConditionTemplate | undefined,
  timeframe: string,
): ChanRenderOptions {
  const enabled = templateUsesChanIndicator(template, timeframe)
  return {
    ...base,
    showFenxing: false,
    showBi: enabled,
    showDuan: enabled,
    showZhongshu: enabled,
    showZhongshuAxis: enabled,
    showBuySellPoints: enabled,
  }
}
