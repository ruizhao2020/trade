/**
 * ============================================================================
 * 策略建议 API
 * ============================================================================
 *
 * 分析是异步任务：createAdvisorRun 立即返回 runId，
 * 前端轮询 fetchAdvisorRun 获取进度与结论。
 */

import { api } from './client'

export interface AdvisorConstraints {
  min_trades?: number
  min_win_rate?: number
  min_frequency?: number
  max_frequency?: number
  min_out_of_sample_return?: number
}

export interface AdvisorRunCreate {
  symbol: string
  symbol_name?: string
  market?: string
  budget?: number
  selection_ratio?: number
  segments?: number
  kline_limit?: number
  constraints?: AdvisorConstraints
}

export interface AdvisorTradeStats {
  trades: number
  win_rate: number
  total_return: number
  max_drawdown: number
  profit_factor: number
  frequency: number
  expectancy: number
}

export interface AdvisorCandidate {
  rank: number | null
  family: string
  primaryLevel: string
  entryLevel: string
  description: string
  score: number
  passed: boolean
  plateauStable: boolean
  rejectedReason: string | null
  inSample: AdvisorTradeStats | null
  outOfSample: AdvisorTradeStats | null
  notes: string[]
}

export interface AdvisorProfile {
  level: string
  bars: number
  volatility_pct: number
  atr_pct: number
  efficiency_ratio: number
  gap_ratio: number
  tags: string[]
  chan: {
    verdict: string
    zhongshu_count: number
    zhongshu_break_rate: number
    point_count: number
    redraw_rate: number | null
    forward_edge: number | null
    reasons: string[]
  }
}

export interface AdvisorRun {
  id: number
  symbol: string
  symbolName: string | null
  status: string
  progressPercent: number
  stage: string | null
  error: string | null
  verdict: string | null
  summary: string | null
  profile: AdvisorProfile | null
  evaluatedCount: number
  truncated: boolean
  engineVersion: string
  createdAt: string | null
  finishedAt: string | null
  candidates: AdvisorCandidate[]
}

export interface AdvisorRunSummary {
  id: number
  symbol: string
  symbolName: string | null
  status: string
  verdict: string | null
  summary: string | null
  createdAt: string | null
}

export interface AdvisorRecommendation {
  id: number
  runId: number
  symbol: string
  templateId: string | null
  status: string
  driftState: string | null
  driftDetail: string | null
  reviewAfterBars: number
  createdAt: string | null
}

interface ApiStats {
  trades: number
  win_rate: number
  total_return: number
  max_drawdown: number
  profit_factor: number
  frequency: number
  expectancy: number
}

interface ApiCandidate {
  rank: number | null
  family: string
  primary_level: string
  entry_level: string
  description: string
  score: number
  passed: boolean
  plateau_stable: boolean
  rejected_reason: string | null
  in_sample: ApiStats | null
  out_of_sample: ApiStats | null
  notes: string[]
}

interface ApiRun {
  id: number
  symbol: string
  symbol_name: string | null
  status: string
  progress_percent: number
  stage: string | null
  error: string | null
  verdict: string | null
  summary: string | null
  profile: AdvisorProfile | null
  evaluated_count: number
  truncated: boolean
  engine_version: string
  created_at: string | null
  finished_at: string | null
  candidates: ApiCandidate[]
}

interface ApiRecommendation {
  id: number
  run_id: number
  symbol: string
  template_id: string | null
  status: string
  drift_state: string | null
  drift_detail: string | null
  review_after_bars: number
  created_at: string | null
}

function toRun(raw: ApiRun): AdvisorRun {
  return {
    id: raw.id,
    symbol: raw.symbol,
    symbolName: raw.symbol_name,
    status: raw.status,
    progressPercent: raw.progress_percent,
    stage: raw.stage,
    error: raw.error,
    verdict: raw.verdict,
    summary: raw.summary,
    profile: raw.profile,
    evaluatedCount: raw.evaluated_count,
    truncated: raw.truncated,
    engineVersion: raw.engine_version,
    createdAt: raw.created_at,
    finishedAt: raw.finished_at,
    candidates: (raw.candidates ?? []).map((item) => ({
      rank: item.rank,
      family: item.family,
      primaryLevel: item.primary_level,
      entryLevel: item.entry_level,
      description: item.description,
      score: item.score,
      passed: item.passed,
      plateauStable: item.plateau_stable,
      rejectedReason: item.rejected_reason,
      inSample: item.in_sample,
      outOfSample: item.out_of_sample,
      notes: item.notes ?? [],
    })),
  }
}

export async function createAdvisorRun(body: AdvisorRunCreate): Promise<AdvisorRunSummary> {
  const raw = await api.post<{ id: number; symbol: string; symbol_name: string | null; status: string; created_at: string | null }>(
    '/advisor/runs', body,
  )
  return {
    id: raw.id, symbol: raw.symbol, symbolName: raw.symbol_name,
    status: raw.status, verdict: null, summary: null, createdAt: raw.created_at,
  }
}

export async function fetchAdvisorRuns(): Promise<AdvisorRunSummary[]> {
  const raw = await api.get<Array<{ id: number; symbol: string; symbol_name: string | null; status: string; verdict: string | null; summary: string | null; created_at: string | null }>>('/advisor/runs')
  return raw.map((item) => ({
    id: item.id, symbol: item.symbol, symbolName: item.symbol_name,
    status: item.status, verdict: item.verdict, summary: item.summary, createdAt: item.created_at,
  }))
}

export async function fetchAdvisorRun(runId: number): Promise<AdvisorRun> {
  return toRun(await api.get<ApiRun>(`/advisor/runs/${runId}`))
}

export async function saveAdvisorTemplate(runId: number, name?: string) {
  const raw = await api.post<{ template_id: string; name: string; primary_tf: string; secondary_tfs: string[] }>(
    `/advisor/runs/${runId}/template`, { name: name ?? null, enabled: true },
  )
  return { templateId: raw.template_id, name: raw.name, primaryTf: raw.primary_tf, secondaryTfs: raw.secondary_tfs }
}

export async function fetchAdvisorRecommendations(): Promise<AdvisorRecommendation[]> {
  const raw = await api.get<ApiRecommendation[]>('/advisor/recommendations')
  return raw.map((item) => ({
    id: item.id, runId: item.run_id, symbol: item.symbol, templateId: item.template_id,
    status: item.status, driftState: item.drift_state, driftDetail: item.drift_detail,
    reviewAfterBars: item.review_after_bars, createdAt: item.created_at,
  }))
}

export async function checkAdvisorRecommendation(recommendationId: number): Promise<AdvisorRecommendation> {
  const item = await api.post<ApiRecommendation>(`/advisor/recommendations/${recommendationId}/check`, {})
  return {
    id: item.id, runId: item.run_id, symbol: item.symbol, templateId: item.template_id,
    status: item.status, driftState: item.drift_state, driftDetail: item.drift_detail,
    reviewAfterBars: item.review_after_bars, createdAt: item.created_at,
  }
}
