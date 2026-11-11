"""Join 0DTE TRACE records to closed trades and evaluate a frozen causal rule."""

from collections import defaultdict
from pathlib import Path
import argparse
import json
import math


def join_traces_to_trades(trace_records, closed_trades):
    entries = defaultdict(list)
    checkpoints = defaultdict(dict)
    for record in trace_records:
        if record.get("type") == "entry":
            entries[record["ticker"]].append(record)
        elif record.get("type") == "checkpoint":
            key = (record["ticker"], record["entry_time"])
            checkpoints[key][int(record["checkpoint"])] = record

    trades = defaultdict(list)
    for trade in closed_trades:
        ticker = trade["symbols"][0]["underlying"]["value"]
        trades[ticker].append(trade)

    rows = []
    for ticker, ticker_entries in entries.items():
        ticker_entries.sort(key=lambda item: item["time"])
        ticker_trades = sorted(trades[ticker], key=lambda item: item["entryTime"])
        if len(ticker_entries) != len(ticker_trades):
            raise ValueError(
                f"Trace/trade count mismatch for {ticker}: "
                f"{len(ticker_entries)} != {len(ticker_trades)}"
            )
        for entry, trade in zip(ticker_entries, ticker_trades):
            rows.append({
                "ticker": ticker,
                "entry": entry,
                "trade": trade,
                "fees": float(trade["totalFees"]),
                "net_pnl": float(trade["profitLoss"]) - float(trade["totalFees"]),
                "checkpoints": checkpoints[(ticker, entry["time"])],
            })
    return rows


def _summarize(values, cuts=0, skipped=0):
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    losing_values = [value for value in values if value < 0]
    return {
        "trades": len(values),
        "wins": sum(value > 0 for value in values),
        "losses": len(losing_values),
        "cuts": cuts,
        "skipped": skipped,
        "net_pnl": round(sum(values), 2),
        "profit_factor": round(gains / losses, 3) if losses else math.inf,
        "average_loss": round(sum(losing_values) / len(losing_values), 2)
        if losing_values else 0.0,
    }


def evaluate_control(rows):
    return _summarize([row["net_pnl"] for row in rows])


def evaluate_rule(rows, take_profit=0.05, checkpoint=15, apply_failure=True):
    """Apply the cost gate and causal underlying invalidation rule."""
    values = []
    cuts = 0
    skipped = 0
    for row in rows:
        entry = row["entry"]
        if float(entry["estimated_roundtrip_friction"]) > take_profit:
            skipped += 1
            continue

        pnl = row["net_pnl"]
        snapshot = row["checkpoints"].get(checkpoint)
        invalidated = snapshot and (
            float(snapshot["level_margin"]) <= 0
            or float(snapshot["invalidation_margin"]) <= 0
        )
        if apply_failure and snapshot and float(snapshot["option_return"]) < 0 and invalidated:
            pnl = (
                float(snapshot["option_return"])
                * float(entry["entry_price"])
                * 100
                * int(entry["quantity"])
                - row["fees"]
            )
            cuts += 1
        values.append(pnl)
    return _summarize(values, cuts=cuts, skipped=skipped)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", action="append", required=True)
    parser.add_argument("--raw", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if len(args.trace) != len(args.raw):
        parser.error("Each --trace file requires one --raw file")

    rows = []
    for trace_path, raw_path in zip(args.trace, args.raw):
        traces = json.loads(Path(trace_path).read_text(encoding="utf-8"))
        payload = json.loads(Path(raw_path).read_text(encoding="utf-8"))
        closed = payload["backtest"]["totalPerformance"]["closedTrades"]
        rows.extend(join_traces_to_trades(traces, closed))

    control = evaluate_control(rows)
    economics = evaluate_rule(rows, apply_failure=False)
    frozen = evaluate_rule(rows, apply_failure=True)
    control_wins = control["wins"]
    result = {
        "rule": {
            "economics_gate": "estimated_roundtrip_friction <= take_profit",
            "checkpoint_minutes": 15,
            "failure_condition": "option_return < 0 and (level_margin <= 0 or invalidation_margin <= 0)",
        },
        "control": control,
        "economics_gate_only": economics,
        "frozen_rule": frozen,
        "winner_retention": round(frozen["wins"] / control_wins, 4)
        if control_wins else 0.0,
        "go": frozen["profit_factor"] > 1 and frozen["net_pnl"] > 0,
    }
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
