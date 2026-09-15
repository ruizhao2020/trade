from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db import get_session
from app.models.auth import User
from app.models.notification import NotificationChannel, NotificationEvent, NotificationTemplate, ScreenerSchedule, StrategyMonitor
from app.models.template import Template
from app.schemas.notification import (
    ChannelCreate, ChannelResponse, ChannelUpdate, EventResponse,
    MonitorCreate, MonitorResponse, MonitorUpdate,
    AdminChannelCreate, MarkEventsReadRequest, NotificationTemplateResponse, NotificationTemplateUpdate,
    ScreenerScheduleCreate, ScreenerScheduleResponse, ScreenerScheduleUpdate,
)
from app.services.notification_service import send_channel

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def _channel_response(channel: NotificationChannel, can_manage: bool = False) -> ChannelResponse:
    from app.services.notification_service import _mask_webhook
    return ChannelResponse(
        id=channel.id, name=channel.name, channel_type=channel.channel_type,
        webhook_url_masked=_mask_webhook(channel.webhook_url) if can_manage else None, enabled=channel.enabled,
        is_shared=channel.is_shared, can_manage=can_manage,
    )


async def _owned_channels(session: AsyncSession, user_id: int, channel_ids: list[int]) -> list[NotificationChannel]:
    if not channel_ids:
        return []
    return (await session.execute(select(NotificationChannel).where(
        ((NotificationChannel.user_id == user_id) & (NotificationChannel.channel_type == "browser")) |
        (NotificationChannel.is_shared.is_(True)),
        NotificationChannel.id.in_(channel_ids),
    ))).scalars().all()


def _monitor_response(monitor: StrategyMonitor, template: Template) -> MonitorResponse:
    return MonitorResponse(
        id=monitor.id, template_id=monitor.template_id, template_name=template.name,
        timeframe=template.primary_tf, symbol=monitor.symbol, symbol_name=monitor.symbol_name,
        channel_ids=monitor.channel_ids or [], enabled=monitor.enabled,
        poll_interval_seconds=monitor.poll_interval_seconds,
        last_checked_at=monitor.last_checked_at, last_bar_time=monitor.last_bar_time,
        in_position=monitor.in_position, entry_price=monitor.entry_price,
        stop_loss_price=monitor.stop_loss_price, take_profit_price=monitor.take_profit_price,
        schedule_enabled=monitor.schedule_enabled, schedule_time=monitor.schedule_time,
        schedule_weekdays=monitor.schedule_weekdays or [],
        event_types=monitor.event_types or ["entry", "exit", "stop_loss", "take_profit"],
    )


def _event_response(event: NotificationEvent) -> EventResponse:
    return EventResponse(
        id=event.id, monitor_id=event.monitor_id, event_type=event.event_type,
        symbol=event.symbol, symbol_name=event.symbol_name, template_name=event.template_name,
        timeframe=event.timeframe, bar_time=event.bar_time, price=event.price,
        title=event.title, content=event.content, delivery_status=event.delivery_status or {},
        is_read=event.is_read, created_at=event.created_at,
    )


def _schedule_response(schedule: ScreenerSchedule, template: Template) -> ScreenerScheduleResponse:
    return ScreenerScheduleResponse(
        id=schedule.id, template_id=schedule.template_id, template_name=template.name,
        market=schedule.market, universe_limit=schedule.universe_limit, min_progress=schedule.min_progress,
        schedule_time=schedule.schedule_time, schedule_weekdays=schedule.schedule_weekdays or [],
        channel_ids=schedule.channel_ids or [], enabled=schedule.enabled,
        last_run_at=schedule.last_run_at, last_result_count=schedule.last_result_count,
        last_error=schedule.last_error,
    )


@router.get("/channels", response_model=list[ChannelResponse], dependencies=[Depends(require_permission("notifications.view"))])
async def list_channels(user: User = Depends(require_permission("notifications.view")), session: AsyncSession = Depends(get_session)):
    # Shared admin channels are selectable by all users. A browser channel is
    # personal and is created lazily so every user has an in-app destination.
    browser = await session.scalar(select(NotificationChannel).where(
        NotificationChannel.user_id == user.id, NotificationChannel.channel_type == "browser",
        NotificationChannel.is_shared.is_(False),
    ))
    if browser is None:
        browser = NotificationChannel(user_id=user.id, name="浏览器通知", channel_type="browser", enabled=True, is_shared=False)
        session.add(browser)
        await session.flush()
    channels = (await session.execute(select(NotificationChannel).where(
        ((NotificationChannel.user_id == user.id) & (NotificationChannel.is_shared.is_(False)) & (NotificationChannel.channel_type == "browser")) |
        (NotificationChannel.is_shared.is_(True) & NotificationChannel.enabled.is_(True))
    ).order_by(NotificationChannel.id))).scalars().all()
    await session.commit()
    return [_channel_response(channel) for channel in channels]


@router.post("/channels", response_model=ChannelResponse, status_code=201, dependencies=[Depends(require_permission("notifications.manage"))])
async def create_channel(body: ChannelCreate, user: User = Depends(require_permission("notifications.manage")), session: AsyncSession = Depends(get_session)):
    if body.channel_type != "browser":
        raise HTTPException(status_code=403, detail="企业微信和飞书 Webhook 只能由管理员配置")
    channel = NotificationChannel(
        user_id=user.id, name=body.name, channel_type=body.channel_type,
        webhook_url=None, enabled=body.enabled, is_shared=False,
    )
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return _channel_response(channel)


@router.put("/channels/{channel_id}", response_model=ChannelResponse, dependencies=[Depends(require_permission("notifications.manage"))])
async def update_channel(channel_id: int, body: ChannelUpdate, user: User = Depends(require_permission("notifications.manage")), session: AsyncSession = Depends(get_session)):
    channel = await session.get(NotificationChannel, channel_id)
    if not channel or channel.user_id != user.id or channel.is_shared:
        raise HTTPException(status_code=404, detail="通知渠道不存在")
    if channel.channel_type != "browser":
        raise HTTPException(status_code=403, detail="企业微信和飞书渠道只能由管理员配置")
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "webhook_url":
            value = str(value) if value else None
        setattr(channel, field, value)
    if channel.channel_type != "browser" and not channel.webhook_url:
        raise HTTPException(status_code=400, detail="企业微信和飞书渠道必须填写机器人 Webhook 地址")
    await session.commit()
    await session.refresh(channel)
    return _channel_response(channel)


@router.delete("/channels/{channel_id}", status_code=204, dependencies=[Depends(require_permission("notifications.manage"))])
async def delete_channel(channel_id: int, user: User = Depends(require_permission("notifications.manage")), session: AsyncSession = Depends(get_session)):
    channel = await session.get(NotificationChannel, channel_id)
    if not channel or channel.user_id != user.id or channel.is_shared:
        raise HTTPException(status_code=404, detail="通知渠道不存在")
    await session.delete(channel)
    await session.commit()


@router.post("/channels/{channel_id}/test", response_model=dict, dependencies=[Depends(require_permission("notifications.admin"))])
async def test_channel(channel_id: int, user: User = Depends(require_permission("notifications.admin")), session: AsyncSession = Depends(get_session)):
    channel = await session.get(NotificationChannel, channel_id)
    if not channel or not channel.is_shared:
        raise HTTPException(status_code=404, detail="通知渠道不存在")
    status = await send_channel(channel, "SignalLayer 通知测试", "通知渠道连接正常。")
    return {"status": status}


@router.get("/admin/channels", response_model=list[ChannelResponse], dependencies=[Depends(require_permission("notifications.admin"))])
async def admin_list_channels(user: User = Depends(require_permission("notifications.admin")), session: AsyncSession = Depends(get_session)):
    channels = (await session.execute(select(NotificationChannel).order_by(NotificationChannel.id))).scalars().all()
    return [_channel_response(channel, can_manage=True) for channel in channels]


@router.post("/admin/channels", response_model=ChannelResponse, status_code=201, dependencies=[Depends(require_permission("notifications.admin"))])
async def admin_create_channel(body: AdminChannelCreate, user: User = Depends(require_permission("notifications.admin")), session: AsyncSession = Depends(get_session)):
    if body.channel_type != "browser" and body.webhook_url is None:
        raise HTTPException(status_code=400, detail="企业微信和飞书渠道必须填写机器人 Webhook 地址")
    channel = NotificationChannel(
        user_id=user.id, name=body.name, channel_type=body.channel_type,
        webhook_url=str(body.webhook_url) if body.webhook_url else None,
        enabled=body.enabled, is_shared=body.is_shared,
    )
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return _channel_response(channel, can_manage=True)


@router.put("/admin/channels/{channel_id}", response_model=ChannelResponse, dependencies=[Depends(require_permission("notifications.admin"))])
async def admin_update_channel(channel_id: int, body: ChannelUpdate, user: User = Depends(require_permission("notifications.admin")), session: AsyncSession = Depends(get_session)):
    channel = await session.get(NotificationChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="通知渠道不存在")
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "webhook_url":
            value = str(value) if value else None
        setattr(channel, field, value)
    if channel.channel_type != "browser" and not channel.webhook_url:
        raise HTTPException(status_code=400, detail="企业微信和飞书渠道必须填写机器人 Webhook 地址")
    await session.commit()
    await session.refresh(channel)
    return _channel_response(channel, can_manage=True)


@router.delete("/admin/channels/{channel_id}", status_code=204, dependencies=[Depends(require_permission("notifications.admin"))])
async def admin_delete_channel(channel_id: int, user: User = Depends(require_permission("notifications.admin")), session: AsyncSession = Depends(get_session)):
    channel = await session.get(NotificationChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="通知渠道不存在")
    await session.delete(channel)
    await session.commit()


def _notification_template_response(item: NotificationTemplate) -> NotificationTemplateResponse:
    return NotificationTemplateResponse(id=item.id, event_type=item.event_type, name=item.name, content=item.content, enabled=item.enabled)


@router.get("/admin/templates", response_model=list[NotificationTemplateResponse], dependencies=[Depends(require_permission("notifications.admin"))])
async def admin_list_templates(user: User = Depends(require_permission("notifications.admin")), session: AsyncSession = Depends(get_session)):
    items = (await session.execute(select(NotificationTemplate).order_by(NotificationTemplate.id))).scalars().all()
    return [_notification_template_response(item) for item in items]


@router.put("/admin/templates/{template_id}", response_model=NotificationTemplateResponse, dependencies=[Depends(require_permission("notifications.admin"))])
async def admin_update_template(template_id: int, body: NotificationTemplateUpdate, user: User = Depends(require_permission("notifications.admin")), session: AsyncSession = Depends(get_session)):
    item = await session.get(NotificationTemplate, template_id)
    if not item:
        raise HTTPException(status_code=404, detail="通知模板不存在")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.updated_by = user.id
    await session.commit()
    await session.refresh(item)
    return _notification_template_response(item)


@router.get("/monitors", response_model=list[MonitorResponse], dependencies=[Depends(require_permission("notifications.view"))])
async def list_monitors(user: User = Depends(require_permission("notifications.view")), session: AsyncSession = Depends(get_session)):
    monitors = (await session.execute(select(StrategyMonitor).where(StrategyMonitor.user_id == user.id).order_by(StrategyMonitor.id.desc()))).scalars().all()
    responses = []
    for monitor in monitors:
        template = await session.get(Template, monitor.template_id)
        if template:
            responses.append(_monitor_response(monitor, template))
    return responses


@router.post("/monitors", response_model=MonitorResponse, status_code=201, dependencies=[Depends(require_permission("notifications.manage"))])
async def create_monitor(body: MonitorCreate, user: User = Depends(require_permission("notifications.manage")), session: AsyncSession = Depends(get_session)):
    template = await session.get(Template, body.template_id)
    if not template or template.user_id != user.id:
        raise HTTPException(status_code=404, detail="策略不存在或不属于当前用户")
    channels = await _owned_channels(session, user.id, body.channel_ids)
    if len(channels) != len(set(body.channel_ids)):
        raise HTTPException(status_code=400, detail="包含不存在的通知渠道")
    exists = await session.scalar(select(StrategyMonitor).where(
        StrategyMonitor.user_id == user.id,
        StrategyMonitor.template_id == body.template_id,
        StrategyMonitor.symbol == body.symbol,
    ))
    if exists:
        raise HTTPException(status_code=409, detail="该策略和标的已经存在监控")
    monitor = StrategyMonitor(
        user_id=user.id, template_id=body.template_id, symbol=body.symbol,
        symbol_name=body.symbol_name, channel_ids=body.channel_ids,
        enabled=body.enabled, poll_interval_seconds=body.poll_interval_seconds,
        schedule_enabled=body.schedule_enabled, schedule_time=body.schedule_time,
        schedule_weekdays=body.schedule_weekdays,
        event_types=body.event_types,
    )
    session.add(monitor)
    await session.commit()
    await session.refresh(monitor)
    return _monitor_response(monitor, template)


@router.put("/monitors/{monitor_id}", response_model=MonitorResponse, dependencies=[Depends(require_permission("notifications.manage"))])
async def update_monitor(monitor_id: int, body: MonitorUpdate, user: User = Depends(require_permission("notifications.manage")), session: AsyncSession = Depends(get_session)):
    monitor = await session.get(StrategyMonitor, monitor_id)
    if not monitor or monitor.user_id != user.id:
        raise HTTPException(status_code=404, detail="策略监控不存在")
    if body.channel_ids is not None:
        channels = await _owned_channels(session, user.id, body.channel_ids)
        if len(channels) != len(set(body.channel_ids)):
            raise HTTPException(status_code=400, detail="包含不存在的通知渠道")
    for field, value in body.model_dump(exclude_unset=True, exclude={"reset_position"}).items():
        setattr(monitor, field, value)
    if body.reset_position:
        monitor.in_position = False
        monitor.entry_price = None
        monitor.stop_loss_price = None
        monitor.take_profit_price = None
    template = await session.get(Template, monitor.template_id)
    await session.commit()
    await session.refresh(monitor)
    return _monitor_response(monitor, template)


@router.delete("/monitors/{monitor_id}", status_code=204, dependencies=[Depends(require_permission("notifications.manage"))])
async def delete_monitor(monitor_id: int, user: User = Depends(require_permission("notifications.manage")), session: AsyncSession = Depends(get_session)):
    monitor = await session.get(StrategyMonitor, monitor_id)
    if not monitor or monitor.user_id != user.id:
        raise HTTPException(status_code=404, detail="策略监控不存在")
    await session.delete(monitor)
    await session.commit()


@router.get("/screener-schedules", response_model=list[ScreenerScheduleResponse], dependencies=[Depends(require_permission("notifications.view"))])
async def list_screener_schedules(user: User = Depends(require_permission("notifications.view")), session: AsyncSession = Depends(get_session)):
    schedules = (await session.execute(select(ScreenerSchedule).where(
        ScreenerSchedule.user_id == user.id
    ).order_by(ScreenerSchedule.id.desc()))).scalars().all()
    responses = []
    for schedule in schedules:
        template = await session.get(Template, schedule.template_id)
        if template:
            responses.append(_schedule_response(schedule, template))
    return responses


@router.post("/screener-schedules", response_model=ScreenerScheduleResponse, status_code=201, dependencies=[Depends(require_permission("notifications.manage"))])
async def create_screener_schedule(body: ScreenerScheduleCreate, user: User = Depends(require_permission("notifications.manage")), session: AsyncSession = Depends(get_session)):
    template = await session.get(Template, body.template_id)
    if not template or template.user_id != user.id:
        raise HTTPException(status_code=404, detail="策略不存在或不属于当前用户")
    channels = await _owned_channels(session, user.id, body.channel_ids)
    if len(channels) != len(set(body.channel_ids)):
        raise HTTPException(status_code=400, detail="包含不存在的通知渠道")
    exists = await session.scalar(select(ScreenerSchedule).where(
        ScreenerSchedule.user_id == user.id, ScreenerSchedule.template_id == body.template_id,
        ScreenerSchedule.market == body.market, ScreenerSchedule.schedule_time == body.schedule_time,
    ))
    if exists:
        raise HTTPException(status_code=409, detail="该策略的定时选股任务已经存在")
    schedule = ScreenerSchedule(user_id=user.id, **body.model_dump())
    session.add(schedule)
    await session.commit()
    await session.refresh(schedule)
    return _schedule_response(schedule, template)


@router.put("/screener-schedules/{schedule_id}", response_model=ScreenerScheduleResponse, dependencies=[Depends(require_permission("notifications.manage"))])
async def update_screener_schedule(schedule_id: int, body: ScreenerScheduleUpdate, user: User = Depends(require_permission("notifications.manage")), session: AsyncSession = Depends(get_session)):
    schedule = await session.get(ScreenerSchedule, schedule_id)
    if not schedule or schedule.user_id != user.id:
        raise HTTPException(status_code=404, detail="定时选股任务不存在")
    if body.channel_ids is not None:
        channels = await _owned_channels(session, user.id, body.channel_ids)
        if len(channels) != len(set(body.channel_ids)):
            raise HTTPException(status_code=400, detail="包含不存在的通知渠道")
    schedule_fields = body.model_dump(exclude_unset=True)
    if any(field in schedule_fields for field in ("schedule_time", "schedule_weekdays", "market", "template_id")):
        schedule.last_run_key = None
    for field, value in schedule_fields.items():
        setattr(schedule, field, value)
    template = await session.get(Template, schedule.template_id)
    await session.commit()
    await session.refresh(schedule)
    return _schedule_response(schedule, template)


@router.delete("/screener-schedules/{schedule_id}", status_code=204, dependencies=[Depends(require_permission("notifications.manage"))])
async def delete_screener_schedule(schedule_id: int, user: User = Depends(require_permission("notifications.manage")), session: AsyncSession = Depends(get_session)):
    schedule = await session.get(ScreenerSchedule, schedule_id)
    if not schedule or schedule.user_id != user.id:
        raise HTTPException(status_code=404, detail="定时选股任务不存在")
    await session.delete(schedule)
    await session.commit()


@router.get("/events", response_model=list[EventResponse], dependencies=[Depends(require_permission("notifications.view"))])
async def list_events(unread_only: bool = Query(default=False), limit: int = Query(default=50, ge=1, le=200), user: User = Depends(require_permission("notifications.view")), session: AsyncSession = Depends(get_session)):
    query = select(NotificationEvent).where(NotificationEvent.user_id == user.id)
    if unread_only:
        query = query.where(NotificationEvent.is_read.is_(False))
    events = (await session.execute(query.order_by(NotificationEvent.created_at.desc()).limit(limit))).scalars().all()
    return [_event_response(event) for event in events]


@router.post("/events/read", response_model=dict, dependencies=[Depends(require_permission("notifications.view"))])
async def mark_events_read(body: MarkEventsReadRequest, user: User = Depends(require_permission("notifications.view")), session: AsyncSession = Depends(get_session)):
    query = select(NotificationEvent).where(NotificationEvent.user_id == user.id)
    if body.ids:
        query = query.where(NotificationEvent.id.in_(body.ids))
    events = (await session.execute(query)).scalars().all()
    for event in events:
        event.is_read = True
    await session.commit()
    return {"updated": len(events)}
