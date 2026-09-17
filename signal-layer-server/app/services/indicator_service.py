"""
============================================================================
指标计算服务
============================================================================

## 功能
提供技术指标计算,包括 MA/MACD/RSI/KDJ/Bollinger。
计算结果通过 Redis 缓存,同一 (symbol+timeframe+type+params) 只算一次,
跨用户共享。

## 缓存键
indicator:{symbol}:{timeframe}:{type}:{params_hash}
示例: indicator:BTCUSDT:1d:ma:period=5

## 数据流
前端 POST /api/v1/indicator/calculate → API 路由 → IndicatorService.calculate()
→ 查 Redis → 命中返回 / 未命中计算 → 写 Redis → 返回

## 指标扩展机制
本服务通过 auto_discover_indicators() 自动扫描 app/engine/indicator/ 目录,
所有用 @register_indicator 装饰的计算器类自动注册到 _registry。
新增指标只需:
  1. 在 app/engine/indicator/ 新建 .py 文件
  2. 继承 IndicatorCalculator,实现 type 和 calculate()
  3. 用 @register_indicator 装饰
无需修改本文件。
"""

from __future__ import annotations

import logging
from app.cache.indicator_cache import IndicatorCache
from app.engine.indicator.base import (
    IndicatorResult, IndicatorCalculator,
    auto_discover_indicators, get_registered_indicators,
)

logger = logging.getLogger(__name__)


class IndicatorService:
    """指标计算服务。管理指标计算器注册和缓存查询"""

    def __init__(self, cache: IndicatorCache):
        self._cache = cache
        # 自动发现并注册所有指标计算器
        auto_discover_indicators()
        # 实例化所有已注册的计算器
        self._registry: dict[str, IndicatorCalculator] = {
            ind_type: cls() for ind_type, cls in get_registered_indicators().items()
        }
        logger.info(f"IndicatorService initialized with {len(self._registry)} indicators: "
                    f"{sorted(self._registry.keys())}")

    async def calculate(
        self,
        symbol: str,
        timeframe: str,
        indicator_type: str,
        params: dict[str, float],
        klines: list[dict],
        context: dict | None = None,
    ) -> IndicatorResult:
        """
        计算指定指标值。优先从 Redis 读取缓存。

        缓存命中条件:数据截止时间一致(K 线未更新)。
        未命中时调用对应的计算器执行计算,完成后写入 Redis。

        Args:
            symbol: 交易对(如 "BTCUSDT")
            timeframe: 周期(如 "15m")
            indicator_type: 指标类型(ma/macd/rsi/kdj/bollinger/...)
            params: 指标参数(如 {"period": 5})

        Returns:
            IndicatorResult: {type, params, values: [{time, value, ...}]}
        """
        from app.cache.indicator_cache import key_indicator

        cache_key = key_indicator(symbol, timeframe, indicator_type, params)
        cached = await self._cache.get(cache_key)

        if cached and klines:
            data_end = cached.get("data_end_time", 0)
            data_start = cached.get("data_start_time")
            data_count = int(cached.get("data_count", 0))
            requested_start = int(klines[0]["open_time"])
            last_time = klines[-1]["open_time"]
            # 缓存必须完整覆盖当前请求区间。仅终点相同但历史更短的缓存
            # （例如先算200根，再请求500根）不能复用。
            if (
                data_end == last_time
                and data_start is not None
                and int(data_start) <= requested_start
                and data_count >= len(klines)
            ):
                logger.info(f"Indicator cache HIT {symbol} {timeframe} {indicator_type} params={params}")
                requested_end = int(last_time)
                values = [
                    item for item in cached["values"]
                    if requested_start <= int(float(item.get("time", 0))) <= requested_end
                ]
                profile_data = cached.get("profile_data")
                if profile_data and isinstance(profile_data, dict):
                    profile_data = {
                        **profile_data,
                        "snapshots": [
                            item for item in profile_data.get("snapshots", [])
                            if requested_start <= int(float(item.get("time", 0))) <= requested_end
                        ],
                    }
                return IndicatorResult(
                    type=cached["type"],
                    params=cached["params"],
                    values=values,
                    render=cached.get("render"),
                    profile_data=profile_data,
                )

        calc = self._registry.get(indicator_type)
        if calc is None:
            logger.error(f"Unknown indicator type: {indicator_type}")
            raise ValueError(f"Unknown indicator type: {indicator_type}. "
                             f"Available: {sorted(self._registry.keys())}")

        logger.info(f"Indicator cache MISS {symbol} {timeframe} {indicator_type} params={params} - computing...")
        params_sanitized = {k: v for k, v in params.items()}
        calculate_with_context = getattr(calc, "calculate_with_context", None)
        result = (
            calculate_with_context(klines, params_sanitized, context or {})
            if calculate_with_context is not None
            else calc.calculate(klines, params_sanitized)
        )

        logger.info(f"Indicator {indicator_type} {symbol} {timeframe} -> {len(result.values)} values")
        cache_data = {
            "type": result.type,
            "params": result.params,
            "values": result.values,
            "render": result.render.model_dump() if result.render else None,
            "profile_data": result.profile_data.model_dump() if result.profile_data else None,
            "data_start_time": klines[0]["open_time"] if klines else 0,
            "data_end_time": klines[-1]["open_time"] if klines else 0,
            "data_count": len(klines),
        }
        await self._cache.set(cache_key, cache_data)

        return result

    @property
    def available_indicators(self) -> list[str]:
        """返回所有可用指标类型列表"""
        return list(self._registry.keys())
