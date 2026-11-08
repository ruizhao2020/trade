from typing import Literal, Optional, Any
from pydantic import BaseModel


class BiSchema(BaseModel):
    index: int
    direction: Literal["up", "down"]
    start_time: int
    end_time: int
    start_price: str
    end_price: str
    high: str
    low: str


class FeatElementSchema(BaseModel):
    first: float
    last: float
    bi: int


class DuanSchema(BaseModel):
    index: int
    direction: Literal["up", "down"]
    bi_indices: list[int]
    start_time: int
    end_time: int
    start_price: str
    end_price: str
    high: str
    low: str
    feat_elements: Optional[list[dict[str, Any]]] = None
    merged_feat: Optional[list[dict[str, Any]]] = None
    fenxing_type: Optional[str] = None


class ZhongshuSchema(BaseModel):
    index: int
    high: str
    low: str
    mid: str
    start_time: int
    end_time: int
    level: str
    broken: bool
    bi_indices: list[int]
    break_direction: Optional[Literal["up", "down"]] = None


class BuySellPointSchema(BaseModel):
    type: Literal["buy1", "buy2", "buy3", "sell1", "sell2", "sell3"]
    price: str
    time: int
    confirmed: bool
    strength: float
    zhongshu_index: Optional[int] = None
    bi_index: int
    reason: Optional[str] = None
    divergence_index: Optional[int] = None


class DivergenceSchema(BaseModel):
    index: int
    type: Literal["top", "bottom"]
    level: Literal["bi"]
    kind: Literal["consolidation"]
    price: str
    time: int
    zhongshu_index: int
    reference_bi_index: int
    current_bi_index: int
    reference_power: float
    current_power: float
    strength_ratio: float
    confirmed: bool
    reasons: list[str]


class KlineOverlapSchema(BaseModel):
    """K 线重叠段：只读的级别参考（零缠的"K线重叠理论"）。"""
    start_time: int
    end_time: int
    low: str
    high: str
    bars: int
    level: Literal["sub1", "sub2", "sub3"]
    label: str


class NextScenarioSchema(BaseModel):
    key: str
    label: str
    condition: str
    implication: str
    active: bool
    children: list["NextScenarioSchema"] = []


class ClassificationSchema(BaseModel):
    position: Literal["above", "inside", "below", "unknown"]
    zhongshu_high: Optional[str] = None
    zhongshu_low: Optional[str] = None
    last_close: Optional[str] = None
    scenarios: list[NextScenarioSchema] = []


class ChanAnalysisResponse(BaseModel):
    symbol: str
    timeframe: str
    bis: list[BiSchema]
    duans: list[DuanSchema]
    zhongshus: list[ZhongshuSchema]              # 笔中枢(level="bi")
    duan_zhongshus: list[ZhongshuSchema]         # 段中枢(level="duan")
    buy_sell_points: list[BuySellPointSchema]
    divergences: list[DivergenceSchema]
    overlaps: list[KlineOverlapSchema] = []      # K 线重叠级别(只读标注)
    classification: Optional[ClassificationSchema] = None  # 走势完全分类(只读)
    updated_at: int
    cached: bool
