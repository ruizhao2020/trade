from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class NotificationChannel(Base, TimestampMixin):
    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Foreign keys are represented in the initialization SQL.  The runtime
    # model intentionally keeps these columns unconstrained so create_all can
    # migrate legacy MySQL installations whose users/templates column types
    # may differ (for example INT UNSIGNED vs INT).
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("idx_notification_channel_user", "user_id"),)


class NotificationTemplate(Base, TimestampMixin):
    __tablename__ = "notification_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    content: Mapped[str] = mapped_column(String(4000), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class StrategyMonitor(Base, TimestampMixin):
    __tablename__ = "strategy_monitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    channel_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_bar_time: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    in_position: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    event_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=lambda: ["entry", "exit", "stop_loss", "take_profit"])
    # Optional personal scheduled strategy push.  Weekdays use ISO values
    # (1=Monday … 7=Sunday); an empty list means every day.
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schedule_time: Mapped[str] = mapped_column(String(5), nullable=False, default="09:30")
    schedule_weekdays: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=lambda: [1, 2, 3, 4, 5])
    last_schedule_key: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "template_id", "symbol", name="uk_monitor_user_template_symbol"),
        Index("idx_strategy_monitor_enabled", "enabled", "last_checked_at"),
    )


class ScreenerSchedule(Base, TimestampMixin):
    """A user's scheduled strategy scan over a configured symbol universe."""

    __tablename__ = "screener_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False, default="stock")
    universe_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    min_progress: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schedule_time: Mapped[str] = mapped_column(String(5), nullable=False, default="01:00")
    schedule_weekdays: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=lambda: [1, 2, 3, 4, 5])
    channel_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_key: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "template_id", "market", "schedule_time", name="uk_screener_schedule_user_template_time"),
        Index("idx_screener_schedule_enabled", "enabled", "last_run_at"),
    )


class NotificationEvent(Base, TimestampMixin):
    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    monitor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    template_name: Mapped[str] = mapped_column(String(100), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    bar_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(String(2000), nullable=False)
    delivery_status: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("monitor_id", "event_type", "bar_time", name="uk_monitor_event_bar"),
        Index("idx_notification_event_user", "user_id", "is_read", "created_at"),
    )
