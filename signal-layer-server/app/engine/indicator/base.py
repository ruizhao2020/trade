"""
============================================================================
指标计算基类与注册中心
============================================================================

## 功能
- IndicatorCalculator: 所有指标计算器的抽象基类
- IndicatorResult: 指标计算结果的标准结构
- registry: 全局指标注册中心(自动发现 + 装饰器注册)

## 新增指标的标准流程(3 步)
1. 在 app/engine/indicator/ 下新建文件,如 my_ind.py
2. 继承 IndicatorCalculator,实现 type 属性和 calculate() 方法
3. 用 @register_indicator 装饰类:

    from app.engine.indicator.base import IndicatorCalculator, IndicatorResult, register_indicator

    @register_indicator
    class MyIndCalculator(IndicatorCalculator):
        @property
        def type(self) -> str:
            return "my_ind"

        def calculate(self, klines, params):
            ...
            return IndicatorResult(type=self.type, params=..., values=...)

IndicatorService 启动时会自动 import 本目录所有 .py 文件,触发注册。
无需修改 IndicatorService 的 _registry 字典。

## 工具函数
- _get_closes / _get_highs / _get_lows / _get_times: 从 K 线提取价格序列
- _sma / _ema / _rma: 简单移动平均 / 指数移动平均 / Wilder 平滑
- _param_int / _param_float: 读取并校验参数(非法值抛 ValueError)

## 输出契约(所有指标必须遵守)

1. **长度对齐**: `len(values) == len(klines)`，逐根一一对应，一个不能多、一个不能少。
   数据整体不足时也要返回等长的行，字段填 None，**不要返回空列表**——
   下游有两条消费路径：回测按 `time` 截断取值，策略搜索(advisor)按**行序**拼序列。
   只要长度对齐，两条路径等价；长度不齐会让 advisor 整体错位。

2. **预热期填 None**: 样本不足的字段必须是 None，不能填 0、不能填首值、不能填周期默认值
   (如 KDJ 的 50)。伪值会被条件判断当成"真实读数"，直接产生假信号。

3. **因果性**: 第 i 行的值只能依赖 0..i 根的数据，不得回填历史下标。
   图表需要"画在更早的位置"时，不要在 `values` 里回填——回填出来的字段
   同样会被条件与回测读到，形成前视。

4. **参数校验**: 非法参数抛 ValueError(接口会转成 invalid_parameters 错误项)，
   不要让它退化成 ZeroDivisionError / 静默垃圾值。
"""

from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any, Optional, Type
import importlib
import pkgutil


# ========================================================================
# 全局指标注册中心
# ========================================================================
# key = 指标 type 字符串(如 "ma", "macd"), value = 计算器类
# 新增指标通过 @register_indicator 装饰器自动加入此字典
_REGISTRY: dict[str, Type["IndicatorCalculator"]] = {}


def register_indicator(cls: Type["IndicatorCalculator"]) -> Type["IndicatorCalculator"]:
    """
    指标计算器注册装饰器。

    用法:
        @register_indicator
        class MyIndCalculator(IndicatorCalculator):
            ...

    注册后,IndicatorService 会自动通过 get_registered_indicators() 发现并实例化。
    """
    indicator_type = cls().type
    if indicator_type in _REGISTRY:
        # 允许重新注册(便于热重载),记录到日志即可
        pass
    _REGISTRY[indicator_type] = cls
    return cls


def get_registered_indicators() -> dict[str, Type["IndicatorCalculator"]]:
    """返回所有已注册的指标计算器类"""
    return dict(_REGISTRY)


def auto_discover_indicators(package_name: str = "app.engine.indicator") -> None:
    """
    自动发现并导入指标模块,触发 @register_indicator 注册。

    IndicatorService 初始化时调用此函数,扫描指定包下所有 .py 文件。
    新增指标文件后无需任何代码改动,服务重启即生效。
    """
    package = importlib.import_module(package_name)
    for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
        if modname.startswith("_") or modname == "base":
            continue
        module_path = f"{package_name}.{modname}"
        try:
            importlib.import_module(module_path)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to import indicator module {module_path}: {e}"
            )


# ========================================================================
# 数据结构
# ========================================================================

class PlotSpec(BaseModel):
    """单条线的渲染规格"""
    field: str                             # 从 values 里取哪个字段(如 "value" / "dif")
    type: str = "line"                     # line | histogram | marker
    color: str = "#ffa726"                 # 线/柱颜色
    label: str = ""                        # 图例标签


class MarkerSpec(BaseModel):
    """信号标记的渲染规格(如 BUY/SELL 箭头)"""
    field: str = "signal"                  # 从 values 里取值,非零则为信号(>0=BUY, <0=SELL)
    buy_color: str = "#22c55e"             # 买入标记颜色
    sell_color: str = "#ef4444"            # 卖出标记颜色
    buy_label: str = "BUY"                 # 买入标签
    sell_label: str = "SELL"               # 卖出标签
    price_field: Optional[str] = None       # 使用指定字段精确定位
    label_index_field: Optional[str] = None # 标签编号字段
    label_tag_field: Optional[str] = None   # 标签附注代码字段
    label_tags: dict[int, str] = {}         # 附注代码与文字映射
    size: int = 2                           # 标记大小
    spacing: int = 0                        # 与 K 线的视觉间距


class RenderSpec(BaseModel):
    """指标渲染规格 - 前端据此自动绘制,无需硬编码"""
    window: str = "main"                   # main=主图叠加, sub=子图独立
    plots: list[PlotSpec] = []             # 每条线/柱的定义
    markers: list[MarkerSpec] = []         # 信号标记(可选)


class ProfileSnapshot(BaseModel):
    """某根 K 线结束时的价格分布快照。"""
    time: int
    weights: list[float]
    metrics: dict[str, float]


class ProfileData(BaseModel):
    """紧凑价格分布；所有快照共享同一价格轴。"""
    prices: list[float]
    snapshots: list[ProfileSnapshot]


class IndicatorResult(BaseModel):
    """指标计算结果标准结构"""
    type: str                              # 指标类型,如 "ma" / "macd"
    params: dict[str, Any]                 # 本次计算使用的参数
    values: list[dict[str, Any]]           # 每根 K 线对应的指标值(含 time)；样本不足的字段为 None
    render: Optional[RenderSpec] = None    # 渲染提示(前端据此画图)
    profile_data: Optional[ProfileData] = None


class IndicatorCalculator(ABC):
    """所有指标计算器的抽象基类"""

    @property
    @abstractmethod
    def type(self) -> str:
        """指标类型字符串,必须唯一,如 "ma" / "macd" """
        ...

    @abstractmethod
    def calculate(self, klines: list[dict], params: dict[str, Any]) -> IndicatorResult:
        """
        计算指标值。

        Args:
            klines: K 线数据列表,每根含 open_time/open/high/low/close/volume
            params: 指标参数,如 {"period": 5}

        Returns:
            IndicatorResult
        """
        ...


# ========================================================================
# 工具函数(供各指标计算器复用)
# ========================================================================

def _get_closes(klines: list[dict]) -> list[float]:
    return [float(k["close"]) for k in klines]


def _get_highs(klines: list[dict]) -> list[float]:
    return [float(k["high"]) for k in klines]


def _get_lows(klines: list[dict]) -> list[float]:
    return [float(k["low"]) for k in klines]


def _get_times(klines: list[dict]) -> list[int]:
    return [int(k["open_time"]) for k in klines]


def _sma(values: list[float], period: int) -> list[Optional[float]]:
    """简单移动平均。period-1 之前样本不足，返回 None 表示“暂无值”。

    不能拿原值填充：那会让长周期均线在预热期画出一条恰好等于收盘价的线，
    看起来像有效均线。None 会被前端渲染成断线（渲染层已过滤 null）。
    """
    if period <= 0:
        raise ValueError("均线周期必须大于0")
    result: list[Optional[float]] = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
            continue
        result.append(sum(values[i - period + 1:i + 1]) / period)
    return result


def _smooth(
    values: list[Optional[float]], period: int, multiplier: float,
) -> list[Optional[float]]:
    """指数平滑的共用骨架：以 SMA 播种，前 period-1 个有效位置返回 None。

    入参允许带前导 None（MACD 的 DEA 这类“均线的均线”上游会有空档）：
    从第一个非 None 值开始取满 period 个连续有效值做种子。
    种子窗口内有空档时整段无法播种，返回全 None。
    """
    if period <= 0:
        raise ValueError("周期必须大于0")
    result: list[Optional[float]] = [None] * len(values)
    head = next((index for index, value in enumerate(values) if value is not None), None)
    if head is None:
        return result
    seed_end = head + period
    if seed_end > len(values):
        return result
    window = values[head:seed_end]
    if any(value is None for value in window):
        return result
    result[seed_end - 1] = sum(window) / period
    for index in range(seed_end, len(values)):
        previous = result[index - 1]
        current = values[index]
        if current is None or previous is None:
            continue
        result[index] = (current - previous) * multiplier + previous
    return result


def _ema(values: list[Optional[float]], period: int) -> list[Optional[float]]:
    """指数移动平均。TA-Lib / Pine `ta.ema` 口径：SMA 播种 + 预热期 None。

    不要用首值播种：那会让第 0 根就输出一个“看起来有效”的值，
    把“算不出来”伪装成“算出来了”（MACD 的 DIF/DEA 会因此在前几十根由
    播种决定而非行情决定）。
    """
    return _smooth(values, period, 2.0 / (period + 1))


def _rma(values: list[Optional[float]], period: int) -> list[Optional[float]]:
    """Wilder 平滑(RMA)。alpha = 1/period，SMA 播种，预热期 None。

    ATR 与 RSI 用的是这个，不是 `_ema`：两者 alpha 不同(1/n vs 2/(n+1))，
    拿 EMA 代替 RMA 会让 ATR 的反应速度约为标准口径的 1.87 倍。
    """
    return _smooth(values, period, 1.0 / period)


def _param_int(params: dict[str, Any], key: str, default: int) -> int:
    """读整数参数。不可转换时抛 ValueError（避免 TypeError 变成 500）。"""
    raw = params.get(key, default)
    try:
        return int(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"参数 {key} 必须是整数，当前为 {raw!r}") from error


def _param_float(params: dict[str, Any], key: str, default: float) -> float:
    """读浮点参数。不可转换或非有限值时抛 ValueError。"""
    raw = params.get(key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"参数 {key} 必须是数字，当前为 {raw!r}") from error
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"参数 {key} 必须是有限数字，当前为 {raw!r}")
    return value
