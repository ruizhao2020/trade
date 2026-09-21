from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.chan import ChanResult
from app.models.notification import NotificationChannel, NotificationEvent, NotificationTemplate, ScreenerSchedule, StrategyMonitor
from app.models.template import Template
from app.schemas.signal import ConditionTemplateSchema, TradeParams
from app.api.symbol import get_symbol_items
from app.services.condition_service import ConditionService
from app.services.signal_evaluation_service import evaluate_template_for_symbol, load_template_context

logger = logging.getLogger(__name__)

CHANNEL_TYPES = {"browser", "wecom", "feishu"}
EVENT_LABELS = {
    "entry": "策略建仓",
    "exit": "策略清仓",
    "stop_loss": "触发止损",
    "take_profit": "触发止盈",
    "scheduled": "策略定时推送",
    "screener_completed": "定时选股完成",
    "screener_failed": "定时选股失败",
}

DEFAULT_MESSAGE_TEMPLATES = {
    "entry": ("策略建仓", "【策略建仓】\n策略：{{strategy_name}}\n标的：{{symbol_name}}（{{symbol}}）\n价格：{{price}}\n建议仓位：{{position_size}}\n止损：{{stop_loss}}\n止盈：{{take_profit}}\n时间：{{trigger_time}}"),
    "exit": ("策略清仓", "【策略清仓】\n策略：{{strategy_name}}\n标的：{{symbol_name}}（{{symbol}}）\n价格：{{price}}\n时间：{{trigger_time}}"),
    "stop_loss": ("触发止损", "【触发止损】\n策略：{{strategy_name}}\n标的：{{symbol_name}}（{{symbol}}）\n价格：{{price}}\n止损价：{{stop_loss}}\n时间：{{trigger_time}}"),
    "take_profit": ("触发止盈", "【触发止盈】\n策略：{{strategy_name}}\n标的：{{symbol_name}}（{{symbol}}）\n价格：{{price}}\n止盈价：{{take_profit}}\n时间：{{trigger_time}}"),
    "scheduled": ("策略定时推送", "【策略定时推送】\n策略：{{strategy_name}}\n标的：{{symbol_name}}（{{symbol}}）\n最新价：{{price}}\n信号状态：{{signal_status}}\n时间：{{trigger_time}}"),
    "screener_completed": ("定时选股完成", "【定时选股完成】\n策略：{{strategy_name}}\n市场：{{market}}\n扫描：{{scanned_count}} 个，命中：{{matched_count}} 个\n结果：{{screen_results}}\n时间：{{trigger_time}}"),
    "screener_failed": ("定时选股失败", "【定时选股失败】\n策略：{{strategy_name}}\n原因：{{error}}\n时间：{{trigger_time}}"),
}
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def _beijing_now() -> datetime:
    """Return a naive Beijing local time for schedule comparisons and DB fields."""
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def _template_schema(template: Template) -> ConditionTemplateSchema:
    return ConditionTemplateSchema.model_validate({
        "id": template.id,
        "name": template.name,
        "logic": template.logic,
        "condition_groups": template.condition_groups or [],
        "primary_tf": template.primary_tf,
        "secondary_tfs": template.secondary_tfs or [],
        "enabled": template.enabled,
        "trade_params": template.trade_params,
    })


def _atr(klines: list[dict], index: int, period: int = 14) -> float:
    if not klines:
        return 0.0
    start = max(0, index - period + 1)
    values = []
    for position in range(start, index + 1):
        current = klines[position]
        previous_close = float(klines[position - 1]["close"]) if position > 0 else float(current["close"])
        values.append(max(
            float(current["high"]) - float(current["low"]),
            abs(float(current["high"]) - previous_close),
            abs(float(current["low"]) - previous_close),
        ))
    return sum(values) / len(values) if values else 0.0


def _risk_prices(template: ConditionTemplateSchema, klines: list[dict]) -> tuple[float, float | None, float | None]:
    latest = klines[-1]
    entry = float(latest["close"])
    params = template.trade_params or TradeParams()
    if params.stop_loss_type == "none":
        stop = None
    elif params.stop_loss_type == "fixed_pct":
        stop = entry * (1 - params.stop_loss_value / 100)
    elif params.stop_loss_type == "swing_low":
        stop = min(float(item["low"]) for item in klines[-20:])
    else:
        stop = entry - _atr(klines, len(klines) - 1) * params.stop_loss_value
    if params.take_profit_type == "none":
        take = None
    elif params.take_profit_type == "fixed_pct":
        take = entry * (1 + params.take_profit_value / 100)
    elif params.take_profit_type == "rr_ratio":
        take = entry + (entry - stop) * params.take_profit_value if stop is not None else None
    else:
        take = entry + _atr(klines, len(klines) - 1) * params.take_profit_value
    return entry, stop, take


def _mask_webhook(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 18:
        return f"{value[:5]}…{value[-4:]}"
    return f"{value[:12]}…{value[-6:]}"


def _post_json(url: str, payload: dict[str, Any]) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status >= 400:
            raise RuntimeError(f"notification webhook HTTP {response.status}")


async def send_channel(channel: NotificationChannel, title: str, content: str) -> str:
    if channel.channel_type == "browser":
        return "stored"
    if not channel.webhook_url:
        return "missing_webhook"
    if channel.channel_type == "wecom":
        payload = {"msgtype": "markdown", "markdown": {"content": f"### {title}\n{content}"}}
    elif channel.channel_type == "feishu":
        payload = {"msg_type": "text", "content": {"text": f"{title}\n{content}"}}
    else:
        return "unsupported"
    try:
        await asyncio.to_thread(_post_json, channel.webhook_url, payload)
        return "sent"
    except Exception as error:
        logger.warning("notification channel %s delivery failed: %s", channel.id, error)
        return f"failed:{error.__class__.__name__}"


class NotificationService:
    def __init__(self, data_service, chan_service, indicator_service, condition_service: ConditionService):
        self._data = data_service
        self._chan = chan_service
        self._indicator = indicator_service
        self._condition = condition_service
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run_loop(), name="notification-monitor-loop")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                await self.poll_once()
            except Exception:
                logger.exception("notification monitor loop failed")
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass

    async def poll_once(self) -> int:
        processed = 0
        async for session in self._session_iter():
            monitors = (await session.execute(
                select(StrategyMonitor).where(StrategyMonitor.enabled.is_(True))
            )).scalars().all()
            for monitor in monitors:
                try:
                    if await self._process_monitor(session, monitor):
                        processed += 1
                except Exception:
                    logger.exception("notification monitor %s failed", monitor.id)
            schedules = (await session.execute(
                select(ScreenerSchedule).where(ScreenerSchedule.enabled.is_(True))
            )).scalars().all()
            for schedule in schedules:
                try:
                    if await self._process_screener_schedule(session, schedule):
                        processed += 1
                except Exception:
                    logger.exception("screener schedule %s failed", schedule.id)
            await session.commit()
        return processed

    @staticmethod
    async def _session_iter():
        from app.db import get_session
        async for session in get_session():
            yield session

    async def _process_monitor(self, session: AsyncSession, monitor: StrategyMonitor) -> bool:
        # Each monitor may have its own polling cadence.  The service loop is
        # intentionally short (30s) so a newly-created monitor is responsive,
        # while this guard prevents unnecessary market/API requests.
        if monitor.last_checked_at is not None:
            elapsed = (_beijing_now() - monitor.last_checked_at).total_seconds()
            if elapsed < max(30, monitor.poll_interval_seconds):
                return False
        template = await session.get(Template, monitor.template_id)
        if not template or not template.enabled:
            return False
        strategy = _template_schema(template)
        groups = list(strategy.condition_groups)
        if strategy.trade_params:
            groups.extend(strategy.trade_params.exit_conditions)
        kline_data, chan_data, indicator_data = await load_template_context(
            monitor.symbol, strategy, self._data, self._chan, self._indicator,
            groups=groups, kline_limit=500,
        )
        timeframe = strategy.primary_tf or "1d"
        klines = kline_data.get(timeframe, [])
        if not klines:
            return False
        latest = klines[-1]
        bar_time = int(latest["open_time"])
        monitor.last_checked_at = _beijing_now()
        signal = await self._condition.evaluate(strategy, kline_data, chan_data, indicator_data)

        # A scheduled push is a personal snapshot of the strategy state.  It
        # shares the monitor's channels and event history, but is deduplicated
        # by local date/time so it is emitted at most once per configured run.
        scheduled_sent = False
        schedule_now = _beijing_now()
        if self._schedule_due(monitor, schedule_now):
            schedule_key = schedule_now.strftime("%Y-%m-%d")
            existing = await session.scalar(select(NotificationEvent).where(
                NotificationEvent.monitor_id == monitor.id,
                NotificationEvent.event_type == "scheduled",
                NotificationEvent.bar_time == bar_time,
            ))
            if not existing:
                title, content = await self._message(session, "scheduled", {
                    "strategy_name": template.name, "symbol_name": monitor.symbol_name or monitor.symbol,
                    "symbol": monitor.symbol, "price": f"{float(latest['close']):.4f}",
                    "signal_status": "满足建仓条件" if signal.is_ready else "等待信号",
                    "trigger_time": datetime.fromtimestamp(bar_time / 1000, BEIJING_TZ).strftime("%Y-%m-%d %H:%M"),
                })
                event = NotificationEvent(
                    user_id=monitor.user_id, monitor_id=monitor.id, event_type="scheduled",
                    symbol=monitor.symbol, symbol_name=monitor.symbol_name or monitor.symbol,
                    template_name=template.name, timeframe=timeframe, bar_time=bar_time,
                    price=float(latest["close"]), title=title, content=content,
                    delivery_status={}, is_read=False,
                )
                session.add(event)
                await session.flush()
                channels = await self._channels_for_user(session, monitor.user_id, monitor.channel_ids)
                event.delivery_status = {str(channel.id): await send_channel(channel, event.title, event.content) for channel in channels}
                scheduled_sent = True
            monitor.last_schedule_key = schedule_key

        # Event-based strategy monitoring is evaluated once per new bar.
        if monitor.last_bar_time == bar_time:
            return scheduled_sent
        monitor.last_bar_time = bar_time

        event_type: str | None = None
        event_price = float(latest["close"])
        if monitor.in_position:
            if monitor.stop_loss_price is not None and float(latest["low"]) <= monitor.stop_loss_price:
                event_type, event_price = "stop_loss", monitor.stop_loss_price
            elif monitor.take_profit_price is not None and float(latest["high"]) >= monitor.take_profit_price:
                event_type, event_price = "take_profit", monitor.take_profit_price
            elif strategy.trade_params and strategy.trade_params.exit_conditions:
                should_exit = await self._condition.evaluate_groups(
                    strategy.trade_params.exit_conditions,
                    strategy.trade_params.exit_logic,
                    timeframe, kline_data, chan_data, indicator_data,
                )
                if should_exit:
                    event_type = "exit"
        elif signal.is_ready:
            event_type = "entry"

        if event_type is None:
            return False
        if event_type not in (monitor.event_types or ["entry", "exit", "stop_loss", "take_profit"]):
            return False
        entry, stop, take = _risk_prices(strategy, klines)
        title, content = await self._message(session, event_type, {
            "strategy_name": template.name, "symbol_name": monitor.symbol_name or monitor.symbol,
            "symbol": monitor.symbol, "price": f"{event_price:.4f}",
            "position_size": "请参考回测建议仓位",
            "stop_loss": f"{stop:.4f}" if stop is not None else "关闭",
            "take_profit": f"{take:.4f}" if take is not None else "关闭",
            "trigger_time": datetime.fromtimestamp(bar_time / 1000, BEIJING_TZ).strftime("%Y-%m-%d %H:%M"),
        })
        event = NotificationEvent(
            user_id=monitor.user_id, monitor_id=monitor.id, event_type=event_type,
            symbol=monitor.symbol, symbol_name=monitor.symbol_name or monitor.symbol,
            template_name=template.name, timeframe=timeframe, bar_time=bar_time,
            price=event_price, title=title, content=content,
            delivery_status={}, is_read=False,
        )
        existing = await session.scalar(select(NotificationEvent).where(
            NotificationEvent.monitor_id == monitor.id,
            NotificationEvent.event_type == event_type,
            NotificationEvent.bar_time == bar_time,
        ))
        if existing:
            return False
        session.add(event)
        await session.flush()
        channels = await self._channels_for_user(session, monitor.user_id, monitor.channel_ids)
        status = {}
        for channel in channels:
            status[str(channel.id)] = await send_channel(channel, event.title, event.content)
        event.delivery_status = status
        if event_type == "entry":
            entry, stop, take = _risk_prices(strategy, klines)
            monitor.in_position = True
            monitor.entry_price = entry
            monitor.stop_loss_price = stop
            monitor.take_profit_price = take
        else:
            monitor.in_position = False
            monitor.entry_price = None
            monitor.stop_loss_price = None
            monitor.take_profit_price = None
        return True

    async def _channels_for_user(self, session: AsyncSession, user_id: int, channel_ids: list[int] | None):
        if not channel_ids:
            return []
        return (await session.execute(select(NotificationChannel).where(
            NotificationChannel.id.in_(channel_ids),
            (((NotificationChannel.user_id == user_id) & (NotificationChannel.channel_type == "browser")) |
             (NotificationChannel.is_shared.is_(True))),
            NotificationChannel.enabled.is_(True),
        ))).scalars().all()

    async def _message(self, session: AsyncSession, event_type: str, values: dict[str, Any]) -> tuple[str, str]:
        item = await session.scalar(select(NotificationTemplate).where(
            NotificationTemplate.event_type == event_type, NotificationTemplate.enabled.is_(True)
        ))
        title, content = (item.name, item.content) if item else DEFAULT_MESSAGE_TEMPLATES.get(event_type, (EVENT_LABELS.get(event_type, event_type), ""))
        rendered = content
        for key, value in values.items():
            rendered = rendered.replace("{{" + key + "}}", str(value))
        return title, rendered[:2000]

    async def _process_screener_schedule(self, session: AsyncSession, schedule: ScreenerSchedule) -> bool:
        now = _beijing_now()
        if not self._schedule_time_due(schedule.schedule_time, schedule.schedule_weekdays, schedule.last_run_key, now):
            return False
        template = await session.get(Template, schedule.template_id)
        if not template or not template.enabled:
            schedule.last_error = "策略不存在或已停用"
            schedule.last_run_key = now.strftime("%Y-%m-%d")
            schedule.last_run_at = now
            return False
        run_key = now.strftime("%Y-%m-%d")
        bar_time = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        try:
            symbols, _ = await get_symbol_items(schedule.market, None, schedule.universe_limit)
            semaphore = asyncio.Semaphore(4)

            async def evaluate(item: dict):
                async with semaphore:
                    try:
                        signal = await evaluate_template_for_symbol(
                            item["symbol"], _template_schema(template), self._data, self._chan,
                            self._indicator, self._condition, kline_limit=200,
                        )
                        if signal.progress_percent < schedule.min_progress:
                            return None
                        return item, signal
                    except Exception as error:
                        logger.warning("scheduled screener failed for %s: %s", item.get("symbol"), error)
                        return None

            evaluated = [item for item in await asyncio.gather(*(evaluate(item) for item in symbols)) if item]
            evaluated.sort(key=lambda pair: (not pair[1].is_ready, -pair[1].progress_percent, pair[0]["symbol"]))
            results = evaluated[:20]
            result_text = "、".join(f"{item['name']}（{item['symbol']}）" for item, _ in results) or "暂无满足条件的标的"
            title, content = await self._message(session, "screener_completed", {
                "strategy_name": template.name, "market": schedule.market,
                "scanned_count": len(symbols), "matched_count": len(evaluated),
                "screen_results": result_text,
                "trigger_time": now.strftime("%Y-%m-%d %H:%M"),
            })
            event_type = "screener_completed"
            schedule.last_result_count = len(evaluated)
            schedule.last_error = None
        except Exception as error:
            title, content = await self._message(session, "screener_failed", {
                "strategy_name": template.name, "error": str(error)[:400], "trigger_time": now.strftime("%Y-%m-%d %H:%M"),
            })
            event_type = "screener_failed"
            schedule.last_result_count = 0
            schedule.last_error = str(error)[:500]
        existing = await session.scalar(select(NotificationEvent).where(
            NotificationEvent.monitor_id == schedule.id,
            NotificationEvent.event_type == event_type,
            NotificationEvent.bar_time == bar_time,
        ))
        if not existing:
            event = NotificationEvent(
                user_id=schedule.user_id, monitor_id=schedule.id, event_type=event_type,
                symbol=f"{schedule.market}:screener", symbol_name="策略选股",
                template_name=template.name, timeframe=template.primary_tf or "1d", bar_time=bar_time,
                price=0, title=title, content=content, delivery_status={}, is_read=False,
            )
            session.add(event)
            await session.flush()
            channels = await self._channels_for_user(session, schedule.user_id, schedule.channel_ids)
            event.delivery_status = {str(channel.id): await send_channel(channel, event.title, event.content) for channel in channels}
        schedule.last_run_key = run_key
        schedule.last_run_at = now
        return True

    @staticmethod
    def _schedule_time_due(schedule_time: str, weekdays: list[int] | None, last_key: str | None, now: datetime) -> bool:
        selected_days = [1, 2, 3, 4, 5] if weekdays is None else weekdays
        if not selected_days:
            selected_days = [1, 2, 3, 4, 5, 6, 7]
        if now.isoweekday() not in selected_days or last_key == now.strftime("%Y-%m-%d"):
            return False
        try:
            hour, minute = (int(part) for part in schedule_time.split(":", 1))
        except (AttributeError, ValueError):
            return False
        return (now.hour, now.minute) >= (hour, minute)

    @staticmethod
    def _schedule_due(monitor: StrategyMonitor, now: datetime) -> bool:
        if not monitor.schedule_enabled:
            return False
        # A legacy NULL value keeps the weekday default (Mon–Fri); an
        # explicitly empty list means the user selected every day.
        weekdays = [1, 2, 3, 4, 5] if monitor.schedule_weekdays is None else monitor.schedule_weekdays
        if not weekdays:
            weekdays = [1, 2, 3, 4, 5, 6, 7]
        if now.isoweekday() not in weekdays:
            return False
        try:
            hour, minute = (int(part) for part in monitor.schedule_time.split(":", 1))
        except (AttributeError, ValueError):
            return False
        if (now.hour, now.minute) < (hour, minute):
            return False
        return monitor.last_schedule_key != now.strftime("%Y-%m-%d")
