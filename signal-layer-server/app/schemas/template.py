from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel
from app.schemas.signal import TradeParams


class TemplateCreate(BaseModel):
    id: str
    name: str
    logic: Literal["AND", "OR"] = "AND"
    condition_groups: list
    primary_tf: str = "15m"
    secondary_tfs: Optional[list[str]] = None
    enabled: bool = True
    trade_params: Optional[TradeParams] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    logic: Optional[Literal["AND", "OR"]] = None
    condition_groups: Optional[list] = None
    primary_tf: Optional[str] = None
    secondary_tfs: Optional[list[str]] = None
    enabled: Optional[bool] = None
    trade_params: Optional[TradeParams] = None


class TemplateResponse(BaseModel):
    id: str
    name: str
    logic: str
    condition_groups: list
    primary_tf: str
    secondary_tfs: Optional[list[str]] = None
    enabled: bool
    trade_params: Optional[TradeParams] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
