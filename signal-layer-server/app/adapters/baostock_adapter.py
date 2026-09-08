"""
============================================================================
BaoStock A-stock 数据适配器
============================================================================

免费开源 A 股数据平台，数据覆盖 1990 年至今。
- 日线/周线/月线: query_history_k_data_plus(frequency="d"/"w"/"m")
- 分钟线 (5/15/30/60): query_history_k_data_plus(frequency="5"/"15"/"30"/"60")
- 使用前需要 bs.login()，结束后 bs.logout()
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Awaitable, Callable

from app.adapters.base import DataAdapter

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))

_bs_lock = threading.Lock()
_bs_logged_in = False


def _ensure_login():
    global _bs_logged_in
    if _bs_logged_in:
        return
    import baostock as bs
    with _bs_lock:
        if _bs_logged_in:
            return
        lg = bs.login()
        if lg.error_code != "0":
            raise RuntimeError(f"baostock login failed: {lg.error_msg}")
        _bs_logged_in = True
        logger.info("baostock session established")


def _logout():
    global _bs_logged_in
    if not _bs_logged_in:
        return
    import baostock as bs
    with _bs_lock:
        if not _bs_logged_in:
            return
        bs.logout()
        _bs_logged_in = False
        logger.info("baostock session closed")

TF_FREQ: dict[str, str] = {
    "1d": "d",
    "1w": "w",
    "1M": "m",
    "5m": "5",
    "30m": "30",
    "60m": "60",
}


def _parse_symbol(symbol: str) -> str:
    """将前端 symbol 转换为 baostock 格式: '000001_sz' → 'sz.000001'"""
    s = symbol.strip()
    if "." in s:
        return s
    if "_" in s:
        code, market = s.rsplit("_", 1)
        return f"{market}.{code}"
    if s.startswith("60") or s.startswith("68"):
        return f"sh.{s}"
    return f"sz.{s}"


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


_FREQ_DAYS: dict[str, float] = {"d": 1.4, "w": 7, "m": 30, "5": 0.0035, "30": 0.0208, "60": 0.0417}


def _fetch_klines_sync(
    symbol: str,
    timeframe: str,
    limit: int,
    start_time: int | None = None,
    end_time: int | None = None,
) -> list[dict]:
    import baostock as bs

    code = _parse_symbol(symbol)
    freq = TF_FREQ.get(timeframe, "d")

    logger.info(f"baostock query code={code} freq={freq} limit={limit}")

    _ensure_login()

    try:
        now = datetime.now(CN_TZ)
        days_back = limit * _FREQ_DAYS.get(freq, 1.4) * 1.5
        start = datetime.fromtimestamp(start_time / 1000, CN_TZ) if start_time is not None else now - timedelta(days=max(days_back, 30))
        end = datetime.fromtimestamp(end_time / 1000, CN_TZ) if end_time is not None else now

        if freq in ("5", "15", "30", "60"):
            fields = "date,time,code,open,high,low,close,volume,amount,adjustflag"
        else:
            fields = "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST"
        rs = bs.query_history_k_data_plus(
            code, fields,
            start_date=_date_str(start),
            end_date=_date_str(end),
            frequency=freq,
            adjustflag="2",
        )

        if rs.error_code != "0":
            raise RuntimeError(f"baostock query failed: {rs.error_msg}")

        rows: list[list[str]] = []
        while rs.next():
            rows.append(rs.get_row_data())

        rows = rows[-limit:] if limit > 0 and len(rows) > limit else rows

        bars: list[dict] = []
        for row in rows:
            d = {f: row[i] for i, f in enumerate(rs.fields)}
            date_str = d.get("date", "")
            time_str = d.get("time", "")

            if time_str and len(time_str) >= 14:
                try:
                    dt = datetime.strptime(time_str, "%Y%m%d%H%M%S%f")
                    open_time = int(dt.replace(tzinfo=CN_TZ).timestamp() * 1000)
                except ValueError:
                    continue
            elif date_str:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    open_time = int(dt.replace(tzinfo=CN_TZ).timestamp() * 1000)
                except ValueError:
                    continue
            else:
                continue

            vol = _safe_float(d.get("volume", "0"))
            amount = _safe_float(d.get("amount", "0"))
            bars.append({
                "open_time": open_time,
                "open": _safe_float(d.get("open", "0")),
                "high": _safe_float(d.get("high", "0")),
                "low": _safe_float(d.get("low", "0")),
                "close": _safe_float(d.get("close", "0")),
                "volume": vol,
                "amount": amount,
                "turnover": amount,
                "is_closed": True,
            })

        if start_time is not None:
            bars = [bar for bar in bars if int(bar["open_time"]) >= start_time]
        if end_time is not None:
            bars = [bar for bar in bars if int(bar["open_time"]) <= end_time]

        logger.info(f"baostock {code} {freq} → {len(bars)} bars")
        return bars
    except Exception:
        _logout()
        raise


def _safe_float(s: str) -> float:
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


class BaoStockAdapter(DataAdapter):

    @property
    def range_authoritative(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "baostock"

    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 500,
    ) -> list[dict]:
        logger.info(
            f"fetch_klines symbol={symbol} tf={timeframe} limit={limit} start={start_time} end={end_time}"
        )
        return await asyncio.to_thread(
            _fetch_klines_sync, symbol, timeframe, limit, start_time, end_time
        )

    async def subscribe_klines(
        self,
        symbol: str,
        timeframe: str,
        callback: Callable[[dict], Awaitable[None]],
    ) -> Callable[[], Awaitable[None]]:
        async def _noop() -> None:
            pass
        return _noop

    def supported_timeframes(self) -> list[str]:
        return list(TF_FREQ.keys())

    def timeframe_to_exchange(self, timeframe: str) -> str:
        return TF_FREQ.get(timeframe, "d")
