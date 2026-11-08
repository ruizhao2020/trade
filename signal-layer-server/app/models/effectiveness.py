from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, DateTime, Float, Integer, JSON, String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class IndicatorEffectiveness(Base, TimestampMixin):
    """指标字段的有效性评测结论。

    评测单元是（指标类型, 字段, 方向, 参数, 周期, 股票池, 持有期），
    而不是"指标"本身：同一个指标的不同输出字段、不同周期、不同池子，
    结论可以完全不同。所以结论必须带作用域（scope）和评测时间。
    """

    __tablename__ = "indicator_effectiveness"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    indicator_type: Mapped[str] = mapped_column(String(50), nullable=False)
    field: Mapped[str] = mapped_column(String(80), nullable=False)
    # long=入场、short=出场/风险、none=方向由评测决定
    direction: Mapped[str] = mapped_column(String(10), default="none")
    params_key: Mapped[str] = mapped_column(String(200), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    universe: Mapped[str] = mapped_column(String(80), nullable=False)
    horizon: Mapped[int] = mapped_column(Integer, default=10)

    sample_n: Mapped[int] = mapped_column(Integer, default=0)       # 不重叠事件数
    raw_events: Mapped[int] = mapped_column(Integer, default=0)     # 原始事件数
    hit_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)       # 扣成本后
    baseline_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    excess_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)          # 已做多重检验校正
    decay: Mapped[dict] = mapped_column(JSON, default=dict)          # 持有期 -> 平均净收益
    stability: Mapped[dict] = mapped_column(JSON, default=dict)      # 前后半段
    # valid=有效、filter_only=仅作过滤、weak=不显著、rejected=显著反向、insufficient=样本不足
    verdict: Mapped[str] = mapped_column(String(16), default="insufficient")
    scope: Mapped[dict] = mapped_column(JSON, default=dict)          # 池子、区间、持有期等
    engine_version: Mapped[str] = mapped_column(String(16), default="v1")
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint(
            "indicator_type", "field", "direction", "params_key",
            "timeframe", "universe", "horizon",
            name="uq_indicator_effectiveness_unit",
        ),
    )
