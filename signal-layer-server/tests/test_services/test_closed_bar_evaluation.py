"""推送告警必须基于「最后一根已收盘主周期 K 线」。

这里验证 load_template_context(closed_bars_only=True) 真的把还在走的那根剔除了，
并且缠论/指标都是基于剔除后的数据计算，保证 idx=-1 读到的是已收盘那根。
"""

import asyncio

from app.schemas.signal import ConditionGroupSchema, ConditionSchema, ConditionTemplateSchema
from app.services.signal_evaluation_service import load_template_context


def bar(open_time: int, is_closed: bool) -> dict:
    return {
        "open_time": open_time,
        "open": 10.0,
        "high": 10.2,
        "low": 9.8,
        "close": 10.0,
        "volume": 100.0,
        "is_closed": is_closed,
    }


class FakeDataService:
    def __init__(self, bars: list[dict]):
        self._bars = bars
        self.requested: list[str] = []

    async def fetch_klines(self, symbol, timeframe, limit, force_refresh=False):
        self.requested.append(timeframe)
        return {"data": list(self._bars)}


class FakeChanService:
    def __init__(self):
        self.seen: list[int] = []

    async def analyze(self, symbol, timeframe, klines):
        self.seen = [item["open_time"] for item in klines]
        return None


class FakeIndicatorService:
    def __init__(self):
        self.seen: list[int] = []

    async def calculate(self, symbol, timeframe, indicator_type, params, klines, context=None):
        self.seen = [item["open_time"] for item in klines]

        class _Result:
            values = [{"time": item["open_time"], "value": 1.0} for item in klines]

        return _Result()


def _template() -> ConditionTemplateSchema:
    return ConditionTemplateSchema(
        id="tpl-closed",
        name="收盘判定",
        logic="AND",
        primary_tf="1d",
        condition_groups=[
            ConditionGroupSchema(
                id="g1",
                conditions=[
                    ConditionSchema(
                        id="c1",
                        name="收盘价站上 MA5",
                        left={"source": "price", "field": "close"},
                        operator="gt",
                        right={"source": "indicator", "indicator_type": "ma", "params": {"period": 5}},
                    ),
                ],
            ),
        ],
    )


BARS = [bar(1_700_000_000_000 + index * 86_400_000, is_closed=True) for index in range(5)]
FORMING = bar(1_700_000_000_000 + 5 * 86_400_000, is_closed=False)


def test_closed_bars_only_drops_the_still_forming_bar():
    data = FakeDataService([*BARS, FORMING])
    chan = FakeChanService()
    indicator = FakeIndicatorService()

    async def run():
        return await load_template_context(
            "000001_sz", _template(), data, chan, indicator,
            kline_limit=10, closed_bars_only=True,
        )

    kline_data, _, _ = asyncio.run(run())

    assert [item["open_time"] for item in kline_data["1d"]] == [item["open_time"] for item in BARS]
    # 缠论与指标都必须基于同一份收盘数据，否则 idx=-1 会错位到未收盘那根
    assert chan.seen == [item["open_time"] for item in BARS]
    assert indicator.seen == [item["open_time"] for item in BARS]


def test_realtime_path_keeps_the_forming_bar():
    """选股/实时信号默认语义不变，仍以当前正在走的 K 线为准。"""

    async def run():
        return await load_template_context(
            "000001_sz", _template(), FakeDataService([*BARS, FORMING]),
            FakeChanService(), FakeIndicatorService(),
            kline_limit=10,
        )

    kline_data, _, _ = asyncio.run(run())
    assert kline_data["1d"][-1]["open_time"] == FORMING["open_time"]


def test_all_bars_forming_falls_back_to_unfiltered():
    """整段都没走完时不做过滤，交由调用方判断不推送。"""
    data = FakeDataService([FORMING])

    async def run():
        return await load_template_context(
            "000001_sz", _template(), data, FakeChanService(), FakeIndicatorService(),
            kline_limit=10, closed_bars_only=True,
        )

    kline_data, _, _ = asyncio.run(run())
    assert len(kline_data["1d"]) == 1
