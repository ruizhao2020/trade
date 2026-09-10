from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import Module

_cache: tuple[float, list[tuple[str, str, bool]]] = (0.0, [])


def invalidate_module_rules():
    global _cache
    _cache = (0.0, [])


async def module_rules(session: AsyncSession) -> list[tuple[str, str, bool]]:
    """返回 `(API 前缀, view 权限, 模块是否启用)`，短时缓存降低 DB 压力。"""
    global _cache
    now = time.monotonic()
    if now - _cache[0] < 30:
        return _cache[1]
    modules = (await session.execute(select(Module))).scalars().all()
    rules = [
        (prefix.strip(), module.api_permission or f"{module.code}.view", module.enabled)
        for module in modules
        for prefix in module.api_prefixes.split(",")
        if prefix.strip()
    ]
    rules.sort(key=lambda item: len(item[0]), reverse=True)
    _cache = (now, rules)
    return rules
