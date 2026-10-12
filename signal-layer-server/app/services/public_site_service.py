from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.indicator.base import get_registered_indicators
from app.models.auth import PublicIndicatorFeaturePolicy, PublicIndicatorPolicy


async def public_indicator_policies(session: AsyncSession) -> list[PublicIndicatorPolicy]:
    """公开站的指标策略行，只保留**当前引擎里真实存在**的指标。

    策略表是数据、引擎是代码，两者会漂移：某个指标被下线后，旧库里仍留着它的策略行
    （种子 SQL 只在空库上执行，启动时的补种也只增不减）。这类死行如果被返回给公开站，
    前端会照着它去请求一个不存在的指标；content_service 里更是**没有 try/except**，
    直接就是 500。所以这里统一按注册表过滤一次。
    """
    registered = set(get_registered_indicators())
    return [
        item for item in (await session.execute(
            select(PublicIndicatorPolicy).order_by(PublicIndicatorPolicy.sort_order, PublicIndicatorPolicy.id)
        )).scalars().all()
        if item.indicator_type in registered
    ]


async def public_indicator_feature_policies(
    session: AsyncSession,
    indicator_type: str | None = None,
) -> list[PublicIndicatorFeaturePolicy]:
    query = select(PublicIndicatorFeaturePolicy)
    if indicator_type:
        query = query.where(PublicIndicatorFeaturePolicy.indicator_type == indicator_type)
    query = query.order_by(
        PublicIndicatorFeaturePolicy.indicator_type,
        PublicIndicatorFeaturePolicy.sort_order,
        PublicIndicatorFeaturePolicy.id,
    )
    return list((await session.execute(query)).scalars().all())


async def public_indicator_map(session: AsyncSession) -> dict[str, PublicIndicatorPolicy]:
    return {item.indicator_type: item for item in await public_indicator_policies(session)}


async def public_indicator_feature_map(
    session: AsyncSession,
    indicator_type: str | None = None,
) -> dict[str, PublicIndicatorFeaturePolicy]:
    return {
        item.feature_code: item
        for item in await public_indicator_feature_policies(session, indicator_type)
    }


async def ensure_public_indicator(
    session: AsyncSession,
    indicator_type: str,
    display_name: str,
    feature_definitions: Iterable[tuple[str, str, bool]],
) -> PublicIndicatorPolicy:
    """Auto-register discovered indicators and features as private by default."""
    policy = await session.scalar(select(PublicIndicatorPolicy).where(
        PublicIndicatorPolicy.indicator_type == indicator_type
    ))
    if policy is None:
        policy = PublicIndicatorPolicy(
            indicator_type=indicator_type, display_name=display_name,
            public_visible=False, show_parameters=False, show_details=False,
            show_markers=False, sort_order=1000,
        )
        session.add(policy)
        await session.flush()
    existing = await public_indicator_feature_map(session, indicator_type)
    for order, (feature_code, feature_name, is_marker) in enumerate(feature_definitions, 1):
        if feature_code in existing:
            continue
        session.add(PublicIndicatorFeaturePolicy(
            indicator_type=indicator_type,
            feature_code=feature_code,
            display_name=feature_name or feature_code,
            public_visible=bool(policy.public_visible and not is_marker),
            show_details=bool(policy.show_details and not is_marker),
            sort_order=order * 10,
        ))
    await session.flush()
    return policy
