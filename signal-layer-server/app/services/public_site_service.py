from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import PublicIndicatorFeaturePolicy, PublicIndicatorPolicy


async def public_indicator_policies(session: AsyncSession) -> list[PublicIndicatorPolicy]:
    return list((await session.execute(
        select(PublicIndicatorPolicy).order_by(PublicIndicatorPolicy.sort_order, PublicIndicatorPolicy.id)
    )).scalars().all())


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
