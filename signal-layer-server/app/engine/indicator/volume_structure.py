from __future__ import annotations

from typing import Any

from app.engine.indicator.base import (
    IndicatorCalculator,
    IndicatorResult,
    PlotSpec,
    RenderSpec,
    _get_times,
    register_indicator,
)


@register_indicator
class VolumeStructureCalculator(IndicatorCalculator):
    """关键量柱、将军柱、黄金柱及其动态防守线。"""

    @property
    def type(self) -> str:
        return "volume_structure"

    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        lookback = int(params.get("lookback", 20))
        key_ratio_min = float(params.get("key_ratio_min", 1.8))
        confirm_bars = int(params.get("confirm_bars", 3))
        break_tolerance = float(params.get("break_tolerance", 0.0))
        if lookback < 3 or not 2 <= confirm_bars <= 10:
            raise ValueError("关键量柱窗口至少为3，确认根数应在2到10之间")
        if key_ratio_min <= 1 or not 0 <= break_tolerance < 0.2:
            raise ValueError("关键量柱倍率应大于1，破位容差应在0到0.2之间")

        times = _get_times(klines)
        volumes = [max(float(item.get("volume") or 0), 0.0) for item in klines]
        opens = [float(item.get("open") or 0) for item in klines]
        closes = [float(item.get("close") or 0) for item in klines]
        lows = [float(item.get("low") or 0) for item in klines]
        values: list[dict[str, float]] = [
            {
                "time": float(timestamp),
                "volume": volumes[index],
                "is_up": 1.0 if closes[index] >= opens[index] else 0.0,
            }
            for index, timestamp in enumerate(times)
        ]
        candidates: list[int] = []

        active_key_line: float | None = None
        active_key_stop: float | None = None
        for index in range(len(klines)):
            previous_volume = volumes[index - 1] if index > 0 else 0.0
            ratio = volumes[index] / previous_volume if previous_volume > 0 else 0.0
            window = volumes[max(0, index - lookback + 1):index + 1]
            is_high = len(window) >= lookback and volumes[index] > 0 and volumes[index] >= max(window)
            bullish = closes[index] > opens[index] and (index == 0 or closes[index] >= closes[index - 1])
            is_key = bullish and (ratio >= key_ratio_min or is_high)

            if active_key_line is not None and active_key_stop is not None:
                values[index]["key_line"] = active_key_line
                values[index]["above_key_line"] = 1.0 if closes[index] >= active_key_line else 0.0
                values[index]["key_line_distance_pct"] = (
                    (closes[index] - active_key_line) / active_key_line * 100 if active_key_line else 0.0
                )
                if closes[index] < active_key_stop * (1 - break_tolerance):
                    values[index]["key_line_break"] = -1.0
                    active_key_line = None
                    active_key_stop = None

            if is_key:
                candidates.append(index)
                active_key_line = max(opens[index], closes[index])
                active_key_stop = lows[index]
                values[index].update({
                    "key_pillar": 1.0,
                    "pillar_kind": 1.0,
                    "key_line": active_key_line,
                    "above_key_line": 1.0,
                    "key_line_distance_pct": 0.0,
                })

        golden_confirmations: dict[int, list[int]] = {}
        for base_index in candidates:
            confirm_index = base_index + confirm_bars
            if confirm_index >= len(klines):
                continue
            follower_indices = range(base_index + 1, confirm_index + 1)
            body_top = max(opens[base_index], closes[base_index])
            body_bottom = min(opens[base_index], closes[base_index])
            follower_closes = [closes[index] for index in follower_indices]
            follower_volumes = [volumes[index] for index in follower_indices]

            is_general = (
                min(follower_closes) >= body_bottom
                and sum(follower_closes) / len(follower_closes) >= body_top
            )
            if not is_general:
                continue
            values[base_index]["general_pillar"] = 1.0
            values[base_index]["pillar_kind"] = 2.0
            values[confirm_index]["general_confirmed"] = 1.0
            values[confirm_index]["general_source_time"] = float(times[base_index])

            is_golden = (
                min(follower_closes) >= body_top
                and follower_closes[-1] >= closes[base_index]
                and all(volume < volumes[base_index] for volume in follower_volumes)
                and follower_volumes[-1] < follower_volumes[0]
            )
            if not is_golden:
                continue
            values[base_index]["golden_pillar"] = 1.0
            values[base_index]["pillar_kind"] = 3.0
            values[confirm_index]["golden_confirmed"] = 1.0
            values[confirm_index]["golden_source_time"] = float(times[base_index])
            golden_confirmations.setdefault(confirm_index, []).append(base_index)

        active_golden_line: float | None = None
        active_golden_stop: float | None = None
        active_golden_volume_line: float | None = None
        for index in range(len(klines)):
            if active_golden_line is not None and active_golden_stop is not None:
                values[index]["golden_line"] = active_golden_line
                values[index]["above_golden_line"] = 1.0 if closes[index] >= active_golden_line else 0.0
                values[index]["golden_line_distance_pct"] = (
                    (closes[index] - active_golden_line) / active_golden_line * 100 if active_golden_line else 0.0
                )
                if active_golden_volume_line is not None:
                    values[index]["golden_volume_line"] = active_golden_volume_line
                if closes[index] < active_golden_stop * (1 - break_tolerance):
                    values[index]["golden_line_break"] = -1.0
                    active_golden_line = None
                    active_golden_stop = None
                    active_golden_volume_line = None

            confirmed = golden_confirmations.get(index)
            if confirmed:
                base_index = confirmed[-1]
                active_golden_line = max(opens[base_index], closes[base_index])
                active_golden_stop = lows[base_index]
                active_golden_volume_line = volumes[base_index]
                # 黄金柱要在原始量柱位置显示黄金线；该线只在确认后才产生，
                # 但静态图会回填基柱到确认柱之间的可视区间。
                for fill_index in range(base_index, index + 1):
                    values[fill_index]["golden_volume_line"] = active_golden_volume_line
                values[index]["golden_line"] = active_golden_line
                values[index]["above_golden_line"] = 1.0 if closes[index] >= active_golden_line else 0.0
                values[index]["golden_line_distance_pct"] = (
                    (closes[index] - active_golden_line) / active_golden_line * 100 if active_golden_line else 0.0
                )

        normalized_params = {
            "lookback": lookback,
            "key_ratio_min": key_ratio_min,
            "confirm_bars": confirm_bars,
            "break_tolerance": break_tolerance,
        }
        return IndicatorResult(
            type=self.type,
            params=normalized_params,
            values=values,
            render=RenderSpec(
                window="sub",
                plots=[
                    PlotSpec(field="volume", type="histogram", color="#596477", label="成交量"),
                    PlotSpec(field="golden_volume_line", type="line", color="#e7c66b", label="黄金线"),
                ],
            ),
        )
