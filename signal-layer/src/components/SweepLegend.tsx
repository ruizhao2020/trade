/**
 * 流动性扫荡反转的图例与释义（SSL SWEEP / BSL SWEEP）。
 *
 * 图上标记直接写着英文缩写，而 SSL/BSL 是 ICT/SMC 的术语：
 * - SSL = Sell-Side Liquidity（卖方流动性）：挂在摆动低点**下方**的卖单池
 *   ——多头止损、以及突破做空者的卖出委托。
 * - BSL = Buy-Side Liquidity（买方流动性）：挂在摆动高点**上方**的买单池
 *   ——空头止损、以及突破做多者的买入委托。
 *
 * 用 SVG 画小图而不是贴图：图示是用户要读懂的东西，DOM 画就能被测试断言
 * （这个仓库里 canvas 是测不到的）。
 */

export type SweepSide = 'ssl' | 'bsl'

/**
 * 参数行里的紧凑图例：一个小箭头 + 颜色，对应图上的标记。
 *
 * 颜色由调用方从**接口的 render.markers** 传进来，不在这里硬编码：
 * 图上标记、图例、释义图三处必须是同一个来源，否则改配色时总会漏一处。
 */
export function SweepSwatch({ side, color }: { side: SweepSide; color: string }) {
  const isBull = side === 'ssl'
  const label = isBull ? 'SSL SWEEP：卖方流动性被扫，看涨' : 'BSL SWEEP：买方流动性被扫，看跌'
  return (
    <span className="inline-flex items-center" role="img" aria-label={label} title={label}>
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
        <path
          d={isBull ? 'M6 2.5 L10 9.5 L2 9.5 Z' : 'M6 9.5 L2 2.5 L10 2.5 Z'}
          fill={color}
        />
      </svg>
    </span>
  )
}

/**
 * 信息图标弹窗里的完整释义：图示 + 文字。
 *
 * 不把文字单独导出：这个文件同时导出组件与常量会破坏 fast-refresh 约定
 * （eslint react-refresh/only-export-components）。
 */
export function SweepGlossary({ bullColor, bearColor }: { bullColor: string; bearColor: string }) {
  return (
    <>
    <svg
      width="252" height="126" viewBox="0 0 252 126"
      role="img"
      aria-label="SSL SWEEP：影线跌破低点后收回，看涨；BSL SWEEP：影线突破高点后收回，看跌"
      className="block"
    >
      {/* 左：卖方流动性被扫（看涨） */}
      <text x={4} y={10} fontSize="9" fill={bullColor}>SSL SWEEP · 看涨</text>
      <line x1={4} y1={62} x2={116} y2={62} stroke="#8a93a6" strokeWidth={1} strokeDasharray="3 3" />
      <text x={118} y={62} fontSize="8" fill="var(--text-muted)">低点</text>
      <path d="M6 30 L34 56 L44 74 L56 50 L80 34 L100 20" fill="none" stroke={bullColor} strokeWidth={1.6} />
      <text x={4} y={88} fontSize="9" fill="var(--text-secondary)">影线跌破低点（拿走卖单）</text>
      <text x={4} y={100} fontSize="9" fill="var(--text-secondary)">收盘收回 → 卖压已释放</text>

      {/* 右：买方流动性被扫（看跌） */}
      <text x={140} y={10} fontSize="9" fill={bearColor}>BSL SWEEP · 看跌</text>
      <line x1={140} y1={62} x2={248} y2={62} stroke="#8a93a6" strokeWidth={1} strokeDasharray="3 3" />
      <text x={140} y={76} fontSize="8" fill="var(--text-muted)">高点</text>
      <path d="M142 96 L170 70 L180 50 L192 74 L216 88 L242 104" fill="none" stroke={bearColor} strokeWidth={1.6} />

      <text x={4} y={118} fontSize="9" fill="var(--text-muted)">被扫掉的挂单成交完后，价格常朝反方向走</text>
    </svg>
    <div className="mt-2 whitespace-pre-line text-[11px] leading-5">{GLOSSARY}</div>
    </>
  )
}

/**
 * 术语释义的正文（信息图标弹出的文字部分）。
 *
 * 顺序刻意是"谁挂的单 → 为什么被扫 → 为什么反向"：只写"SSL 看涨"等于没解释。
 */
const GLOSSARY = [
  'SSL = 卖方流动性：挂在摆动低点下方的卖单池（多头止损 + 突破者卖出）。',
  'BSL = 买方流动性：挂在摆动高点上方的买单池（空头止损 + 突破者买入）。',
  '扫荡＝影线越过这些水平（触发并成交那些挂单）后收盘又回到内侧。',
  '大资金想建仓但盘口不够深时，会主动把价格推向这些挂单池去成交。',
  'SSL 被扫说明卖方挂单已被吃光、接货的是买方 → 看涨反转（图上标 SSL SWEEP）。',
  'BSL 被扫说明买方挂单已被吃光、接货的是卖方 → 看跌反转（图上标 BSL SWEEP）。',
  '标记挂在「被扫的那个价位」上，所以图上还能看出扫荡发生在哪。',
].join('\n')
