"""
============================================================================
缠论引擎入口 — 完全对齐 czsc 算法
============================================================================

## 算法流程(对齐 czsc analyze 模块)
1. get_bars_ubi(raw_klines): 去包含关系 → NewBar 列表
2. check_fxs(bars_ubi): 滑窗扫描分型,强制顶底交替
3. build_bis_from_bars(bars_ubi): 循环 check_bi 找笔,min_bi_len=6
4. identify_zhongshus_from_bis(bis): 3 笔重叠扩展法构建中枢
5. identify_buy_sell_points(bis, zhongshus): 标准买卖点识别

## 与 czsc 的对齐情况
- remove_include: ✅ 完全对齐(方向判断、合并规则、dt 取法)
- check_fx: ✅ 完全对齐(3 根 K 线,严格 4 条件)
- check_fxs: ✅ 完全对齐(滑窗 + 顶底交替强制)
- check_bi: ✅ 完全对齐(fx_a 起点,极值 fx_b,min_bi_len=6,包含检查)
- ZS 数据结构: ✅ 完全对齐(zg/zd/zz/gg/dd 字段定义)
- 中枢识别: ⚠️ czsc analyze 模块无此函数,本实现用标准 3 笔重叠扩展法
- 买卖点: ⚠️ czsc 在 signals 模块,本实现用标准缠论定义

## 关键参数
- CZSC_MIN_BI_LEN = 6 (czsc 默认值,对应 Rust resolve_min_bi_len)
- CZSC_MAX_BI_NUM = 50 (czsc 默认值,限制最大笔数)
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from app.engine.chan.merge import merge_containment, get_bars_ubi, MergedKLine, NewBar
from app.engine.chan.fenxing import detect_fenxings, check_fxs, Fenxing
from app.engine.chan.bi import build_bis, build_bis_from_bars, Bi, CZSC_MIN_BI_LEN
from app.engine.chan.zhongshu import build_duans, Duan
from app.engine.chan.signal import (
    identify_zhongshus_from_bis, identify_zhongshus,
    Zhongshu, identify_buy_sell_points, BuySellPoint,
)

logger = logging.getLogger(__name__)

# czsc 默认最大笔数(对应 Rust resolve_max_bi_num)
CZSC_MAX_BI_NUM = 50


@dataclass
class ChanResult:
    symbol: str
    timeframe: str
    merged_klines: list[MergedKLine]
    fenxings: list[Fenxing]
    bis: list[Bi]
    duans: list[Duan]
    zhongshus: list[Zhongshu]              # 笔中枢(3 笔重叠扩展,level="bi")
    duan_zhongshus: list[Zhongshu]         # 段中枢(3 段重叠扩展,level="duan")
    buy_sell_points: list[BuySellPoint]
    updated_at: int


class ChanEngine:
    """
    缠论分析引擎 — 完全对齐 czsc 算法。

    使用批量模式处理 K 线(非增量),结果与 czsc 增量模式等价。
    """

    def analyze(self, klines: list[dict], symbol: str = "", timeframe: str = "") -> ChanResult:
        logger.info(f"ChanEngine.analyze {symbol} {timeframe} starting with {len(klines)} raw klines")

        # 1. 去包含关系(对齐 czsc update_bar 中的去包含逻辑)
        bars_ubi = get_bars_ubi(klines)
        merged = merge_containment(klines)  # 兼容旧接口

        # 2. 扫描分型(对齐 czsc check_fxs)
        fenxings = check_fxs(bars_ubi)

        # 3. 构建笔(对齐 czsc check_bi + __update_bi 循环)
        bis = build_bis_from_bars(bars_ubi, min_bi_len=CZSC_MIN_BI_LEN)

        # 限制最大笔数(对齐 czsc max_bi_num)
        if len(bis) > CZSC_MAX_BI_NUM:
            bis = bis[-CZSC_MAX_BI_NUM:]

        # 4. 构建段(简化版,缠论原著需要特征序列分型)
        duans = build_duans(bis)

        # 5. 构建中枢
        # 5a. 笔中枢:3 笔重叠扩展法(对齐 czsc ZS 数据结构)
        zhongshus = identify_zhongshus_from_bis(bis)
        # 5b. 段中枢:3 段重叠扩展法(缠论原著严格定义)
        duan_zhongshus = identify_zhongshus(duans)

        # 6. 识别买卖点(基于笔中枢,信号更及时)
        points = identify_buy_sell_points(bis, zhongshus)

        last_time = klines[-1]["open_time"] if klines else 0

        logger.info(f"ChanEngine.analyze {symbol} {timeframe} complete: "
                    f"{len(bars_ubi)} bars_ubi, {len(fenxings)} fenxings, "
                    f"{len(bis)} bis, {len(duans)} duans, "
                    f"{len(zhongshus)} bi_zs, {len(duan_zhongshus)} duan_zs, "
                    f"{len(points)} buy_sell_points")
        return ChanResult(
            symbol=symbol,
            timeframe=timeframe,
            merged_klines=[m[0] for m in merged],
            fenxings=fenxings,
            bis=bis,
            duans=duans,
            zhongshus=zhongshus,
            duan_zhongshus=duan_zhongshus,
            buy_sell_points=points,
            updated_at=last_time,
        )
