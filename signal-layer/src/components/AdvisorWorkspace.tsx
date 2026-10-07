/**
 * ============================================================================
 * 策略建议工作区
 * ============================================================================
 *
 * 手动触发：选标的 → 设置约束 → 分析（异步，轮询进度）→ 结论 + 画像 + 候选明细。
 *
 * 结论只有三种：推荐 / 数据不足 / 无稳定优势——「无法推荐」是合法结果，
 * 因为交易数不足或参数尖峰时给出确定建议对用户是有害的。
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { SymbolSelector } from './SymbolSelector.tsx'
import {
  checkAdvisorRecommendation,
  createAdvisorRun,
  fetchAdvisorRecommendations,
  fetchAdvisorRun,
  fetchAdvisorRuns,
  saveAdvisorTemplate,
} from '../api/advisor.ts'
import type { AdvisorProfile, AdvisorRecommendation, AdvisorRun, AdvisorRunSummary } from '../api/advisor.ts'

const VERDICT_STYLE: Record<string, { label: string; className: string; hint: string }> = {
  '推荐': {
    label: '推荐',
    className: 'border-[rgba(54,201,149,.35)] bg-[rgba(54,201,149,.1)] text-[var(--accent-green)]',
    hint: '通过全部硬约束、参数邻域稳定，且留出期（样本外）为正',
  },
  '数据不足': {
    label: '数据不足',
    className: 'border-[var(--border-accent)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)]',
    hint: '交易样本太少，统计上不可靠，不建议据此操作',
  },
  '无稳定优势': {
    label: '无稳定优势',
    className: 'border-[rgba(240,163,90,.35)] bg-[rgba(240,163,90,.08)] text-[var(--accent-orange)]',
    hint: '有候选满足约束，但参数邻域不稳或样本外为负',
  },
}

const CHAN_STYLE: Record<string, string> = {
  '适合': 'text-[var(--accent-green)]',
  '不适合': 'text-[var(--accent-orange)]',
  '数据不足': 'text-[var(--text-muted)]',
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-[11px] text-[var(--text-muted)]">{label}</span>
      <span className={`font-mono text-[12px] ${tone ?? 'text-[var(--text-primary)]'}`}>{value}</span>
    </div>
  )
}

function percent(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

function number(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined) return '—'
  return value.toFixed(digits)
}

function ProfileCard({ profile }: { profile: AdvisorProfile }) {
  const chan = profile.chan
  return (
    <section className="rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] p-4">
      <div className="flex items-center gap-2">
        <span className="text-[12px] font-semibold">标的画像</span>
        <span className="text-[11px] text-[var(--text-muted)]">（{profile.level} · {profile.bars} 根）</span>
        <div className="ml-auto flex items-center gap-1.5">
          {profile.tags.map((tag) => (
            <span key={tag} className="px-1.5 py-0.5 rounded border border-[var(--border-primary)] text-[11px] text-[var(--text-secondary)]">{tag}</span>
          ))}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5">
        <Stat label="趋势效率比" value={number(profile.efficiency_ratio)} />
        <Stat label="波动率" value={`${number(profile.volatility_pct)}%`} />
        <Stat label="ATR 占比" value={`${number(profile.atr_pct)}%`} />
        <Stat label="跳空占比" value={percent(profile.gap_ratio, 1)} />
      </div>

      <div className="mt-4 pt-3 border-t border-[var(--border-primary)]">
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-[var(--text-muted)]">缠论结构</span>
          <span className={`text-[12px] font-semibold ${CHAN_STYLE[chan.verdict] ?? ''}`}>{chan.verdict}</span>
          <span className="ml-auto text-[11px] text-[var(--text-muted)]">中枢 {chan.zhongshu_count} · 买卖点 {chan.point_count}</span>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1.5">
          <Stat label="信号重绘率" value={percent(chan.redraw_rate)} />
          <Stat label="中枢破坏率" value={percent(chan.zhongshu_break_rate)} />
          <Stat label="买卖点前瞻超额" value={chan.forward_edge === null ? '—' : `${number(chan.forward_edge)}%`} />
        </div>
        {chan.reasons.length > 0 && (
          <ul className="mt-2.5 space-y-1">
            {chan.reasons.map((reason) => (
              <li key={reason} className="text-[11px] text-[var(--text-muted)]">· {reason}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

function CandidateTable({ run }: { run: AdvisorRun }) {
  const passed = run.candidates.filter((item) => item.passed)
  const rejected = run.candidates.filter((item) => !item.passed)

  return (
    <section className="rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)]">
      <div className="px-4 py-3 border-b border-[var(--border-primary)] flex items-center gap-3">
        <span className="text-[12px] font-semibold">候选策略</span>
        <span className="text-[11px] text-[var(--text-muted)]">
          共评估 {run.evaluatedCount} 个，通过约束 {passed.length} 个
        </span>
        {run.truncated && <span className="text-[11px] text-[var(--accent-orange)]">已达到候选预算上限，空间被截断</span>}
      </div>

      {passed.length === 0 ? (
        <div className="px-4 py-8 text-center text-[11px] text-[var(--text-muted)]">
          没有候选同时满足全部约束
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-[var(--text-muted)] border-b border-[var(--border-primary)]">
                <th className="px-4 py-2 text-left font-medium">候选</th>
                <th className="px-3 py-2 text-right font-medium">稳健分</th>
                <th className="px-3 py-2 text-right font-medium">选定期交易</th>
                <th className="px-3 py-2 text-right font-medium">选定期胜率</th>
                <th className="px-3 py-2 text-right font-medium">选定期收益</th>
                <th className="px-3 py-2 text-right font-medium">回撤</th>
                <th className="px-3 py-2 text-right font-medium">留出期收益</th>
                <th className="px-3 py-2 text-center font-medium">参数平台</th>
              </tr>
            </thead>
            <tbody>
              {passed.slice(0, 20).map((item) => (
                <tr key={`${item.family}-${item.description}`} className="border-b border-[var(--border-primary)] last:border-b-0">
                  <td className="px-4 py-2 text-[var(--text-secondary)]">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-muted)] mr-1.5">{item.family}</span>
                    {item.description}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{item.score.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right font-mono">{item.inSample?.trades ?? 0}</td>
                  <td className="px-3 py-2 text-right font-mono">{number(item.inSample?.win_rate, 0)}%</td>
                  <td className={`px-3 py-2 text-right font-mono ${(item.inSample?.total_return ?? 0) >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>
                    {number(item.inSample?.total_return, 1)}%
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{number(item.inSample?.max_drawdown, 1)}%</td>
                  <td className={`px-3 py-2 text-right font-mono ${(item.outOfSample?.total_return ?? 0) >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>
                    {number(item.outOfSample?.total_return, 1)}%
                  </td>
                  <td className="px-3 py-2 text-center">
                    {item.plateauStable
                      ? <span className="text-[var(--accent-green)]">稳</span>
                      : <span className="text-[var(--accent-orange)]" title={item.notes.join('；')}>尖峰</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {rejected.length > 0 && (
        <div className="px-4 py-3 border-t border-[var(--border-primary)]">
          <div className="text-[11px] text-[var(--text-muted)] mb-2">被约束淘汰的候选（部分）</div>
          <ul className="space-y-1">
            {rejected.slice(0, 6).map((item) => (
              <li key={`r-${item.family}-${item.description}`} className="text-[11px] text-[var(--text-muted)]">
                · <span className="text-[var(--text-secondary)]">{item.description}</span>
                <span className="ml-2 text-[var(--accent-orange)]">{item.rejectedReason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

export function AdvisorWorkspace() {
  const [market, setMarket] = useState('')
  const [symbol, setSymbol] = useState('')
  const [symbolName, setSymbolName] = useState('')
  const [minTrades, setMinTrades] = useState(20)
  const [minWinRate, setMinWinRate] = useState(40)
  const [maxFrequency, setMaxFrequency] = useState(0.5)
  const [minHoldoutTrades, setMinHoldoutTrades] = useState(5)

  const [runs, setRuns] = useState<AdvisorRunSummary[]>([])
  const [recommendations, setRecommendations] = useState<AdvisorRecommendation[]>([])
  const [activeRun, setActiveRun] = useState<AdvisorRun | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const pollRef = useRef<number | null>(null)

  async function refreshLists() {
    try {
      const [nextRuns, nextRecommendations] = await Promise.all([fetchAdvisorRuns(), fetchAdvisorRecommendations()])
      setRuns(nextRuns)
      setRecommendations(nextRecommendations)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '列表加载失败')
    }
  }

  useEffect(() => {
    // 与其它工作区一致：延后到下一个 tick，避免在 effect 里直接 setState
    const timer = window.setTimeout(() => { void refreshLists() }, 0)
    return () => window.clearTimeout(timer)
  }, [])

  // 分析进行中时轮询进度
  useEffect(() => {
    if (!activeRun || !['pending', 'running'].includes(activeRun.status)) return
    pollRef.current = window.setInterval(() => {
      void fetchAdvisorRun(activeRun.id).then(setActiveRun).catch(() => undefined)
    }, 2000)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [activeRun])

  async function start() {
    if (!symbol) {
      setError('请先选择市场与标的')
      return
    }
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const created = await createAdvisorRun({
        symbol,
        symbol_name: symbolName || undefined,
        market: market || undefined,
        constraints: {
          min_trades: minTrades,
          min_win_rate: minWinRate,
          max_frequency: maxFrequency,
          min_out_of_sample_trades: minHoldoutTrades,
        },
      })
      setActiveRun(await fetchAdvisorRun(created.id))
      await refreshLists()
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : '分析启动失败')
    } finally {
      setBusy(false)
    }
  }

  async function saveAsTemplate() {
    if (!activeRun) return
    setError(null)
    try {
      const saved = await saveAdvisorTemplate(activeRun.id, `[建议] ${activeRun.symbol} ${activeRun.profile?.tags.join('') ?? ''}`.trim())
      setNotice(`已生成策略模板「${saved.name}」，可在策略模块中查看与回测`)
      await refreshLists()
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : '生成策略失败')
    }
  }

  async function runDriftCheck(recommendationId: number) {
    setError(null)
    try {
      const updated = await checkAdvisorRecommendation(recommendationId)
      setRecommendations((current) => current.map((item) => item.id === updated.id ? updated : item))
      setNotice(updated.driftDetail ?? null)
    } catch (checkError) {
      setError(checkError instanceof Error ? checkError.message : '复核失败')
    }
  }

  const verdictStyle = useMemo(() => {
    const verdict = activeRun?.verdict
    return verdict ? VERDICT_STYLE[verdict] : undefined
  }, [activeRun?.verdict])

  const running = activeRun ? ['pending', 'running'].includes(activeRun.status) : false

  return (
    <div className="flex-1 min-h-0 flex flex-col bg-[var(--bg-primary)]">
      <header className="h-16 px-6 flex items-center border-b border-[var(--border-primary)] bg-[var(--bg-secondary)] shrink-0">
        <div>
          <h1 className="text-[16px] font-semibold">策略建议</h1>
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">自动分析标的适合的技术指标与操盘方式，并给出可验证的依据</p>
        </div>
        <div className="ml-auto text-[11px] text-[var(--text-muted)]">研究建议，不构成投资建议</div>
      </header>

      {error && (
        <div role="alert" className="mx-5 mt-4 px-3 py-2 rounded-md border border-[rgba(255,107,114,.25)] text-[11px] text-[var(--accent-red)]">{error}</div>
      )}
      {notice && (
        <div role="status" className="mx-5 mt-4 px-3 py-2 rounded-md border border-[var(--border-primary)] text-[11px] text-[var(--text-secondary)]">{notice}</div>
      )}

      <div className="flex-1 min-h-0 grid grid-cols-[320px_minmax(0,1fr)] overflow-hidden">
        <aside className="border-r border-[var(--border-primary)] bg-[var(--bg-secondary)] overflow-y-auto">
          <div className="p-4 space-y-4 border-b border-[var(--border-primary)]">
            <div className="text-[11px] font-semibold">选择标的</div>
            <SymbolSelector
              market={market}
              symbol={symbol}
              symbolName={symbolName}
              onMarketChange={(next) => { setMarket(next); setSymbol(''); setSymbolName('') }}
              onSymbolChange={(next, name) => { setSymbol(next); setSymbolName(name) }}
            />
            <button type="button" disabled={busy || running || !symbol} onClick={() => void start()} className="action-primary w-full disabled:opacity-40">
              {running ? '分析中…' : '开始分析'}
            </button>
          </div>

          <div className="p-4 space-y-3 border-b border-[var(--border-primary)]">
            <div className="text-[11px] font-semibold">约束条件</div>
            <label className="block text-[11px] text-[var(--text-muted)]">
              最少交易数
              <input type="number" min={1} value={minTrades} onChange={(event) => setMinTrades(Number(event.target.value))} className="field mt-1 w-full" />
            </label>
            <label className="block text-[11px] text-[var(--text-muted)]">
              最低胜率（%）
              <input type="number" min={0} max={100} value={minWinRate} onChange={(event) => setMinWinRate(Number(event.target.value))} className="field mt-1 w-full" />
            </label>
            <label className="block text-[11px] text-[var(--text-muted)]">
              最高频率（次/根）
              <input type="number" min={0.01} step={0.05} value={maxFrequency} onChange={(event) => setMaxFrequency(Number(event.target.value))} className="field mt-1 w-full" />
            </label>
            <label className="block text-[11px] text-[var(--text-muted)]">
              样本外交易数下限
              <input type="number" min={1} max={200} value={minHoldoutTrades} onChange={(event) => setMinHoldoutTrades(Number(event.target.value))} className="field mt-1 w-full" />
            </label>
            <p className="text-[11px] leading-5 text-[var(--text-muted)]">交易数不足或参数不稳时不会给结论，「无法推荐」是正常结果。</p>
          </div>

          <div className="p-4 space-y-2">
            <div className="text-[11px] font-semibold">历史分析</div>
            {runs.length === 0 && <div className="text-[11px] text-[var(--text-muted)]">暂无记录</div>}
            {runs.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => void fetchAdvisorRun(item.id).then(setActiveRun)}
                className={`w-full text-left px-2.5 py-2 rounded-md border transition-colors ${activeRun?.id === item.id ? 'border-[var(--accent)] bg-[rgba(108,140,255,.08)]' : 'border-[var(--border-primary)] hover:border-[var(--border-accent)]'}`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-[12px] text-[var(--text-primary)]">{item.symbolName || item.symbol}</span>
                  {item.verdict && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${VERDICT_STYLE[item.verdict]?.className ?? 'border-[var(--border-primary)] text-[var(--text-muted)]'}`}>{item.verdict}</span>
                  )}
                </div>
                <div className="mt-1 text-[11px] text-[var(--text-muted)]">{item.createdAt ? new Date(item.createdAt).toLocaleString('zh-CN') : ''}</div>
              </button>
            ))}
          </div>

          {recommendations.length > 0 && (
            <div className="p-4 space-y-2 border-t border-[var(--border-primary)]">
              <div className="text-[11px] font-semibold">已生成建议</div>
              {recommendations.map((item) => (
                <div key={item.id} className="rounded-md border border-[var(--border-primary)] px-2.5 py-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px]">{item.symbol}</span>
                    <span className={`text-[10px] ${item.driftState === 'stale' ? 'text-[var(--accent-orange)]' : 'text-[var(--text-muted)]'}`}>
                      {item.driftState === 'stale' ? '需复核' : item.driftState === 'ok' ? '未见漂移' : '未复核'}
                    </span>
                    <button type="button" onClick={() => void runDriftCheck(item.id)} className="ml-auto text-[10px] text-[var(--accent)] hover:underline">复核</button>
                  </div>
                  {item.driftDetail && <div className="mt-1 text-[11px] text-[var(--text-muted)]">{item.driftDetail}</div>}
                </div>
              ))}
            </div>
          )}
        </aside>

        <main className="min-w-0 overflow-y-auto p-5 space-y-4">
          {!activeRun && <div className="h-full flex items-center justify-center text-[11px] text-[var(--text-muted)]">选择标的并开始分析</div>}

          {activeRun && (
            <>
              <section className="rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] p-4">
                <div className="flex items-center gap-3">
                  <span className="text-[14px] font-semibold">{activeRun.symbolName || activeRun.symbol}</span>
                  {verdictStyle && (
                    <span title={verdictStyle.hint} className={`text-[11px] px-2 py-0.5 rounded border ${verdictStyle.className}`}>{verdictStyle.label}</span>
                  )}
                  {running && <span className="text-[11px] text-[var(--text-muted)]">{activeRun.stage ?? '分析中'} · {activeRun.progressPercent}%</span>}
                  {activeRun.verdict === '推荐' && (
                    <button type="button" onClick={() => void saveAsTemplate()} className="action-primary ml-auto">生成策略模板</button>
                  )}
                </div>

                {running && (
                  <div className="mt-3 h-1 rounded bg-[var(--bg-tertiary)] overflow-hidden">
                    <div className="h-full bg-[var(--accent)] transition-[width] duration-300" style={{ width: `${activeRun.progressPercent}%` }} />
                  </div>
                )}

                {activeRun.error && <div className="mt-3 text-[11px] text-[var(--accent-red)]">{activeRun.error}</div>}
                {activeRun.summary && <p className="mt-3 text-[12px] leading-6 text-[var(--text-secondary)]">{activeRun.summary}</p>}
                {verdictStyle && !running && (
                  <p className="mt-2 text-[11px] text-[var(--text-muted)]">判定依据：{verdictStyle.hint}</p>
                )}
              </section>

              {activeRun.profile && <ProfileCard profile={activeRun.profile} />}
              {activeRun.candidates.length > 0 && <CandidateTable run={activeRun} />}
            </>
          )}
        </main>
      </div>
    </div>
  )
}
