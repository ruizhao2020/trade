import asyncio

from app.api import screener as screener_api
from app.schemas.screener import ScreenerRequest
from app.schemas.signal import ConditionTemplateSchema, SignalResult


def test_screener_sorts_ready_matches_and_counts_failures(monkeypatch):
    async def fake_symbols(market, keyword, limit):
        assert market == "stock"
        assert keyword is None
        assert limit == 3
        return ([
            {"symbol": "000001_sz", "name": "A", "market": "stock", "industry": "银行"},
            {"symbol": "000002_sz", "name": "B", "market": "stock", "industry": "地产"},
            {"symbol": "000003_sz", "name": "C", "market": "stock", "industry": "制造"},
        ], 5000)

    async def fake_evaluate(symbol, template, *services, **kwargs):
        if symbol == "000003_sz":
            raise RuntimeError("data unavailable")
        ready = symbol == "000002_sz"
        return SignalResult(
            template_id=template.id,
            state="ready" if ready else "partial",
            groups=[],
            is_ready=ready,
            progress_percent=100 if ready else 50,
        )

    monkeypatch.setattr(screener_api, "get_symbol_items", fake_symbols)
    monkeypatch.setattr(screener_api, "evaluate_template_for_symbol", fake_evaluate)
    monkeypatch.setattr(screener_api, "get_data_service", lambda: object())
    monkeypatch.setattr(screener_api, "get_chan_service", lambda: object())
    monkeypatch.setattr(screener_api, "get_indicator_service", lambda: object())
    monkeypatch.setattr(screener_api, "get_condition_service", lambda: object())

    request = ScreenerRequest(
        template=ConditionTemplateSchema(
            id="template-1",
            name="测试策略",
            logic="AND",
            condition_groups=[],
            primary_tf="1d",
        ),
        limit=3,
    )
    response = asyncio.run(screener_api.run_screener(request))

    assert response.universe_total == 5000
    assert response.scanned_count == 3
    assert response.matched_count == 2
    assert response.failed_count == 1
    assert [item.symbol for item in response.results] == ["000002_sz", "000001_sz"]
