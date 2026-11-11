"""Create comparable economic summaries from QuantConnect result payloads."""

from pathlib import Path
import json

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
RUNS = {
    "CLOSE_CONTINUATION": "qc_close_continuation_raw.json",
    "OPENING_CONTINUATION": "qc_opening_continuation_raw.json",
    "OPENING_FADE": "qc_opening_fade_raw.json",
}


def parse_percent(value: str) -> float:
    return float(value.replace("%", "").strip()) / 100.0


def summarize(path: Path) -> dict:
    backtest = json.loads(path.read_text(encoding="utf-8"))["backtest"]
    statistics = backtest["statistics"]
    trades = backtest["totalPerformance"]["closedTrades"]
    rows = []
    for trade in trades:
        gross = float(trade["profitLoss"])
        fees = float(trade["totalFees"])
        rows.append({
            "exit_time": pd.to_datetime(trade["exitTime"], utc=True),
            "ticker": trade["symbols"][0]["value"],
            "gross_pnl": gross,
            "fees": fees,
            "net_pnl": gross - fees,
        })
    frame = pd.DataFrame(rows)
    gains = frame.loc[frame.net_pnl > 0, "net_pnl"].sum()
    losses = -frame.loc[frame.net_pnl < 0, "net_pnl"].sum()
    yearly = frame.groupby(frame.exit_time.dt.year).net_pnl.sum().reindex(
        range(2022, 2026), fill_value=0.0
    )
    symbols = frame.groupby("ticker").net_pnl.sum()
    exit_month = frame.exit_time.dt.tz_convert(None).dt.to_period("M")
    monthly = frame.groupby(exit_month).net_pnl.sum().reindex(
        pd.period_range("2022-01", "2025-12", freq="M"), fill_value=0.0
    )
    random = np.random.default_rng(20261025)
    samples = random.choice(monthly.to_numpy(), size=(20_000, len(monthly)), replace=True)
    annualized_samples = samples.mean(axis=1) * 12.0
    return {
        "completed": backtest["completed"],
        "error": backtest["error"],
        "backtest_id": backtest["backtestId"],
        "net_profit": parse_percent(statistics["Net Profit"]),
        "cagr": parse_percent(statistics["Compounding Annual Return"]),
        "drawdown": -parse_percent(statistics["Drawdown"]),
        "official_sharpe": float(statistics["Sharpe Ratio"]),
        "alpha": float(statistics["Alpha"]),
        "information_ratio": float(statistics["Information Ratio"]),
        "trades": len(frame),
        "win_rate": float((frame.net_pnl > 0).mean()),
        "net_profit_factor": float(gains / losses),
        "net_pnl": float(frame.net_pnl.sum()),
        "fees": float(frame.fees.sum()),
        "yearly_net_pnl": {str(year): float(value) for year, value in yearly.items()},
        "positive_year_fraction": float((yearly > 0).mean()),
        "positive_symbol_fraction": float((symbols > 0).mean()),
        "profitable_month_fraction": float((monthly > 0).mean()),
        "annualized_monthly_pnl_bootstrap_95": [
            float(np.quantile(annualized_samples, 0.025)),
            float(np.quantile(annualized_samples, 0.975)),
        ],
        "bootstrap_probability_positive_annualized_pnl": float(
            (annualized_samples > 0).mean()
        ),
        "top_symbols": {
            symbol: float(value)
            for symbol, value in symbols.sort_values(ascending=False).head(5).items()
        },
        "bottom_symbols": {
            symbol: float(value)
            for symbol, value in symbols.sort_values().head(5).items()
        },
    }


def main():
    output = {family: summarize(ROOT / filename) for family, filename in RUNS.items()}
    (ROOT / "operability_summary.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
