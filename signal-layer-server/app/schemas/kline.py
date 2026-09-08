from pydantic import BaseModel, Field
from typing import Optional


class KlineItem(BaseModel):
    open_time: int
    open: str
    high: str
    low: str
    close: str
    volume: str
    turnover: Optional[str] = None
    is_closed: bool = True


class KlineResponse(BaseModel):
    symbol: str
    timeframe: str
    data: list[KlineItem]
    from_time: Optional[int] = None
    to_time: Optional[int] = None
    count: int
    cached: bool = False
