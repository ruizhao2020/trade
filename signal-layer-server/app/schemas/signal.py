from typing import Literal, Optional, Union, Annotated
from pydantic import AliasChoices, BaseModel, Field, Discriminator


# ============================================================
# Trade Parameters
# ============================================================

class TradeParams(BaseModel):
    # 止损
    stop_loss_type: Literal["atr", "fixed_pct", "swing_low"] = "atr"
    stop_loss_value: float = 2.0
    # 止盈
    take_profit_type: Literal["atr", "fixed_pct", "rr_ratio"] = "rr_ratio"
    take_profit_value: float = 2.0
    # 仓位
    position_type: Literal["fixed_pct", "kelly"] = "fixed_pct"
    position_value: float = 20.0
    # 条件式出场（复用条件组结构，引用指标/价格/缠论做判断）
    exit_conditions: list["ConditionGroupSchema"] = Field(default_factory=list)
    exit_logic: Literal["AND", "OR"] = "AND"


# ============================================================
# Condition value types
# ============================================================

class PriceValue(BaseModel):
    source: Literal["price"]
    field: Literal["open", "high", "low", "close", "volume"]


class IndicatorValue(BaseModel):
    source: Literal["indicator"]
    indicator_type: str
    params: dict[str, float] = Field(default_factory=dict)
    field: str = "value"


class ChanValue(BaseModel):
    source: Literal["chan"]
    element: Literal["fenxing", "bi", "zhongshu", "divergence", "buySellPoint"]
    property: Optional[str] = None


class ConstantValue(BaseModel):
    source: Literal["constant"]
    value: float


class TimeframeValue(BaseModel):
    source: Literal["timeframe"]
    timeframe_id: str
    inner: "ConditionValueUnion"


ConditionValueUnion = Union[
    PriceValue, IndicatorValue, ChanValue, ConstantValue, TimeframeValue
]


class ConditionSchema(BaseModel):
    id: str
    name: str
    left: ConditionValueUnion = Field(discriminator="source")
    operator: Literal[
        "gt", "gte", "lt", "lte", "eq", "crossAbove", "crossBelow",
        "rising", "falling", "turnDown", "turnUp", "between"
    ]
    right: ConditionValueUnion = Field(discriminator="source")
    right2: Optional[ConditionValueUnion] = Field(
        default=None,
        validation_alias=AliasChoices("right2", "right_2"),
    )
    timeframe_id: Optional[str] = None
    enabled: bool = True


class ConditionGroupSchema(BaseModel):
    id: str
    name: str = ""
    conditions: list[ConditionSchema]


class ConditionTemplateSchema(BaseModel):
    id: str
    name: str
    logic: Literal["AND", "OR"]
    condition_groups: list[ConditionGroupSchema]
    primary_tf: str = "15m"
    secondary_tfs: list[str] = Field(default_factory=list)
    enabled: bool = True
    trade_params: Optional[TradeParams] = None


class EvaluateRequest(BaseModel):
    symbol: str
    template: ConditionTemplateSchema


class ConditionEval(BaseModel):
    condition_id: str
    satisfied: bool
    left_value: float = 0.0
    right_value: float = 0.0
    diff_percent: float = 0.0


class GroupEval(BaseModel):
    group_id: str
    evaluations: list[ConditionEval]
    satisfied: bool


class SignalResult(BaseModel):
    template_id: str
    state: Literal["evaluating", "partial", "ready"]
    groups: list[GroupEval]
    is_ready: bool
    progress_percent: int


class BacktestRequest(BaseModel):
    symbol: str
    template: ConditionTemplateSchema
    kline_limit: int = Field(default=500, ge=50, le=2000)


class TradeRecord(BaseModel):
    entry_time: int
    exit_time: int
    side: str
    entry_price: float
    exit_price: float
    pnl_pct: float
    exit_reason: str


class BacktestResult(BaseModel):
    template_id: str
    symbol: str
    timeframe: str
    total_trades: int
    win_trades: int
    win_rate: float
    total_return: float
    avg_return: float
    max_drawdown: float
    profit_factor: float
    trades: list[TradeRecord]
