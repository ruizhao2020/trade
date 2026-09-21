import { api } from './client'
import type { ConditionTemplate, Condition, ConditionValue } from '../core/types.ts'

/* ========== Backend snake_case interfaces (shared with signal.ts) ========== */

interface ApiConditionValue {
  source: string
  field?: string
  indicator_type?: string
  params?: Record<string, number>
  element?: string
  property?: string
  value?: number
  timeframe_id?: string
  inner?: ApiConditionValue
}

interface ApiCondition {
  id: string
  name: string
  left: ApiConditionValue
  operator: string
  right: ApiConditionValue
  right_2?: ApiConditionValue
  right2?: ApiConditionValue
  timeframe_id?: string
  enabled: boolean
}

interface ApiConditionGroup {
  id: string
  name?: string
  logic?: 'AND' | 'OR'
  conditions: ApiCondition[]
}

interface ApiTemplate {
  id: string
  name: string
  logic: string
  condition_groups: ApiConditionGroup[]
  primary_tf: string
  secondary_tfs: string[]
  created_at?: number | string
  updated_at?: number | string
  enabled: boolean
  trade_params?: {
    stop_loss_type: 'none' | 'atr' | 'fixed_pct' | 'swing_low'
    stop_loss_value: number
    take_profit_type: 'none' | 'atr' | 'fixed_pct' | 'rr_ratio'
    take_profit_value: number
    exit_conditions: ApiConditionGroup[]
    exit_logic: 'AND' | 'OR'
  }
}

/* ========== camelCase ← → snake_case conversion ========== */

function conditionValueToSnake(v: ConditionValue): ApiConditionValue {
  if (v.source === 'indicator') {
    return {
      source: 'indicator',
      indicator_type: v.indicatorType,
      params: v.params,
      field: v.field,
    }
  }
  if (v.source === 'chan') {
    return {
      source: 'chan',
      element: v.element,
      property: v.property,
    }
  }
  if (v.source === 'timeframe') {
    return {
      source: 'timeframe',
      timeframe_id: v.timeframeId,
      inner: conditionValueToSnake(v.inner),
    }
  }
  return v as unknown as ApiConditionValue
}

function conditionValueFromSnake(v: ApiConditionValue): ConditionValue {
  if (v.source === 'indicator') {
    return {
      source: 'indicator',
      indicatorType: v.indicator_type ?? '',
      params: v.params ?? {},
      field: v.field ?? 'value',
    }
  }
  if (v.source === 'chan') {
    return {
      source: 'chan',
      element: v.element as 'fenxing' | 'bi' | 'zhongshu' | 'buySellPoint',
      property: v.property,
    }
  }
  if (v.source === 'timeframe') {
    return {
      source: 'timeframe',
      timeframeId: v.timeframe_id ?? '',
      inner: conditionValueFromSnake(v.inner!),
    }
  }
  return v as unknown as ConditionValue
}

function conditionToSnake(c: Condition): ApiCondition {
  const result: ApiCondition = {
    id: c.id,
    name: c.name,
    left: conditionValueToSnake(c.left),
    operator: c.operator,
    right: conditionValueToSnake(c.right),
    enabled: c.enabled,
  }
  if (c.right2) result.right2 = conditionValueToSnake(c.right2)
  if (c.timeframeId) result.timeframe_id = c.timeframeId
  return result
}

function conditionFromSnake(c: ApiCondition): Condition {
  const legacyBetween = c.operator === 'between'
  const result: Condition = {
    id: c.id,
    name: c.name,
    left: conditionValueFromSnake(c.left),
    operator: (legacyBetween ? 'gte' : c.operator) as Condition['operator'],
    right: conditionValueFromSnake(c.right),
    enabled: c.enabled,
  }
  const right2 = c.right2 ?? c.right_2
  if (right2 && !legacyBetween) result.right2 = conditionValueFromSnake(right2)
  if (c.timeframe_id) result.timeframeId = c.timeframe_id
  return result
}

export function templateToSnake(t: ConditionTemplate): ApiTemplate {
  const result: ApiTemplate = {
    id: t.id,
    name: t.name,
    logic: t.logic,
    condition_groups: t.conditionGroups.map((g) => ({
      id: g.id,
      name: g.name,
      logic: g.logic ?? 'AND',
      conditions: g.conditions.map(conditionToSnake),
    })),
    primary_tf: t.primaryTimeframeId,
    secondary_tfs: t.secondaryTimeframeIds,
    created_at: t.createdAt,
    updated_at: t.updatedAt,
    enabled: t.enabled,
  }
  if (t.tradeParams) {
    result.trade_params = {
      stop_loss_type: t.tradeParams.stopLossType,
      stop_loss_value: t.tradeParams.stopLossValue,
      take_profit_type: t.tradeParams.takeProfitType,
      take_profit_value: t.tradeParams.takeProfitValue,
      exit_conditions: t.tradeParams.exitConditions.map((group) => ({
        id: group.id,
        name: group.name,
        logic: group.logic ?? 'AND',
        conditions: group.conditions.map(conditionToSnake),
      })),
      exit_logic: t.tradeParams.exitLogic,
    }
  }
  return result
}

function templateFromSnake(t: ApiTemplate): ConditionTemplate {
  const now = Date.now()
  const parseTimestamp = (value: number | string | undefined) => {
    if (typeof value === 'number') return value
    if (typeof value === 'string') {
      const parsed = Date.parse(value)
      if (!Number.isNaN(parsed)) return parsed
    }
    return now
  }
  const result: ConditionTemplate = {
    id: t.id,
    name: t.name,
    logic: t.logic as 'AND' | 'OR',
    conditionGroups: t.condition_groups.map((g) => ({
      id: g.id,
      name: g.name,
      logic: g.logic ?? 'AND',
      conditions: g.conditions.map(conditionFromSnake),
    })),
    primaryTimeframeId: t.primary_tf,
    secondaryTimeframeIds: t.secondary_tfs,
    createdAt: parseTimestamp(t.created_at),
    updatedAt: parseTimestamp(t.updated_at),
    enabled: t.enabled,
  }
  if (t.trade_params) {
    result.tradeParams = {
      stopLossType: t.trade_params.stop_loss_type,
      stopLossValue: t.trade_params.stop_loss_value,
      takeProfitType: t.trade_params.take_profit_type,
      takeProfitValue: t.trade_params.take_profit_value,
      exitConditions: (t.trade_params.exit_conditions ?? []).map((group) => ({
        id: group.id,
        name: group.name,
        logic: group.logic ?? 'AND',
        conditions: group.conditions.map(conditionFromSnake),
      })),
      exitLogic: t.trade_params.exit_logic,
    }
  }
  return result
}

/* ========== Public API ========== */

/** GET /api/v1/templates — list all condition templates */
export async function fetchTemplates(): Promise<ConditionTemplate[]> {
  console.log('[SL:API] GET /templates')
  const raw = await api.get<ApiTemplate[]>('/templates')
  console.log('[SL:API] GET /templates -> OK', raw.length)
  return raw.map(templateFromSnake)
}

/** POST /api/v1/templates — create a new template, returns saved template with server-assigned id */
export async function createTemplate(template: ConditionTemplate): Promise<ConditionTemplate> {
  console.log('[SL:API] POST /templates', { name: template.name })
  const raw = await api.post<ApiTemplate>('/templates', templateToSnake(template))
  console.log('[SL:API] POST /templates -> OK', raw.id)
  return templateFromSnake(raw)
}

/** PUT /api/v1/templates/{id} — update existing template */
export async function updateTemplate(id: string, template: ConditionTemplate): Promise<ConditionTemplate> {
  console.log('[SL:API] PUT /templates/' + id, { name: template.name })
  const raw = await api.put<ApiTemplate>(`/templates/${id}`, templateToSnake(template))
  console.log('[SL:API] PUT /templates/' + id + ' -> OK')
  return templateFromSnake(raw)
}

export async function deleteTemplate(id: string): Promise<void> {
  console.log('[SL:API] DELETE /templates/' + id)
  await api.delete(`/templates/${id}`)
  console.log('[SL:API] DELETE /templates/' + id + ' -> OK')
}
