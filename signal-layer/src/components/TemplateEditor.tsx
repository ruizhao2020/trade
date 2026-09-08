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

interface Props {
  template?: ConditionTemplate
  onClose: () => void
}

const selectArrow = `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 8 5'%3e%3cpath stroke='%238B8B9E' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M1 1l3 3 3-3'/%3e%3c/svg%3e")`

function LogicControl({ value, onChange }: { value: 'AND' | 'OR'; onChange: (value: 'AND' | 'OR') => void }) {
  return (
    <div className="flex items-center gap-2 shrink-0">
      <span className="text-[10px] text-[var(--text-muted)]">组间关系</span>
      <div className="flex h-8 p-0.5 rounded-md bg-[var(--bg-primary)] border border-[var(--border-primary)]">
        <button type="button" onClick={() => onChange('AND')} className={`px-3 rounded text-[11px] transition-colors ${value === 'AND' ? 'bg-[var(--accent)] text-white' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}`}>全部满足</button>
        <button type="button" onClick={() => onChange('OR')} className={`px-3 rounded text-[11px] transition-colors ${value === 'OR' ? 'bg-[var(--accent)] text-white' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}`}>任一组</button>
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
    positionType: 'fixed_pct', positionValue: 20.0,
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
        className="relative bg-[var(--bg-secondary)] rounded-xl border border-[var(--border-primary)] shadow-2xl w-[min(920px,calc(100vw-32px))] max-h-[92vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="h-14 flex items-center justify-between px-7 border-b border-[var(--border-primary)] shrink-0">
          <h3 className="text-[15px] font-semibold text-[var(--text-primary)]">
            {template ? '编辑策略' : '新建策略'}
          </h3>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors duration-150"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-7 py-6 flex flex-col gap-7">
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

          <section className="rounded-xl border border-[var(--border-primary)] bg-[var(--bg-primary)]/30 p-5">
            <div className="flex items-center justify-between gap-4 mb-4">
              <div className="flex items-center gap-2.5">
                <span className="w-1 h-4 rounded-full bg-[var(--accent)]" />
                <h4 className="text-[13px] font-semibold text-[var(--text-primary)]">入场条件</h4>
                <span className="text-[10px] font-mono text-[var(--text-muted)]">{groups.length} 组</span>
              </div>
              {groups.length > 1 && <LogicControl value={logic} onChange={setLogic} />}
            </div>
            <ConditionGroupEditor groups={groups} indicators={indicators} onChange={setGroups} />
          </section>

          <section className="rounded-xl border border-[var(--border-primary)] bg-[var(--bg-primary)]/30 p-5">
            <div className="flex items-center gap-2.5 mb-4">
              <span className="w-1 h-4 rounded-full bg-[var(--accent-orange)]" />
              <h4 className="text-[13px] font-semibold text-[var(--text-primary)]">退出与仓位</h4>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="text-[10px] text-[var(--text-muted)] block mb-1.5">止损</label>
                <select value={`${tradeParams.stopLossType}:${tradeParams.stopLossValue}`}
                  onChange={e => {
                    const [t, v] = e.target.value.split(':')
                    setTradeParams({ ...tradeParams, stopLossType: t as TradeParams['stopLossType'], stopLossValue: parseFloat(v) })
                  }}
                  className="w-full h-10 bg-[var(--bg-tertiary)] text-[12px] text-[var(--text-primary)] px-3 rounded-lg border border-[var(--border-primary)] outline-none focus:border-[var(--accent)] appearance-none"
                  style={{ backgroundImage: selectArrow, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 8px center', backgroundSize: '8px 5px', paddingRight: '26px' }}>
                  <option value="atr:2.0">平均真实波幅 × 2.0</option>
                  <option value="atr:1.5">平均真实波幅 × 1.5</option>
                  <option value="atr:3.0">平均真实波幅 × 3.0</option>
                  <option value="fixed_pct:5">固定跌幅 5%</option>
                  <option value="fixed_pct:8">固定跌幅 8%</option>
                  <option value="swing_low:0">近期低点</option>
                </select>
              </div>
              <div>
                <label className="text-[10px] text-[var(--text-muted)] block mb-1.5">止盈</label>
                <select value={`${tradeParams.takeProfitType}:${tradeParams.takeProfitValue}`}
                  onChange={e => {
                    const [t, v] = e.target.value.split(':')
                    setTradeParams({ ...tradeParams, takeProfitType: t as TradeParams['takeProfitType'], takeProfitValue: parseFloat(v) })
                  }}
                  className="w-full h-10 bg-[var(--bg-tertiary)] text-[12px] text-[var(--text-primary)] px-3 rounded-lg border border-[var(--border-primary)] outline-none focus:border-[var(--accent)] appearance-none"
                  style={{ backgroundImage: selectArrow, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 8px center', backgroundSize: '8px 5px', paddingRight: '26px' }}>
                  <option value="rr_ratio:2.0">盈亏比 1:2</option>
                  <option value="rr_ratio:3.0">盈亏比 1:3</option>
                  <option value="rr_ratio:1.5">盈亏比 1:1.5</option>
                  <option value="fixed_pct:10">固定涨幅 10%</option>
                  <option value="fixed_pct:20">固定涨幅 20%</option>
                  <option value="atr:3.0">平均真实波幅 × 3.0</option>
                </select>
              </div>
              <div>
                <label className="text-[10px] text-[var(--text-muted)] block mb-1.5">仓位</label>
                <select value={`${tradeParams.positionType}:${tradeParams.positionValue}`}
                  onChange={e => {
                    const [t, v] = e.target.value.split(':')
                    setTradeParams({ ...tradeParams, positionType: t as TradeParams['positionType'], positionValue: parseFloat(v) })
                  }}
                  className="w-full h-10 bg-[var(--bg-tertiary)] text-[12px] text-[var(--text-primary)] px-3 rounded-lg border border-[var(--border-primary)] outline-none focus:border-[var(--accent)] appearance-none"
                  style={{ backgroundImage: selectArrow, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 8px center', backgroundSize: '8px 5px', paddingRight: '26px' }}>
                  <option value="fixed_pct:20">20%</option>
                  <option value="fixed_pct:10">10%</option>
                  <option value="fixed_pct:30">30%</option>
                  <option value="fixed_pct:50">50%</option>
                  <option value="kelly:1.0">凯利公式</option>
                </select>
              </div>
            </div>

            <div className="mt-5 pt-5 border-t border-[var(--border-primary)]">
              <div className="flex items-center justify-between gap-4 mb-4">
                <div className="flex items-center gap-2">
                  <h5 className="text-[12px] font-medium text-[var(--text-secondary)]">条件出场</h5>
                  <span className="text-[10px] text-[var(--text-muted)]">可选 · 收盘价执行</span>
                  <span className="text-[10px] font-mono text-[var(--text-muted)]">{exitGroups.length} 组</span>
                </div>
                {exitGroups.length > 1 && <LogicControl value={exitLogic} onChange={setExitLogic} />}
              </div>
              <ConditionGroupEditor groups={exitGroups} indicators={indicators} onChange={setExitGroups} allowEmpty />
            </div>
          </section>
        </div>

        <div className="h-16 flex items-center justify-end gap-3 px-7 border-t border-[var(--border-primary)] shrink-0 bg-[var(--bg-secondary)]">
          {saveError && (
            <div className="flex-1 text-[13px] text-[var(--accent-red)] self-center truncate">{saveError}</div>
          )}
          <button onClick={onClose} disabled={saving}
            className="px-5 py-2.5 text-[13px] rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors duration-150 disabled:opacity-40">
            取消
          </button>
          <button onClick={handleSave} disabled={!name.trim() || saving}
            className="px-6 py-2.5 text-[13px] font-semibold rounded-lg bg-[var(--accent)] text-white hover:brightness-110 transition-all duration-150 disabled:opacity-30 disabled:cursor-not-allowed">
            {saving ? '正在保存...' : '保存策略'}
          </button>
        </div>
      </div>
    </div>
  )
}
