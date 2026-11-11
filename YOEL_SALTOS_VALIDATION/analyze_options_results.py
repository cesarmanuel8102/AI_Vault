"""Analyze the two frozen QuantConnect option backtests."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import json

from options_operability_core import passes_options_go_gate


ROOT = Path(__file__).resolve().parent
UNIVERSE = {
    "AAPL", "AMZN", "COIN", "DIA", "GLD", "IWM", "META", "NFLX",
    "NIO", "QQQ", "SPY", "TSLA", "USO", "XPEV", "LI",
}


def pct(value: str) -> float:
    return float(value.replace("%", "").strip()) / 100


def analyze(path: str) -> dict:
    backtest = json.loads((ROOT / path).read_text(encoding="utf-8"))["backtest"]
    stats = backtest["statistics"]
    runtime = backtest["runtimeStatistics"]
    trades = backtest["totalPerformance"]["closedTrades"]
    yearly = defaultdict(float)
    symbols = defaultdict(float)
    net_wins = []
    net_losses = []
    for trade in trades:
        net = float(trade["profitLoss"]) - float(trade["totalFees"])
        yearly[trade["exitTime"][:4]] += net
        symbol = trade["symbols"][0].get("underlying", {}).get("value")
        if not symbol:
            symbol = trade["symbols"][0]["value"].split()[0]
        symbols[symbol] += net
        (net_wins if net > 0 else net_losses).append(net)
    gross_profit = sum(net_wins)
    gross_loss = abs(sum(net_losses))
    completed_positions = int(runtime["Closed"])
    result = {
        "backtest_id": backtest["backtestId"],
        "variant": runtime["Variant"],
        "total_return": pct(stats["Net Profit"]),
        "cagr": pct(stats["Compounding Annual Return"]),
        "sharpe": float(stats["Sharpe Ratio"]),
        "max_drawdown": -pct(stats["Drawdown"]),
        "profit_factor": gross_profit / gross_loss if gross_loss else float("inf"),
        "trades": completed_positions,
        "closed_trade_lots": len(trades),
        "win_rate": pct(stats["Win Rate"]),
        "profit_loss_ratio": float(stats["Profit-Loss Ratio"]),
        "net_pnl": sum(net_wins) + sum(net_losses),
        "fees": sum(float(trade["totalFees"]) for trade in trades),
        "signals": int(runtime["Signals"]),
        "selection_skips": int(runtime["Selection Skips"]),
        "quote_skips": int(runtime["Quote Skips"]),
        "target_exits": int(runtime["Target Exits"]),
        "time_exits": int(runtime["Time Exits"]),
        "reinforcements": int(runtime["Reinforcements"]),
        "yearly_net_pnl": dict(sorted(yearly.items())),
        "positive_year_fraction": sum(value > 0 for value in yearly.values()) / len(yearly),
        "symbol_net_pnl": dict(sorted(symbols.items())),
        "positive_symbol_fraction": sum(value > 0 for value in symbols.values()) / len(symbols),
    }
    result["reinforcement_required_for_solvency"] = False
    result["go"] = passes_options_go_gate(result)
    return result


def stock_subset() -> dict:
    backtest = json.loads((ROOT / "qc_close_continuation_raw.json").read_text(encoding="utf-8"))["backtest"]
    trades = backtest["totalPerformance"]["closedTrades"]
    yearly = defaultdict(float)
    net_pnl = 0.0
    count = 0
    for trade in trades:
        symbol = trade["symbols"][0].get("underlying", {}).get("value")
        if not symbol:
            symbol = trade["symbols"][0]["value"].split()[0]
        if symbol not in UNIVERSE:
            continue
        net = float(trade["profitLoss"]) - float(trade["totalFees"])
        net_pnl += net
        yearly[trade["exitTime"][:4]] += net
        count += 1
    return {
        "trades": count,
        "net_pnl": net_pnl,
        "approx_total_return": net_pnl / 100_000,
        "yearly_net_pnl": dict(sorted(yearly.items())),
        "positive_year_fraction": sum(value > 0 for value in yearly.values()) / len(yearly),
    }


def main():
    output = {
        "base": analyze("options_base_raw.json"),
        "reinforcement": analyze("options_reinforcement_raw.json"),
        "same_universe_stock_reference": stock_subset(),
    }
    (ROOT / "options_summary.json").write_text(
        json.dumps(output, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
