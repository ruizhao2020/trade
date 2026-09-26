import { api } from './client'
import type {
  ConditionTemplate,
  Condition,
  ConditionValue,
  TemplateSignal,
  GroupEvaluation,
  ConditionEvaluation,
  SignalState,
} from '../core/types.ts'

/* ========== Backend snake_case interfaces ========== */

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

export interface ApiTemplate {
  id: string
  name: string
  logic: string
  condition_groups: ApiConditionGroup[]
  primary_tf: string
  secondary_tfs: string[]
  created_at: number
  updated_at: number
  enabled: boolean
  trade_params?: {
    stop_loss_type: string
    stop_loss_value: number
    take_profit_type: string
    take_profit_value: number
    exit_conditions: ApiConditionGroup[]
    exit_logic: string
  }
}

interface ApiConditionEvaluation {
  condition_id: string
  satisfied: boolean
  left_value: number | null
  right_value: number | null
  diff_percent: number
}

interface ApiGroupEvaluation {
  group_id: string
  evaluations: ApiConditionEvaluation[]
  satisfied: boolean
}

interface ApiTradeRecord {
  entry_time: number
  exit_time: number
  entry_price: number
  exit_price: number
  pnl_pct: number
  exit_reason: string
}

interface ApiBacktestResponse {
  template_id: string
  symbol: string
  timeframe: string
  total_trades: number
  win_trades: number
  win_rate: number
  total_return: number
  avg_return: number
  max_drawdown: number
  profit_factor: number
  payoff_ratio: number
  suggested_position: number
  trades: ApiTradeRecord[]
}

export interface TradeRecord {
  entryTime: number
  exitTime: number
  entryPrice: number
  exitPrice: number
  pnlPct: number
  exitReason: string
}

export interface BacktestResult {
  templateId: string
  symbol: string
  timeframe: string
  totalTrades: number
  winTrades: number
  winRate: number
  totalReturn: number
  avgReturn: number
  maxDrawdown: number
  profitFactor: number
  payoffRatio: number
  suggestedPosition: number
  trades: TradeRecord[]
}

interface ApiEvaluateResponse {
  template_id: string
  state: string
  groups: ApiGroupEvaluation[]
  is_ready: boolean
  progress_percent: number
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
  // price or constant — structure already matches
  return v as unknown as ApiConditionValue
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
      exit_conditions: t.tradeParams.exitConditions.map((g) => ({
        id: g.id,
        name: g.name,
        logic: g.logic ?? 'AND',
        conditions: g.conditions.map(conditionToSnake),
      })),
      exit_logic: t.tradeParams.exitLogic,
    }
  }
  return result
}

function evaluationFromSnake(e: ApiConditionEvaluation): ConditionEvaluation {
  return {
    conditionId: e.condition_id,
    satisfied: e.satisfied,
    leftValue: e.left_value,
    rightValue: e.right_value,
    diffPercent: e.diff_percent,
  }
}

function groupEvalFromSnake(g: ApiGroupEvaluation): GroupEvaluation {
  return {
    groupId: g.group_id,
    evaluations: g.evaluations.map(evaluationFromSnake),
    satisfied: g.satisfied,
  }
}

/* ========== Public API ========== */

/**
 * Evaluate a signal template against a symbol.
 * POST /api/v1/signal/evaluate
 */
export async function evaluateSignal(
  symbol: string,
  template: ConditionTemplate,
): Promise<TemplateSignal> {
  console.log('[SL:API] POST /signal/evaluate', { symbol, template: template.name })
  const raw = await api.post<ApiEvaluateResponse>('/signal/evaluate', {
    symbol,
    template: templateToSnake(template),
  })
  console.log('[SL:API] POST /signal/evaluate -> OK', { state: raw.state })
  return {
    templateId: raw.template_id,
    state: raw.state as SignalState,
    groups: raw.groups.map(groupEvalFromSnake),
    isReady: raw.is_ready,
    updatedAt: Date.now(),
    progressPercent: raw.progress_percent,
  }
}


export async function runBacktest(
  symbol: string,
  template: ConditionTemplate,
  klineLimit = 500,
): Promise<BacktestResult> {
  console.log('[SL:API] POST /signal/backtest', { symbol, template: template.name })
  const raw = await api.post<ApiBacktestResponse>('/signal/backtest', {
    symbol,
    template: templateToSnake(template),
    kline_limit: klineLimit,
  })
  console.log('[SL:API] POST /signal/backtest -> OK', { trades: raw.total_trades })
  return {
    templateId: raw.template_id,
    symbol: raw.symbol,
    timeframe: raw.timeframe,
    totalTrades: raw.total_trades,
    winTrades: raw.win_trades,
    winRate: raw.win_rate,
    totalReturn: raw.total_return,
    avgReturn: raw.avg_return,
    maxDrawdown: raw.max_drawdown,
    profitFactor: raw.profit_factor,
    payoffRatio: raw.payoff_ratio,
    suggestedPosition: raw.suggested_position,
    trades: raw.trades.map(t => ({
      entryTime: t.entry_time,
      exitTime: t.exit_time,
      entryPrice: t.entry_price,
      exitPrice: t.exit_price,
      pnlPct: t.pnl_pct,
      exitReason: t.exit_reason,
    })),
  }
}
