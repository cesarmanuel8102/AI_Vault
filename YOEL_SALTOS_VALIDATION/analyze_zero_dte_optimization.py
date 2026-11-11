"""Cost-aware selection and validation metrics for the preregistered 0DTE study."""

from collections import defaultdict
from pathlib import Path
import json
import math
import re


ROOT = Path(__file__).resolve().parent


def number(value):
    match = re.search(r"-?[\d,.]+", str(value))
    return float(match.group(0).replace(",", "")) if match else 0.0


def trade_metrics(trades):
    net_values = []
    semesters = defaultdict(float)
    for trade in trades:
        net = float(trade.get("profitLoss", 0)) - float(trade.get("totalFees", 0))
        net_values.append(net)
        exit_time = str(trade.get("exitTime", ""))
        year = exit_time[:4] or "UNKNOWN"
        month = int(exit_time[5:7]) if len(exit_time) >= 7 else 1
        semesters[f"{year}-H{1 if month <= 6 else 2}"] += net
    gains = sum(value for value in net_values if value > 0)
    losses = -sum(value for value in net_values if value < 0)
    profit_factor = gains / losses if losses else (math.inf if gains else 0.0)
    return {
        "trades": len(net_values),
        "net_pnl": sum(net_values),
        "expectancy": sum(net_values) / len(net_values) if net_values else 0.0,
        "profit_factor": profit_factor,
        "semester_net_pnl": dict(sorted(semesters.items())),
        "positive_semesters": sum(value > 0 for value in semesters.values()),
    }


def choose_candidate(summaries):
    return max(
        summaries,
        key=lambda name: (
            summaries[name]["profit_factor"],
            summaries[name]["expectancy"],
            -summaries[name]["drawdown_pct"],
            summaries[name]["positive_semesters"],
            name,
        ),
    )


def validation_verdict(candidate, control):
    if candidate["trades"] < 12:
        return "INSUFFICIENT"
    passed = (
        candidate["expectancy"] > 0
        and candidate["profit_factor"] > 1.0
        and candidate["return_pct"] > 0
        and candidate["drawdown_pct"] < control["drawdown_pct"]
    )
    return "GO" if passed else "NO-GO"


def summarize_raw(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    backtest = payload["backtest"]
    stats = backtest.get("statistics") or {}
    runtime = backtest.get("runtimeStatistics") or {}
    trades = (backtest.get("totalPerformance") or {}).get("closedTrades") or []
    result = trade_metrics(trades)
    result.update({
        "completed": bool(backtest.get("completed")),
        "error": backtest.get("error"),
        "return_pct": number(stats.get("Net Profit")),
        "drawdown_pct": number(stats.get("Drawdown")),
        "sharpe": number(stats.get("Sharpe Ratio")),
        "end_equity": number(stats.get("End Equity")),
        "fees": sum(float(trade.get("totalFees", 0)) for trade in trades),
        "entries": int(runtime.get("Entries", 0)),
        "closed": int(runtime.get("Closed", 0)),
        "target_exits": int(runtime.get("Target Exits", 0)),
        "failure_exits": int(runtime.get("Failure Exits", 0)),
        "time_exits": int(runtime.get("Time Exits", 0)),
        "entry_rejects": int(runtime.get("Entry Rejects", 0)),
        "close_rejects": int(runtime.get("Close Rejects", 0)),
        "flat": runtime.get("Holdings") == "$0.00",
    })
    return result


def main():
    manifest_path = ROOT / "zero_dte_optimization_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summaries = {}
    for name, variant in manifest["variants"].items():
        raw = variant.get("train_raw")
        if raw and (ROOT / raw).exists():
            summaries[name] = summarize_raw(ROOT / raw)
    if summaries:
        manifest["train_summaries"] = summaries
        manifest["selected_candidate"] = choose_candidate(summaries)
        control_raw = manifest["variants"]["control"].get("validation_raw")
        selected_raw = manifest["variants"][manifest["selected_candidate"]].get("validation_raw")
        if control_raw and selected_raw and (ROOT / control_raw).exists() and (ROOT / selected_raw).exists():
            validation = {
                "control": summarize_raw(ROOT / control_raw),
                "candidate": summarize_raw(ROOT / selected_raw),
            }
            validation["verdict"] = validation_verdict(validation["candidate"], validation["control"])
            manifest["validation"] = validation
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=True))


if __name__ == "__main__":
    main()
