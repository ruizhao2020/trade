from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.signal import ConditionTemplateSchema


class ScreenerRequest(BaseModel):
    template: ConditionTemplateSchema
    market: Literal["stock", "futures"] = "stock"
    keyword: Optional[str] = None
    limit: int = Field(default=24, ge=1, le=100)
    min_progress: int = Field(default=1, ge=0, le=100)
    concurrency: int = Field(default=4, ge=1, le=8)
    kline_limit: int = Field(default=200, ge=50, le=500)


class ScreenerMatch(BaseModel):
    symbol: str
    name: str
    market: str
    industry: Optional[str] = None
    exchange: Optional[str] = None
    state: str
    is_ready: bool
    progress_percent: int


class ScreenerResponse(BaseModel):
    market: str
    universe_total: int
    scanned_count: int
    matched_count: int
    failed_count: int
    results: list[ScreenerMatch]
