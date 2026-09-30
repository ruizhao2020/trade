from __future__ import annotations

import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import Module

MODULE_RULES_TTL_SECONDS = 30

# 缓存为 None 表示"需要重新读取"。
# 注意不要用 (0.0, []) 这种哨兵值：判断是 `now - cached_at < TTL`，而
# time.monotonic() 在部分环境（容器/沙箱/刚启动的进程）会小于 TTL，
# 于是"已失效"会被误判成"刚缓存过"，直接返回空规则——模块准入被静默跳过。
_cache: Optional[tuple[float, list[tuple[str, str, bool, bool]]]] = None


def invalidate_module_rules() -> None:
    global _cache
    _cache = None


async def module_rules(session: AsyncSession) -> list[tuple[str, str, bool, bool]]:
    """返回 `(API 前缀, view 权限, 模块是否启用, 是否允许匿名)`。"""
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < MODULE_RULES_TTL_SECONDS:
        return _cache[1]

    modules = (await session.execute(select(Module))).scalars().all()
    rules = [
        (prefix.strip(), module.api_permission or f"{module.code}.view", module.enabled, module.public_access)
        for module in modules
        for prefix in module.api_prefixes.split(",")
        if prefix.strip()
    ]
    rules.sort(key=lambda item: len(item[0]), reverse=True)
    _cache = (now, rules)
    return rules
