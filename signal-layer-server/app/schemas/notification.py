from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


ChannelType = Literal["browser", "wecom", "feishu"]
EventType = Literal["entry", "exit", "stop_loss", "take_profit", "scheduled", "screener_completed", "screener_failed"]


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    channel_type: ChannelType
    webhook_url: Optional[HttpUrl] = None
    enabled: bool = True


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    webhook_url: Optional[HttpUrl] = None
    enabled: Optional[bool] = None


class ChannelResponse(BaseModel):
    id: int
    name: str
    channel_type: ChannelType
    webhook_url_masked: Optional[str]
    enabled: bool
    is_shared: bool = False
    can_manage: bool = False


class AdminChannelCreate(ChannelCreate):
    is_shared: bool = True


class MonitorCreate(BaseModel):
    template_id: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=1, max_length=32)
    symbol_name: str = Field(default="", max_length=80)
    channel_ids: list[int] = Field(default_factory=list)
    enabled: bool = True
    poll_interval_seconds: int = Field(default=60, ge=30, le=3600)
    schedule_enabled: bool = False
    schedule_time: str = Field(default="09:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    schedule_weekdays: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5], min_length=0, max_length=7)
    event_types: list[Literal["entry", "exit", "stop_loss", "take_profit"]] = Field(default_factory=lambda: ["entry", "exit", "stop_loss", "take_profit"], min_length=1)

    @field_validator("schedule_weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 1 or day > 7 for day in value) or len(set(value)) != len(value):
            raise ValueError("星期必须是 1 到 7 且不能重复")
        return sorted(value)


class MonitorUpdate(BaseModel):
    symbol_name: Optional[str] = Field(default=None, max_length=80)
    channel_ids: Optional[list[int]] = None
    enabled: Optional[bool] = None
    poll_interval_seconds: Optional[int] = Field(default=None, ge=30, le=3600)
    reset_position: bool = False
    schedule_enabled: Optional[bool] = None
    schedule_time: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    schedule_weekdays: Optional[list[int]] = Field(default=None, min_length=0, max_length=7)
    event_types: Optional[list[Literal["entry", "exit", "stop_loss", "take_profit"]]] = Field(default=None, min_length=1)

    @field_validator("schedule_weekdays")
    @classmethod
    def validate_weekdays(cls, value: Optional[list[int]]) -> Optional[list[int]]:
        if value is not None and (any(day < 1 or day > 7 for day in value) or len(set(value)) != len(value)):
            raise ValueError("星期必须是 1 到 7 且不能重复")
        return sorted(value) if value is not None else None


class MonitorResponse(BaseModel):
    id: int
    template_id: str
    template_name: str
    timeframe: str
    symbol: str
    symbol_name: str
    channel_ids: list[int]
    enabled: bool
    poll_interval_seconds: int
    last_checked_at: Optional[datetime]
    last_bar_time: Optional[int]
    in_position: bool
    entry_price: Optional[float]
    stop_loss_price: Optional[float]
    take_profit_price: Optional[float]
    schedule_enabled: bool
    schedule_time: str
    schedule_weekdays: list[int]
    event_types: list[str]


class ScreenerScheduleCreate(BaseModel):
    template_id: str = Field(min_length=1, max_length=64)
    market: Literal["stock", "futures"] = "stock"
    universe_limit: int = Field(default=50, ge=1, le=500)
    min_progress: int = Field(default=1, ge=0, le=100)
    schedule_time: str = Field(default="01:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    schedule_weekdays: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5], min_length=0, max_length=7)
    channel_ids: list[int] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("schedule_weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 1 or day > 7 for day in value) or len(set(value)) != len(value):
            raise ValueError("星期必须是 1 到 7 且不能重复")
        return sorted(value)


class ScreenerScheduleUpdate(BaseModel):
    market: Optional[Literal["stock", "futures"]] = None
    universe_limit: Optional[int] = Field(default=None, ge=1, le=500)
    min_progress: Optional[int] = Field(default=None, ge=0, le=100)
    schedule_time: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    schedule_weekdays: Optional[list[int]] = Field(default=None, min_length=0, max_length=7)
    channel_ids: Optional[list[int]] = None
    enabled: Optional[bool] = None

    @field_validator("schedule_weekdays")
    @classmethod
    def validate_weekdays(cls, value: Optional[list[int]]) -> Optional[list[int]]:
        if value is not None and (any(day < 1 or day > 7 for day in value) or len(set(value)) != len(value)):
            raise ValueError("星期必须是 1 到 7 且不能重复")
        return sorted(value) if value is not None else None


class ScreenerScheduleResponse(BaseModel):
    id: int
    template_id: str
    template_name: str
    market: str
    universe_limit: int
    min_progress: int
    schedule_time: str
    schedule_weekdays: list[int]
    channel_ids: list[int]
    enabled: bool
    last_run_at: Optional[datetime]
    last_result_count: int
    last_error: Optional[str]


class NotificationTemplateResponse(BaseModel):
    id: int
    event_type: str
    name: str
    content: str
    enabled: bool


class NotificationTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    content: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    enabled: Optional[bool] = None


class EventResponse(BaseModel):
    id: int
    monitor_id: int
    event_type: EventType
    symbol: str
    symbol_name: str
    template_name: str
    timeframe: str
    bar_time: int
    price: float
    title: str
    content: str
    delivery_status: dict
    is_read: bool
    created_at: datetime


class MarkEventsReadRequest(BaseModel):
    ids: Optional[list[int]] = None
