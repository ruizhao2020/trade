from math import sqrt
from app.engine.indicator.base import (
    IndicatorCalculator, IndicatorResult, RenderSpec, PlotSpec,
    _get_closes, _get_times, _param_float, _param_int, _sma, register_indicator,
)
from typing import Any


@register_indicator
class BollingerCalculator(IndicatorCalculator):
    @property
    def type(self) -> str:
        return "bollinger"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        period = _param_int(params, "period", 20)
        std_dev = _param_float(params, "std", 2.0)
        squeeze_lookback = _param_int(params, "squeeze_lookback", 10)
        squeeze_threshold_pct = _param_float(params, "squeeze_threshold_pct", 30.0)
        if not 2 <= period <= 500:
            raise ValueError("布林带周期应在 2 到 500 之间")
        if not 0 < std_dev <= 10:
            raise ValueError("布林带标准差倍数应大于0且不超过10")
        if not 1 <= squeeze_lookback <= 200:
            raise ValueError("开口/收口的对比回看根数应在 1 到 200 之间")
        if not 0 < squeeze_threshold_pct <= 100:
            raise ValueError("开口/收口的幅度阈值应在 0 到 100 之间")

        closes = _get_closes(klines)
        times = _get_times(klines)

        sma = _sma(closes, period)

        upper: list[float | None] = []
        middle: list[float | None] = []
        lower: list[float | None] = []
        # 带宽 = 上轨 − 下轨（价格单位）。开口＝带宽走阔、收口＝带宽收窄。
        # 同时给出相对中轨的百分比版本，方便跨标的比较与设阈值。
        bandwidth: list[float | None] = []
        bandwidth_pct: list[float | None] = []
        squeeze: list[float] = []
        expand: list[float] = []

        for i in range(len(closes)):
            # 样本不足 period 根时中轨与上下轨都无意义，输出 None 让前端断线
            if i < period - 1:
                upper.append(None)
                middle.append(None)
                lower.append(None)
                bandwidth.append(None)
                bandwidth_pct.append(None)
                squeeze.append(0.0)
                expand.append(0.0)
                continue

            window = closes[i - period + 1:i + 1]
            mean = sma[i]
            variance = sum((x - mean) ** 2 for x in window) / period
            std = sqrt(variance)

            band_diff = std_dev * std
            upper.append(mean + band_diff)
            middle.append(mean)
            lower.append(mean - band_diff)
            span = 2 * band_diff
            bandwidth.append(span)
            # 中轨为 0 时百分比带宽无意义（真实行情里不会出现，防御一下）
            bandwidth_pct.append(span / mean * 100 if mean else None)

            # 开口/收口：与 squeeze_lookback 根之前的带宽比较，幅度超过阈值才算。
            # 没有这道阈值的话"收窄一点点"几乎每根都成立，当条件用没有意义。
            previous = bandwidth[i - squeeze_lookback] if i >= squeeze_lookback else None
            if previous and previous > 0:
                change_pct = (span - previous) / previous * 100
                squeeze.append(1.0 if change_pct <= -squeeze_threshold_pct else 0.0)
                expand.append(1.0 if change_pct >= squeeze_threshold_pct else 0.0)
            else:
                # 还没有足够的对比样本：两个事件都不成立
                squeeze.append(0.0)
                expand.append(0.0)

        values: list[dict[str, Any]] = []
        for i in range(len(times)):
            values.append({
                "time": float(times[i]),
                "upper": None if upper[i] is None else round(upper[i], 8),
                "middle": None if middle[i] is None else round(middle[i], 8),
                "lower": None if lower[i] is None else round(lower[i], 8),
                "bandwidth": None if bandwidth[i] is None else round(bandwidth[i], 6),
                "bandwidth_pct": None if bandwidth_pct[i] is None else round(bandwidth_pct[i], 6),
                "band_squeeze": squeeze[i],
                "band_expand": expand[i],
            })

        return IndicatorResult(
            type=self.type,
            params={
                "period": period, "std": std_dev,
                "squeeze_lookback": squeeze_lookback,
                "squeeze_threshold_pct": squeeze_threshold_pct,
            },
            values=values,
            render=RenderSpec(
                window="main",
                plots=[
                    PlotSpec(field="upper", type="line", color="#7e57c2", label="UP"),
                    PlotSpec(field="middle", type="line", color="#ffa726", label="MID"),
                    PlotSpec(field="lower", type="line", color="#7e57c2", label="LOW"),
                ],
            ),
        )
