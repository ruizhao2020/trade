from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ContentTemplate(Base, TimestampMixin):
    __tablename__ = "content_templates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    sections: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    built_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ArticleDraft(Base, TimestampMixin):
    __tablename__ = "article_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol_name: Mapped[str] = mapped_column(String(100), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    timeframes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    chart_specs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    standard_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    platform_variants: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_article_draft_user", "user_id", "created_at"),
        Index("idx_article_draft_symbol", "symbol", "as_of"),
    )
