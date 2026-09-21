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
  turnDown: '上转下', turnUp: '下转上', support: '支撑', resistance: '压制',
}

const PRICE_OPTIONS = [
  { value: 'price:close', label: '收盘价' },
  { value: 'price:high', label: '最高价' },
  { value: 'price:low', label: '最低价' },
  { value: 'price:open', label: '开盘价' },
  { value: 'price:volume', label: '成交量' },
]

const CHAN_OPTIONS = [
  { value: 'chan:bottom', label: '底背驰', element: 'divergence' as const, property: 'bottom' },
  { value: 'chan:top', label: '顶背驰', element: 'divergence' as const, property: 'top' },
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

const CHIP_FIELD_OPTIONS = [
  { field: 'peak_price', label: '主筹码峰' },
  { field: 'average_cost', label: '平均成本' },
  { field: 'profit_ratio', label: '获利盘比例' },
  { field: 'range70_low', label: '70%成本下沿' },
  { field: 'range70_high', label: '70%成本上沿' },
  { field: 'concentration70', label: '70%集中度' },
  { field: 'range90_low', label: '90%成本下沿' },
  { field: 'range90_high', label: '90%成本上沿' },
  { field: 'concentration90', label: '90%集中度' },
  { field: 'price_vs_peak_pct', label: '距主峰百分比' },
  { field: 'price_vs_average_pct', label: '距平均成本百分比' },
  { field: 'above_peak', label: '站上主筹码峰' },
  { field: 'above_average_cost', label: '站上平均成本' },
  { field: 'inside_range70', label: '位于70%成本区间' },
  { field: 'inside_range90', label: '位于90%成本区间' },
  { field: 'support_chip_ratio', label: '下方支撑筹码' },
  { field: 'pressure_chip_ratio', label: '上方压力筹码' },
  { field: 'upper_chip_ratio', label: '套牢筹码比例' },
  { field: 'near_price_chip_ratio', label: '现价附近筹码' },
  { field: 'dominant_peak_ratio', label: '主峰筹码占比' },
  { field: 'peak_count', label: '有效筹码峰数量' },
  { field: 'single_peak', label: '单峰密集' },
  { field: 'double_peak', label: '双峰结构' },
  { field: 'secondary_peak_price', label: '次筹码峰' },
  { field: 'peak_separation_pct', label: '主次峰间距' },
  { field: 'peak_change_pct', label: '主峰迁移幅度' },
  { field: 'average_cost_change_pct', label: '平均成本变化' },
  { field: 'profit_ratio_change', label: '获利盘变化' },
  { field: 'concentration70_change', label: '集中度变化' },
  { field: 'peak_direction', label: '主峰迁移方向' },
  { field: 'average_cost_direction', label: '平均成本方向' },
  { field: 'chip_converging', label: '筹码正在集中' },
  { field: 'chip_spreading', label: '筹码正在发散' },
  { field: 'cross_peak_up', label: '上穿主筹码峰' },
  { field: 'cross_peak_down', label: '下穿主筹码峰' },
  { field: 'cross_average_cost_up', label: '上穿平均成本' },
  { field: 'cross_average_cost_down', label: '下穿平均成本' },
  { field: 'break_range70_high', label: '突破70%成本上沿' },
  { field: 'break_range70_low', label: '跌破70%成本下沿' },
  { field: 'retest_peak', label: '回踩主峰' },
  { field: 'single_peak_formed', label: '单峰密集形成' },
  { field: 'double_peak_formed', label: '双峰结构形成' },
  { field: 'peak_shifted_up', label: '主峰确认上移' },
  { field: 'peak_shifted_down', label: '主峰确认下移' },
  { field: 'concentration_started', label: '开始集中' },
  { field: 'pressure_released', label: '上方压力释放' },
  { field: 'support_strengthened', label: '下方支撑增强' },
  { field: 'coverage_ratio', label: '数据覆盖率' },
]

const selectArrow = `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 8 5'%3e%3cpath stroke='%238B8B9E' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M1 1l3 3 3-3'/%3e%3c/svg%3e")`

type IndicatorValue = Extract<ConditionValue, { source: 'indicator' }>

const PARAM_LABELS: Record<string, string> = {
  period: '周期', touch_tolerance_pct: '触碰容差', fast: '快线', slow: '慢线', signal: '信号线',
  n: '计算周期', m1: 'K值平滑', m2: 'D值平滑', std: '标准差倍数',
  bins: '价格档位', lookback: '回看天数', min_turnover_days: '最少有效天数',
  piv_len: '枢轴长度', atr_len: '波幅周期',
  shrink_max: '缩量上限', increase_min: '增量起点', double_min: '倍量起点',
  triple_min: '三倍量起点', multiple_min: '多倍量起点', flat_tolerance: '平量容差',
  sequence_length: '连续根数', relative_period: '相对量周期', key_ratio_min: '关键柱倍率',
  confirm_bars: '确认根数', break_tolerance: '破位容差',
  near_range_pct: '现价附近范围', support_range_pct: '支撑压力范围',
  peak_prominence: '峰值显著度', min_peak_distance: '最小峰间距',
  trend_period: '迁移周期', migration_threshold_pct: '迁移阈值',
  concentration_change_threshold: '集中变化阈值', pressure_release_threshold: '压力释放阈值',
  retest_tolerance_pct: '回踩容差',
  departure_confirm_bars: '脱离确认根数', true_departure_bars: '真脱离根数',
  false_departure_max_bars: '假脱离窗口', retest_window: '回归失败窗口',
  maturity_bars: '态势成熟根数', maturity_folds: '态势成熟折叠',
  breakout_buffer_pct: '突破缓冲',
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
    <div className="flex items-center gap-3 flex-wrap">
      {Object.entries(value.params).map(([key, paramValue]) => {
        const label = PARAM_LABELS[key] ?? key
        if (value.indicatorType === 'ma' && key === 'period') {
          return (
            <label key={key} className="flex items-center">
              <select
                aria-label={`${info.name} ${label}`}
                value={paramValue}
                onChange={(event) => onChange({ ...value.params, [key]: Number(event.target.value) })}
                className="h-10 w-[104px] px-2.5 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[12px] font-mono text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
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
              className="h-10 w-[76px] px-2.5 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[12px] font-mono text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
            />
          </label>
        )
      })}
    </div>
  )
}

function indicatorOutputs(info: IndicatorInfo | null | undefined) {
  if (!info) return []
  return info.outputs?.length
    ? info.outputs
    : info.render.plots.map((plot) => ({ field: plot.field, label: plot.label || plot.field }))
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
      logic: 'AND',
      conditions: [defaultCondition()],
    }])
  }

  function updateGroupName(groupIndex: number, name: string) {
    onChange(groups.map((group, index) => index === groupIndex ? { ...group, name } : group))
  }

  function updateGroupLogic(groupIndex: number, logic: 'AND' | 'OR') {
    onChange(groups.map((group, index) => index === groupIndex ? { ...group, logic } : group))
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

  const selClass = "h-10 bg-[var(--bg-tertiary)] text-[12px] text-[var(--text-primary)] px-3 rounded-lg border border-[var(--border-primary)] outline-none focus:border-[var(--accent)] transition-colors duration-150 appearance-none"
  const selStyle = { backgroundImage: selectArrow, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 10px center', backgroundSize: '8px 5px', paddingRight: '28px' }

  return (
    <div className="space-y-5">
      {groups.map((group, gi) => (
        <div key={`${group.id}:${gi}`} className="border border-[var(--border-primary)] rounded-xl overflow-hidden bg-[var(--bg-secondary)]/55 shadow-[0_1px_0_rgba(255,255,255,.02)]">
          <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4 bg-[var(--bg-tertiary)]/45 border-b border-[var(--border-primary)]">
            <div className="flex items-center gap-3 min-w-[240px] flex-1">
              <span className="w-2 h-2 rounded-full bg-[var(--accent)] shrink-0" />
              <input
                value={group.name ?? ''}
                onChange={(event) => updateGroupName(gi, event.target.value)}
                aria-label={`条件组 ${gi + 1} 名称`}
                placeholder={`条件组 ${gi + 1}`}
                className="w-full max-w-[340px] h-10 px-3 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)]/70 text-[12px] font-medium text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] outline-none focus:border-[var(--accent)]"
              />
            </div>
            <div className="flex flex-wrap items-center justify-end gap-3">
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-[var(--text-muted)] whitespace-nowrap">组内关系</span>
                <div className="flex h-10 p-1 rounded-lg bg-[var(--bg-primary)] border border-[var(--border-primary)]" aria-label={`条件组 ${gi + 1} 组内关系`}>
                  <button type="button" onClick={() => updateGroupLogic(gi, 'AND')} className={`min-w-[64px] px-3 rounded-md text-[11px] font-medium transition-colors ${(group.logic ?? 'AND') === 'AND' ? 'bg-[var(--accent)] text-white shadow-sm' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'}`}>与 · 全部</button>
                  <button type="button" onClick={() => updateGroupLogic(gi, 'OR')} className={`min-w-[64px] px-3 rounded-md text-[11px] font-medium transition-colors ${(group.logic ?? 'AND') === 'OR' ? 'bg-[var(--accent)] text-white shadow-sm' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'}`}>或 · 任一</button>
                </div>
              </div>
              {(allowEmpty || groups.length > 1) && (
                <button type="button" onClick={() => removeGroup(gi)} className="h-9 px-3 rounded-lg border border-[rgba(255,107,114,.25)] text-[11px] text-[var(--accent-red)] hover:bg-[rgba(255,107,114,.08)] transition-colors">删除组</button>
              )}
              <button type="button" onClick={() => addCondition(gi)} className="h-9 px-3.5 rounded-lg border border-[var(--border-accent)] text-[11px] text-[var(--accent)] hover:bg-[rgba(108,140,255,.10)] transition-colors">+ 添加条件</button>
            </div>
          </div>

          <div className="px-5 py-5 space-y-3">
            {group.conditions.map((cond, conditionIndex) => {
              const leftSrc = cond.left.source
              const rightSrc = cond.right.source
              const leftInfo = leftSrc === 'indicator' ? indicators.find(i => i.type === (cond.left as {indicatorType?: string}).indicatorType) : null
              const rightInfo = rightSrc === 'indicator' ? indicators.find(i => i.type === (cond.right as {indicatorType?: string}).indicatorType) : null
              const leftOutputs = indicatorOutputs(leftInfo)
              const rightOutputs = indicatorOutputs(rightInfo)
              // 缠论背驰和买卖点是独立事件条件，不需要操作符和右值
              const isChanSignal = leftSrc === 'chan' && ['divergence', 'buySellPoint'].includes((cond.left as {element?: string}).element ?? '')
              const isMaLeft = leftSrc === 'indicator' && (cond.left as IndicatorValue).indicatorType === 'ma'
              const isChipLeft = leftSrc === 'indicator' && (cond.left as IndicatorValue).indicatorType === 'chip_distribution'
              const unaryOperators: ConditionOperator[] = [
                ConditionOperator.Rising,
                ConditionOperator.Falling,
                ConditionOperator.TurnDown,
                ConditionOperator.TurnUp,
                ConditionOperator.Support,
                ConditionOperator.Resistance,
              ]
              const isUnaryOperator = unaryOperators.includes(cond.operator)

              const srcValue = (c: ConditionValue) =>
                c.source === 'price' ? `price:${(c as {field: string}).field}`
                : c.source === 'indicator' ? `indicator:${(c as {indicatorType?: string}).indicatorType || ''}`
                : c.source === 'chan' ? `chan:${(c as {element?: string, property?: string}).property || (c as {element?: string}).element || ''}`
                : c.source

              const onSrcChange = (side: 'left' | 'right') => (e: React.ChangeEvent<HTMLSelectElement>) => {
                const [src, val] = e.target.value.split(':')
                const resetDirection = side === 'left' && isUnaryOperator && !(src === 'indicator' && val === 'ma')
                const operatorUpdate = resetDirection ? { operator: ConditionOperator.GreaterThan } : {}
                if (src === 'price') {
                  updateCondition(gi, conditionIndex, { [side]: { source: 'price', field: val as 'open'|'high'|'low'|'close'|'volume' }, ...operatorUpdate })
                } else if (src === 'indicator') {
                  const ind = indicators.find(i => i.type === val)
                  const field = val === 'chip_distribution' ? CHIP_FIELD_OPTIONS[0]!.field : indicatorOutputs(ind)[0]?.field ?? 'value'
                  updateCondition(gi, conditionIndex, { [side]: { source: 'indicator', indicatorType: val, params: { ...(ind?.default_params ?? {}) }, field }, ...operatorUpdate })
                } else if (src === 'chan') {
                  const opt = [...CHAN_OPTIONS, ...CHAN_SHAPE_OPTIONS].find(o => o.value === e.target.value)
                  const element = opt?.element ?? 'bi'
                  const property = (opt as typeof CHAN_OPTIONS[0])?.property
                  if (side === 'left' && ['divergence', 'buySellPoint'].includes(element)) {
                    // 缠论事件：独立条件，自动设为「数量 > 0」（存在即满足）
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
                <div key={`${cond.id}:${conditionIndex}`} className="flex flex-wrap items-center gap-3 p-3 rounded-xl border border-[var(--border-primary)] bg-[var(--bg-primary)]/45 transition-colors duration-150 hover:border-[var(--border-accent)] group">
                  <span className="min-w-6 h-6 px-1.5 rounded-md bg-[var(--bg-tertiary)] flex items-center justify-center text-[10px] font-mono text-[var(--text-muted)] shrink-0">{conditionIndex + 1}</span>
                  {/* 级别选择（周期） */}
                  <select value={cond.timeframeId ?? ''}
                    onChange={e => updateCondition(gi, conditionIndex, { timeframeId: e.target.value || undefined })}
                    className={`${selClass} w-[96px] font-mono`} style={selStyle}>
                    <option value="" className="bg-[var(--bg-secondary)] text-[var(--text-muted)]">主周期</option>
                    {DEFAULT_TIMEFRAMES.map(tf => <option key={tf.id} value={tf.id} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{tf.label}</option>)}
                  </select>

                  <select value={srcValue(cond.left)} onChange={onSrcChange('left')}
                    className={`${selClass} flex-1 min-w-[168px]`} style={selStyle}>
                    <optgroup label="价格">{PRICE_OPTIONS.map(o => <option key={o.value} value={o.value} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{o.label}</option>)}</optgroup>
                    <optgroup label="指标">{indicators.map(i => <option key={`indicator:${i.type}`} value={`indicator:${i.type}`} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{i.name}</option>)}</optgroup>
                    <optgroup label="缠论·信号">{CHAN_OPTIONS.map(o => <option key={o.value} value={o.value} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{o.label}</option>)}</optgroup>
                    <optgroup label="缠论·形态">{CHAN_SHAPE_OPTIONS.map(o => <option key={o.value} value={o.value} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{o.label}</option>)}</optgroup>
                    <optgroup label="其他"><option value="constant" className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">固定值</option></optgroup>
                  </select>

                  {leftSrc === 'indicator' && leftInfo && !isChipLeft && leftOutputs.length > 1 && (
                    <select value={(cond.left as {field?: string}).field ?? 'value'}
                      aria-label={`${leftInfo.name} 输出线`}
                      onChange={e => updateCondition(gi, conditionIndex, { left: { ...cond.left, field: e.target.value } as ConditionValue })}
                      className={`${selClass} w-[90px] font-mono text-[12px]`} style={{ ...selStyle, paddingRight: '24px' }}>
                      {leftOutputs.map(output => <option key={output.field} value={output.field} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{output.label}</option>)}
                    </select>
                  )}

                  {isChipLeft && (
                    <select value={(cond.left as IndicatorValue).field} aria-label="筹码分布字段" onChange={e => updateCondition(gi, conditionIndex, { left: { ...cond.left, field: e.target.value } as ConditionValue })} className={`${selClass} w-[120px]`} style={selStyle}>
                      {CHIP_FIELD_OPTIONS.map(option => <option key={option.field} value={option.field}>{option.label}</option>)}
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

                  {/* 缠论背驰/买卖点：独立条件，不显示操作符和右值 */}
                  {!isChanSignal && (
                    <>
                      <select value={cond.operator} aria-label={`条件 ${conditionIndex + 1} 运算符`} onChange={(e) => {
                        updateCondition(gi, conditionIndex, { operator: e.target.value as ConditionOperator })
                      }}
                        className={`${selClass} w-[104px] font-mono`} style={selStyle}>
                        {Object.entries(OPERATOR_LABELS).filter(([key]) => isMaLeft || !unaryOperators.includes(key as ConditionOperator)).map(([key, label]) => (
                          <option key={key} value={key} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{label}</option>
                        ))}
                      </select>

                      {!isUnaryOperator && (
                        <>
                          <select value={srcValue(cond.right)} onChange={onSrcChange('right')}
                            className={`${selClass} flex-1 min-w-[168px]`} style={selStyle}>
                            <optgroup label="价格">{PRICE_OPTIONS.map(o => <option key={o.value} value={o.value} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{o.label}</option>)}</optgroup>
                            <optgroup label="指标">{indicators.map(i => <option key={`indicator:${i.type}`} value={`indicator:${i.type}`} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{i.name}</option>)}</optgroup>
                            <optgroup label="缠论·信号">{CHAN_OPTIONS.map(o => <option key={o.value} value={o.value} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{o.label}</option>)}</optgroup>
                            <optgroup label="缠论·形态">{CHAN_SHAPE_OPTIONS.map(o => <option key={o.value} value={o.value} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{o.label}</option>)}</optgroup>
                            <optgroup label="其他"><option value="constant" className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">固定值</option></optgroup>
                          </select>

                          {rightSrc === 'indicator' && rightInfo && (cond.right as IndicatorValue).indicatorType !== 'chip_distribution' && rightOutputs.length > 1 && (
                            <select value={(cond.right as {field?: string}).field ?? 'value'}
                              aria-label={`${rightInfo.name} 输出线`}
                              onChange={e => updateCondition(gi, conditionIndex, { right: { ...cond.right, field: e.target.value } as ConditionValue })}
                              className={`${selClass} w-[90px] font-mono text-[12px]`} style={{ ...selStyle, paddingRight: '24px' }}>
                              {rightOutputs.map(output => <option key={output.field} value={output.field} className="bg-[var(--bg-secondary)] text-[var(--text-primary)]">{output.label}</option>)}
                            </select>
                          )}

                          {rightSrc === 'indicator' && (cond.right as IndicatorValue).indicatorType === 'chip_distribution' && (
                            <select value={(cond.right as IndicatorValue).field} aria-label="筹码分布右值字段" onChange={e => updateCondition(gi, conditionIndex, { right: { ...cond.right, field: e.target.value } as ConditionValue })} className={`${selClass} w-[120px]`} style={selStyle}>
                              {CHIP_FIELD_OPTIONS.map(option => <option key={option.field} value={option.field}>{option.label}</option>)}
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

                        </>
                      )}
                    </>
                  )}

                  <button onClick={() => removeCondition(gi, conditionIndex)}
                    disabled={group.conditions.length <= 1 && groups.length <= 1 && !allowEmpty}
                    aria-label={`删除条件 ${conditionIndex + 1}`}
                    className="w-10 h-10 rounded-lg border border-transparent flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--accent-red)] hover:border-[rgba(255,107,114,.25)] hover:bg-[rgba(255,107,114,.08)] transition-colors duration-150 disabled:opacity-20 disabled:cursor-not-allowed shrink-0">
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      ))}

      <button type="button" onClick={addGroup}
        className="w-full h-11 text-[11px] font-medium text-[var(--text-muted)] hover:text-[var(--accent)] border border-dashed border-[var(--border-primary)] hover:border-[var(--accent)] hover:bg-[rgba(108,140,255,.06)] rounded-xl transition-all duration-150">
        + 添加条件组
      </button>
    </div>
  )
}
