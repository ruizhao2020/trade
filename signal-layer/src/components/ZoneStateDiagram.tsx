/**
 * 流动性聚集区的"方框状态"图示。
 *
 * 用 SVG 而不是 canvas：图示是用户要**读懂**的东西，用 DOM 画就能被测试断言
 * （这个仓库里 canvas 是测不到的）。形状与配色对齐真实渲染：
 * **填充＝流动性还在**（实线＝聚集阶段；虚线＝已被扫荡；填充随被拿走而抽空）。
 */

export type ZoneState = 'accumulating' | 'swept' | 'gone'

const ACTIVE_COLOR = '#6c8cff'
const SWEPT_COLOR = '#9b8cf2'

/** 生成 / 聚集：实线框 + 填满（流动性完整）。 */
function FilledBox({
  x, y, width, height, color = ACTIVE_COLOR, dashed = false, fillRatio = 1, fillFromTop = true,
}: {
  x: number; y: number; width: number; height: number
  color?: string; dashed?: boolean; fillRatio?: number; fillFromTop?: boolean
}) {
  const ratio = Math.min(Math.max(fillRatio, 0), 1)
  const fillHeight = height * ratio
  const fillY = fillFromTop ? y : y + height - fillHeight
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill="rgba(108,140,255,0.08)" />
      {ratio > 0 && (
        <rect x={x} y={fillY} width={width} height={Math.max(fillHeight, 1)} fill="rgba(108,140,255,0.34)" />
      )}
      <rect
        x={x} y={y} width={width} height={height}
        fill="none" stroke={color} strokeWidth={1}
        strokeDasharray={dashed ? '4 3' : undefined}
      />
    </g>
  )
}

/** 参数行里的紧凑图例：一眼看出三种方框形态。 */
export function ZoneStateSwatch({ state }: { state: ZoneState }) {
  const label = state === 'accumulating' ? '聚集中的方框：实线 + 填满'
    : state === 'swept' ? '被扫荡的方框：虚线 + 填充按剩余比例递减'
      : '完全扫荡的方框：虚线 + 不填充'
  return (
    <span className="inline-flex items-center" role="img" aria-label={label} title={label}>
      <svg width="14" height="12" viewBox="0 0 14 12" aria-hidden="true">
        {state === 'accumulating' && <FilledBox x={1} y={1} width={12} height={10} />}
        {state === 'swept' && (
          <FilledBox x={1} y={1} width={12} height={10} color={SWEPT_COLOR} dashed fillRatio={0.6} fillFromTop={false} />
        )}
        {state === 'gone' && (
          <FilledBox x={1} y={1} width={12} height={10} color={SWEPT_COLOR} dashed fillRatio={0} />
        )}
      </svg>
    </span>
  )
}

/**
 * 信息图标弹窗里的完整图示：从生成到消失的时间线。
 *
 * 只画"等高区（流动性在上方）"这一种：等低区是它的镜像，
 * 画两份会让图变复杂而不增加信息量。
 */
export function ZoneStateDiagram() {
  return (
    <svg
      width="252" height="132" viewBox="0 0 252 132"
      role="img" aria-label="流动性聚集区的方框状态：填充表示流动性还在——聚集阶段实线并填满，被扫荡后转虚线、填充按剩余比例递减直到抽空"
      className="block"
    >
      <FilledBox x={4} y={10} width={68} height={46} />
      <text x={38} y={70} textAnchor="middle" fontSize="9" fill="var(--text-secondary)">生成 → 聚集</text>
      <text x={38} y={82} textAnchor="middle" fontSize="9" fill="var(--text-muted)">实线框 + 填满</text>

      <line x1={76} y1={33} x2={90} y2={33} stroke="var(--text-muted)" strokeWidth={1} />
      <path d="M90 33 l-4 -2.5 l0 5 z" fill="var(--text-muted)" />

      <FilledBox x={94} y={10} width={68} height={46} color={SWEPT_COLOR} dashed fillRatio={0.6} fillFromTop={false} />
      <text x={128} y={70} textAnchor="middle" fontSize="9" fill="var(--text-secondary)">被扫荡（部分）</text>
      <text x={128} y={82} textAnchor="middle" fontSize="9" fill="var(--text-muted)">虚线 + 填充递减</text>

      <line x1={166} y1={33} x2={180} y2={33} stroke="var(--text-muted)" strokeWidth={1} />
      <path d="M180 33 l-4 -2.5 l0 5 z" fill="var(--text-muted)" />

      <FilledBox x={184} y={10} width={68} height={46} color={SWEPT_COLOR} dashed fillRatio={0} />
      <text x={218} y={70} textAnchor="middle" fontSize="9" fill="var(--text-secondary)">消失（完全扫荡）</text>
      <text x={218} y={82} textAnchor="middle" fontSize="9" fill="var(--text-muted)">虚线 + 不填充</text>

      <text x={4} y={100} fontSize="9" fill="var(--text-secondary)">填充比例 = 1 − 越界幅度 ÷ 区带高度</text>
      <text x={4} y={112} fontSize="9" fill="var(--text-muted)">即"这块流动性还剩多少"，从被扫荡那侧抽空</text>
      <text x={4} y={124} fontSize="9" fill="var(--text-muted)">方框右边界停在被扫荡那一刻，之后不再延伸</text>
    </svg>
  )
}
