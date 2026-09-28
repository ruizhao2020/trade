"""条件级别的解析。

条件的级别（`condition.timeframe_id`）有三种写法：

- 未指定（None/空）：按模板的**主周期**判定；
- 具体级别（如 `30m`）：只在该级别判定；
- 哨兵值 `secondary`：按模板声明的**次级周期集合**判定，集合内**满足任一即成立**（或的关系）。

放在独立模块里，供 condition_service 与 signal_evaluation_service 共用，
避免两者之间的循环导入。
"""

from __future__ import annotations

SECONDARY_TIMEFRAME = "secondary"


def resolve_condition_timeframes(
    raw_timeframe: str | None,
    primary_tf: str,
    secondary_tfs: list[str] | None,
) -> list[str]:
    """把条件的级别解析成需要判定的具体级别列表。

    返回空列表表示「次级周期」条件但模板没有声明任何次级周期——
    此时该条件无法成立，由调用方判定为不满足。
    """
    if raw_timeframe == SECONDARY_TIMEFRAME:
        # 去重并保持声明顺序，避免同一级别被重复判定
        resolved: list[str] = []
        for timeframe in secondary_tfs or []:
            if timeframe and timeframe not in resolved:
                resolved.append(timeframe)
        return resolved
    return [raw_timeframe or primary_tf]
