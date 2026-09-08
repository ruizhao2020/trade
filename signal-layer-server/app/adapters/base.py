from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Awaitable, Callable


class DataAdapter(ABC):
    @property
    def range_authoritative(self) -> bool:
        """数据源能否确认请求区间完整（包括其中没有交易数据的日期）。"""
        return False

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 500,
    ) -> list[dict]:
        ...

    @abstractmethod
    async def subscribe_klines(
        self,
        symbol: str,
        timeframe: str,
        callback: Callable[[dict], Awaitable[None]],
    ) -> Callable[[], Awaitable[None]]:
        ...

    @abstractmethod
    def supported_timeframes(self) -> list[str]:
        ...

    @abstractmethod
    def timeframe_to_exchange(self, timeframe: str) -> str:
        ...
