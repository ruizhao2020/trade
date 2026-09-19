import asyncio

from app.api import screener as screener_api
from app.schemas.screener import ScreenerRequest
from app.schemas.signal import ConditionTemplateSchema, SignalResult


def test_screener_sorts_ready_matches_and_counts_failures(monkeypatch):
    async def fake_symbols(market, keyword, limit, offset=0):
        assert market == "stock"
        assert keyword is None
        assert limit == 3
        assert offset == 0
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


def test_screener_stops_starting_new_batches_after_target_is_reached(monkeypatch):
    symbols = [
        {"symbol": f"00000{index}_sz", "name": str(index), "market": "stock"}
        for index in range(1, 11)
    ]

    async def fake_symbols(market, keyword, limit, offset=0):
        return symbols[offset:offset + limit], len(symbols)

    async def fake_evaluate(symbol, template, *services, **kwargs):
        return SignalResult(
            template_id=template.id, state="ready", groups=[],
            is_ready=True, progress_percent=100,
        )

    monkeypatch.setattr(screener_api, "get_symbol_items", fake_symbols)
    monkeypatch.setattr(screener_api, "evaluate_template_for_symbol", fake_evaluate)
    monkeypatch.setattr(screener_api, "get_data_service", lambda: object())
    monkeypatch.setattr(screener_api, "get_chan_service", lambda: object())
    monkeypatch.setattr(screener_api, "get_indicator_service", lambda: object())
    monkeypatch.setattr(screener_api, "get_condition_service", lambda: object())

    request = ScreenerRequest(
        template=ConditionTemplateSchema(
            id="template-1", name="测试策略", logic="AND",
            condition_groups=[], primary_tf="1d",
        ),
        limit=10, target_count=2, concurrency=4,
    )
    response = asyncio.run(screener_api.run_screener(request))

    assert response.scanned_count == 4
    assert response.matched_count == 2
    assert response.stopped_early is True


def test_screener_filters_multiple_selected_states(monkeypatch):
    symbols = [
        {"symbol": "000001_sz", "name": "就绪", "market": "stock"},
        {"symbol": "000002_sz", "name": "部分", "market": "stock"},
        {"symbol": "000003_sz", "name": "未满足", "market": "stock"},
    ]

    async def fake_symbols(market, keyword, limit, offset=0):
        return symbols[offset:offset + limit], len(symbols)

    async def fake_evaluate(symbol, template, *services, **kwargs):
        state, progress = {
            "000001_sz": ("ready", 100),
            "000002_sz": ("partial", 50),
            "000003_sz": ("evaluating", 0),
        }[symbol]
        return SignalResult(
            template_id=template.id, state=state, groups=[],
            is_ready=state == "ready", progress_percent=progress,
        )

    monkeypatch.setattr(screener_api, "get_symbol_items", fake_symbols)
    monkeypatch.setattr(screener_api, "evaluate_template_for_symbol", fake_evaluate)
    monkeypatch.setattr(screener_api, "get_data_service", lambda: object())
    monkeypatch.setattr(screener_api, "get_chan_service", lambda: object())
    monkeypatch.setattr(screener_api, "get_indicator_service", lambda: object())
    monkeypatch.setattr(screener_api, "get_condition_service", lambda: object())

    request = ScreenerRequest(
        template=ConditionTemplateSchema(
            id="template-1", name="测试策略", logic="AND",
            condition_groups=[], primary_tf="1d",
        ),
        limit=3,
        states=["ready", "evaluating"],
        min_progress=0,
    )
    response = asyncio.run(screener_api.run_screener(request))

    assert [item.state for item in response.results] == ["ready", "evaluating"]
    assert [item.symbol for item in response.results] == ["000001_sz", "000003_sz"]
