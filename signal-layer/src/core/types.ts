/* ========== 周期定义 ========== */

export const PeriodType = {
  Intraday: 'intraday',
  Calendar: 'calendar',
} as const
export type PeriodType = (typeof PeriodType)[keyof typeof PeriodType]

export interface Timeframe {
  id: string
  label: string
  type: PeriodType
  intervalMinutes: number | null
  layerIndex: number
  expanded: boolean
}

/* ========== K 线数据 ========== */

export interface RawKline {
  openTime: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount?: number
  turnover?: number
  turnoverRate?: number
  circulatingShares?: number
  adjustmentFactor?: number
  adjustmentType?: string
  isClosed: boolean
}

export interface ChanKLine {
  openTime: number
  high: number
  low: number
  isUp: boolean
  rawIndices: number[]
  mergedCount: number
}

/* ========== 缠论元素 ========== */

export interface Fenxing {
  index: number
  direction: 'top' | 'bottom'
  price: number
  strength: number
  klineIndices: [number, number, number]
}

export interface Bi {
  index: number
  direction: 'up' | 'down'
  startFenxingIndex: number
  endFenxingIndex: number
  startTime: number
  endTime: number
  startPrice: number
  endPrice: number
  high: number
  low: number
  power: number
  klineRange: [number, number]
}

export interface FeatElement {
  first: number
  last: number
  bi: number
}

export interface Duan {
  index: number
  direction: 'up' | 'down'
  biIndices: number[]
  startTime: number
  endTime: number
  startPrice: number
  endPrice: number
  high: number
  low: number
  featElements?: FeatElement[]
  mergedFeat?: FeatElement[]
  fenxingType?: 'top' | 'bottom'
}

export interface Zhongshu {
  index: number
  high: number
  low: number
  mid: number
  biIndices: number[]
  startTime: number
  endTime: number
  level: string
  broken: boolean
  breakDirection?: 'up' | 'down'
}

export const SignalType = {
  Buy1: 'buy1',
  Buy2: 'buy2',
  Buy3: 'buy3',
  Sell1: 'sell1',
  Sell2: 'sell2',
  Sell3: 'sell3',
} as const
export type SignalType = (typeof SignalType)[keyof typeof SignalType]

export interface BuySellPoint {
  type: SignalType
  price: number
  time: number
  zhongshuIndex?: number
  biIndex: number
  confirmed: boolean
  strength: number
  reason?: string
  divergenceIndex?: number
}

export interface Divergence {
  index: number
  type: 'top' | 'bottom'
  level: 'bi'
  kind: 'consolidation'
  price: number
  time: number
  zhongshuIndex: number
  referenceBiIndex: number
  currentBiIndex: number
  referencePower: number
  currentPower: number
  strengthRatio: number
  confirmed: boolean
  reasons: string[]
}

/** 图表指标标记提供给通用详情浮窗的数据。 */
export interface IndicatorMarkerDetail {
  id: string
  title: string
  subtitle?: string
  accentColor: string
  fields: Array<{ label: string; value: string }>
  reasons?: string[]
}

export interface ChanAnalysis {
  timeframeId: string
  chanKLines: ChanKLine[]
  fenxings: Fenxing[]
  bis: Bi[]
  duans: Duan[]
  zhongshus: Zhongshu[]         // 笔中枢(level="bi")
  duanZhongshus: Zhongshu[]     // 段中枢(level="duan")
  buySellPoints: BuySellPoint[]
  divergences: Divergence[]
  updatedAt: number
  isComplete: boolean
}

/** 中枢级别:笔中枢(快速、噪音多)或段中枢(严格、滞后) */
export type ZhongshuLevel = 'bi' | 'duan'

/**
 * 缠论渲染选项 - 控制各元素是否显示及样式
 */
export interface ChanRenderOptions {
  showFenxing: boolean          // 显示分型(顶/底标记)
  showBi: boolean               // 显示笔(黄色细线)
  showDuan: boolean             // 显示线段(蓝色粗线)
  showZhongshu: boolean         // 显示中枢(矩形盒)
  showBuySellPoints: boolean    // 显示买卖点(一买/二买/三买)
  showDivergences: boolean      // 显示顶背驰/底背驰
  biColor?: string              // 笔颜色,默认黄色
  duanColor?: string            // 线段颜色,默认蓝色
  zhongshuColor?: string        // 中枢颜色,默认蓝色(未破)/绿/红(已破)
  showZhongshuAxis: boolean     // 显示中枢中轴虚线
  zsLevel: ZhongshuLevel        // 中枢级别:'bi'=笔中枢,'duan'=段中枢
}

/* ========== 指标系统 ========== */

/** 单条线的渲染规格 */
export interface PlotSpec {
  field: string                // 从 values 里取哪个字段(如 "value" / "dif")
  type: 'line' | 'histogram' | 'marker' | 'profile'  // 线、柱状图、信号标记或价格分布
  color: string
  label: string
}

/** 信号标记的渲染规格(如 BUY/SELL 箭头) */
export interface MarkerSpec {
  field: string                // 从 values 里取值,非零则为信号(>0=BUY, <0=SELL)
  priceField?: string          // 可选：使用指定价格精确定位，与 K 线拉开距离
  labelIndexField?: string     // 可选：追加到标签后的编号字段
  labelTagField?: string       // 可选：读取标签附注代码（如止损/止盈）
  labelTags?: Record<number, string> // 附注代码与显示文本的映射
  size?: number               // 标记大小，默认 2
  spacing?: number            // 与 K 线的固定视觉间距（以标记尺寸为单位）
  buyColor: string             // 买入标记颜色
  sellColor: string            // 卖出标记颜色
  buyLabel: string             // 买入标签(如 "BUY")
  sellLabel: string            // 卖出标签(如 "SELL")
}

/** 指标渲染规格 - 前端据此自动绘制,无需硬编码 */
export interface RenderSpec {
  window: 'main' | 'sub'       // main=主图叠加, sub=子图独立
  plots: PlotSpec[]
  markers?: MarkerSpec[]       // 信号标记(可选)
}

export interface IndicatorProfileSnapshot {
  time: number
  weights: number[]
  metrics: Record<string, number>
}

export interface IndicatorProfileData {
  prices: number[]
  snapshots: IndicatorProfileSnapshot[]
}

/** 指标计算结果(开放 values 字段,由后端 render 描述如何画) */
export interface IndicatorResult {
  type: string
  params: Record<string, number>
  values: Record<string, number>[]   // 每根 K 线一个对象,字段由指标决定(必含 time)
  render: RenderSpec
  profileData?: IndicatorProfileData
}

/** 指标元信息(指标库展示用) */
export interface IndicatorInfo {
  type: string
  name: string
  description: string
  default_params: Record<string, number>
  render: RenderSpec
}

/* ========== 条件引擎 ========== */

export const ConditionOperator = {
  GreaterThan: 'gt',
  GreaterEqual: 'gte',
  LessThan: 'lt',
  LessEqual: 'lte',
  Equal: 'eq',
  CrossAbove: 'crossAbove',
  CrossBelow: 'crossBelow',
  Rising: 'rising',
  Falling: 'falling',
  TurnDown: 'turnDown',
  TurnUp: 'turnUp',
  Between: 'between',
} as const
export type ConditionOperator = (typeof ConditionOperator)[keyof typeof ConditionOperator]

export type ConditionValue =
  | { source: 'price'; field: 'open' | 'high' | 'low' | 'close' | 'volume' }
  | { source: 'indicator'; indicatorType: string; params: Record<string, number>; field: 'value' | string }
  | { source: 'chan'; element: 'fenxing' | 'bi' | 'zhongshu' | 'divergence' | 'buySellPoint'; property?: string }
  | { source: 'constant'; value: number }
  | { source: 'timeframe'; timeframeId: string; inner: ConditionValue }

export interface Condition {
  id: string
  name: string
  left: ConditionValue
  operator: ConditionOperator
  right: ConditionValue
  right2?: ConditionValue
  timeframeId?: string
  enabled: boolean
}

export interface TradeParams {
  stopLossType: 'atr' | 'fixed_pct' | 'swing_low'
  stopLossValue: number
  takeProfitType: 'atr' | 'fixed_pct' | 'rr_ratio'
  takeProfitValue: number
  positionType: 'fixed_pct' | 'kelly'
  positionValue: number
  // 条件式出场：复用条件组结构，引用指标/价格/缠论做判断
  exitConditions: ConditionGroup[]
  exitLogic: 'AND' | 'OR'
}

export interface ConditionTemplate {
  id: string
  name: string
  logic: 'AND' | 'OR'
  conditionGroups: ConditionGroup[]
  primaryTimeframeId: string
  secondaryTimeframeIds: string[]
  createdAt: number
  updatedAt: number
  enabled: boolean
  tradeParams?: TradeParams
}

export interface ConditionGroup {
  id: string
  name?: string
  conditions: Condition[]
}

export const SignalState = {
  Idle: 'idle',
  Evaluating: 'evaluating',
  Partial: 'partial',
  Ready: 'ready',
} as const
export type SignalState = (typeof SignalState)[keyof typeof SignalState]

export interface ConditionEvaluation {
  conditionId: string
  satisfied: boolean
  leftValue: number
  rightValue: number
  diffPercent: number
}

export interface GroupEvaluation {
  groupId: string
  evaluations: ConditionEvaluation[]
  satisfied: boolean
}

export interface TemplateSignal {
  templateId: string
  state: SignalState
  groups: GroupEvaluation[]
  isReady: boolean
  updatedAt: number
  progressPercent: number
}

/* ========== 图表渲染 ========== */

// 每个周期图层需要显示什么指标
export interface IndicatorDisplay {
  type: 'ma' | 'ema' | 'macd' | 'bollinger' | 'rsi' | 'kdj' | 'chan' | string
  params: Record<string, number>
  window: 'main' | 'sub'
  color?: string
}

// 图层配置——存储层面的定义（配合 Zustand 使用）
export interface LayerConfig {
  timeframeId: string
  layerIndex: number
  visible: boolean
  opacity: number
  indicators: IndicatorDisplay[]
  colorScheme?: { upColor: string; downColor: string }
}

/* ========== 设置与状态 ========== */

export interface AppSettings {
  symbol: string
  primaryTimeframe: string
  layers: LayerConfig[]
  showVolume: boolean
  theme: 'dark' | 'light'
}
