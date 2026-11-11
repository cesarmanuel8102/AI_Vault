"""Consolidate the frozen ATM and OTM 0DTE backtests."""

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import json
import re
import statistics


ROOT = Path(__file__).resolve().parent
FILES = {
    "atm_tp35": "zero_dte_atm_raw.json",
    "otm_tp35": "zero_dte_otm_raw.json",
    "atm_tp5": "zero_dte_atm_tp5_raw.json",
    "otm_tp5": "zero_dte_otm_tp5_raw.json",
    "atm_tp5_hold25": "zero_dte_atm_tp5_hold25_raw.json",
    "otm_tp5_hold20": "zero_dte_otm_tp5_hold20_raw.json",
}


def number(value):
    match = re.search(r"-?[\d,.]+", str(value))
    return float(match.group(0).replace(",", "")) if match else 0.0


def summarize(filename):
    backtest = json.loads((ROOT / filename).read_text(encoding="utf-8"))["backtest"]
    stats = backtest.get("statistics") or {}
    runtime = backtest.get("runtimeStatistics") or {}
    trades = (backtest.get("totalPerformance") or {}).get("closedTrades") or []
    years = defaultdict(float)
    symbols = defaultdict(float)
    gross_pnl = fees = 0.0
    winner_minutes = []
    for trade in trades:
        pnl = float(trade.get("profitLoss", 0))
        fee = float(trade.get("totalFees", 0))
        net = pnl - fee
        symbol_data = (trade.get("symbols") or [{}])[0]
        symbol = (symbol_data.get("underlying") or {}).get("value")
        symbol = symbol or str(symbol_data.get("value", "UNKNOWN")).split()[0]
        symbol = "META" if symbol == "FB" else symbol
        years[str(trade.get("exitTime", ""))[:4]] += net
        symbols[symbol] += net
        gross_pnl += pnl
        fees += fee
        if pnl > 0:
            entry = datetime.fromisoformat(str(trade["entryTime"]).replace("Z", "+00:00"))
            exit_ = datetime.fromisoformat(str(trade["exitTime"]).replace("Z", "+00:00"))
            winner_minutes.append((exit_ - entry).total_seconds() / 60)
    entries = int(runtime.get("Entries", 0))
    closed = int(runtime.get("Closed", 0))
    return {
        "completed": bool(backtest.get("completed")),
        "error": backtest.get("error"),
        "return_pct": number(stats.get("Net Profit")),
        "cagr_pct": number(stats.get("Compounding Annual Return")),
        "drawdown_pct": number(stats.get("Drawdown")),
        "sharpe": number(stats.get("Sharpe Ratio")),
        "end_equity": number(stats.get("End Equity")),
        "gross_pnl_before_fees": round(gross_pnl, 2),
        "fees": round(fees, 2),
        "net_pnl": round(gross_pnl - fees, 2),
        "entries": entries,
        "closed": closed,
        "target_exits": int(runtime.get("Target Exits", 0)),
        "time_exits": int(runtime.get("Time Exits", 0)),
        "target_rate": round(int(runtime.get("Target Exits", 0)) / entries, 4) if entries else 0,
        "signals": int(runtime.get("Signals", 0)),
        "no_0dte_skips": int(runtime.get("No 0DTE Skips", 0)),
        "average_fee_per_round_trip": round(fees / entries, 2) if entries else 0,
        "average_net_pnl_per_trade": round((gross_pnl - fees) / entries, 2) if entries else 0,
        "winner_hold_minutes_mean": round(statistics.mean(winner_minutes), 2) if winner_minutes else None,
        "winner_hold_minutes_median": round(statistics.median(winner_minutes), 2) if winner_minutes else None,
        "by_year_net_pnl": dict(sorted((key, round(value, 2)) for key, value in years.items())),
        "by_symbol_net_pnl": dict(sorted((key, round(value, 2)) for key, value in symbols.items())),
        "runtime": runtime,
        "valid_flat_run": (
            bool(backtest.get("completed"))
            and not backtest.get("error")
            and runtime.get("Holdings") == "$0.00"
            and entries == closed
        ),
    }


def main():
    result = {name: summarize(filename) for name, filename in FILES.items()}
    (ROOT / "zero_dte_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
