from app.engine.indicator.volume_structure import VolumeStructureCalculator


def bar(timestamp: int, open_price: float, close: float, low: float, volume: float) -> dict:
    return {
        "open_time": timestamp,
        "open": open_price,
        "high": max(open_price, close) + 0.2,
        "low": low,
        "close": close,
        "volume": volume,
    }


def golden_sample() -> list[dict]:
    return [
        bar(1, 9.8, 10.0, 9.7, 100),
        bar(2, 9.9, 10.0, 9.8, 100),
        bar(3, 10.0, 11.0, 9.9, 220),  # 关键量柱
        bar(4, 11.0, 11.2, 10.8, 160),
        bar(5, 11.1, 11.3, 10.9, 130),
        bar(6, 11.2, 11.4, 11.0, 90),   # 第3根确认：将军柱+黄金柱
        bar(7, 10.0, 9.5, 9.3, 80),     # 跌破基柱最低价
    ]


def test_volume_structure_confirms_general_and_golden_pillars_without_future_signal():
    calculator = VolumeStructureCalculator()
    before_confirmation = calculator.calculate(golden_sample()[:5], {"lookback": 3})
    complete = calculator.calculate(golden_sample(), {"lookback": 3})

    assert before_confirmation.values[2].get("general_pillar", 0) == 0
    assert before_confirmation.values[2].get("golden_pillar", 0) == 0

    assert complete.values[2]["key_pillar"] == 1
    assert complete.values[2]["general_pillar"] == 1
    assert complete.values[2]["golden_pillar"] == 1
    assert complete.values[2]["pillar_kind"] == 3
    assert complete.values[5]["general_confirmed"] == 1
    assert complete.values[5]["golden_confirmed"] == 1
    assert complete.values[5]["golden_line"] == 11.0
    assert complete.values[2]["golden_volume_line"] == 220
    assert complete.values[5]["golden_volume_line"] == 220


def test_volume_structure_marks_key_and_golden_line_breaks():
    result = VolumeStructureCalculator().calculate(golden_sample(), {"lookback": 3})

    assert result.values[6]["key_line_break"] == -1
    assert result.values[6]["golden_line_break"] == -1
    assert result.render.window == "sub"
    assert [plot.field for plot in result.render.plots] == ["volume", "golden_volume_line"]
    assert result.render.markers == []
