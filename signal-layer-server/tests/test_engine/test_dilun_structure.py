from app.engine.indicator.dilun_structure import DilunStructureCalculator


def bar(index: int, high: float, low: float, close: float) -> dict:
    return {
        "open_time": index + 1,
        "open": close - 0.1,
        "high": high,
        "low": low,
        "close": close,
        "volume": 100,
    }


def zone_base() -> list[dict]:
    points = [
        (10, 9, 9.5),
        (15, 14, 14.5),       # 顶分型
        (13, 12, 12.5),
        (11, 10, 10.5),       # 底分型
        (13, 12, 12.5),
        (14, 13, 13.5),       # 顶分型
        (12, 11, 11.5),
        (11.5, 10.5, 11.0),   # 底分型，确认第三段折叠
        (13, 12, 12.5),
        (14.5, 13.5, 14.0),   # 顶分型，增加折叠次数
        (13, 12, 12.5),
    ]
    return [bar(index, *point) for index, point in enumerate(points)]


def test_dilun_zone_is_available_only_after_third_segment_confirmation():
    calculator = DilunStructureCalculator()
    before = calculator.calculate(zone_base()[:8], {})
    complete = calculator.calculate(zone_base(), {})

    assert all("zone_id" not in item for item in before.values)
    assert complete.values[8]["zone_confirmed"] == 1
    assert complete.values[8]["zone_low"] == 10.5
    assert complete.values[8]["zone_high"] == 14.0
    assert complete.values[8]["fold_count"] == 3
    assert complete.values[10]["fold_count"] == 4
    assert complete.values[2]["fractal_confirmed"] == -1
    assert complete.values[4]["fractal_confirmed"] == 1


def test_dilun_marks_departure_return_and_false_departure_on_confirmation_bars():
    rows = [
        *zone_base(),
        bar(11, 10.0, 9.0, 9.5),
        bar(12, 9.8, 8.8, 9.2),
        bar(13, 12.0, 10.6, 10.8),
    ]
    result = DilunStructureCalculator().calculate(rows, {
        "departure_confirm_bars": 2,
        "true_departure_bars": 3,
        "maturity_bars": 4,
    })

    assert result.values[12]["zone_departure_signal"] == -1
    assert result.values[13]["zone_return_signal"] == 1
    assert result.values[13]["false_departure_signal"] == 1
    assert result.values[11].get("zone_return_signal", 0) == 0


def test_dilun_marks_true_departure_terminal_breakout_and_failed_retest():
    rows = [
        *zone_base(),
        bar(11, 15.5, 14.5, 15.0),
        bar(12, 16.0, 15.0, 15.5),
        bar(13, 15.0, 14.2, 14.5),
        bar(14, 16.2, 15.0, 16.0),
    ]
    result = DilunStructureCalculator().calculate(rows, {
        "departure_confirm_bars": 2,
        "true_departure_bars": 3,
        "maturity_bars": 4,
    })

    assert result.values[12]["zone_departure_signal"] == 1
    assert result.values[13]["true_departure_signal"] == 1
    assert result.values[13]["terminal_breakout_signal"] == 1
    assert result.values[14]["return_failure_signal"] == 1


def test_dilun_render_keeps_zone_geometry_and_confirmed_event_markers():
    result = DilunStructureCalculator().calculate(zone_base(), {})

    assert result.render.window == "main"
    assert result.render.plots == []
    assert [marker.field for marker in result.render.markers] == [
        "fractal_marker", "zone_return_signal", "return_failure_signal", "terminal_breakout_signal",
    ]
