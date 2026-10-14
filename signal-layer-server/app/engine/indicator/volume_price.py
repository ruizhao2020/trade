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
        rally_streak = _param_int(params, "rally_streak", 3)
        volume_ratio_min = _param_float(params, "volume_ratio_min", 1.5)
        shrink_max = _param_float(params, "shrink_max", 0.7)
        stagnant_pct = _param_float(params, "stagnant_pct", 1.0)
        low_position_pct = _param_float(params, "low_position_pct", 20.0)

        if not 2 <= breakout_window <= 500:
            raise ValueError("突破参考窗口应在 2 到 500 之间")
        if not 2 <= baseline_window <= 500:
            raise ValueError("量能基线窗口应在 2 到 500 之间")
        if not 2 <= position_window <= 1000:
            raise ValueError("位置参考窗口应在 2 到 1000 之间")
        if not 2 <= rally_streak <= 20:
            raise ValueError("量价齐升的连续根数应在 2 到 20 之间")
        if volume_ratio_min <= 1:
            raise ValueError("放量阈值必须大于1（放量＝相对量能高于基线）")
        if not 0 < shrink_max < 1:
            raise ValueError("缩量阈值必须在0到1之间（缩量＝相对量能低于基线）")
        if not 0 <= stagnant_pct <= 20:
            raise ValueError("放量滞涨的涨幅上限应在0到20之间")
        if not 0 <= low_position_pct < 100:
            raise ValueError("低位回撤阈值应在0到100之间")

        times = _get_times(klines)
        opens = [float(item.get("open") or 0) for item in klines]
        closes = [float(item.get("close") or 0) for item in klines]
        highs = [float(item.get("high") or 0) for item in klines]
        lows = [float(item.get("low") or 0) for item in klines]
        volumes = [max(float(item.get("volume") or 0), 0.0) for item in klines]

        values: list[dict[str, Any]] = []
        for index in range(len(klines)):
            row: dict[str, Any] = {"time": float(times[index]), "volume": volumes[index]}

            # 量能基线：当根之前 baseline_window 根的中位数。用中位数而不是均值，
            # 单根异常量（涨跌停、指数调仓）不会把整条基线抬起来。
            baseline_slice = volumes[max(0, index - baseline_window):index]
            baseline = (
                median(baseline_slice)
                if len(baseline_slice) >= baseline_window and baseline_slice else None
            )
            row["baseline"] = baseline
            relative_volume = volumes[index] / baseline if baseline else None
            row["relative_volume"] = relative_volume

            # 前高/前低：当根之前 breakout_window 根，不含当根——突破要比的是"之前的高点"
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

            # 位置极值：含当根的 position_window 根窗口，"创 N 周期新高/新低"由此判定
            if index >= position_window - 1:
                window_volumes = volumes[index - position_window + 1:index + 1]
                window_closes = closes[index - position_window + 1:index + 1]
                window_highs = highs[index - position_window + 1:index + 1]
                window_high = max(window_highs)
                row["drawdown_pct"] = (
                    (window_high - closes[index]) / window_high * 100 if window_high else None
                )
            else:
                window_volumes = None
                window_closes = None
                window_high = None
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

            # 放量突破：收盘站上当根之前的前高，且量能高于基线阈值
            row["volume_breakout"] = (
                1.0 if closes[index] > reference_high and relative_volume >= volume_ratio_min else 0.0
            ) if has_baseline and has_breakout else None

            # 缩量回调：收跌且缩量，但没有跌破参考窗口最低价——是回调，不是破位下跌
            row["shrink_pullback"] = (
                1.0 if (
                    previous_close is not None
                    and closes[index] < previous_close
                    and closes[index] > reference_low
                    and relative_volume <= shrink_max
                ) else 0.0
            ) if has_baseline and has_breakout else None

            # 量价齐升：连续 rally_streak 根收涨，且量能逐根放大
            row["price_volume_rise"] = (
                1.0 if (
                    all(
                        closes[offset] > closes[offset - 1]
                        for offset in range(index - rally_streak + 1, index + 1)
                    )
                    and all(
                        volumes[offset] > volumes[offset - 1]
                        for offset in range(index - rally_streak + 1, index + 1)
                    )
                ) else 0.0
            ) if index >= rally_streak else None

            # 放量滞涨：量能放大但价格几乎没动（顶部预警：威科夫讲的"努力与结果背离"）。
            # 取 -1：顶部预警是卖出侧，事件字段的符号即方向（前端 markers 按
            # val > 0 判买卖；条件引擎的「成立」用绝对值，不受影响）。
            row["volume_stagnation"] = (
                -1.0 if (
                    relative_volume >= volume_ratio_min
                    and change_pct is not None
                    and abs(change_pct) <= stagnant_pct
                ) else 0.0
            ) if has_baseline else None

            # 天量天价（同为卖出侧，见上）/ 地量地价（买入侧）
            row["climax_top"] = (
                -1.0 if (
                    volumes[index] >= max(window_volumes)
                    and closes[index] >= max(window_closes)
                ) else 0.0
            ) if has_position else None
            row["exhaustion_bottom"] = (
                1.0 if (
                    volumes[index] <= min(window_volumes)
                    and closes[index] <= min(window_closes)
                ) else 0.0
            ) if has_position else None

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
            "rally_streak": rally_streak,
            "volume_ratio_min": volume_ratio_min,
            "shrink_max": shrink_max,
            "stagnant_pct": stagnant_pct,
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
                # 标记一律落在主图的 K 线上（挂在 candlestick series 上、走价格轴），
                # 因此和副图那根量柱对齐在同一根 K 线——量价形态本来就是"同一根上
                # 量与价的关系"，这才是它在图上该被读出来的样子。
                # 颜色沿用仓库的国内配色：阳红 #ff5b62 / 阴绿 #2fc58d。
                # 只标 4 个"值得看图"的形态；缩量回调、量价齐升、地量地价语义偏中性，
                # 全标上去会盖满 K 线，它们只作为策略条件可用。
                # 每个字段都是单向的（买入侧恒正、预警侧恒负），但两个 label 都写成中文：
                # 留默认的 BUY/SELL，万一哪天符号变了就会把英文漏到图上。
                markers=[
                    MarkerSpec(
                        field="volume_breakout", buy_color="#ff5b62", sell_color="#ff5b62",
                        buy_label="放量突破", sell_label="放量突破", size=1,
                    ),
                    MarkerSpec(
                        field="bottom_volume", buy_color="#ff5b62", sell_color="#ff5b62",
                        buy_label="底部放量", sell_label="底部放量", size=1,
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
