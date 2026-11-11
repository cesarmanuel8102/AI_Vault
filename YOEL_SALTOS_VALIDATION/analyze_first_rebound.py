"""Consolidate the frozen first-rebound QuantConnect experiments."""

from collections import defaultdict
from pathlib import Path
import json
import re


ROOT = Path(__file__).resolve().parent
RUNS = {
    "stock": "first_rebound_stock_raw.json",
    "long_option": "first_rebound_long_option_raw.json",
    "debit_spread": "first_rebound_debit_spread_raw.json",
}


def number(value):
    match = re.search(r"-?[\d,.]+", str(value))
    return float(match.group(0).replace(",", "")) if match else 0.0


def summarize(filename):
    backtest = json.loads((ROOT / filename).read_text(encoding="utf-8"))["backtest"]
    statistics = backtest.get("statistics") or {}
    runtime = backtest.get("runtimeStatistics") or {}
    trades = (backtest.get("totalPerformance") or {}).get("closedTrades") or []
    by_year = defaultdict(float)
    by_symbol = defaultdict(float)
    gross_profit_by_symbol = defaultdict(float)
    gross_profit = gross_loss = trade_fees = 0.0

    for trade in trades:
        net = float(trade.get("profitLoss", 0)) - float(trade.get("totalFees", 0))
        year = str(trade.get("exitTime", ""))[:4]
        symbol_data = (trade.get("symbols") or [{}])[0]
        symbol = (symbol_data.get("underlying") or {}).get("value")
        symbol = symbol or str(symbol_data.get("value", "UNKNOWN")).split()[0]
        symbol = "META" if symbol == "FB" else symbol
        by_year[year] += net
        by_symbol[symbol] += net
        trade_fees += float(trade.get("totalFees", 0))
        if net > 0:
            gross_profit += net
            gross_profit_by_symbol[symbol] += net
        elif net < 0:
            gross_loss -= net

    positive_symbols = sum(value > 0 for value in by_symbol.values())
    top_gross = max(gross_profit_by_symbol.values(), default=0.0)
    summary = {
        "completed": bool(backtest.get("completed")),
        "error": backtest.get("error"),
        "return_pct": number(statistics.get("Net Profit")),
        "cagr_pct": number(statistics.get("Compounding Annual Return")),
        "drawdown_pct": number(statistics.get("Drawdown")),
        "sharpe": number(statistics.get("Sharpe Ratio")),
        "official_fees": number(statistics.get("Total Fees")),
        "end_equity": number(statistics.get("End Equity")),
        "runtime_holdings": runtime.get("Holdings"),
        "entries": int(runtime.get("Entries", 0)),
        "closed_positions": int(runtime.get("Closed", 0)),
        "closed_legs_or_trades": len(trades),
        "net_closed_trade_pnl": round(sum(by_year.values()), 2),
        "profit_factor_net_of_trade_fees": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "positive_years": sum(value > 0 for value in by_year.values()),
        "tested_years": len(by_year),
        "positive_symbol_fraction": round(positive_symbols / len(by_symbol), 4) if by_symbol else 0,
        "top_symbol_gross_profit_share": round(top_gross / gross_profit, 4) if gross_profit else 0,
        "by_year_net_pnl": dict(sorted((key, round(value, 2)) for key, value in by_year.items())),
        "by_symbol_net_pnl": dict(sorted((key, round(value, 2)) for key, value in by_symbol.items())),
        "runtime": runtime,
    }
    summary["valid_flat_run"] = (
        summary["completed"]
        and not summary["error"]
        and runtime.get("Holdings") == "$0.00"
        and summary["end_equity"] > 0
    )
    summary["passes_frozen_gate"] = (
        summary["valid_flat_run"]
        and summary["return_pct"] > 0
        and summary["cagr_pct"] > 0
        and summary["sharpe"] >= 0.75
        and (summary["profit_factor_net_of_trade_fees"] or 0) >= 1.2
        and summary["drawdown_pct"] <= 20
        and summary["entries"] >= 150
        and summary["positive_years"] >= 4
        and summary["positive_symbol_fraction"] >= 0.55
        and summary["top_symbol_gross_profit_share"] <= 0.35
    )
    return summary


def main():
    result = {name: summarize(filename) for name, filename in RUNS.items()}
    (ROOT / "first_rebound_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
