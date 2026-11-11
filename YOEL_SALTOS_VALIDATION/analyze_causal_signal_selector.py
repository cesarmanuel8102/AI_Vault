"""Freeze a simple causal range-extension gate without using holdout years."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def pair_trace_records(records):
    entries = {
        (record["ticker"], record["time"]): record
        for record in records
        if record.get("type") == "entry"
    }
    exits = {
        (record["ticker"], record["entry_time"]): record
        for record in records
        if record.get("type") == "exit"
    }
    paired = []
    for key, entry in entries.items():
        exit_record = exits.get(key)
        if exit_record is None or "range_atr" not in entry:
            continue
        net_return = (
            float(exit_record["exit_price"]) / float(entry["entry_price"])
            - 1
            - float(entry["estimated_roundtrip_friction"])
        )
        paired.append({
            "year": int(entry["time"][:4]),
            "ticker": entry["ticker"],
            "range_atr": float(entry["range_atr"]),
            "net_return": round(net_return, 10),
            "reason": exit_record["reason"],
        })
    return sorted(paired, key=lambda row: (row["year"], row["ticker"]))


def summarize(rows):
    gains = sum(max(0.0, row["net_return"]) for row in rows)
    losses = -sum(min(0.0, row["net_return"]) for row in rows)
    return {
        "trades": len(rows),
        "wins": sum(row["net_return"] > 0 for row in rows),
        "win_rate": round(sum(row["net_return"] > 0 for row in rows) / len(rows), 4) if rows else 0.0,
        "net_return_units": round(sum(row["net_return"] for row in rows), 6),
        "profit_factor": round(gains / losses, 6) if losses else 999.0,
    }


def select_broadest_viable_profile(
    rows,
    *,
    range_atr_maxima=(1.25, 1.50, 1.75, 2.00, 2.25),
    minimum_training_trades=8,
    minimum_confirmation_trades=4,
):
    tested = []
    viable = []
    for maximum in range_atr_maxima:
        training_rows = [
            row for row in rows
            if row["year"] in (2022, 2023) and row["range_atr"] <= maximum
        ]
        confirmation_rows = [
            row for row in rows
            if row["year"] == 2024 and row["range_atr"] <= maximum
        ]
        profile = {
            "range_atr_max": float(maximum),
            "training": summarize(training_rows),
            "confirmation": summarize(confirmation_rows),
        }
        profile["viable"] = (
            profile["training"]["trades"] >= minimum_training_trades
            and profile["confirmation"]["trades"] >= minimum_confirmation_trades
            and profile["training"]["net_return_units"] > 0
            and profile["confirmation"]["net_return_units"] > 0
            and profile["training"]["profit_factor"] > 1
            and profile["confirmation"]["profit_factor"] > 1
        )
        tested.append(profile)
        if profile["viable"]:
            viable.append(profile)
    return {
        "selection_rule": "broadest viable range_atr_max",
        "training_years": [2022, 2023],
        "confirmation_year": 2024,
        "selected": max(viable, key=lambda profile: profile["range_atr_max"]) if viable else None,
        "tested_profiles": tested,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("trace")
    parser.add_argument("output")
    args = parser.parse_args()
    trace_path = Path(args.trace)
    records = json.loads(trace_path.read_text(encoding="utf-8"))
    result = select_broadest_viable_profile(pair_trace_records(records))
    result["source"] = trace_path.name
    result["source_sha256"] = hashlib.sha256(trace_path.read_bytes()).hexdigest()
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
