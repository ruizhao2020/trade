from __future__ import annotations

from statistics import median
from typing import Any

from app.engine.indicator.base import (
    IndicatorCalculator,
    IndicatorResult,
    MarkerSpec,
    PlotSpec,
    RenderSpec,
    _get_times,
    _param_float,
    _param_int,
    register_indicator,
)


@register_indicator
class VolumePriceCalculator(IndicatorCalculator):
    """量价结合形态。

    与 `volume` / `volume_structure` 的分工：那两个指标描述量柱自身的长相
    （倍量、梯量、黄金柱……），这里只看"量"与"价"的关系——量能相对基线
    是放大还是萎缩、价格有没有同时创出区间新高/新低、放量之后价格跟没跟。

    **单根与多根的分界**：缩量回调、量价齐升、地量地价这三个形态按
    `consecutive_bars` 根**连续 K 线**判定——它们描述的是一段走势，单根的量缩
    或量增没有意义；放量突破、放量滞涨、天量天价、底部放量本身就是单根
    K 线上的事件，与前面几根无关。

    所有判定都只用截至当根的数据：前高/前低取**当根之前**的窗口，
    区间极值取**含当根**的窗口（"创 N 周期新高"天然包含当根）。

    事件字段的**符号即方向**（仓库既有约定，前端 markers 按 `val > 0` 判买卖、
    条件引擎的「成立」用绝对值）：买入侧为 +1，顶部预警（放量滞涨、天量天价）
    为 -1。
    """

    @property
    def type(self) -> str:
        return "volume_price"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        breakout_window = _param_int(params, "breakout_window", 20)
        baseline_window = _param_int(params, "baseline_window", 20)
        position_window = _param_int(params, "position_window", 60)
        consecutive_bars = _param_int(params, "consecutive_bars", 3)
        volume_ratio_min = _param_float(params, "volume_ratio_min", 1.5)
        shrink_max = _param_float(params, "shrink_max", 0.7)
        stagnant_pct = _param_float(params, "stagnant_pct", 1.0)
        stagnant_max_drawdown_pct = _param_float(params, "stagnant_max_drawdown_pct", 10.0)
        low_position_pct = _param_float(params, "low_position_pct", 20.0)

        if not 2 <= breakout_window <= 500:
            raise ValueError("突破参考窗口应在 2 到 500 之间")
        if not 2 <= baseline_window <= 500:
            raise ValueError("量能基线窗口应在 2 到 500 之间")
        if not 2 <= position_window <= 1000:
            raise ValueError("位置参考窗口应在 2 到 1000 之间")
        if not 2 <= consecutive_bars <= 20:
            raise ValueError("连续确认根数应在 2 到 20 之间")
        if volume_ratio_min <= 1:
            raise ValueError("放量阈值必须大于1（放量＝相对量能高于基线）")
        if not 0 < shrink_max < 1:
            raise ValueError("缩量阈值必须在0到1之间（缩量＝相对量能低于基线）")
        if not 0 <= stagnant_pct <= 20:
            raise ValueError("放量滞涨的涨幅上限应在0到20之间")
        if not 0 <= stagnant_max_drawdown_pct <= 100:
            raise ValueError("放量滞涨的高位回撤上限应在0到100之间")
        if not 0 <= low_position_pct < 100:
            raise ValueError("低位回撤阈值应在0到100之间")

        times = _get_times(klines)
        opens = [float(item.get("open") or 0) for item in klines]
        closes = [float(item.get("close") or 0) for item in klines]
        highs = [float(item.get("high") or 0) for item in klines]
        lows = [float(item.get("low") or 0) for item in klines]
        volumes = [max(float(item.get("volume") or 0), 0.0) for item in klines]

        def relative_at(offset: int) -> float | None:
            """第 offset 根的相对量能（用当根之前 baseline_window 根 K 线的量柱中位数做基线）。"""
            if offset < baseline_window:
                return None
            window = volumes[offset - baseline_window:offset]
            base = median(window) if window else 0.0
            return volumes[offset] / base if base > 0 else None

        def drawdown_at(offset: int) -> float | None:
            """第 offset 根距位置窗口最高价的回撤（%），窗口含当根。"""
            if offset < position_window - 1:
                return None
            window_high = max(highs[offset - position_window + 1:offset + 1])
            return (window_high - closes[offset]) / window_high * 100 if window_high else None

        values: list[dict[str, Any]] = []
        for index in range(len(klines)):
            row: dict[str, Any] = {"time": float(times[index]), "volume": volumes[index]}

            # 量能基线：当根之前 baseline_window 根 K 线的成交量中位数。用中位数而不是
            # 均值，单根异常量（涨跌停、指数调仓）不会把整条基线抬起来。
            baseline_slice = volumes[max(0, index - baseline_window):index]
            baseline = (
                median(baseline_slice)
                if len(baseline_slice) >= baseline_window and baseline_slice else None
            )
            row["baseline"] = baseline
            relative_volume = volumes[index] / baseline if baseline else None
            row["relative_volume"] = relative_volume

            # 前高/前低：当根之前 breakout_window 根 K 线，不含当根——突破要比的是"之前的高点"
            if index >= breakout_window:
                reference_high = max(highs[index - breakout_window:index])
                reference_low = min(lows[index - breakout_window:index])
                row["breakout_pct"] = (
                    (closes[index] - reference_high) / reference_high * 100 if reference_high else None
                )
            else:
                reference_high = None
                reference_low = None
                row["breakout_pct"] = None

            # 位置极值：含当根的 position_window 根 K 线窗口，"创 N 周期新高/新低"由此判定
            if index >= position_window - 1:
                window_volumes = volumes[index - position_window + 1:index + 1]
                window_closes = closes[index - position_window + 1:index + 1]
                window_high = max(highs[index - position_window + 1:index + 1])
                drawdown_pct = (
                    (window_high - closes[index]) / window_high * 100 if window_high else None
                )
                row["drawdown_pct"] = drawdown_pct
            else:
                window_volumes = None
                window_closes = None
                window_high = None
                drawdown_pct = None
                row["drawdown_pct"] = None

            previous_close = closes[index - 1] if index > 0 else None
            change_pct = (
                (closes[index] - previous_close) / previous_close * 100
                if previous_close else None
            )
            row["change_pct"] = change_pct

            has_baseline = relative_volume is not None
            has_breakout = reference_high is not None and reference_low is not None
            has_position = window_volumes is not None and window_closes is not None
            is_up_bar = closes[index] >= opens[index]
            # 副图的成交量柱按当日阴阳着红绿：前端据此上色，判据是"画的是 volume 柱
            # 且带了 is_up"，所以这里必须逐根给出。
            row["is_up"] = 1.0 if is_up_bar else 0.0

            # 最近 consecutive_bars 根的逐根特征（多根形态共用）
            legs = range(index - consecutive_bars + 1, index + 1) if index >= consecutive_bars else ()
            sustained_shrink = bool(legs) and all(
                (value := relative_at(offset)) is not None and value <= shrink_max for offset in legs
            )

            # 放量突破：收盘站上当根之前的前高，且量能高于基线阈值
            row["volume_breakout"] = (
                1.0 if closes[index] > reference_high and relative_volume >= volume_ratio_min else 0.0
            ) if has_baseline and has_breakout else None

            # 缩量回调（连续 consecutive_bars 根）：这几根**逐根走低**且**逐根缩量**，
            # 但最后一根的收盘仍在前低之上——是一段回调，不是破位下跌。
            row["shrink_pullback"] = (
                1.0 if (
                    sustained_shrink
                    and all(closes[offset] < closes[offset - 1] for offset in legs)
                    and closes[index] > reference_low
                ) else 0.0
            ) if has_baseline and has_breakout else None

            # 量价齐升（连续 consecutive_bars 根）：这几根**逐根收涨**且**量能逐根放大**
            row["price_volume_rise"] = (
                1.0 if (
                    all(closes[offset] > closes[offset - 1] for offset in legs)
                    and all(volumes[offset] > volumes[offset - 1] for offset in legs)
                ) else 0.0
            ) if index >= consecutive_bars else None

            # 放量滞涨：量能放大但价格几乎没动，**且处于相对高位**。
            # 高位这一条是必要的：下跌途中的放量横盘是承接/换手，不是顶部预警，
            # 不加位置约束会把它一起标成卖出信号。
            # 取 -1：顶部预警是卖出侧，事件字段的符号即方向（前端 markers 按
            # val > 0 判买卖；条件引擎的「成立」用绝对值，不受影响）。
            row["volume_stagnation"] = (
                -1.0 if (
                    relative_volume >= volume_ratio_min
                    and change_pct is not None
                    and abs(change_pct) <= stagnant_pct
                    and drawdown_pct is not None
                    and drawdown_pct <= stagnant_max_drawdown_pct
                ) else 0.0
            ) if has_baseline and has_position else None

            # 天量天价（同为卖出侧，见上）/ 地量地价（买入侧，见下）
            row["climax_top"] = (
                -1.0 if (
                    volumes[index] >= max(window_volumes)
                    and closes[index] >= max(window_closes)
                ) else 0.0
            ) if has_position else None

            # 地量地价（连续 consecutive_bars 根）：这几根**逐根都是缩量**、且**逐根都在
            # 位置窗口的低位**。地量是"一段时间的量能枯竭"而不是单根的最小量，
            # 所以这里用连续缩量 + 持续低位来表达，而不是"当根量创窗口新低"。
            row["exhaustion_bottom"] = (
                1.0 if (
                    sustained_shrink
                    and index >= position_window - 1
                    and all(
                        (value := drawdown_at(offset)) is not None and value >= low_position_pct
                        for offset in legs
                    )
                ) else 0.0
            ) if has_baseline and has_position else None

            # 底部放量：处在低位（距区间高点回撤够深）时放量收阳
            row["bottom_volume"] = (
                1.0 if (
                    window_high
                    and (window_high - closes[index]) / window_high * 100 >= low_position_pct
                    and relative_volume >= volume_ratio_min
                    and is_up_bar
                ) else 0.0
            ) if has_baseline and has_position else None

            values.append(row)

        normalized_params = {
            "breakout_window": breakout_window,
            "baseline_window": baseline_window,
            "position_window": position_window,
            "consecutive_bars": consecutive_bars,
            "volume_ratio_min": volume_ratio_min,
            "shrink_max": shrink_max,
            "stagnant_pct": stagnant_pct,
            "stagnant_max_drawdown_pct": stagnant_max_drawdown_pct,
            "low_position_pct": low_position_pct,
        }
        return IndicatorResult(
            type=self.type,
            params=normalized_params,
            values=values,
            render=RenderSpec(
                window="sub",
                plots=[
                    PlotSpec(field="volume", type="histogram", color="#596477", label="成交量"),
                    PlotSpec(field="baseline", type="line", color="#e7c66b", label="量能基线"),
                ],
                # 七个形态全部上图，标记落在主图的 K 线上（挂在 candlestick series 上、
                # 走价格轴），因此与副图那根量柱对齐在同一根 K 线。
                # 颜色沿用仓库的国内配色：买入侧阳红 #ff5b62 / 卖出侧阴绿 #2fc58d。
                # 提示：七个形态都标之后，满屏（几百根 K 线）时标签会拥挤，
                # 看图时放大到几十根的区间即可。
                markers=[
                    MarkerSpec(
                        field="volume_breakout", buy_color="#ff5b62", sell_color="#ff5b62",
                        buy_label="放量突破", sell_label="放量突破", size=1,
                    ),
                    MarkerSpec(
                        field="shrink_pullback", buy_color="#ff5b62", sell_color="#ff5b62",
                        buy_label="缩量回调", sell_label="缩量回调", size=1,
                    ),
                    MarkerSpec(
                        field="price_volume_rise", buy_color="#ff5b62", sell_color="#ff5b62",
                        buy_label="量价齐升", sell_label="量价齐升", size=1,
                    ),
                    MarkerSpec(
                        field="bottom_volume", buy_color="#ff5b62", sell_color="#ff5b62",
                        buy_label="底部放量", sell_label="底部放量", size=1,
                    ),
                    MarkerSpec(
                        field="exhaustion_bottom", buy_color="#ff5b62", sell_color="#ff5b62",
                        buy_label="地量地价", sell_label="地量地价", size=1,
                    ),
                    MarkerSpec(
                        field="volume_stagnation", buy_color="#2fc58d", sell_color="#2fc58d",
                        buy_label="放量滞涨", sell_label="放量滞涨", size=1,
                    ),
                    MarkerSpec(
                        field="climax_top", buy_color="#2fc58d", sell_color="#2fc58d",
                        buy_label="天量天价", sell_label="天量天价", size=1,
                    ),
                ],
            ),
        )
