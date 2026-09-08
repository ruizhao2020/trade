/**
 * ============================================================================
 * 条件组编辑器（通用）
 * ============================================================================
 *
 * 用于编辑一组条件（ConditionGroup[]）。入场条件和出场条件都复用它。
 * 受控组件：groups 由父组件传入，编辑通过 onChange 回调回传。
 *
 * 每个条件 = 左值(价格/指标/缠论/常量) + 操作符 + 右值。
 */

import type { ConditionGroup, Condition, ConditionValue, IndicatorInfo } from '../core/types.ts'
import { ConditionOperator } from '../core/types.ts'
import { DEFAULT_TIMEFRAMES } from '../core/constants.ts'
import { MA_PERIODS } from '../core/indicatorColors.ts'

interface Props {
  /** 条件组列表 */
  groups: ConditionGroup[]
  /** 可用指标列表（下拉选项） */
  indicators: IndicatorInfo[]
  /** 编辑回调 */
  onChange: (groups: ConditionGroup[]) => void
  /** 是否允许空（出场条件可为空，入场条件至少一组） */
  allowEmpty?: boolean
}

let _idSequence = 0
const nextId = (prefix: string) => `${prefix}_${Date.now()}_${_idSequence++}`
const nextGroupId = () => nextId('g')
const nextCondId = () => nextId('c')

const OPERATOR_LABELS: Record<string, string> = {
  gt: '>', gte: '>=', lt: '<', lte: '<=', eq: '=',
  crossAbove: '上穿', crossBelow: '下穿', rising: '向上', falling: '向下',
  turnDown: '上转下', turnUp: '下转上', between: '介于',
}

const PRICE_OPTIONS = [
  { value: 'price:close', label: '收盘价' },
  { value: 'price:high', label: '最高价' },
  { value: 'price:low', label: '最低价' },
  { value: 'price:open', label: '开盘价' },
  { value: 'price:volume', label: '成交量' },
]

const CHAN_OPTIONS = [
  { value: 'chan:buy1', label: '一买', element: 'buySellPoint' as const, property: 'buy1' },
  { value: 'chan:buy2', label: '二买', element: 'buySellPoint' as const, property: 'buy2' },
  { value: 'chan:buy3', label: '三买', element: 'buySellPoint' as const, property: 'buy3' },
  { value: 'chan:sell1', label: '一卖', element: 'buySellPoint' as const, property: 'sell1' },
  { value: 'chan:sell2', label: '二卖', element: 'buySellPoint' as const, property: 'sell2' },
  { value: 'chan:sell3', label: '三卖', element: 'buySellPoint' as const, property: 'sell3' },
]

const CHAN_SHAPE_OPTIONS = [
  { value: 'chan:bi', label: '笔数', element: 'bi' as const },
  { value: 'chan:zhongshu', label: '中枢数', element: 'zhongshu' as const },
]

const selectArrow = `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 8 5'%3e%3cpath stroke='%238B8B9E' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M1 1l3 3 3-3'/%3e%3c/svg%3e")`

type IndicatorValue = Extract<ConditionValue, { source: 'indicator' }>

const PARAM_LABELS: Record<string, string> = {
  period: '周期', fast: '快线', slow: '慢线', signal: '信号线',
  n: '计算周期', m1: 'K值平滑', m2: 'D值平滑', std: '标准差倍数',
  piv_len: '枢轴长度', atr_len: '波幅周期',
}

function IndicatorParamsEditor({
  value,
  info,
  onChange,
}: {
  value: IndicatorValue
  info: IndicatorInfo
  onChange: (params: Record<string, number>) => void
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {Object.entries(value.params).map(([key, paramValue]) => {
        const label = PARAM_LABELS[key] ?? key
        if (value.indicatorType === 'ma' && key === 'period') {
          return (
            <label key={key} className="flex items-center">
              <select
                aria-label={`${info.name} ${label}`}
                value={paramValue}
                onChange={(event) => onChange({ ...value.params, [key]: Number(event.target.value) })}
                className="h-9 w-[96px] px-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[12px] font-mono text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
              >
                {MA_PERIODS.map((period) => <option key={period} value={period}>周期 {period}</option>)}
              </select>
            </label>
          )
        }
        return (
          <label key={key} className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
            {label}
            <input
              type="number"
              aria-label={`${info.name} ${label}`}
              value={paramValue}
              onChange={(event) => onChange({ ...value.params, [key]: Number(event.target.value) })}
              className="h-9 w-[68px] px-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[12px] font-mono text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
            />
          </label>
        )
      })}
    </div>
  )
}

/** 创建一个默认的空条件 */
function defaultCondition(): Condition {
  return {
    id: nextCondId(), name: '',
    left: { source: 'price', field: 'close' },
    operator: ConditionOperator.GreaterThan,
    right: { source: 'constant', value: 0 },
    enabled: true,
  }
}

export function ConditionGroupEditor({ groups, indicators, onChange, allowEmpty = false }: Props) {
  function addGroup() {
    onChange([...groups, {
      id: nextGroupId(),
      name: `条件组 ${groups.length + 1}`,
      conditions: [defaultCondition()],
    }])
  }

  function updateGroupName(groupIndex: number, name: string) {
    onChange(groups.map((group, index) => index === groupIndex ? { ...group, name } : group))
  }

  function removeGroup(groupIndex: number) {
    if (!allowEmpty && groups.length <= 1) return
    onChange(groups.filter((_, index) => index !== groupIndex))
  }

  function addCondition(groupIndex: number) {
    onChange(groups.map((group, index) =>
      index === groupIndex ? { ...group, conditions: [...group.conditions, defaultCondition()] } : group
    ))
  }

  function updateCondition(groupIndex: number, conditionIndex: number, updates: Partial<Condition>) {
    onChange(groups.map((group, index) =>
      index === groupIndex
        ? { ...group, conditions: group.conditions.map((condition, innerIndex) => innerIndex === conditionIndex ? { ...condition, ...updates } : condition) }
        : group
    ))
  }

  function removeCondition(groupIndex: number, conditionIndex: number) {
    onChange(groups.map((group, index) =>
      index === groupIndex ? { ...group, conditions: group.conditions.filter((_, innerIndex) => innerIndex !== conditionIndex) } : group
    ))
  }

  const selClass = "h-9 bg-[var(--bg-tertiary)] text-[12px] text-[var(--text-primary)] px-3 rounded-lg border border-[var(--border-primary)] outline-none focus:border-[var(--accent)] transition-colors duration-150 appearance-none"
  const selStyle = { backgroundImage: selectArrow, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 10px center', backgroundSize: '8px 5px', paddingRight: '28px' }

  return (
    <div className="space-y-3">
      {groups.map((group, gi) => (
        <div key={`${group.id}:${gi}`} className="border border-[var(--border-primary)] rounded-lg overflow-hidden bg-[var(--bg-secondary)]/50">
          <div className="flex items-center justify-between px-4 py-2.5 bg-[var(--bg-tertiary)]/45 border-b border-[var(--border-primary)]">
            <div className="flex items-center gap-3 min-w-0 flex-1 mr-3">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)]" />
              <input
                value={group.name ?? ''}
                onChange={(event) => updateGroupName(gi, event.target.value)}
                aria-label={`条件组 ${gi + 1} 名称`}
                placeholder={`条件组 ${gi + 1}`}
                className="w-full max-w-[260px] h-8 px-2.5 rounded-md border border-transparent bg-[var(--bg-primary)]/70 text-[12px] font-medium text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] outline-none hover:border-[var(--border-primary)] focus:border-[var(--accent)]"
              />
            </div>
            <div className="flex items-center gap-3">
              {(allowEmpty || groups.length > 1) && (
                <button onClick={() => removeGroup(gi)} className="text-[11px] text-[var(--accent-red)] hover:underline">删除</button>
              )}
              <button onClick={() => addCondition(gi)} className="text-[11px] text-[var(--accent)] hover:underline">+ 条件</button>
            </div>
          </div>

          <div className="px-4 py-3 space-y-2">
            {group.conditions.map((cond, conditionIndex) => {
              const leftSrc = cond.left.source
              const rightSrc = cond.right.source
              const leftInfo = leftSrc === 'indicator' ? indicators.find(i => i.type === (cond.left as {indicatorType?: string}).indicatorType) : null
              const rightInfo = rightSrc === 'indicator' ? indicators.find(i => i.type === (cond.right as {indicatorType?: string}).indicatorType) : null
              // 缠论买卖点（1/2/3买/卖）是独立条件，不需要操作符和右值
              const isChanSignal = leftSrc === 'chan' && (cond.left as {element?: string}).element === 'buySellPoint'
              const isMaLeft = leftSrc === 'indicator' && (cond.left as IndicatorValue).indicatorType === 'ma'
              const directionOperators: ConditionOperator[] = [
                ConditionOperator.Rising,
                ConditionOperator.Falling,
                ConditionOperator.TurnDown,
                ConditionOperator.TurnUp,
              ]
              const isDirectionOperator = directionOperators.includes(cond.operator)

              const srcValue = (c: ConditionValue) =>
                c.source === 'price' ? `price:${(c as {field: string}).field}`
                : c.source === 'indicator' ? `indicator:${(c as {indicatorType?: string}).indicatorType || ''}`
                : c.source === 'chan' ? `chan:${(c as {element?: string, property?: string}).property || (c as {element?: string}).element || ''}`
                : c.source

              const onSrcChange = (side: 'left' | 'right') => (e: React.ChangeEvent<HTMLSelectElement>) => {
                const [src, val] = e.target.value.split(':')
                const resetDirection = side === 'left' && isDirectionOperator && !(src === 'indicator' && val === 'ma')
                const operatorUpdate = resetDirection ? { operator: ConditionOperator.GreaterThan } : {}
                if (src === 'price') {
                  updateCondition(gi, conditionIndex, { [side]: { source: 'price', field: val as 'open'|'high'|'low'|'close'|'volume' }, ...operatorUpdate })
                } else if (src === 'indicator') {
                  const ind = indicators.find(i => i.type === val)
                  const field = ind?.render.plots[0]?.field ?? 'value'
                  updateCondition(gi, conditionIndex, { [side]: { source: 'indicator', indicatorType: val, params: { ...(ind?.default_params ?? {}) }, field }, ...operatorUpdate })
                } else if (src === 'chan') {
                  const opt = [...CHAN_OPTIONS, ...CHAN_SHAPE_OPTIONS].find(o => o.value === e.target.value)
                  const element = opt?.element ?? 'bi'
                  const property = (opt as typeof CHAN_OPTIONS[0])?.property
                  if (side === 'left' && element === 'buySellPoint') {
                    // 缠论买卖点：独立条件，自动设为「数量 > 0」（存在即满足）
                    updateCondition(gi, conditionIndex, {
                      left: { source: 'chan', element, property },
                      operator: ConditionOperator.GreaterThan,
                      right: { source: 'constant', value: 0 },
                    })
                  } else {
                    updateCondition(gi, conditionIndex, { [side]: { source: 'chan', element, property }, ...operatorUpdate })
                  }
                } else {
                  updateCondition(gi, conditionIndex, { [side]: { source: 'constant', value: 0 }, ...operatorUpdate })
                }
              }

              return (
                <div key={`${cond.id}:${conditionIndex}`} className="flex flex-wrap items-center gap-2.5 py-1.5 rounded-lg transition-colors duration-150 group">
                  {/* 级别选择（周期） */}
                  <select value={cond.timeframeId ?? ''}
                    onChange={e => updateCondition(gi, conditionIndex, { timeframeId: e.target.value || undefined })}
                    className={`${selClass} w-[88px] font-mono`} style={selStyle}>
                    <option value="" className="bg-[var(--bg-secondary)] text-[var(--text-muted)]">主周期</option>
                    {DEFAULT_TIMEFRAMES.map(tf => <option key={tf.id} value={tf.id} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{tf.label}</option>)}
                  </select>

                  <select value={srcValue(cond.left)} onChange={onSrcChange('left')}
                    className={`${selClass} flex-1 min-w-[150px]`} style={selStyle}>
                    <optgroup label="价格">{PRICE_OPTIONS.map(o => <option key={o.value} value={o.value} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{o.label}</option>)}</optgroup>
                    <optgroup label="指标">{indicators.map(i => <option key={`indicator:${i.type}`} value={`indicator:${i.type}`} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{i.name}</option>)}</optgroup>
                    <optgroup label="缠论·买卖点">{CHAN_OPTIONS.map(o => <option key={o.value} value={o.value} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{o.label}</option>)}</optgroup>
                    <optgroup label="缠论·形态">{CHAN_SHAPE_OPTIONS.map(o => <option key={o.value} value={o.value} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{o.label}</option>)}</optgroup>
                    <optgroup label="其他"><option value="constant" className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">固定值</option></optgroup>
                  </select>

                  {leftSrc === 'indicator' && leftInfo && leftInfo.render.plots.length > 1 && (
                    <select value={(cond.left as {field?: string}).field ?? 'value'}
                      aria-label={`${leftInfo.name} 输出线`}
                      onChange={e => updateCondition(gi, conditionIndex, { left: { ...cond.left, field: e.target.value } as ConditionValue })}
                      className={`${selClass} w-[90px] font-mono text-[12px]`} style={{ ...selStyle, paddingRight: '24px' }}>
                      {leftInfo.render.plots.map(p => <option key={p.field} value={p.field} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{p.label || p.field}</option>)}
                    </select>
                  )}

                  {leftSrc === 'indicator' && leftInfo && (
                    <IndicatorParamsEditor
                      value={cond.left as IndicatorValue}
                      info={leftInfo}
                      onChange={(params) => updateCondition(gi, conditionIndex, { left: { ...cond.left, params } as ConditionValue })}
                    />
                  )}

                  {leftSrc === 'constant' && (
                    <input type="number" value={(cond.left as {value?: number}).value ?? 0}
                      onChange={e => updateCondition(gi, conditionIndex, { left: { source: 'constant', value: parseFloat(e.target.value) || 0 } })}
                      className="w-[90px] bg-[var(--bg-tertiary)] text-[13px] text-[var(--text-primary)] px-3 py-2 rounded-lg border border-[var(--border-primary)] outline-none focus:border-[var(--accent)] transition-colors duration-150 text-right font-mono" placeholder="数值" />
                  )}

                  {/* 缠论买卖点：独立条件，不显示操作符和右值 */}
                  {!isChanSignal && (
                    <>
                      <select value={cond.operator} aria-label={`条件 ${conditionIndex + 1} 运算符`} onChange={(e) => {
                        const operator = e.target.value as ConditionOperator
                        updateCondition(gi, conditionIndex, {
                          operator,
                          ...(operator === ConditionOperator.Between && !cond.right2
                            ? { right2: { source: 'constant', value: 0 } as ConditionValue }
                            : {}),
                        })
                      }}
                        className={`${selClass} w-[92px] font-mono`} style={selStyle}>
                        {Object.entries(OPERATOR_LABELS).filter(([key]) => isMaLeft || !directionOperators.includes(key as ConditionOperator)).map(([key, label]) => (
                          <option key={key} value={key} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{label}</option>
                        ))}
                      </select>

                      {!isDirectionOperator && (
                        <>
                          <select value={srcValue(cond.right)} onChange={onSrcChange('right')}
                            className={`${selClass} flex-1 min-w-[150px]`} style={selStyle}>
                            <optgroup label="价格">{PRICE_OPTIONS.map(o => <option key={o.value} value={o.value} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{o.label}</option>)}</optgroup>
                            <optgroup label="指标">{indicators.map(i => <option key={`indicator:${i.type}`} value={`indicator:${i.type}`} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{i.name}</option>)}</optgroup>
                            <optgroup label="缠论·买卖点">{CHAN_OPTIONS.map(o => <option key={o.value} value={o.value} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{o.label}</option>)}</optgroup>
                            <optgroup label="缠论·形态">{CHAN_SHAPE_OPTIONS.map(o => <option key={o.value} value={o.value} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{o.label}</option>)}</optgroup>
                            <optgroup label="其他"><option value="constant" className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">固定值</option></optgroup>
                          </select>

                          {rightSrc === 'indicator' && rightInfo && rightInfo.render.plots.length > 1 && (
                            <select value={(cond.right as {field?: string}).field ?? 'value'}
                              aria-label={`${rightInfo.name} 输出线`}
                              onChange={e => updateCondition(gi, conditionIndex, { right: { ...cond.right, field: e.target.value } as ConditionValue })}
                              className={`${selClass} w-[90px] font-mono text-[12px]`} style={{ ...selStyle, paddingRight: '24px' }}>
                              {rightInfo.render.plots.map(p => <option key={p.field} value={p.field} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{p.label || p.field}</option>)}
                            </select>
                          )}

                          {rightSrc === 'indicator' && rightInfo && (
                            <IndicatorParamsEditor
                              value={cond.right as IndicatorValue}
                              info={rightInfo}
                              onChange={(params) => updateCondition(gi, conditionIndex, { right: { ...cond.right, params } as ConditionValue })}
                            />
                          )}

                          {rightSrc === 'constant' && (
                            <input type="number" value={(cond.right as {value?: number}).value ?? 0}
                              onChange={e => updateCondition(gi, conditionIndex, { right: { source: 'constant', value: parseFloat(e.target.value) || 0 } })}
                              className="w-[90px] bg-[var(--bg-tertiary)] text-[13px] text-[var(--text-primary)] px-3 py-2 rounded-lg border border-[var(--border-primary)] outline-none focus:border-[var(--accent)] transition-colors duration-150 text-right font-mono" placeholder="数值" />
                          )}

                          {cond.operator === ConditionOperator.Between && (
                            <label className="flex items-center gap-2 text-[12px] text-[var(--text-muted)] shrink-0">
                              至
                              <input
                                type="number"
                                value={cond.right2?.source === 'constant' ? cond.right2.value : 0}
                                onChange={(e) => updateCondition(gi, conditionIndex, {
                                  right2: { source: 'constant', value: parseFloat(e.target.value) || 0 },
                                })}
                                className="w-[90px] bg-[var(--bg-tertiary)] text-[13px] text-[var(--text-primary)] px-3 py-2 rounded-lg border border-[var(--border-primary)] outline-none focus:border-[var(--accent)] transition-colors duration-150 text-right font-mono"
                                placeholder="上限"
                              />
                            </label>
                          )}
                        </>
                      )}
                    </>
                  )}

                  <button onClick={() => removeCondition(gi, conditionIndex)}
                    disabled={group.conditions.length <= 1 && groups.length <= 1 && !allowEmpty}
                    className="w-8 h-8 rounded-lg flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--accent-red)] hover:bg-[var(--bg-tertiary)] transition-colors duration-150 disabled:opacity-20 disabled:cursor-not-allowed shrink-0 opacity-0 group-hover:opacity-100">
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      ))}

      <button onClick={addGroup}
        className="w-full h-9 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] border border-dashed border-[var(--border-primary)] hover:border-[var(--border-accent)] rounded-lg transition-all duration-150">
        + 条件组
      </button>
    </div>
  )
}
