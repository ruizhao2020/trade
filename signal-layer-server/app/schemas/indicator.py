from pydantic import BaseModel, Field
from typing import Any, Optional
from app.engine.indicator.base import (
    ProfileData,
    RenderSpec as EngineRenderSpec,
    PlotSpec as EnginePlotSpec,
)


# 复用 engine 层的 RenderSpec/PlotSpec,避免类型不一致
RenderSpec = EngineRenderSpec
PlotSpec = EnginePlotSpec


class IndicatorParams(BaseModel):
    type: str
    params: dict[str, float] = Field(default_factory=dict)


class IndicatorCalculateRequest(BaseModel):
    symbol: str
    timeframe: str
    kline_limit: int = Field(default=200, ge=10, le=1000)
    indicators: list[IndicatorParams]


class IndicatorResultItem(BaseModel):
    type: str
    params: dict[str, Any]
    values: list[dict[str, float]]
    render: Optional[RenderSpec] = None
    profile_data: Optional[ProfileData] = None
    cached: bool = False


class IndicatorErrorItem(BaseModel):
    type: str
    code: str
    message: str


class IndicatorCalculateResponse(BaseModel):
    symbol: str
    timeframe: str
    results: list[IndicatorResultItem]
    errors: list[IndicatorErrorItem] = Field(default_factory=list)


class IndicatorInfo(BaseModel):
    """指标元信息(用于前端展示指标库)"""
    type: str
    name: str
    description: str
    default_params: dict[str, float]
    render: RenderSpec
    outputs: list[dict[str, str]] = Field(default_factory=list)


class IndicatorListResponse(BaseModel):
    indicators: list[IndicatorInfo]
