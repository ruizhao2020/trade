from __future__ import annotations
from sqlalchemy import BigInteger, String, Numeric, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Kline(Base, TimestampMixin):
    __tablename__ = "klines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    open_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    open: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)
    turnover: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "open_time", name="uk_symbol_tf_time"),
        Index("idx_symbol_tf", "symbol", "timeframe"),
        Index("idx_open_time", "open_time"),
    )
