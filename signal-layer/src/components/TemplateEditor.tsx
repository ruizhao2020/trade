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
      primaryTimeframeId: template?.primaryTimeframeId ?? '1d',
      secondaryTimeframeIds: template?.secondaryTimeframeIds ?? [],
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
            <label className="text-[11px] font-medium text-[var(--text-muted)] block mb-2">
              策略名称
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full h-11 bg-[var(--bg-tertiary)] text-[14px] text-[var(--text-primary)] px-4 rounded-lg border border-[var(--border-primary)] outline-none focus:border-[var(--accent)] transition-colors duration-150 placeholder:text-[var(--text-muted)]"
              placeholder="请输入策略名称"
            />
          </div>

          <section className="rounded-2xl border border-[var(--border-primary)] bg-[var(--bg-primary)]/30 p-6">
            <div className="flex flex-wrap items-center justify-between gap-5 mb-5">
              <div className="flex items-center gap-2.5">
                <span className="w-1 h-4 rounded-full bg-[var(--accent)]" />
                <h4 className="text-[13px] font-semibold text-[var(--text-primary)]">入场条件</h4>
                <span className="text-[11px] font-mono text-[var(--text-muted)]">{groups.length} 组</span>
              </div>
              {groups.length > 1 && <LogicControl value={logic} onChange={setLogic} />}
            </div>
            <ConditionGroupEditor groups={groups} indicators={indicators} onChange={setGroups} />
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
                <div className="flex items-center gap-2">
                  <h5 className="text-[12px] font-medium text-[var(--text-secondary)]"><ParameterHint label="条件出场" text="使用价格、指标或缠论条件作为卖出依据；满足条件后按当前K线收盘价执行退出。" /></h5>
                  <span className="text-[11px] text-[var(--text-muted)]">可选 · 收盘价执行</span>
                  <span className="text-[11px] font-mono text-[var(--text-muted)]">{exitGroups.length} 组</span>
                </div>
                {exitGroups.length > 1 && <LogicControl value={exitLogic} onChange={setExitLogic} />}
              </div>
              <ConditionGroupEditor groups={exitGroups} indicators={indicators} onChange={setExitGroups} allowEmpty />
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
