from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AdvisorRun(Base, TimestampMixin):
    """一次策略建议分析。

    把候选空间/评分函数/约束/数据区间一起存下来，任何一次结论都能重放，
    否则改了方法无法判断是变好还是变坏。
    """

    __tablename__ = "advisor_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    market: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 可复现性快照
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    data_range: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1")

    # 结果
    verdict: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    profile: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    evaluated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_advisor_run_user", "user_id"),
        Index("idx_advisor_run_symbol", "symbol"),
    )


class AdvisorCandidate(Base, TimestampMixin):
    """一次分析中的一个候选策略及其评分与淘汰原因。"""

    __tablename__ = "advisor_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    family: Mapped[str] = mapped_column(String(40), nullable=False)
    primary_level: Mapped[str] = mapped_column(String(10), nullable=False)
    entry_level: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(String(400), nullable=False)

    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rejected_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    plateau_stable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    in_sample: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    out_of_sample: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    notes: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # 结构化候选（规则/出场/级别），落成真实策略模板时据此重建
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_advisor_candidate_run", "run_id"),
    )


class AdvisorRecommendation(Base, TimestampMixin):
    """一条落地的建议：指向生成的真实策略模板，并记录基线画像与复核期。"""

    __tablename__ = "advisor_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)

    template_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    baseline_profile: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    review_after_bars: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    drift_state: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    drift_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_advisor_recommendation_user", "user_id"),
        Index("idx_advisor_recommendation_symbol", "symbol"),
    )
