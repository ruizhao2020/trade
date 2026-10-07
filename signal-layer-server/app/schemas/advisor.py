from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AdvisorConstraints(BaseModel):
    """硬约束，全部可选；不传则用引擎默认值。"""

    min_trades: Optional[int] = Field(default=None, ge=1, le=1000)
    min_win_rate: Optional[float] = Field(default=None, ge=0, le=100)
    min_frequency: Optional[float] = Field(default=None, ge=0, le=10)
    max_frequency: Optional[float] = Field(default=None, gt=0, le=10)
    min_out_of_sample_return: Optional[float] = None
    min_out_of_sample_trades: Optional[int] = Field(default=None, ge=1, le=200)


class AdvisorRunCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    symbol_name: Optional[str] = Field(default=None, max_length=80)
    market: Optional[str] = Field(default=None, max_length=20)
    budget: int = Field(default=4000, ge=50, le=20000)
    selection_ratio: float = Field(default=0.7, gt=0.3, lt=0.95)
    segments: int = Field(default=3, ge=1, le=8)
    kline_limit: int = Field(default=500, ge=120, le=2000)
    constraints: Optional[AdvisorConstraints] = None


class AdvisorTradeStats(BaseModel):
    trades: int = 0
    win_rate: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    frequency: float = 0.0
    expectancy: float = 0.0


class AdvisorCandidateItem(BaseModel):
    rank: Optional[int] = None
    family: str
    primary_level: str
    entry_level: str
    description: str
    score: float = 0.0
    passed: bool = False
    plateau_stable: bool = False
    rejected_reason: Optional[str] = None
    in_sample: Optional[AdvisorTradeStats] = None
    out_of_sample: Optional[AdvisorTradeStats] = None
    notes: list[str] = []


class AdvisorRunResponse(BaseModel):
    id: int
    symbol: str
    symbol_name: Optional[str] = None
    market: Optional[str] = None
    status: str
    progress_percent: int = 0
    stage: Optional[str] = None
    error: Optional[str] = None
    verdict: Optional[str] = None
    summary: Optional[str] = None
    profile: Optional[dict] = None
    evaluated_count: int = 0
    truncated: bool = False
    engine_version: str = "1"
    config: Optional[dict] = None
    created_at: Optional[str] = None
    finished_at: Optional[str] = None
    candidates: list[AdvisorCandidateItem] = []


class AdvisorRunSummary(BaseModel):
    id: int
    symbol: str
    symbol_name: Optional[str] = None
    status: str
    verdict: Optional[str] = None
    summary: Optional[str] = None
    created_at: Optional[str] = None


class AdvisorTemplateSave(BaseModel):
    """把建议落成真实策略模板时的可选覆盖。"""

    name: Optional[str] = Field(default=None, max_length=120)
    enabled: bool = True


class AdvisorTemplateResponse(BaseModel):
    template_id: str
    name: str
    primary_tf: str
    secondary_tfs: list[str] = []


class AdvisorRecommendationItem(BaseModel):
    id: int
    run_id: int
    symbol: str
    template_id: Optional[str] = None
    status: str
    drift_state: Optional[str] = None
    drift_detail: Optional[str] = None
    review_after_bars: int = 20
    baseline_profile: Optional[dict] = None
    created_at: Optional[str] = None
