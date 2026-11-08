/**
 * 形态示意图：给「看图才懂」的形态配一张线稿。
 *
 * 只覆盖形态类字段（量价 8 形态 + 筹码双峰），连续量字段不配图。
 * 图是示意，不是真实行情：颜色/线宽跟主题走，尺寸固定，避免撑高条件卡片。
 */

export type FormDiagramKind =
  | 'volume_price:volume_breakout'
  | 'volume_price:shrink_pullback'
  | 'volume_price:price_volume_rise'
  | 'volume_price:volume_stagnation'
  | 'volume_price:climax_top'
  | 'volume_price:exhaustion_bottom'
  | 'volume_price:bottom_volume'
  | 'volume_price:failed_breakout'
  | 'chip_distribution:double_peak_formed'

const STROKE = '#8b93a7'
const ACCENT_UP = '#ff5b62'
const ACCENT_DOWN = '#2fc58d'
const FAINT = 'rgba(139,147,167,0.28)'

function Shape({ children }: { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 160 72" width="160" height="72" role="img" aria-hidden="true" className="shrink-0">
      <rect x="0.5" y="0.5" width="159" height="71" rx="6" fill="rgba(255,255,255,0.02)" stroke={FAINT} />
      {children}
    </svg>
  )
}

// 一根简化的 K 线：竖线 + 实体
function Candle({ x, open, close, high, low, up }: { x: number; open: number; close: number; high: number; low: number; up: boolean }) {
  const top = Math.min(open, close)
  const height = Math.max(1.5, Math.abs(open - close))
  return (
    <g stroke={up ? ACCENT_UP : ACCENT_DOWN} fill={up ? ACCENT_UP : ACCENT_DOWN}>
      <line x1={x} y1={high} x2={x} y2={low} strokeWidth={1} />
      <rect x={x - 2.5} y={top} width={5} height={height} rx={0.8} />
    </g>
  )
}

const DIAGRAMS: Record<FormDiagramKind, React.ReactNode> = {
  'volume_price:volume_breakout': (
    <Shape>
      {[30, 38, 34, 42, 40, 48, 46].map((v, i) => <Candle key={i} x={28 + i * 10} open={v + 4} close={v} high={v - 4} low={v + 7} up={false} />)}
      <Candle x={98} open={38} close={26} high={22} low={40} up />
      <line x1={20} y1={28} x2={140} y2={28} stroke={FAINT} strokeDasharray="4 3" />
      <text x={24} y={66} fill={STROKE} fontSize="8">突破前高</text>
    </Shape>
  ),
  'volume_price:shrink_pullback': (
    <Shape>
      <Candle x={30} open={58} close={40} high={36} low={62} up />
      <Candle x={42} open={44} close={38} high={34} low={48} up />
      {[54, 62, 70].map((x, i) => <Candle key={i} x={x} open={36 + i * 3} close={40 + i * 3} high={34 + i * 3} low={43 + i * 3} up={false} />)}
      <Candle x={86} open={46} close={38} high={34} low={50} up />
      <line x1={78} y1={52} x2={78} y2={30} stroke={ACCENT_UP} strokeDasharray="3 2" />
      <text x={94} y={40} fill={STROKE} fontSize="8">量缩</text>
    </Shape>
  ),
  'volume_price:price_volume_rise': (
    <Shape>
      {[34, 30, 26, 22].map((v, i) => <Candle key={i} x={34 + i * 14} open={v + 6} close={v} high={v - 4} low={v + 8} up />)}
      {[10, 14, 19, 25].map((h, i) => <rect key={i} x={34 + i * 14 - 3} y={62 - h} width={6} height={h} fill={ACCENT_UP} opacity={0.55} />)}
      <text x={96} y={22} fill={STROKE} fontSize="8">价升量增</text>
    </Shape>
  ),
  'volume_price:volume_stagnation': (
    <Shape>
      <Candle x={34} open={56} close={30} high={26} low={60} up />
      <Candle x={52} open={30} close={26} high={24} low={34} up />
      <rect x={49} y={34} width={6} height={28} fill={ACCENT_UP} opacity={0.55} />
      <rect x={31} y={46} width={6} height={16} fill={ACCENT_UP} opacity={0.55} />
      <line x1={24} y1={22} x2={140} y2={22} stroke={FAINT} strokeDasharray="4 3" />
      <text x={86} y={40} fill={STROKE} fontSize="8">放量滞涨</text>
    </Shape>
  ),
  'volume_price:climax_top': (
    <Shape>
      {[50, 40, 30, 22, 16].map((v, i) => <Candle key={i} x={38 + i * 12} open={v + 7} close={v} high={v - 4} low={v + 9} up />)}
      <rect x={86} y={30} width={8} height={34} fill={ACCENT_UP} opacity={0.65} />
      <line x1={30} y1={12} x2={130} y2={12} stroke={FAINT} strokeDasharray="4 3" />
      <text x={104} y={50} fill={STROKE} fontSize="8">天量</text>
    </Shape>
  ),
  'volume_price:exhaustion_bottom': (
    <Shape>
      {[26, 34, 42, 50].map((v, i) => <Candle key={i} x={36 + i * 13} open={v} close={v + 6} high={v - 4} low={v + 8} up={false} />)}
      {[16, 12, 9, 7].map((h, i) => <rect key={i} x={36 + i * 13 - 3} y={62 - h} width={6} height={h} fill={ACCENT_DOWN} opacity={0.55} />)}
      <text x={96} y={22} fill={STROKE} fontSize="8">地量地价</text>
    </Shape>
  ),
  'volume_price:bottom_volume': (
    <Shape>
      {[50, 56, 60].map((v, i) => <Candle key={i} x={34 + i * 12} open={v} close={v + 5} high={v - 4} low={v + 7} up={false} />)}
      <Candle x={82} open={60} close={48} high={44} low={64} up />
      <rect x={79} y={34} width={7} height={26} fill={ACCENT_UP} opacity={0.6} />
      <line x1={24} y1={64} x2={144} y2={64} stroke={FAINT} strokeDasharray="4 3" />
      <text x={96} y={44} fill={STROKE} fontSize="8">低位放量阳线</text>
    </Shape>
  ),
  'volume_price:failed_breakout': (
    <Shape>
      <Candle x={48} open={40} close={34} high={28} low={44} up />
      <Candle x={64} open={34} close={24} high={16} low={38} up />
      <line x1={26} y1={30} x2={146} y2={30} stroke={FAINT} strokeDasharray="4 3" />
      <line x1={64} y1={16} x2={64} y2={44} stroke={ACCENT_DOWN} strokeWidth={1} />
      <text x={92} y={20} fill={STROKE} fontSize="8">冲高后收回</text>
    </Shape>
  ),
  'chip_distribution:double_peak_formed': (
    <Shape>
      <line x1={40} y1={66} x2={40} y2={8} stroke={FAINT} />
      <line x1={40} y1={66} x2={148} y2={66} stroke={FAINT} />
      <path d="M40 58 C 52 58 54 26 64 26 C 74 26 76 58 86 58 C 96 58 98 38 108 38 C 118 38 120 58 130 58" fill="none" stroke={STROKE} strokeWidth={1.6} />
      <line x1={44} y1={26} x2={84} y2={26} stroke={ACCENT_DOWN} strokeDasharray="3 2" />
      <line x1={88} y1={38} x2={128} y2={38} stroke={ACCENT_UP} strokeDasharray="3 2" />
      <text x={48} y={20} fill={STROKE} fontSize="7">支撑峰</text>
      <text x={92} y={32} fill={STROKE} fontSize="7">压力峰</text>
    </Shape>
  ),
}

export function FormDiagram({ kind }: { kind: string }) {
  const diagram = DIAGRAMS[kind as FormDiagramKind]
  return diagram ?? null
}
