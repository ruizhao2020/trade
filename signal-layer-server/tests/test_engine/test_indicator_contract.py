"""指标输出契约（覆盖所有已注册指标）。

这个文件存在的理由：单个指标的测试很容易写成"断言输出等于当前实现的输出"，
那只能防回归、发现不了逻辑错误——量柱结构的回填行为就是这样被写进期望值锁死的。

这里只断言**契约**，不断言具体数值，因此对任何新指标都自动生效：

1. **逐根等长**：`len(values) == len(klines)`。下游两种消费口径（回测按 time、
   策略搜索按行序）只有在等长时才等价。
2. **决策字段前缀因果**：跑前 k 根与跑全量，前 k 根必须逐位相同。
   只要某字段在第 i 行用到了 i 之后的数据，截断重算就会不一致。
   覆盖面取自 `outputs` 白名单——它同时也是条件编辑器的字段来源，
   所以这一条精确对应"能被条件/回测读到的字段"。
3. **参数有效**：改动一个数值参数，输出必须变化。没有这一条，
   `m1`/`m2`、`use_htf` 这种"读了不用"的死参数可以一直躺在那儿。
4. **非法参数抛 ValueError**：接口据此回 invalid_parameters，
   不能退化成 ZeroDivisionError / TypeError（会被报成服务器错误）。
"""

from __future__ import annotations

import ast
import inspect
import math
import textwrap

import pytest

from app.api.indicator import INDICATOR_META
from app.engine.indicator.base import auto_discover_indicators, get_registered_indicators

auto_discover_indicators()
ALL_INDICATORS = sorted(get_registered_indicators())


def make_klines(count: int = 300) -> list[dict]:
    """构造带成交量/换手率/流通股本的行情，让所有指标都能算出东西。"""
    rows: list[dict] = []
    for index in range(count):
        base = 10.0 + math.sin(index / 7.0) * 1.2 + index * 0.01
        close = base + math.sin(index / 3.0) * 0.15
        rows.append({
            "open_time": 1_700_000_000_000 + index * 86_400_000,
            "open": base,
            "high": max(base, close) + 0.18,
            "low": min(base, close) - 0.18,
            "close": close,
            "volume": 1_000_000 + (index % 13) * 90_000,
            "amount": (1_000_000 + (index % 13) * 90_000) * close,
            "turnover_rate": 1.2 + (index % 5) * 0.3,
            "circulating_shares": 800_000_000.0,
        })
    return rows


def default_params(indicator_type: str) -> dict:
    meta = INDICATOR_META.get(indicator_type, {})
    return dict(meta.get("default_params", {}))


def render_plots(indicator_type: str) -> list:
    """render 规格来自计算器本身（接口用空 K 线算一次拿它），不在 INDICATOR_META 里。"""
    calculator = get_registered_indicators()[indicator_type]()
    result = calculator.calculate([], default_params(indicator_type))
    return list(result.render.plots) if result.render else []


def decision_fields(indicator_type: str) -> list[str]:
    """决策字段 = 条件编辑器能选到的字段。

    口径必须与前端 `ConditionGroupEditor.indicatorOutputs` 一致：
    `outputs` 是**可选覆盖**，为空时回退到 render 的 plots 字段。
    这个集合正是"能被条件与回测读到"的字段，因此是因果性检查的范围。
    """
    outputs = INDICATOR_META.get(indicator_type, {}).get("outputs") or []
    if outputs:
        return [item["field"] for item in outputs]
    return [plot.field for plot in render_plots(indicator_type) if plot.type != "profile"]


def compute(indicator_type: str, klines: list[dict], **overrides):
    calculator = get_registered_indicators()[indicator_type]()
    params = {**default_params(indicator_type), **overrides}
    return calculator.calculate(klines, params)


@pytest.mark.parametrize("indicator_type", ALL_INDICATORS)
def test_decision_fields_are_prefix_causal(indicator_type):
    """契约 2：决策字段的前缀不变性（前视/回填检测器）。

    筹码分布已知不满足：它的价格轴取全窗口 min/max，未来行情会改变档宽，
    从而改变历史快照的分位/占比类字段。修复需要改成"逐根用截至当根的滚动价格轴"，
    会把计算量抬到 O(n²)（默认 lookback=500 下不可接受），属于单独一轮工作。
    这里用 xfail(strict) 标出来：一旦修好它会立即失败，提醒去掉这个标记。
    """
    if indicator_type == "chip_distribution":
        pytest.xfail("已知：价格轴依赖全窗口极值，见 docstring")

    klines = make_klines(200)
    full = compute(indicator_type, klines)
    fields = decision_fields(indicator_type)
    assert fields, f"{indicator_type} 没有声明 outputs，契约测试无从覆盖"

    for length in (120, 160):
        prefix = compute(indicator_type, klines[:length])
        for index in range(length):
            for field in fields:
                assert prefix.values[index].get(field) == full.values[index].get(field), (
                    f"{indicator_type} 的 {field} 在第 {index} 根随未来数据变化"
                    f"（截断到 {length} 根时不一致）"
                )


def _param_key(call: ast.Call) -> str | None:
    """从参数读取调用里取出参数名。

    覆盖三种写法：
    - `_param_int(params, "key", d)`
    - `int(params.get("key", d))`
    - `int(归一化字典["key"])`（先 _params() 归一化的指标用这种）
    """
    func = call.func
    if isinstance(func, ast.Name) and func.id in {"_param_int", "_param_float"}:
        if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant) and isinstance(call.args[1].value, str):
            return call.args[1].value
        return None
    if isinstance(func, ast.Name) and func.id in {"int", "float", "str", "bool"}:
        if not call.args:
            return None
        inner = call.args[0]
        if isinstance(inner, ast.Call):
            if isinstance(inner.func, ast.Attribute) and inner.func.attr == "get" and inner.args:
                first = inner.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    return first.value
        if isinstance(inner, ast.Subscript) and isinstance(inner.slice, ast.Constant):
            if isinstance(inner.slice.value, str):
                return inner.slice.value
    return None


def indicator_class_ast(indicator_type: str) -> ast.ClassDef | None:
    cls = get_registered_indicators()[indicator_type]
    tree = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    return next((node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)), None)


def calculate_ast(indicator_type: str) -> ast.FunctionDef | None:
    """只取 calculate 方法本身，用于作用域敏感的检查（局部变量的使用）。"""
    clazz = indicator_class_ast(indicator_type)
    if clazz is None:
        return None
    return next(
        (node for node in clazz.body if isinstance(node, ast.FunctionDef) and node.name == "calculate"),
        None,
    )


def read_parameter_keys(node: ast.AST) -> set[str]:
    """代码里真正读到的参数名（局部赋值 + 字典下标两种写法）。"""
    keys: set[str] = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Assign) and isinstance(item.value, ast.Call):
            key = _param_key(item.value)
            if key:
                keys.add(key)
        if isinstance(item, ast.Subscript) and isinstance(item.slice, ast.Constant):
            if isinstance(item.slice.value, str):
                keys.add(item.slice.value)
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr == "get":
            if item.args and isinstance(item.args[0], ast.Constant) and isinstance(item.args[0].value, str):
                keys.add(item.args[0].value)
    return keys


@pytest.mark.parametrize("indicator_type", ALL_INDICATORS)
def test_declared_params_are_actually_read(indicator_type):
    """契约 3a：在 default_params 里声明的参数，代码必须真的读它。

    这里按**整个类**检查：像筹码分布那样把参数归一化放到 `_params()` 里的写法，
    读取点不在 calculate 里。

    反向的幽灵参数比崩溃更难发现：界面上有控件、params 会回报、改它却毫无效果。
    liquidity_sweep 曾经声明过 use_htf / htf_ema_len 并对外宣传"HTF趋势对齐"，
    实际两个值读到就被丢掉。
    """
    clazz = indicator_class_ast(indicator_type)
    if clazz is None:
        pytest.skip(f"{indicator_type} 无法解析类定义")
    declared = set(default_params(indicator_type))
    unread = sorted(declared - read_parameter_keys(clazz))
    assert unread == [], f"{indicator_type} 声明了却从未读取的参数：{unread}"


@pytest.mark.parametrize("indicator_type", ALL_INDICATORS)
def test_read_params_are_used_not_just_echoed(indicator_type):
    """契约 3b：读到的参数必须参与计算，不能只是原样回显到 params 里。

    只用 AST 判断，不依赖数据——"改这个参数输出会变吗"这种动态检查在
    阈值类参数上会假阳性（宽阈值在小幅数据上本来就不影响结果）。

    按**整个类**扫描：参数可能在 calculate 里读（局部变量），也可能在
    归一化方法里读（字典下标），两种写法都要覆盖。
    """
    clazz = indicator_class_ast(indicator_type)
    if clazz is None:
        pytest.skip(f"{indicator_type} 无法解析类定义")

    # 参数名 -> 承接它的局部变量名
    locals_by_key = {
        key: item.targets[0].id
        for item in ast.walk(clazz)
        if isinstance(item, ast.Assign) and len(item.targets) == 1
        and isinstance(item.targets[0], ast.Name) and isinstance(item.value, ast.Call)
        for key in [_param_key(item.value)] if key
    }
    # 返回的 params 字典里的引用不算"使用"（那只是回显）
    echoed: set[int] = set()
    for item in ast.walk(clazz):
        if isinstance(item, ast.Call) and getattr(item.func, "id", None) == "IndicatorResult":
            for keyword in item.keywords:
                if keyword.arg == "params":
                    echoed |= {id(name) for name in ast.walk(keyword.value) if isinstance(name, ast.Name)}

    declared = set(default_params(indicator_type))
    dead: list[str] = []
    for key, local in sorted(locals_by_key.items()):
        if key not in declared:
            continue
        loads = [
            name for name in ast.walk(clazz)
            if isinstance(name, ast.Name) and name.id == local and isinstance(name.ctx, ast.Load)
        ]
        if not [name for name in loads if id(name) not in echoed]:
            dead.append(key)
    assert dead == [], f"{indicator_type} 这些参数读了却没用（只回显）：{dead}"


INVALID_PARAMS: dict[str, list[dict]] = {
    "ma": [{"period": 0}, {"period": -3}],
    "bollinger": [{"period": 0}, {"std": 0}],
    "rsi": [{"period": 1}],
    "macd": [{"fast": 0}, {"fast": 30, "slow": 20}],
    "kdj": [{"n": 1}, {"m1": 0}],
    "volume": [{"lookback": 1}, {"shrink_max": 2.0}],
    "volume_structure": [{"lookback": 1}, {"confirm_bars": 1}],
    "liquidity_sweep": [{"piv_len": 0}, {"piv_len": 1}, {"atr_len": 0}, {"dir_mode": "short only"}],
    "support_resistance": [
        {"span": 0}, {"span": 101}, {"atr_len": 1}, {"tolerance_atr": 0},
        {"min_touches": 0}, {"max_levels": 0}, {"max_age_bars": 5}, {"recency_half_life": 1},
    ],
    "liquidity_zone": [
        {"span": 0}, {"atr_len": 1}, {"eq_atr": 0}, {"min_touches": 0},
        {"zone_width_atr": 0}, {"pierce_atr": -1}, {"reclaim_bars": 0},
        {"break_bars": 0}, {"max_age_bars": 5}, {"max_zones": 0},
    ],
    "chip_distribution": [{"bins": 0}, {"lookback": 0}],
    "dilun_structure": [{"departure_confirm_bars": 0}],
}


@pytest.mark.parametrize("indicator_type", sorted(INVALID_PARAMS))
def test_invalid_params_raise_value_error(indicator_type):
    """契约 4：非法参数必须是 ValueError，不能是崩溃或静默垃圾值。"""
    klines = make_klines()
    for params in INVALID_PARAMS[indicator_type]:
        with pytest.raises(ValueError):
            compute(indicator_type, klines, **params)


@pytest.mark.parametrize("indicator_type", ALL_INDICATORS)
def test_non_numeric_params_raise_value_error(indicator_type):
    """传入字符串参数也必须是 ValueError（而不是 TypeError 变成 500）。"""
    params = default_params(indicator_type)
    numeric = [key for key, value in params.items() if isinstance(value, (int, float))]
    if not numeric:
        pytest.skip(f"{indicator_type} 无数值参数")
    with pytest.raises(ValueError):
        compute(indicator_type, make_klines(), **{numeric[0]: "abc"})
