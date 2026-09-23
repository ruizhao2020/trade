from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting


DIVERGENCE_POWER_RATIO_KEY = "chan.divergence_power_ratio"
DEFAULT_DIVERGENCE_POWER_RATIO = 0.7


async def get_divergence_power_ratio(session: AsyncSession) -> float:
    item = await session.get(SystemSetting, DIVERGENCE_POWER_RATIO_KEY)
    return float(item.value_number) if item else DEFAULT_DIVERGENCE_POWER_RATIO


async def set_divergence_power_ratio(session: AsyncSession, value: float) -> SystemSetting:
    item = await session.get(SystemSetting, DIVERGENCE_POWER_RATIO_KEY)
    if item is None:
        item = SystemSetting(
            key=DIVERGENCE_POWER_RATIO_KEY,
            value_number=value,
            name="缠论背驰力度阈值",
            description="当前笔力度必须小于参考笔力度乘以该阈值，才确认背驰。",
        )
        session.add(item)
    else:
        item.value_number = value
    await session.commit()
    await session.refresh(item)
    return item
