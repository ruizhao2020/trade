import asyncio

from app.api import indicator as indicator_api
from app.engine.indicator.base import IndicatorResult, PlotSpec, RenderSpec
from app.schemas.indicator import IndicatorCalculateRequest


class FakeRequest:
    headers = {"x-signal-surface": "private"}


class FakeDataService:
    def __init__(self, fail_daily: bool = False):
        self.fail_daily = fail_daily

    async def fetch_klines(self, symbol, timeframe, limit, force_refresh=False):
        if self.fail_daily and timeframe == "1d":
            raise RuntimeError("daily source unavailable")
        return {
            "data": [
                {
                    "open_time": index,
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10,
                    "volume": 100,
                }
                for index in range(limit)
            ]
        }


class FakeIndicatorService:
    def __init__(self):
        self.calls: list[str] = []
        self.first_closes: dict[str, float] = {}

    async def calculate(self, symbol, timeframe, indicator_type, params, klines, context=None):
        self.calls.append(indicator_type)
        self.first_closes[indicator_type] = float(klines[0]["close"])
        if indicator_type == "mutating_broken":
            klines[0]["close"] = 999
            raise RuntimeError("mutated then failed")
        if indicator_type == "broken":
            raise ValueError("broken parameters")
        return IndicatorResult(
            type=indicator_type,
            params=params,
            values=[{"time": float(item["open_time"]), "value": 1.0} for item in klines],
            render=RenderSpec(
                window="main",
                plots=[PlotSpec(field="value", type="line", label="value")],
            ),
        )


def private_access(monkeypatch, data_service, indicator_service):
    monkeypatch.setattr(indicator_api, "permission_codes", lambda user: {"private.access"})
    monkeypatch.setattr(indicator_api, "get_data_service", lambda: data_service)
    monkeypatch.setattr(indicator_api, "get_indicator_service", lambda: indicator_service)


def test_one_indicator_failure_does_not_discard_successful_results(monkeypatch):
    service = FakeIndicatorService()
    private_access(monkeypatch, FakeDataService(), service)
    request = IndicatorCalculateRequest(
        symbol="000001_sz", timeframe="1d", kline_limit=50,
        indicators=[
            {"type": "ma", "params": {"period": 5}},
            {"type": "broken", "params": {}},
            {"type": "rsi", "params": {"period": 14}},
        ],
    )

    response = asyncio.run(indicator_api.calculate_indicators(
        request, FakeRequest(), user=object(), session=object(),
    ))

    assert [item.type for item in response.results] == ["ma", "rsi"]
    assert [(item.type, item.code) for item in response.errors] == [("broken", "invalid_parameters")]
    assert service.calls == ["ma", "broken", "rsi"]


def test_indicator_input_mutation_cannot_leak_into_the_next_indicator(monkeypatch):
    service = FakeIndicatorService()
    private_access(monkeypatch, FakeDataService(), service)
    request = IndicatorCalculateRequest(
        symbol="000001_sz", timeframe="1d", kline_limit=50,
        indicators=[
            {"type": "mutating_broken", "params": {}},
            {"type": "ma", "params": {"period": 5}},
        ],
    )

    response = asyncio.run(indicator_api.calculate_indicators(
        request, FakeRequest(), user=object(), session=object(),
    ))

    assert [item.type for item in response.results] == ["ma"]
    assert service.first_closes == {"mutating_broken": 10.0, "ma": 10.0}


def test_chip_context_failure_only_skips_chip_indicator(monkeypatch):
    service = FakeIndicatorService()
    private_access(monkeypatch, FakeDataService(fail_daily=True), service)
    request = IndicatorCalculateRequest(
        symbol="000001_sz", timeframe="5m", kline_limit=50,
        indicators=[
            {"type": "chip_distribution", "params": {"lookback": 30}},
            {"type": "ma", "params": {"period": 5}},
        ],
    )

    response = asyncio.run(indicator_api.calculate_indicators(
        request, FakeRequest(), user=object(), session=object(),
    ))

    assert [item.type for item in response.results] == ["ma"]
    assert response.errors[0].type == "chip_distribution"
    assert response.errors[0].code == "context_unavailable"
    assert service.calls == ["ma"]
