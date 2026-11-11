"""Analyze entry-level countermeasures against the accepted 0DTE rule."""

from collections import defaultdict
from datetime import datetime
import math


def replay_accepted_pnl(row):
    """Replay the frozen economics gate and one-shot 15-minute loss cut."""
    entry = row["entry"]
    if float(entry["estimated_roundtrip_friction"]) > 0.10:
        return None

    checkpoint = row["checkpoints"].get(15)
    if checkpoint and (
        float(checkpoint["option_return"]) <= -0.40
        and float(checkpoint["underlying_return"]) < 0
    ):
        return round(
            float(checkpoint["option_return"])
            * float(entry["entry_price"])
            * 100
            * int(entry["quantity"])
            - float(row["fees"]),
            2,
        )
    return float(row["net_pnl"])


def _summary(values):
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    return {
        "trades": len(values),
        "wins": sum(value > 0 for value in values),
        "win_rate": round(sum(value > 0 for value in values) / len(values), 4),
        "net_pnl": round(sum(values), 2),
        "profit_factor": round(gains / losses, 3) if losses else math.inf,
    }


def summarize_by(rows, key):
    groups = defaultdict(list)
    for row in rows:
        pnl = replay_accepted_pnl(row)
        if pnl is not None:
            groups[key(row)].append(pnl)
    return {name: _summary(values) for name, values in sorted(groups.items())}


def entry_hour(row):
    return datetime.fromisoformat(row["entry"]["time"]).hour
