"""
============================================================================
AkShare A-stock 数据适配器
============================================================================

## 功能
使用 akshare 库从公开数据源拉取中国 A 股 K 线数据。
- 日线/周线/月线: akshare.stock_zh_a_hist()
- 分钟线 (5m, 30m, 60m): akshare.stock_zh_a_minute()
- 无实时推送能力，subscribe_klines 返回空操作
"""

from __future__ import annotations
import asyncio
import logging
import time
from datetime import date, datetime, timezone, timedelta
from typing import Awaitable, Callable

from app.adapters.base import DataAdapter

logger = logging.getLogger(__name__)

# ---- timeframe mapping: internal → akshare period parameter -----------------

TF_PERIOD: dict[str, str] = {
    "1d": "daily",
    "1w": "weekly",
    "1M": "monthly",
}

TF_MINUTE: dict[str, str] = {
    "5m": "5",
    "30m": "30",
    "60m": "60",
}

# 尝试在导入时检测 akshare 是否已安装
try:
    import akshare as ak  # noqa: F401
    _AKSHARE_AVAILABLE = True
except ImportError:
    _AKSHARE_AVAILABLE = False

# ---- helpers ----------------------------------------------------------------

_CN_TZ = timezone(timedelta(hours=8))
_factor_cache: dict[str, tuple[float, list[tuple[date, float]]]] = {}
_FACTOR_CACHE_TTL = 24 * 3600


def _parse_symbol(symbol: str) -> tuple[str, str]:
    """将前端传入的 symbol (如 "000001_sz") 解析为 (code, market)。

    返回 (6 位代码, 市场后缀) —— market 为 "sz" 或 "sh" 或 ""。
    """
    symbol = symbol.strip().lower()
    # 常见格式: "000001_sz", "600000.sh", "sh600000", "sz000001"
    for sep in ("_", "."):
        if sep in symbol:
            code, market = symbol.rsplit(sep, 1)
            code = code.strip().lstrip("sh").lstrip("sz")
            market = market.strip().replace("_", "").replace(".", "")
            return code.zfill(6), market
    # 纯 6 位代码，无市场后缀
    if symbol.isdigit() and len(symbol) == 6:
        return symbol, ""
    return symbol, ""


def _to_date_str(epoch_ms: int | None) -> str | None:
    """将 epoch 毫秒转换为 'YYYYMMDD' 字符串。"""
    if epoch_ms is None:
        return None
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).astimezone(_CN_TZ)
    return dt.strftime("%Y%m%d")


def _row_to_bar(row, *, is_closed: bool = True) -> dict:
    """将 akshare DataFrame 行转换为统一 bar 格式。"""
    # stock_zh_a_hist 列: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, ...
    # stock_zh_a_minute 列: 时间, 开盘, 收盘, 最高, 最低, 成交量, ...
    date_val = row.get("日期")
    if date_val is None:
        date_val = row.get("时间")
    if date_val is None:
        date_val = row.get("date")
    if date_val is None:
        date_val = row.get("day")
    if date_val is None:
        raise KeyError("akshare row missing date column")

    def value(cn_name: str, en_name: str, default=0):
        result = row.get(cn_name)
        return row.get(en_name, default) if result is None else result

    # 解析日期 → epoch 毫秒
    if isinstance(date_val, datetime):
        dt = date_val.replace(tzinfo=_CN_TZ) if date_val.tzinfo is None else date_val.astimezone(_CN_TZ)
    elif isinstance(date_val, date):
        dt = datetime.combine(date_val, datetime.min.time(), tzinfo=_CN_TZ)
    elif isinstance(date_val, str) and len(date_val) == 8 and date_val.isdigit():  # "20250101"
        dt = datetime.strptime(date_val, "%Y%m%d").replace(tzinfo=_CN_TZ)
    elif isinstance(date_val, str) and len(date_val) >= 10 and date_val[4] == "-" and date_val[7] == "-":
        fmt = "%Y-%m-%d %H:%M:%S" if ":" in date_val else "%Y-%m-%d"
        dt = datetime.strptime(date_val[:19] if ":" in date_val else date_val[:10], fmt).replace(tzinfo=_CN_TZ)
    elif isinstance(date_val, str) and ":" in date_val:  # "09:30:00"
        try:
            dt = datetime.strptime(date_val, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_CN_TZ)
        except ValueError:
            # 只有时间，需要结合当日日期 —— 这里用当天
            today = datetime.now(_CN_TZ).strftime("%Y-%m-%d")
            dt = datetime.strptime(f"{today} {date_val}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=_CN_TZ)
    else:
        dt = datetime.fromtimestamp(float(str(date_val)) / 1000, tz=_CN_TZ)

    open_time_ms = int(dt.timestamp() * 1000)

    amount = float(value("成交额", "amount"))
    bar = {
        "open_time": open_time_ms,
        "open": float(value("开盘", "open")),
        "high": float(value("最高", "high")),
        "low": float(value("最低", "low")),
        "close": float(value("收盘", "close")),
        "volume": float(value("成交量", "volume")),
        "amount": amount,
        "turnover": amount,
        "is_closed": is_closed,
    }
    for field in ("turnover_rate", "circulating_shares", "adjustment_factor"):
        field_value = row.get(field)
        if field_value is not None:
            bar[field] = float(field_value)
    adjustment_type = row.get("adjustment_type")
    if adjustment_type is not None:
        bar["adjustment_type"] = str(adjustment_type)
    return bar


def _load_qfq_factor_events(ak, full_code: str) -> list[tuple[date, float]]:
    cached = _factor_cache.get(full_code)
    now = time.monotonic()
    if cached and now - cached[0] < _FACTOR_CACHE_TTL:
        return cached[1]
    factor_df = ak.stock_zh_a_daily(symbol=full_code, adjust="qfq-factor")
    events = sorted([
        (datetime.fromisoformat(str(row["date"])[:19]).date(), float(row["qfq_factor"]))
        for _, row in factor_df.iterrows()
    ], key=lambda item: item[0])
    _factor_cache[full_code] = (now, events)
    return events


def _factor_for_date(events: list[tuple[date, float]], raw_date: object) -> float | None:
    if isinstance(raw_date, datetime):
        target = raw_date.date()
    elif isinstance(raw_date, date):
        target = raw_date
    else:
        target = datetime.fromisoformat(str(raw_date)[:19]).date()
    matched: float | None = None
    for effective_date, factor in events:
        if effective_date > target:
            break
        matched = factor
    return matched


# ---- sync data-fetch functions (wrapped in asyncio.to_thread) ---------------


def _fetch_daily(symbol: str, start: str | None, end: str | None, limit: int) -> list[dict]:
    """通过 akshare 拉取日线数据。"""
    import akshare as ak

    code, market = _parse_symbol(symbol)
    if not market:
        market = "sz" if code.startswith(("0", "3")) else "sh"
    full_code = f"{market}{code}"
    logger.info(f"akshare stock_zh_a_daily symbol={full_code} start={start} end={end}")

    source = "sina"
    try:
        df = ak.stock_zh_a_daily(
            symbol=full_code,
            start_date=start or "19900101",
            end_date=end or "20991231",
            adjust="qfq",
        )
    except Exception as e:
        logger.warning("akshare 新浪日线失败，尝试东方财富接口: %s", e)
        source = "eastmoney"
        try:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start or "19900101",
                end_date=end or "20991231",
                adjust="qfq",
                timeout=10,
            )
        except Exception as fallback_error:
            raise RuntimeError(
                f"股票日线接口均不可用 (symbol={code}): {fallback_error}"
            ) from fallback_error

    if df is None or df.empty:
        logger.warning(f"akshare returned no data for {code}")
        return []

    try:
        factor_events = _load_qfq_factor_events(ak, full_code)
    except Exception as error:
        logger.warning("qfq factor unavailable for %s: %s", full_code, error)
        factor_events = []

    bars: list[dict] = []
    for _, row in df.iterrows():
        normalized = row.to_dict()
        normalized["adjustment_type"] = "qfq"
        raw_date = normalized.get("date") or normalized.get("日期")
        normalized["adjustment_factor"] = _factor_for_date(factor_events, raw_date) if factor_events else None
        if source == "sina":
            outstanding = normalized.get("outstanding_share")
            turnover_fraction = normalized.get("turnover")
            normalized["circulating_shares"] = float(outstanding) if outstanding is not None else None
            normalized["turnover_rate"] = float(turnover_fraction) * 100 if turnover_fraction is not None else None
        else:
            # 东方财富日线成交量单位为手，统一转换为股。
            raw_volume = normalized.get("成交量")
            if raw_volume is not None:
                normalized["成交量"] = float(raw_volume) * 100
            turnover_rate = normalized.get("换手率")
            normalized["turnover_rate"] = float(turnover_rate) if turnover_rate is not None else None
            if normalized["turnover_rate"] and normalized.get("成交量") is not None:
                normalized["circulating_shares"] = float(normalized["成交量"]) * 100 / normalized["turnover_rate"]
        bars.append(_row_to_bar(normalized))
    return bars[-limit:] if limit > 0 and len(bars) > limit else bars


def _fetch_weekly_monthly(symbol: str, period: str, start: str | None, end: str | None, limit: int) -> list[dict]:
    """通过 akshare 拉取周线/月线数据。"""
    import akshare as ak

    code, _market = _parse_symbol(symbol)
    logger.info(f"akshare stock_zh_a_hist symbol={code} period={period} start={start} end={end}")

    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period=period,
            start_date=start or "19900101",
            end_date=end or "20991231",
            adjust="qfq",
        )
    except Exception as e:
        raise RuntimeError(
            f"akshare stock_zh_a_hist({period}) 调用失败 (symbol={code}): {e}"
        ) from e

    if df is None or df.empty:
        return []

    bars = [_row_to_bar(row) for _, row in df.iterrows()]
    return bars[-limit:] if limit > 0 and len(bars) > limit else bars


def _fetch_minute(symbol: str, period: str, limit: int) -> list[dict]:
    """通过 akshare 拉取分钟线数据 (5/15/30/60 分钟)。"""
    import akshare as ak

    code, market = _parse_symbol(symbol)
    # akshare.stock_zh_a_minute 需要市场前缀: "sh600000" 或 "sz000001"
    if not market:
        market = "sz" if code.startswith(("0", "3")) else "sh"
    full_code = f"{market}{code}"

    logger.info(f"akshare stock_zh_a_minute symbol={full_code} period={period}")

    try:
        df = ak.stock_zh_a_minute(symbol=full_code, period=period)
    except Exception as e:
        raise RuntimeError(
            f"akshare stock_zh_a_minute 调用失败 (symbol={full_code}, period={period}): {e}"
        ) from e

    if df is None or df.empty:
        logger.warning(f"akshare minute returned no data for {full_code} period={period}")
        return []

    bars = [_row_to_bar(row) for _, row in df.iterrows()]
    return bars[-limit:] if limit > 0 and len(bars) > limit else bars


# ---- mock fallback ----------------------------------------------------------

import random
import math

_MOCK_BASE: dict[str, float] = {
    "000001": 12.50,  # 平安银行
    "000002": 8.30,   # 万科A
    "600000": 10.20,  # 浦发银行
    "600036": 42.00,  # 招商银行
    "600519": 1450.0, # 贵州茅台
    "000858": 128.0,  # 五粮液
    "300750": 250.0,  # 宁德时代
}


def _generate_mock_klines(symbol: str, timeframe: str, limit: int) -> list[dict]:
    code, _market = _parse_symbol(symbol)
    base = _MOCK_BASE.get(code, 50.0)
    random.seed(hash(code) % (2 ** 31))

    interval_ms = {"1d": 86400_000, "5m": 300_000, "30m": 1800_000, "60m": 3600_000}.get(timeframe, 86400_000)
    now = int(datetime.now(_CN_TZ).timestamp() * 1000)
    start_ts = now - (limit * interval_ms)

    bars: list[dict] = []
    price = base * (0.5 + 0.5 * random.random())

    for i in range(limit):
        open_time = start_ts + i * interval_ms
        change_pct = random.gauss(0, 0.02)
        close = price * (1 + change_pct)
        high = max(price, close) * (1 + abs(random.gauss(0, 0.008)))
        low = min(price, close) * (1 - abs(random.gauss(0, 0.008)))
        vol = abs(random.gauss(10000000, 5000000))

        bars.append({
            "open_time": open_time,
            "open": round(price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": round(vol, 0),
            "is_closed": True,
        })
        price = close

    return bars


# ---- adapter class ----------------------------------------------------------


class AkShareAdapter(DataAdapter):
    """基于 akshare 的 A 股 K 线数据适配器。

    日线/周线/月线数据通过 stock_zh_a_hist() 获取；
    分钟线数据通过 stock_zh_a_minute() 获取；
    不支持实时推送。
    """

    @property
    def name(self) -> str:
        return "akshare"

    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 500,
    ) -> list[dict]:
        logger.info(
            f"fetch_klines symbol={symbol} tf={timeframe} "
            f"start={start_time} end={end_time} limit={limit}"
        )

        if not _AKSHARE_AVAILABLE:
            logger.warning(f"akshare not available, using mock data for {symbol}")
            return _generate_mock_klines(symbol, timeframe, limit)

        start_str = _to_date_str(start_time)
        end_str = _to_date_str(end_time)

        # 最新 N 根日线只查询必要的日历区间，避免每次下载该股票全部历史数据。
        if timeframe == "1d" and start_str is None:
            now = datetime.now(_CN_TZ)
            start_str = (now - timedelta(days=max(int(limit * 1.8), 30))).strftime("%Y%m%d")
            end_str = end_str or now.strftime("%Y%m%d")

        try:
            if timeframe in TF_PERIOD:
                period = TF_PERIOD[timeframe]
                if timeframe == "1d":
                    return await asyncio.to_thread(
                        _fetch_daily, symbol, start_str, end_str, limit
                    )
                else:
                    return await asyncio.to_thread(
                        _fetch_weekly_monthly, symbol, period, start_str, end_str, limit
                    )
            elif timeframe in TF_MINUTE:
                period = TF_MINUTE[timeframe]
                return await asyncio.to_thread(
                    _fetch_minute, symbol, period, limit
                )
            else:
                raise ValueError(f"Unsupported timeframe: {timeframe}")
        except Exception as e:
            # 线上行情失败时必须显式报错，不能把模拟行情写进正式行情表。
            logger.error("akshare fetch failed for %s/%s: %s", symbol, timeframe, e)
            raise

    async def subscribe_klines(
        self,
        symbol: str,
        timeframe: str,
        callback: Callable[[dict], Awaitable[None]],
    ) -> Callable[[], Awaitable[None]]:
        # akshare 无实时推送能力
        async def _noop() -> None:
            pass
        return _noop

    def supported_timeframes(self) -> list[str]:
        """返回支持的时间周期列表。

        日线始终可用；分钟线需要 akshare >= 1.12 版本的 stock_zh_a_minute。
        """
        # 尝试判断 stock_zh_a_minute 是否可用
        intraday = list(TF_MINUTE.keys())
        if _AKSHARE_AVAILABLE:
            try:
                import akshare as ak
                if hasattr(ak, "stock_zh_a_minute"):
                    return [*intraday, "1d"]
            except Exception:
                pass
        return ["1d"]

    def timeframe_to_exchange(self, timeframe: str) -> str:
        """将内部 timeframe 映射为 akshare 的 period 参数值。"""
        if timeframe in TF_PERIOD:
            return TF_PERIOD[timeframe]
        if timeframe in TF_MINUTE:
            return TF_MINUTE[timeframe]
        raise ValueError(f"Unsupported timeframe: {timeframe}")
