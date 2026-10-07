"""策略建议的判定校准。

回答的是「方法本身对不对」，而不是「代码对不对」：
  - 结论分布：推荐 / 无稳定优势 / 数据不足各占多少；
  - 阈值相关指标：参数平台通过率、平台稳定且样本外为正的比例；
  - 稳定性：搬动选定期/留出期的切分点，同一标的的结论是否一致
    （对切分点敏感 = 方法不稳）。

用法：
    python scripts/advisor_calibration.py                       # 默认标的与切分点
    python scripts/advisor_calibration.py --symbols V0,RB0 --ratios 0.6,0.7,0.8
    python scripts/advisor_calibration.py --out /tmp/calib.json

注意：这是抽样读数，不是统计检验。默认 10 个标的只够看出"推荐率是不是离谱"
这一档的问题；要定阈值应当扩大标的数量后重复运行。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cache.indicator_cache import IndicatorCache
from app.engine.advisor.scoring import Constraints
from app.services.advisor_service import AdvisorService
from app.services.backtest_service import BacktestService
from app.services.chan_service import ChanService
from app.services.condition_service import ConditionService
from app.services.data_service import DataService
from app.services.indicator_service import IndicatorService

DEFAULT_SYMBOLS = [
    "V0", "RB0", "I0", "M0", "P0", "TA0", "SR0", "CF0",   # 期货
    "000001_sz", "600519_sh",                               # 股票
]
DEFAULT_RATIOS = [0.6, 0.7, 0.8]


def build_service() -> AdvisorService:
    cache = IndicatorCache(None)
    indicator = IndicatorService(cache)
    return AdvisorService(
        DataService(),
        ChanService(cache),
        indicator,
        BacktestService(ConditionService(indicator)),
    )


def summarize(symbol: str, ratio: float, result: dict) -> dict:
    passed = result.get("results") or []
    stable = [item for item in passed if item.plateau_stable]
    stable_positive = [item for item in stable if item.out_of_sample.total_return > 0]
    best = stable[0] if stable else (passed[0] if passed else None)
    return {
        "symbol": symbol,
        "ratio": ratio,
        "verdict": result.get("verdict"),
        "evaluated": result.get("evaluated_count") or 0,
        "passed": len(passed),
        "plateau_stable": len(stable),
        "plateau_and_positive": len(stable_positive),
        "top_score": round(best.score, 4) if best else None,
        "top_description": best.candidate.describe() if best else None,
        "top_holdout_return": round(best.out_of_sample.total_return, 2) if best else None,
        "top_in_sample_return": round(best.in_sample.total_return, 2) if best else None,
        "profile": result.get("profile"),
    }


async def calibrate(symbols: list[str], ratios: list[float], budget: int, limit: int, constraints: Constraints):
    service = build_service()
    rows: list[dict] = []
    for symbol in symbols:
        for ratio in ratios:
            try:
                result = await service.analyze(
                    symbol, constraints=constraints, selection_ratio=ratio,
                    budget=budget, limit=limit,
                )
            except Exception as error:  # 单个标的失败不影响整批
                rows.append({"symbol": symbol, "ratio": ratio, "verdict": f"运行失败：{error}"})
                print(f"  ! {symbol} @{ratio}: {error}", flush=True)
                continue
            row = summarize(symbol, ratio, result)
            rows.append(row)
            print(
                f"  {symbol:<12} @{ratio}  结论={row['verdict']:<6} "
                f"通过={row['passed']:<4} 平台稳={row['plateau_stable']:<4} "
                f"平台且样本外为正={row['plateau_and_positive']:<3} "
                f"最高分={row['top_score']}",
                flush=True,
            )
    return rows


def report(rows: list[dict], ratios: list[float]) -> None:
    ok = [row for row in rows if row.get("verdict") in {"推荐", "无稳定优势", "数据不足"}]
    print("\n" + "=" * 72)
    print("结论分布（按切分点）")
    for ratio in ratios:
        subset = [row for row in ok if row["ratio"] == ratio]
        if not subset:
            continue
        counts = Counter(row["verdict"] for row in subset)
        detail = "  ".join(f"{name} {counts[name]}" for name in ("推荐", "无稳定优势", "数据不足") if counts[name])
        rate = counts["推荐"] / len(subset) * 100
        print(f"  切分点 {ratio}: 推荐率 {rate:>5.1f}%   {detail}")

    print("\n阈值相关指标（全部切分点合并）")
    passed_total = sum(row.get("passed") or 0 for row in ok)
    stable_total = sum(row.get("plateau_stable") or 0 for row in ok)
    positive_total = sum(row.get("plateau_and_positive") or 0 for row in ok)
    if passed_total:
        print(f"  通过约束候选合计 {passed_total}，其中参数平台稳定 {stable_total}"
              f"（{stable_total / passed_total * 100:.1f}%）")
        print(f"  平台稳定且样本外为正 {positive_total}"
              f"（占稳定候选 {positive_total / stable_total * 100:.1f}%）"
              if stable_total else "  平台稳定候选为 0，无法计算样本外为正比例")
    else:
        print("  没有任何候选通过约束——先看约束是否过严或数据是否够")

    if "推荐" in {row.get("verdict") for row in ok}:
        print("\n（出现「推荐」的样本）")
        for row in ok:
            if row.get("verdict") == "推荐":
                print(f"  {row['symbol']} @{row['ratio']}: {row['top_description']}"
                      f" | 选定期 {row['top_in_sample_return']}% / 留出 {row['top_holdout_return']}%")

    print("\n稳定性（同一标的不同切分点结论是否一致）")
    by_symbol: dict[str, list[dict]] = {}
    for row in ok:
        by_symbol.setdefault(row["symbol"], []).append(row)
    consistent = 0
    for symbol, items in by_symbol.items():
        verdicts = {item["verdict"] for item in items}
        if len(verdicts) == 1:
            consistent += 1
        else:
            detail = "、".join(f"{item['ratio']}→{item['verdict']}" for item in sorted(items, key=lambda x: x["ratio"]))
            print(f"  结论随切分点变化: {symbol}  {detail}")
    print(f"  一致 {consistent}/{len(by_symbol)} 个标的")

    profiles = [(row["symbol"], row["profile"]) for row in ok if row.get("profile") and row["ratio"] == ratios[len(ratios) // 2]]
    if profiles:
        print("\n标的画像（默认切分点）")
        for symbol, profile in profiles:
            chan = profile.get("chan") or {}
            print(f"  {symbol:<12} 效率比={profile['efficiency_ratio']:<6} "
                  f"ATR%={profile['atr_pct']:<6} 缠论={chan.get('verdict')} "
                  f"重绘率={chan.get('redraw_rate')} 买卖点={chan.get('point_count')}")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="策略建议判定校准")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--ratios", default=",".join(str(item) for item in DEFAULT_RATIOS))
    parser.add_argument("--budget", type=int, default=1500)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--min-trades", type=int, default=10)
    parser.add_argument("--min-win-rate", type=float, default=35.0)
    parser.add_argument("--max-frequency", type=float, default=1.0)
    parser.add_argument("--min-oos-trades", type=int, default=5)
    parser.add_argument("--out", default=None, help="把明细写入 JSON 文件")
    args = parser.parse_args()

    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    ratios = [float(item) for item in args.ratios.split(",") if item.strip()]
    constraints = Constraints(
        min_trades=args.min_trades,
        min_win_rate=args.min_win_rate,
        max_frequency=args.max_frequency,
        min_out_of_sample_trades=args.min_oos_trades,
    )

    print(f"标的 {len(symbols)} 个 × 切分点 {len(ratios)} 个，预算 {args.budget}")
    print(f"约束：{constraints.describe()}\n")
    rows = asyncio.run(calibrate(symbols, ratios, args.budget, args.limit, constraints))
    report(rows, ratios)

    if args.out:
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n明细已写入 {args.out}")


if __name__ == "__main__":
    main()
