"""
============================================================================
缠论分析服务
============================================================================

## 功能
封装缠论引擎（ChanEngine）的调用，加上 Redis 缓存管理。
同一品种+周期的缠论结构只计算一次，后续请求直接返回缓存。

## 缓存策略
- Redis key: chan:{symbol}:{timeframe}
- 缓存条件：K 线数据的最后一根时间未变（数据未更新）
- TTL: 默认 300 秒（config 中配置）
- 新 K 线到达时由 DataService 主动失效

## 数据流
1. 前端请求 GET /api/v1/chan/BTCUSDT/15m
2. ChanService.analyze() 被调用
3. 查 Redis → 命中则直接返回
4. 未命中 → 调 ChanEngine.analyze() 计算 → 写入 Redis → 返回

## 依赖
- app.engine.chan.ChanEngine: 纯计算引擎（无 I/O）
- app.cache.indicator_cache.IndicatorCache: Redis 缓存管理
"""

import logging
from app.engine.chan import ChanEngine, ChanResult
from app.cache.indicator_cache import IndicatorCache, key_chan

logger = logging.getLogger(__name__)


class ChanService:
    """缠论分析服务。封装计算逻辑和缓存管理"""

    def __init__(self, cache: IndicatorCache):
        self._engine = ChanEngine()
        self._cache = cache
        self._divergence_power_ratio = 0.7

    @property
    def divergence_power_ratio(self) -> float:
        return self._divergence_power_ratio

    def set_divergence_power_ratio(self, value: float) -> None:
        self._divergence_power_ratio = value

    async def analyze(
        self, symbol: str, timeframe: str, klines: list[dict],
    ) -> ChanResult:
        """
        获取某品种+周期的缠论分析结果。

        优先从 Redis 读取缓存。
        缓存命中条件：最后一根 K 线的 open_time 与缓存中的 updated_at 一致，
        说明数据未更新，可以复用。否则重新计算。

        Args:
            symbol: 交易对（如 "BTCUSDT"）
            timeframe: 周期（如 "15m"）
            klines: K 线数据列表

        Returns:
            ChanResult: 包含 bis/duans/zhongshus/buy_sell_points 的完整结构
        """
        cache_key = key_chan(symbol, timeframe, self._divergence_power_ratio)
        cached = await self._cache.get(cache_key)

        if cached and klines:
            last_time = klines[-1]["open_time"]
            if cached.get("updated_at") == last_time:
                logger.info(f"Chan cache HIT {symbol} {timeframe} ({len(cached.get('bis', []))} bis, "
                            f"{len(cached.get('duans', []))} duans, "
                            f"{len(cached.get('zhongshus', []))} zhongshus, "
                            f"{len(cached.get('divergences', []))} divergences, "
                            f"{len(cached.get('buy_sell_points', []))} points)")
                return self._deserialize(cached)

        logger.info(f"Chan cache MISS {symbol} {timeframe} - computing...")
        result = self._engine.analyze(
            klines, symbol=symbol, timeframe=timeframe,
            divergence_power_ratio=self._divergence_power_ratio,
        )

        logger.info(f"Chan analysis {symbol} {timeframe} -> {len(result.bis)} bis, "
                    f"{len(result.duans)} duans, {len(result.zhongshus)} zhongshus, "
                    f"{len(result.divergences)} divergences, "
                    f"{len(result.buy_sell_points)} buy_sell_points")
        await self._cache.set(cache_key, self._serialize(result))
        return result

    def _serialize(self, result: ChanResult) -> dict:
        """将计算结果序列化为 JSON 可存储的 dict。价格字段转字符串避免精度丢失"""
        return {
            "symbol": result.symbol,
            "timeframe": result.timeframe,
            "bis": [
                {
                    "index": b.index, "direction": b.direction,
                    "start_time": b.start_time, "end_time": b.end_time,
                    "start_price": str(b.start_price), "end_price": str(b.end_price),
                    "high": str(b.high), "low": str(b.low),
                }
                for b in result.bis
            ],
            "duans": [
                {
                    "index": d.index, "direction": d.direction,
                    "bi_indices": d.bi_indices,
                    "start_time": d.start_time, "end_time": d.end_time,
                    "start_price": str(d.start_price), "end_price": str(d.end_price),
                    "high": str(d.high), "low": str(d.low),
                    "feat_elements": d.feat_elements,
                    "merged_feat": d.merged_feat,
                    "fenxing_type": d.fenxing_type,
                }
                for d in result.duans
            ],
            "zhongshus": self._serialize_zs(result.zhongshus),
            "duan_zhongshus": self._serialize_zs(result.duan_zhongshus),
            "buy_sell_points": [
                {
                    "type": p.type, "price": str(p.price), "time": p.time,
                    "confirmed": p.confirmed, "strength": p.strength,
                    "zhongshu_index": p.zhongshu_index, "bi_index": p.bi_index,
                    "reason": p.reason, "divergence_index": p.divergence_index,
                }
                for p in result.buy_sell_points
            ],
            "divergences": [
                {
                    "index": item.index, "type": item.type, "level": item.level,
                    "kind": item.kind, "price": str(item.price), "time": item.time,
                    "zhongshu_index": item.zhongshu_index,
                    "reference_bi_index": item.reference_bi_index,
                    "current_bi_index": item.current_bi_index,
                    "reference_power": item.reference_power,
                    "current_power": item.current_power,
                    "strength_ratio": item.strength_ratio,
                    "confirmed": item.confirmed,
                    "reasons": item.reasons,
                }
                for item in result.divergences
            ],
            "updated_at": result.updated_at,
        }

    @staticmethod
    def _serialize_zs(zs_list: list) -> list[dict]:
        """序列化中枢列表(笔中枢和段中枢共用)"""
        return [
            {
                "index": z.index, "high": str(z.high), "low": str(z.low),
                "mid": str(z.mid),
                "start_time": z.start_time, "end_time": z.end_time,
                "level": z.level, "broken": z.broken,
                "bi_indices": z.bi_indices,
                "break_direction": z.break_direction,
            }
            for z in zs_list
        ]

    def _deserialize(self, data: dict) -> ChanResult:
        """从 Redis 读取的 dict 还原为 ChanResult 对象。价格字段从字符串转回 float"""
        from app.engine.chan.bi import Bi
        from app.engine.chan.zhongshu import Duan
        from app.engine.chan.signal import Zhongshu, BuySellPoint
        from app.engine.chan.divergence import Divergence

        return ChanResult(
            symbol=data.get("symbol", ""),
            timeframe=data.get("timeframe", ""),
            merged_klines=[],
            fenxings=[],
            bis=[
                Bi(
                    index=b["index"], direction=b["direction"],
                    fx_a=None, fx_b=None, bars=[],
                    start_time=b["start_time"], end_time=b["end_time"],
                    start_price=float(b["start_price"]), end_price=float(b["end_price"]),
                    high=float(b["high"]), low=float(b["low"]),
                    power=0.0, fenxing_start=None, fenxing_end=None, merged_span=0,
                )
                for b in data.get("bis", [])
            ],
            duans=[
                Duan(
                    index=d["index"], direction=d["direction"],
                    bi_indices=d["bi_indices"],
                    start_time=d["start_time"], end_time=d["end_time"],
                    start_price=float(d["start_price"]), end_price=float(d["end_price"]),
                    high=float(d["high"]), low=float(d["low"]),
                )
                for d in data.get("duans", [])
            ],
            zhongshus=self._deserialize_zs(data.get("zhongshus", [])),
            duan_zhongshus=self._deserialize_zs(data.get("duan_zhongshus", [])),
            buy_sell_points=[
                BuySellPoint(
                    type=p["type"], price=float(p["price"]), time=p["time"],
                    zhongshu_index=p.get("zhongshu_index"), bi_index=p.get("bi_index", 0),
                    confirmed=p["confirmed"], strength=p["strength"],
                    reason=p.get("reason"), divergence_index=p.get("divergence_index"),
                )
                for p in data.get("buy_sell_points", [])
            ],
            divergences=[
                Divergence(
                    index=item["index"], type=item["type"],
                    level=item.get("level", "bi"), kind=item.get("kind", "consolidation"),
                    price=float(item["price"]), time=item["time"],
                    zhongshu_index=item["zhongshu_index"],
                    reference_bi_index=item["reference_bi_index"],
                    current_bi_index=item["current_bi_index"],
                    reference_power=item["reference_power"],
                    current_power=item["current_power"],
                    strength_ratio=item["strength_ratio"],
                    confirmed=item.get("confirmed", True),
                    reasons=item.get("reasons", []),
                )
                for item in data.get("divergences", [])
            ],
            updated_at=data.get("updated_at", 0),
        )

    @staticmethod
    def _deserialize_zs(zs_data: list[dict]) -> list:
        """反序列化中枢列表(笔中枢和段中枢共用)"""
        from app.engine.chan.signal import Zhongshu
        return [
            Zhongshu(
                index=z["index"], high=float(z["high"]), low=float(z["low"]),
                mid=float(z["mid"]),
                start_time=z["start_time"], end_time=z["end_time"],
                level=z["level"],
                bi_indices=z.get("bi_indices", z.get("duan_indices", [])),
                broken=z["broken"],
                break_direction=z.get("break_direction"),
            )
            for z in zs_data
        ]
