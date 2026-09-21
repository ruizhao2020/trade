import type { ChanAnalysis, ChanRenderOptions, ConditionTemplate, ConditionValue } from './types.ts'

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

export function collectStrategyTimeframes(template: ConditionTemplate | undefined): string[] {
  if (!template) return []
  const found = new Set<string>([template.primaryTimeframeId, ...template.secondaryTimeframeIds])
  visitTemplateValues(template, (_value, timeframe) => found.add(timeframe))
  return [template.primaryTimeframeId, ...[...found].filter((item) => item !== template.primaryTimeframeId)]
}

interface ChanRequirements {
  used: boolean
  allBuySellPoints: boolean
  buySellPointTypes: Set<string>
  allDivergences: boolean
  divergenceTypes: Set<string>
}

function collectChanRequirements(template: ConditionTemplate | undefined, timeframe: string): ChanRequirements {
  const requirements: ChanRequirements = {
    used: false,
    allBuySellPoints: false,
    buySellPointTypes: new Set(),
    allDivergences: false,
    divergenceTypes: new Set(),
  }
  if (!template) return requirements
  visitTemplateValues(template, (value, valueTimeframe) => {
    if (valueTimeframe !== timeframe || value.source !== 'chan') return
    requirements.used = true
    if (value.element === 'buySellPoint') {
      if (value.property) requirements.buySellPointTypes.add(value.property)
      else requirements.allBuySellPoints = true
    }
    if (value.element === 'divergence') {
      if (value.property) requirements.divergenceTypes.add(value.property)
      else requirements.allDivergences = true
    }
  })
  return requirements
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

export function filterStrategyChanAnalysis(
  analysis: ChanAnalysis | null,
  template: ConditionTemplate | undefined,
  timeframe: string,
): ChanAnalysis | null {
  if (!analysis) return null
  const requirements = collectChanRequirements(template, timeframe)
  if (!requirements.used) return null
  return {
    ...analysis,
    buySellPoints: requirements.allBuySellPoints
      ? analysis.buySellPoints
      : analysis.buySellPoints.filter((point) => requirements.buySellPointTypes.has(point.type)),
    divergences: requirements.allDivergences
      ? analysis.divergences
      : analysis.divergences.filter((item) => requirements.divergenceTypes.has(item.type)),
  }
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
    showDivergences: enabled,
  }
}
