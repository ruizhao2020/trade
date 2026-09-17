from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.signal import ConditionTemplateSchema


class ScreenerRequest(BaseModel):
    template: ConditionTemplateSchema
    market: str = Field(default="stock", min_length=1, max_length=16)
    keyword: Optional[str] = None
    limit: int = Field(default=500, ge=1, le=2000, description="最多扫描的候选标的数量")
    offset: int = Field(default=0, ge=0, description="候选池起始偏移，用于前端分批扫描")
    target_count: int = Field(default=10, ge=1, le=100, description="选够该数量后停止")
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
    target_count: int
    stopped_early: bool
    results: list[ScreenerMatch]
