"""
============================================================================
AkShare 国内期货数据适配器
============================================================================

## 功能
使用 akshare 库从新浪财经公开数据源拉取国内期货 K 线数据。

## 数据源接口
- 主力连续日线: akshare.futures_main_sina(symbol="RB0")
    symbol 格式 = 品种代码 + "0"（0 表示主力连续），如:
    - "RB0"  螺纹钢主力连续
    - "IF0"  沪深300股指主力连续
    - "MA0"  甲醇主力连续
- 分钟线: akshare.futures_zh_minute_sina(symbol="RB2501", period="30")
    symbol 必须是具体合约（如 "RB2501"），period 取 1/5/15/30/60
    ⚠️ 新浪源只返回近期约 1 个月数据（约 1023 行限制）

## symbol 约定
- 日线: 传品种代码（如 "RB"、"IF"），适配器自动补 "0" 拉主力连续
- 分钟线: 传完整合约代码（如 "RB2501"）

## 无实时推送能力
subscribe_klines 返回空操作。
"""

from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Awaitable, Callable

from app.adapters.base import DataAdapter

logger = logging.getLogger(__name__)

# ---- timeframe mapping ------------------------------------------------------

# 日线级周期 → 主力连续（用 futures_main_sina，symbol 末尾补 "0"）
TF_DAILY: dict[str, str] = {
    "1d": "daily",
    "1w": "weekly",
    "1M": "monthly",
}

# 分钟级周期 → akshare period 参数
TF_MINUTE: dict[str, str] = {
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
}

try:
    import akshare as ak  # noqa: F401
    _AKSHARE_AVAILABLE = True
except ImportError:
    _AKSHARE_AVAILABLE = False

_CN_TZ = timezone(timedelta(hours=8))


# ---- helpers ----------------------------------------------------------------

def _to_main_contract(symbol: str) -> str:
    """把品种代码转成主力连续代码。

    "RB" → "RB0", "IF" → "IF0", "MA" → "MA0"。
    如果已经带数字（如 "RB2501"）则不处理，交由调用方决定。
    """
    symbol = symbol.strip().upper()
    if symbol.endswith("0") and symbol[:-1].isalpha():
        return symbol  # 已是 "RB0" 形式
    if symbol.isalpha():
        return symbol + "0"
    return symbol


def _to_minute_contract(symbol: str) -> str:
    """把品种代码转成分钟线需要的具体合约格式。

    新浪分钟接口支持具体合约（如 "RB2610"）和主力连续（"RB0"）。
    纯品种代码（如 "RB"）会在请求前尝试解析当前主力合约。
    """
    return symbol.strip().upper()


def _row_to_bar(row, *, is_closed: bool = True) -> dict:
    """将 akshare DataFrame 行转换为统一 bar 格式。

    futures_main_sina 列: 日期, 开盘价, 最高价, 最低价, 收盘价, 成交量, 持仓量
    futures_zh_minute_sina 列: datetime, open, high, low, close, volume, hold
    """
    date_val = row.get("日期") or row.get("date") or row.get("datetime")
    if date_val is None:
        raise KeyError("futures row missing date column")

    open_price = row.get("开盘价") or row.get("open")
    high_price = row.get("最高价") or row.get("high")
    low_price = row.get("最低价") or row.get("low")
    close_price = row.get("收盘价") or row.get("close")
    volume = row.get("成交量") or row.get("volume") or 0

    # 解析日期 → epoch 毫秒
    # 支持的格式：20250101 / 2009-03-27 / 2026-01-15 14:15:00 / datetime 对象
    if isinstance(date_val, str) and len(date_val) == 8 and date_val.isdigit():
        dt = datetime.strptime(date_val, "%Y%m%d").replace(tzinfo=_CN_TZ)
    elif isinstance(date_val, str) and ":" in date_val:
        try:
            dt = datetime.strptime(date_val, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_CN_TZ)
        except ValueError:
            dt = datetime.strptime(date_val, "%Y-%m-%d %H:%M").replace(tzinfo=_CN_TZ)
    elif isinstance(date_val, str) and "-" in date_val:
        # 纯日期字符串，如 "2009-03-27"
        dt = datetime.strptime(date_val, "%Y-%m-%d").replace(tzinfo=_CN_TZ)
    elif isinstance(date_val, datetime):
        dt = date_val.replace(tzinfo=_CN_TZ) if date_val.tzinfo is None else date_val.astimezone(_CN_TZ)
    elif isinstance(date_val, date):
        # datetime.date 对象（无时间部分），如 datetime.date(2009, 3, 27)
        dt = datetime.combine(date_val, datetime.min.time()).replace(tzinfo=_CN_TZ)
    else:
        dt = datetime.fromtimestamp(float(str(date_val)) / 1000, tz=_CN_TZ)

    return {
        "open_time": int(dt.timestamp() * 1000),
        "open": float(open_price),
        "high": float(high_price),
        "low": float(low_price),
        "close": float(close_price),
        "volume": float(volume),
        "is_closed": is_closed,
    }


def _fetch_daily_main(symbol: str, limit: int) -> list[dict]:
    """拉取主力连续日线数据。"""
    import akshare as ak

    main_code = _to_main_contract(symbol)
    logger.info(f"akshare futures_main_sina symbol={main_code}")

    try:
        df = ak.futures_main_sina(symbol=main_code)
    except Exception as e:
        raise RuntimeError(f"akshare futures_main_sina 调用失败 ({main_code}): {e}") from e

    if df is None or df.empty:
        logger.warning(f"akshare returned no data for {main_code}")
        return []

    bars = [_row_to_bar(row) for _, row in df.iterrows()]
    return bars[-limit:] if limit > 0 and len(bars) > limit else bars


def _fetch_minute(symbol: str, period: str, limit: int) -> list[dict]:
    """拉取期货分钟线数据（仅近期约 1023 行 / 约 5 个月）。

    分钟线接口支持具体合约（如 RB2610）和主力连续（RB0）。
    若传入纯品种代码（如 RB），自动用 match_main_contract 解析当前主力合约。
    """
    import akshare as ak

    contract = _to_minute_contract(symbol)

    # 品种代码（纯字母）→ 自动解析当前主力合约
    if not any(ch.isdigit() for ch in contract):
        try:
            main = ak.match_main_contract(symbol=contract.lower())
            if main is not None:
                contract = str(main)
                logger.info(f"自动解析主力合约: {symbol} → {contract}")
        except Exception as e:
            logger.warning(f"match_main_contract 失败 ({contract}): {e}")

    if not any(ch.isdigit() for ch in contract):
        raise ValueError(
            f"无法解析期货分钟线合约 {symbol}：请传具体合约代码（如 RB2610），"
            f"或确保 match_main_contract 可用"
        )

    logger.info(f"akshare futures_zh_minute_sina symbol={contract} period={period}")

    try:
        df = ak.futures_zh_minute_sina(symbol=contract, period=period)
    except Exception as e:
        raise RuntimeError(
            f"akshare futures_zh_minute_sina 调用失败 ({contract}, period={period}): {e}"
        ) from e

    if df is None or df.empty:
        logger.warning(f"akshare minute returned no data for {contract} period={period}")
        return []

    bars = [_row_to_bar(row) for _, row in df.iterrows()]
    return bars[-limit:] if limit > 0 and len(bars) > limit else bars


# ---- mock fallback ----------------------------------------------------------

import random

_FUT_MOCK_BASE: dict[str, float] = {
    "RB": 3500.0,   # 螺纹钢
    "IF": 3800.0,   # 沪深300股指
    "MA": 2500.0,   # 甲醇
    "CU": 68000.0,  # 沪铜
    "AU": 550.0,    # 沪金
}


def _generate_mock_klines(symbol: str, timeframe: str, limit: int) -> list[dict]:
    """akshare 不可用时生成模拟数据。"""
    code = symbol.strip().upper()[:2]  # 取品种前两位
    base = _FUT_MOCK_BASE.get(code, 3000.0)
    random.seed(hash(code) % (2 ** 31))

    interval_ms = {
        "1d": 86400_000, "5m": 300_000, "15m": 900_000,
        "30m": 1800_000, "60m": 3600_000,
    }.get(timeframe, 86400_000)

    now = int(datetime.now(_CN_TZ).timestamp() * 1000)
    start_ts = now - limit * interval_ms

    bars: list[dict] = []
    price = base
    for i in range(limit):
        open_time = start_ts + i * interval_ms
        change_pct = random.gauss(0, 0.01)
        close = price * (1 + change_pct)
        high = max(price, close) * (1 + abs(random.gauss(0, 0.005)))
        low = min(price, close) * (1 - abs(random.gauss(0, 0.005)))
        vol = abs(random.gauss(100000, 50000))

        bars.append({
            "open_time": open_time,
            "open": round(price, 1),
            "high": round(high, 1),
            "low": round(low, 1),
            "close": round(close, 1),
            "volume": round(vol, 0),
            "is_closed": True,
        })
        price = close

    return bars


# ---- adapter class ----------------------------------------------------------

class FuturesAdapter(DataAdapter):
    """基于 akshare 的国内期货 K 线数据适配器。

    - 日线（主力连续）: futures_main_sina()
    - 分钟线（具体合约，仅近期）: futures_zh_minute_sina()
    - 无实时推送能力
    """

    def __init__(self, allow_mock: bool = True):
        self._allow_mock = allow_mock

    @property
    def name(self) -> str:
        return "futures_akshare"

    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 500,
    ) -> list[dict]:
        logger.info(f"futures fetch_klines symbol={symbol} tf={timeframe} limit={limit}")

        if not _AKSHARE_AVAILABLE:
            if self._allow_mock:
                logger.warning(f"akshare not available, using mock data for {symbol}")
                return _generate_mock_klines(symbol, timeframe, limit)
            raise RuntimeError("akshare is not available")

        try:
            if timeframe in TF_DAILY:
                bars = await asyncio.to_thread(_fetch_daily_main, symbol, limit)
            elif timeframe in TF_MINUTE:
                bars = await asyncio.to_thread(
                    _fetch_minute, symbol, TF_MINUTE[timeframe], limit
                )
            else:
                raise ValueError(f"Unsupported timeframe: {timeframe}")
            if start_time is not None:
                bars = [bar for bar in bars if int(bar["open_time"]) >= start_time]
            if end_time is not None:
                bars = [bar for bar in bars if int(bar["open_time"]) <= end_time]
            return bars[-limit:] if limit > 0 else bars
        except Exception as e:
            if self._allow_mock:
                logger.warning(
                    f"futures fetch failed ({e}), falling back to mock data for {symbol}/{timeframe}"
                )
                return _generate_mock_klines(symbol, timeframe, limit)
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
        """返回支持的时间周期列表。"""
        if _AKSHARE_AVAILABLE:
            return list(TF_DAILY.keys()) + list(TF_MINUTE.keys())
        return list(TF_DAILY.keys())

    def timeframe_to_exchange(self, timeframe: str) -> str:
        """将内部 timeframe 映射为 akshare 的 period 参数值。"""
        if timeframe in TF_DAILY:
            return TF_DAILY[timeframe]
        if timeframe in TF_MINUTE:
            return TF_MINUTE[timeframe]
        raise ValueError(f"Unsupported timeframe: {timeframe}")
