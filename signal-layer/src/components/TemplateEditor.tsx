/**
 * ============================================================================
 * 策略模板编辑器
 * ============================================================================
 *
 * 编辑一个完整的交易策略模板，包含：
 *   - 名称、组合逻辑
 *   - 入场条件（ConditionGroupEditor）
 *   - 出场规则（止损/止盈/仓位 + 条件式出场）
 */

import { useState, useEffect } from 'react'
import { useAppStore } from '../store/useAppStore.ts'
import { createTemplate, updateTemplate } from '../api/template.ts'
import { fetchIndicatorList } from '../api/indicator.ts'
import type { ConditionTemplate, ConditionGroup, IndicatorInfo, TradeParams } from '../core/types.ts'
import { SUPPORTED_TIMEFRAME_IDS, isFinerTimeframe, isSupportedTimeframeId, timeframeLabel } from '../core/constants.ts'
import type { SupportedTimeframeId } from '../core/constants.ts'
import { ConditionGroupEditor } from './ConditionGroupEditor.tsx'
import { ParameterHint } from './ParameterHint.tsx'

interface Props {
  template?: ConditionTemplate
  onClose: () => void
}

const selectArrow = `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 8 5'%3e%3cpath stroke='%238B8B9E' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M1 1l3 3 3-3'/%3e%3c/svg%3e")`

function LogicControl({ value, onChange }: { value: 'AND' | 'OR'; onChange: (value: 'AND' | 'OR') => void }) {
  return (
    <div className="flex items-center gap-3 shrink-0">
      <span className="text-[11px] text-[var(--text-muted)]">组间关系</span>
      <div className="flex h-10 p-1 rounded-lg bg-[var(--bg-primary)] border border-[var(--border-primary)]">
        <button type="button" onClick={() => onChange('AND')} className={`min-w-[82px] px-4 rounded-md text-[11px] font-medium transition-colors ${value === 'AND' ? 'bg-[var(--accent)] text-white shadow-sm' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'}`}>全部满足</button>
        <button type="button" onClick={() => onChange('OR')} className={`min-w-[82px] px-4 rounded-md text-[11px] font-medium transition-colors ${value === 'OR' ? 'bg-[var(--accent)] text-white shadow-sm' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'}`}>任一组</button>
      </div>
    </div>
  )
}

export function TemplateEditor({ template, onClose }: Props) {
  const addTemplate = useAppStore((s) => s.addTemplate)
  const updateStoreTemplate = useAppStore((s) => s.updateTemplate)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [indicators, setIndicators] = useState<IndicatorInfo[]>([])

  useEffect(() => {
    fetchIndicatorList().then(setIndicators).catch(() => {})
  }, [])

  const [name, setName] = useState(template?.name ?? '')
  const [logic, setLogic] = useState<'AND' | 'OR'>(template?.logic ?? 'AND')
  // 主周期决定未指定级别的条件、回测步进与推送节流粒度；次级周期用于多周期共振
  const [primaryTimeframeId, setPrimaryTimeframeId] = useState<SupportedTimeframeId>(
    template && isSupportedTimeframeId(template.primaryTimeframeId) ? template.primaryTimeframeId : '1d',
  )
  const [secondaryTimeframeIds, setSecondaryTimeframeIds] = useState<SupportedTimeframeId[]>(
    (template?.secondaryTimeframeIds ?? []).filter(isSupportedTimeframeId),
  )

  // 主周期变粗后，原本更粗或同级的次级周期不再合法，需要一并剔除
  function handlePrimaryTimeframeChange(next: SupportedTimeframeId) {
    setPrimaryTimeframeId(next)
    setSecondaryTimeframeIds((current) => current.filter((id) => isFinerTimeframe(id, next)))
  }

  function toggleSecondaryTimeframe(id: SupportedTimeframeId) {
    if (!isFinerTimeframe(id, primaryTimeframeId)) return
    setSecondaryTimeframeIds((current) => (
      current.includes(id)
        ? current.filter((item) => item !== id)
        : SUPPORTED_TIMEFRAME_IDS.filter((tf) => current.includes(tf) || tf === id)
    ))
  }
  // 止损/止盈/仓位（不含条件式出场，后者独立管理）
  const [tradeParams, setTradeParams] = useState<Omit<TradeParams, 'exitConditions' | 'exitLogic'>>(template?.tradeParams ?? {
    stopLossType: 'atr', stopLossValue: 2.0,
    takeProfitType: 'rr_ratio', takeProfitValue: 2.0,
  })
  // 入场条件
  const [groups, setGroups] = useState<ConditionGroup[]>(template?.conditionGroups ?? [])
  // 条件式出场
  const [exitGroups, setExitGroups] = useState<ConditionGroup[]>(template?.tradeParams?.exitConditions ?? [])
  const [exitLogic, setExitLogic] = useState<'AND' | 'OR'>(template?.tradeParams?.exitLogic ?? 'AND')

  async function handleSave() {
    if (!name.trim()) return
    setSaving(true)
    setSaveError(null)
    const now = Date.now()
    const tpl: ConditionTemplate = {
      id: template?.id ?? `tpl_${now}`,
      name: name.trim(),
      logic,
      conditionGroups: groups,
      primaryTimeframeId,
      secondaryTimeframeIds,
      createdAt: template?.createdAt ?? now,
      updatedAt: now,
      enabled: true,
      tradeParams: { ...tradeParams, exitConditions: exitGroups, exitLogic },
    }
    try {
      if (template) {
        const updated = await updateTemplate(template.id, tpl)
        updateStoreTemplate(template.id, updated)
      } else {
        const created = await createTemplate(tpl)
        addTemplate(created)
      }
      onClose()
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div
        className="relative bg-[var(--bg-secondary)] rounded-2xl border border-[var(--border-primary)] shadow-2xl w-[min(1120px,calc(100vw-32px))] max-h-[94vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="h-16 flex items-center justify-between px-8 border-b border-[var(--border-primary)] shrink-0">
          <h3 className="text-[15px] font-semibold text-[var(--text-primary)]">
            {template ? '编辑策略' : '新建策略'}
          </h3>
          <button
            onClick={onClose}
            className="w-9 h-9 rounded-lg flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors duration-150"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-8 py-7 flex flex-col gap-8">
          <div>
            <label htmlFor="template-name" className="text-[11px] font-medium text-[var(--text-muted)] block mb-2">
              策略名称
            </label>
            <input
              id="template-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full h-11 bg-[var(--bg-tertiary)] text-[14px] text-[var(--text-primary)] px-4 rounded-lg border border-[var(--border-primary)] outline-none focus:border-[var(--accent)] transition-colors duration-150 placeholder:text-[var(--text-muted)]"
              placeholder="请输入策略名称"
            />
          </div>

          <section className="rounded-2xl border border-[var(--border-primary)] bg-[var(--bg-primary)]/30 p-6">
            <div className="flex items-center gap-2.5 mb-5">
              <span className="w-1 h-4 rounded-full bg-[var(--accent-green)]" />
              <h4 className="text-[13px] font-semibold text-[var(--text-primary)]">周期设置</h4>
            </div>
            <div className="flex flex-wrap items-start gap-x-10 gap-y-5">
              <div className="block">
                <span className="mb-2 flex items-center gap-1.5 text-[11px] font-medium text-[var(--text-muted)]">
                  主周期
                  <ParameterHint
                    ariaLabel="主周期说明"
                    text="策略的判定基准级别：没有单独指定级别的条件按主周期判定；回测按主周期的K线逐根推进；监控推送也以「每根主周期K线走完推送一次」为节流粒度。"
                  />
                </span>
                <select
                  value={primaryTimeframeId}
                  onChange={(e) => handlePrimaryTimeframeChange(e.target.value as SupportedTimeframeId)}
                  aria-label="主周期"
                  className="h-10 min-w-[132px] px-3 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-primary)] text-[12px] text-[var(--text-primary)] outline-none focus:border-[var(--accent)] transition-colors duration-150 appearance-none"
                  style={{ backgroundImage: selectArrow, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 8px center', backgroundSize: '8px 5px', paddingRight: '26px' }}
                >
                  {SUPPORTED_TIMEFRAME_IDS.map((id) => <option key={id} value={id}>{timeframeLabel(id)}</option>)}
                </select>
              </div>
              <div>
                <span className="mb-2 flex items-center gap-1.5 text-[11px] font-medium text-[var(--text-muted)]">
                  次级周期
                  <ParameterHint
                    ariaLabel="次级周期说明"
                    text="可勾选多个。条件的级别选「次级周期」时，表示这些级别里任意一个满足即成立（或的关系）。只能选比主周期更细的级别。"
                  />
                </span>
                <div className="flex items-center gap-2" role="group" aria-label="次级周期">
                  {SUPPORTED_TIMEFRAME_IDS.map((id) => {
                    const selectable = isFinerTimeframe(id, primaryTimeframeId)
                    const active = secondaryTimeframeIds.includes(id)
                    return (
                      <button
                        key={id}
                        type="button"
                        disabled={!selectable}
                        aria-pressed={active}
                        title={selectable ? undefined : `不细于主周期（${timeframeLabel(primaryTimeframeId)}），不可作为次级周期`}
                        onClick={() => toggleSecondaryTimeframe(id)}
                        className={`h-10 px-4 rounded-lg border text-[12px] transition-colors duration-150 ${
                          !selectable
                            ? 'border-[var(--border-primary)] text-[var(--text-muted)] opacity-40 cursor-not-allowed'
                            : active
                              ? 'border-[var(--accent)] text-[#b9c9ff] bg-[rgba(108,140,255,.1)]'
                              : 'border-[var(--border-primary)] text-[var(--text-muted)] hover:border-[var(--border-accent)] hover:text-[var(--text-secondary)]'
                        }`}
                      >
                        {timeframeLabel(id)}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          </section>

          <section className="rounded-2xl border border-[var(--border-primary)] bg-[var(--bg-primary)]/30 p-6">
            <div className="flex flex-wrap items-center justify-between gap-5 mb-5">
              <div className="flex items-center gap-2.5">
                <span className="w-1 h-4 rounded-full bg-[var(--accent)]" />
                <h4 className="text-[13px] font-semibold text-[var(--text-primary)]">入场条件</h4>
                <span className="text-[11px] font-mono text-[var(--text-muted)]">{groups.length} 组</span>
              </div>
              {groups.length > 1 && <LogicControl value={logic} onChange={setLogic} />}
            </div>
            <ConditionGroupEditor groups={groups} indicators={indicators} onChange={setGroups} primaryTimeframeId={primaryTimeframeId} secondaryTimeframeIds={secondaryTimeframeIds} />
          </section>

          <section className="rounded-2xl border border-[var(--border-primary)] bg-[var(--bg-primary)]/30 p-6">
            <div className="flex items-center gap-2.5 mb-5">
              <span className="w-1 h-4 rounded-full bg-[var(--accent-orange)]" />
              <h4 className="text-[13px] font-semibold text-[var(--text-primary)]">退出设置</h4>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div>
                <label className="text-[11px] text-[var(--text-muted)] block mb-1.5"><ParameterHint label="止损" text="当持仓价格向不利方向达到设定条件时退出。选择关闭表示回测不触发止损。" /></label>
                <select value={`${tradeParams.stopLossType}:${tradeParams.stopLossValue}`}
                  onChange={e => {
                    const [t, v] = e.target.value.split(':')
                    const stopLossType = t as TradeParams['stopLossType']
                    setTradeParams({
                      ...tradeParams,
                      stopLossType,
                      stopLossValue: parseFloat(v),
                      ...(stopLossType === 'none' && tradeParams.takeProfitType === 'rr_ratio'
                        ? { takeProfitType: 'none' as const, takeProfitValue: 0 }
                        : {}),
                    })
                  }}
                  className="w-full h-10 bg-[var(--bg-tertiary)] text-[12px] text-[var(--text-primary)] px-3 rounded-lg border border-[var(--border-primary)] outline-none focus:border-[var(--accent)] appearance-none"
                  style={{ backgroundImage: selectArrow, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 8px center', backgroundSize: '8px 5px', paddingRight: '26px' }}>
                  <option value="none:0">关闭</option>
                  <option value="atr:2.0">平均真实波幅 × 2.0</option>
                  <option value="atr:1.5">平均真实波幅 × 1.5</option>
                  <option value="atr:3.0">平均真实波幅 × 3.0</option>
                  <option value="fixed_pct:5">固定跌幅 5%</option>
                  <option value="fixed_pct:8">固定跌幅 8%</option>
                  <option value="swing_low:0">近期低点</option>
                </select>
              </div>
              <div>
                <label className="text-[11px] text-[var(--text-muted)] block mb-1.5"><ParameterHint label="止盈" text="当持仓价格向有利方向达到设定条件时退出。选择关闭表示回测不触发止盈。盈亏比止盈依赖已开启的止损。" /></label>
                <select value={`${tradeParams.takeProfitType}:${tradeParams.takeProfitValue}`}
                  onChange={e => {
                    const [t, v] = e.target.value.split(':')
                    setTradeParams({ ...tradeParams, takeProfitType: t as TradeParams['takeProfitType'], takeProfitValue: parseFloat(v) })
                  }}
                  className="w-full h-10 bg-[var(--bg-tertiary)] text-[12px] text-[var(--text-primary)] px-3 rounded-lg border border-[var(--border-primary)] outline-none focus:border-[var(--accent)] appearance-none"
                  style={{ backgroundImage: selectArrow, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 8px center', backgroundSize: '8px 5px', paddingRight: '26px' }}>
                  <option value="none:0">关闭</option>
                  <option value="rr_ratio:2.0" disabled={tradeParams.stopLossType === 'none'}>盈亏比 1:2</option>
                  <option value="rr_ratio:3.0" disabled={tradeParams.stopLossType === 'none'}>盈亏比 1:3</option>
                  <option value="rr_ratio:1.5" disabled={tradeParams.stopLossType === 'none'}>盈亏比 1:1.5</option>
                  <option value="fixed_pct:10">固定涨幅 10%</option>
                  <option value="fixed_pct:20">固定涨幅 20%</option>
                  <option value="atr:3.0">平均真实波幅 × 3.0</option>
                </select>
              </div>
            </div>

            <div className="mt-6 pt-6 border-t border-[var(--border-primary)]">
              <div className="flex flex-wrap items-center justify-between gap-5 mb-5">
                <div className="flex items-center gap-2.5">
                  <span className="w-1 h-4 rounded-full bg-[var(--accent)]" />
                  <h4 className="text-[13px] font-semibold text-[var(--text-primary)]">出场条件</h4>
                  <ParameterHint ariaLabel="出场条件说明" text="使用价格、指标或缠论条件作为卖出依据；满足条件后按当前K线收盘价执行退出。" />
                  <span className="text-[11px] text-[var(--text-muted)]">可选 · 收盘价执行</span>
                  <span className="text-[11px] font-mono text-[var(--text-muted)]">{exitGroups.length} 组</span>
                </div>
                {exitGroups.length > 1 && <LogicControl value={exitLogic} onChange={setExitLogic} />}
              </div>
              <ConditionGroupEditor groups={exitGroups} indicators={indicators} onChange={setExitGroups} allowEmpty primaryTimeframeId={primaryTimeframeId} secondaryTimeframeIds={secondaryTimeframeIds} />
            </div>
          </section>
        </div>

        <div className="h-[72px] flex items-center justify-end gap-4 px-8 border-t border-[var(--border-primary)] shrink-0 bg-[var(--bg-secondary)]">
          {saveError && (
            <div className="flex-1 text-[13px] text-[var(--accent-red)] self-center truncate">{saveError}</div>
          )}
          <button onClick={onClose} disabled={saving}
            className="min-w-[88px] h-10 px-5 text-[13px] rounded-lg border border-[var(--border-primary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors duration-150 disabled:opacity-40">
            取消
          </button>
          <button onClick={handleSave} disabled={!name.trim() || saving}
            className="min-w-[112px] h-10 px-6 text-[13px] font-semibold rounded-lg bg-[var(--accent)] text-white hover:brightness-110 transition-all duration-150 disabled:opacity-30 disabled:cursor-not-allowed">
            {saving ? '正在保存...' : '保存策略'}
          </button>
        </div>
      </div>
    </div>
  )
}
