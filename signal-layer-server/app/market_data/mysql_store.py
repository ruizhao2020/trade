from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from app.config import settings


TIMEFRAME_SUFFIX: dict[str, str] = {
    "5m": "5分钟",
    "15m": "15分钟",
    "30m": "30分钟",
    "60m": "60分钟",
    "1d": "日线",
}

TIMEFRAME_MINUTES: dict[str, int] = {
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
    "1d": 1440,
}

MYSQL_CONFIG = {
    "host": settings.mysql_host,
    "port": settings.mysql_port,
    "user": settings.mysql_user,
    "password": settings.mysql_password,
    "database": settings.mysql_database,
    "connect_timeout": 15,
    "read_timeout": 20,
    "write_timeout": 20,
    "charset": "utf8mb4",
}

_SAFE_SYMBOL = re.compile(r"^[A-Za-z0-9_.-]+$")
_COVERAGE_TABLE = "_market_data_coverage"


class MySQLMarketDataStore:
    """按 `{symbol}_{周期}` 独立表管理 K 线，并维护已确认的数据覆盖区间。"""

    retry_transient = True

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = dict(config or MYSQL_CONFIG)
        self._column_cache: dict[str, set[str]] = {}

    def _connect(self):
        import pymysql
        return pymysql.connect(**self._config)

    @staticmethod
    def table_name(symbol: str, timeframe: str) -> str:
        if not _SAFE_SYMBOL.fullmatch(symbol):
            raise ValueError(f"Invalid market symbol: {symbol}")
        suffix = TIMEFRAME_SUFFIX.get(timeframe)
        if not suffix:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        normalized = symbol.replace(".", "_").replace("-", "_")
        return f"{normalized}_{suffix}"

    @staticmethod
    def _is_stock(symbol: str) -> bool:
        return bool(symbol) and symbol[0].isdigit()

    @staticmethod
    def _quote(identifier: str) -> str:
        return f"`{identifier}`"

    def _table_exists(self, cursor, table: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
            (table,),
        )
        return cursor.fetchone() is not None

    def _ensure_data_table(self, cursor, table: str):
        cursor.execute(
            f"""CREATE TABLE IF NOT EXISTS {self._quote(table)} (
                code VARCHAR(16) NOT NULL,
                date_time TIMESTAMP NOT NULL,
                date_time_int BIGINT NOT NULL,
                freq VARCHAR(8) NOT NULL,
                open DOUBLE NOT NULL,
                close DOUBLE NOT NULL,
                high DOUBLE NOT NULL,
                low DOUBLE NOT NULL,
                volume DOUBLE NOT NULL DEFAULT 0,
                amount DOUBLE NOT NULL DEFAULT 0,
                turnover_rate DOUBLE NULL,
                circulating_shares DOUBLE NULL,
                adjustment_factor DOUBLE NULL,
                adjustment_type VARCHAR(8) NULL,
                PRIMARY KEY (date_time_int)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
        )

    def _table_columns(self, cursor, table: str) -> set[str]:
        cached = self._column_cache.get(table)
        if cached is not None:
            return cached
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=DATABASE() AND table_name=%s",
            (table,),
        )
        columns = {str(row[0]) for row in cursor.fetchall()}
        self._column_cache[table] = columns
        return columns

    def _ensure_chip_columns(self, cursor, table: str) -> None:
        columns = self._table_columns(cursor, table)
        definitions = {
            "turnover_rate": "DOUBLE NULL",
            "circulating_shares": "DOUBLE NULL",
            "adjustment_factor": "DOUBLE NULL",
            "adjustment_type": "VARCHAR(8) NULL",
        }
        for column, definition in definitions.items():
            if column not in columns:
                cursor.execute(
                    f"ALTER TABLE {self._quote(table)} ADD COLUMN {self._quote(column)} {definition}"
                )
                columns.add(column)
        self._column_cache[table] = columns

    def _chip_projection(self, cursor, table: str) -> str:
        columns = self._table_columns(cursor, table)
        return ", ".join(
            self._quote(column) if column in columns else f"NULL AS {self._quote(column)}"
            for column in ("turnover_rate", "circulating_shares", "adjustment_factor", "adjustment_type")
        )

    def _ensure_coverage_table(self, cursor):
        cursor.execute(
            f"""CREATE TABLE IF NOT EXISTS {self._quote(_COVERAGE_TABLE)} (
                symbol VARCHAR(64) NOT NULL,
                timeframe VARCHAR(10) NOT NULL,
                start_time BIGINT NOT NULL,
                end_time BIGINT NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (symbol, timeframe, start_time, end_time),
                INDEX idx_market_coverage (symbol, timeframe, start_time, end_time)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
        )

    def _rows_to_bars(self, symbol: str, rows: list[tuple]) -> list[dict]:
        volume_scale = 100 if self._is_stock(symbol) else 1
        return [
            {
                "open_time": int(row[0]) * 1000,
                "open": float(row[1]),
                "close": float(row[2]),
                "high": float(row[3]),
                "low": float(row[4]),
                "volume": float(row[5]) * volume_scale,
                "amount": float(row[6]),
                "turnover": float(row[6]),
                "turnover_rate": float(row[7]) if row[7] is not None else None,
                "circulating_shares": float(row[8]) if row[8] is not None else None,
                "adjustment_factor": float(row[9]) if row[9] is not None else None,
                "adjustment_type": str(row[10]) if row[10] is not None else None,
                "is_closed": True,
            }
            for row in rows
        ]

    def fetch_latest(self, symbol: str, timeframe: str, limit: int) -> list[dict]:
        table = self.table_name(symbol, timeframe)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                if not self._table_exists(cursor, table):
                    return []
                chip_projection = self._chip_projection(cursor, table)
                cursor.execute(
                    f"SELECT date_time_int, open, close, high, low, volume, amount, {chip_projection} "
                    f"FROM {self._quote(table)} ORDER BY date_time_int DESC LIMIT %s",
                    (limit,),
                )
                rows = list(reversed(cursor.fetchall()))
        return self._rows_to_bars(symbol, rows)

    def fetch_range(self, symbol: str, timeframe: str, start_time: int, end_time: int) -> list[dict]:
        table = self.table_name(symbol, timeframe)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                if not self._table_exists(cursor, table):
                    return []
                chip_projection = self._chip_projection(cursor, table)
                cursor.execute(
                    f"SELECT date_time_int, open, close, high, low, volume, amount, {chip_projection} "
                    f"FROM {self._quote(table)} WHERE date_time_int BETWEEN %s AND %s "
                    f"ORDER BY date_time_int ASC",
                    (start_time // 1000, end_time // 1000),
                )
                rows = cursor.fetchall()
        return self._rows_to_bars(symbol, rows)

    def upsert(self, symbol: str, timeframe: str, bars: list[dict]):
        if not bars:
            return
        table = self.table_name(symbol, timeframe)
        stock = self._is_stock(symbol)
        rows = [
            (
                symbol,
                datetime.fromtimestamp(int(bar["open_time"]) / 1000),
                int(bar["open_time"]) // 1000,
                # freq 仅作为表内元数据，使用稳定的 ASCII 周期 ID。
                # 部分历史行情表的该字段仍是 latin1，写入“日线/分钟”会失败。
                timeframe,
                float(bar["open"]),
                float(bar["close"]),
                float(bar["high"]),
                float(bar["low"]),
                float(bar.get("volume", 0)) / 100 if stock else float(bar.get("volume", 0)),
                float(bar.get("amount", bar.get("turnover", 0))),
                float(bar["turnover_rate"]) if bar.get("turnover_rate") is not None else None,
                float(bar["circulating_shares"]) if bar.get("circulating_shares") is not None else None,
                float(bar["adjustment_factor"]) if bar.get("adjustment_factor") is not None else None,
                str(bar["adjustment_type"]) if bar.get("adjustment_type") is not None else None,
            )
            for bar in bars
        ]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._ensure_data_table(cursor, table)
                self._ensure_chip_columns(cursor, table)
                cursor.executemany(
                    f"INSERT INTO {self._quote(table)} "
                    "(code, date_time, date_time_int, freq, open, close, high, low, volume, amount, "
                    "turnover_rate, circulating_shares, adjustment_factor, adjustment_type) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE date_time=VALUES(date_time), open=VALUES(open), "
                    "close=VALUES(close), high=VALUES(high), low=VALUES(low), "
                    "volume=VALUES(volume), amount=VALUES(amount), "
                    "turnover_rate=COALESCE(VALUES(turnover_rate), turnover_rate), "
                    "circulating_shares=COALESCE(VALUES(circulating_shares), circulating_shares), "
                    "adjustment_factor=COALESCE(VALUES(adjustment_factor), adjustment_factor), "
                    "adjustment_type=COALESCE(VALUES(adjustment_type), adjustment_type)",
                    rows,
                )
            connection.commit()

    def coverage(self, symbol: str, timeframe: str) -> list[tuple[int, int]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._ensure_coverage_table(cursor)
                cursor.execute(
                    f"SELECT start_time, end_time FROM {self._quote(_COVERAGE_TABLE)} "
                    "WHERE symbol=%s AND timeframe=%s ORDER BY start_time",
                    (symbol, timeframe),
                )
                rows = cursor.fetchall()
            connection.commit()
        return [(int(row[0]), int(row[1])) for row in rows]

    def add_coverage(self, symbol: str, timeframe: str, start_time: int, end_time: int):
        from app.market_data.ranges import TimeRange, merge_ranges

        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._ensure_coverage_table(cursor)
                cursor.execute(
                    f"SELECT start_time, end_time FROM {self._quote(_COVERAGE_TABLE)} "
                    "WHERE symbol=%s AND timeframe=%s FOR UPDATE",
                    (symbol, timeframe),
                )
                existing = [TimeRange(int(row[0]), int(row[1])) for row in cursor.fetchall()]
                merged = merge_ranges([*existing, TimeRange(start_time, end_time)])
                cursor.execute(
                    f"DELETE FROM {self._quote(_COVERAGE_TABLE)} WHERE symbol=%s AND timeframe=%s",
                    (symbol, timeframe),
                )
                cursor.executemany(
                    f"INSERT INTO {self._quote(_COVERAGE_TABLE)} "
                    "(symbol, timeframe, start_time, end_time, updated_at) VALUES (%s, %s, %s, %s, %s)",
                    [(symbol, timeframe, item.start, item.end, datetime.now()) for item in merged],
                )
            connection.commit()
