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
- _sma / _ema: 简单移动平均 / 指数移动平均
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


class RenderSpec(BaseModel):
    """指标渲染规格 - 前端据此自动绘制,无需硬编码"""
    window: str = "main"                   # main=主图叠加, sub=子图独立
    plots: list[PlotSpec] = []             # 每条线/柱的定义
    markers: list[MarkerSpec] = []         # 信号标记(可选)


class IndicatorResult(BaseModel):
    """指标计算结果标准结构"""
    type: str                              # 指标类型,如 "ma" / "macd"
    params: dict[str, Any]                 # 本次计算使用的参数
    values: list[dict[str, float]]         # 每根 K 线对应的指标值(含 time 字段)
    render: Optional[RenderSpec] = None    # 渲染提示(前端据此画图)


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


def _sma(values: list[float], period: int) -> list[float]:
    """简单移动平均。period-1 之前的位置用原值填充(避免 NaN)"""
    result: list[float] = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(values[i])
            continue
        result.append(sum(values[i - period + 1:i + 1]) / period)
    return result


def _ema(values: list[float], period: int) -> list[float]:
    """指数移动平均"""
    if not values:
        return []
    multiplier = 2.0 / (period + 1)
    result: list[float] = [values[0]]
    for i in range(1, len(values)):
        result.append((values[i] - result[-1]) * multiplier + result[-1])
    return result
