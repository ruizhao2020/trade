from typing import Any, Optional
from sqlalchemy import BigInteger, String, Boolean, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Template(Base, TimestampMixin):
    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    logic: Mapped[str] = mapped_column(String(3), default="AND")
    condition_groups: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    primary_tf: Mapped[str] = mapped_column(String(10), default="1d")
    secondary_tfs: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trade_params: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (Index("idx_user", "user_id"),)
