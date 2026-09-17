from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ContentTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    sections: list[str]
    enabled: bool
    built_in: bool
    editable: bool = False


class ContentTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    sections: list[Literal["summary", "trend", "momentum", "volume", "structure", "risk"]] = Field(min_length=1)


class ContentTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    sections: Optional[list[Literal["summary", "trend", "momentum", "volume", "structure", "risk"]]] = Field(default=None, min_length=1)
    enabled: Optional[bool] = None


class ArticleGenerateRequest(BaseModel):
    template_id: str = "stock_technical_overview"
    symbol: str = Field(min_length=1, max_length=32)
    symbol_name: str = Field(min_length=1, max_length=100)
    market: str = Field(default="stock", min_length=1, max_length=16)
    timeframes: list[Literal["1d", "30m", "5m"]] = Field(default_factory=lambda: ["1d"])
    kline_limit: int = Field(default=300, ge=100, le=1000)


class ArticleDraftResponse(BaseModel):
    id: int
    template_id: str
    title: str
    symbol: str
    symbol_name: str
    market: str
    as_of: datetime
    timeframes: list[str]
    structured_data: dict[str, Any]
    chart_specs: list[dict[str, Any]]
    standard_markdown: str
    platform_variants: dict[str, str]
    status: str
    created_at: datetime


class ArticleStatusUpdate(BaseModel):
    status: Literal["draft", "reviewed", "rejected"]


class ArticleContentUpdate(BaseModel):
    standard_markdown: Optional[str] = Field(default=None, max_length=50000)
    platform_variants: Optional[dict[str, str]] = None
