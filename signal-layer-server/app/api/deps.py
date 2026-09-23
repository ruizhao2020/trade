from __future__ import annotations
import logging
from functools import lru_cache
from redis.asyncio import Redis
from app.config import settings

logger = logging.getLogger(__name__)
from app.cache.indicator_cache import IndicatorCache
from app.db import init_db, close_db, get_session
from app.services.data_service import DataService
from app.services.chan_service import ChanService
from app.services.indicator_service import IndicatorService
from app.services.condition_service import ConditionService
from app.services.notification_service import NotificationService
from app.services.system_setting_service import get_divergence_power_ratio


_redis: Redis | None = None
_cache_instance: IndicatorCache | None = None
_data_service: DataService | None = None
_chan_service: ChanService | None = None
_indicator_service: IndicatorService | None = None
_condition_service: ConditionService | None = None
_notification_service: NotificationService | None = None


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


def get_data_service() -> DataService:
    global _data_service
    if _data_service is None:
        _data_service = DataService()
    return _data_service


def get_chan_service() -> ChanService:
    global _chan_service
    if _chan_service is None:
        raise RuntimeError("ChanService not initialized. Call init_services first.")
    return _chan_service


def get_indicator_service() -> IndicatorService:
    global _indicator_service
    if _indicator_service is None:
        raise RuntimeError("IndicatorService not initialized. Call init_services first.")
    return _indicator_service


def get_condition_service() -> ConditionService:
    global _condition_service
    if _condition_service is None:
        raise RuntimeError("ConditionService not initialized. Call init_services first.")
    return _condition_service


async def init_services():
    global _redis, _cache_instance, _chan_service, _indicator_service, _condition_service, _notification_service

    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database init failed: {e}, using SQLite")

    try:
        r = await get_redis()
        await r.ping()
        _cache_instance = IndicatorCache(r)
        logger.info("Redis connection established successfully")
    except Exception:
        logger.warning("Redis unavailable - caching disabled, using no-op cache")
        _cache_instance = IndicatorCache(None)

    _chan_service = ChanService(_cache_instance)
    try:
        async for session in get_session():
            _chan_service.set_divergence_power_ratio(await get_divergence_power_ratio(session))
            break
    except Exception:
        logger.warning("System settings unavailable; using default Chan parameters", exc_info=True)
    logger.info("ChanService initialized")
    _indicator_service = IndicatorService(_cache_instance)
    logger.info("IndicatorService initialized")
    _condition_service = ConditionService(_indicator_service)
    logger.info("ConditionService initialized")
    _notification_service = NotificationService(
        get_data_service(), _chan_service, _indicator_service, _condition_service,
    )
    _notification_service.start()
    logger.info("NotificationService initialized")


async def shutdown_services():
    global _redis, _notification_service
    if _notification_service:
        await _notification_service.stop()
        _notification_service = None
    if _redis:
        logger.info("Closing Redis connection...")
        await _redis.close()
        _redis = None
        logger.info("Redis connection closed")
    await close_db()
    logger.info("Database connection closed")
