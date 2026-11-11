"""Independent, cost-aware tests of post-shock equity strategies.

The OOS period is evaluated once. Candidate selection uses IS and validation
only; the final gate is applied without changing parameters.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
import yfinance as yf

from operability_core import choose_barrier_exit, passes_go_gate, position_size


ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "operability_yahoo"
CACHE.mkdir(parents=True, exist_ok=True)

U2 = {
    "TSLA", "AAPL", "AMZN", "NFLX", "META", "COIN", "NIO", "XPEV", "LI",
    "SPY", "IWM", "QQQ", "DIA", "GLD", "USO", "MSFT", "GOOG", "NVDA",
    "AMD", "AVGO", "JPM", "BAC", "WMT", "COST", "HD", "UNH", "JNJ",
    "XOM", "CVX", "CAT", "BA", "DIS", "TLT", "XLF", "XLE", "XBI",
    "XLK", "XLV", "EEM", "SMH",
}

INITIAL_EQUITY = 100_000.0
SLIPPAGE_BPS = 5.0
COMMISSION_PER_SHARE = 0.005
MIN_COMMISSION = 1.0


@dataclass(frozen=True)
class Config:
    family: str
    threshold_atr: float
    hold_days: int

    @property
    def key(self) -> str:
        return f"{self.family}|atr={self.threshold_atr:.2f}|hold={self.hold_days}"


def load_ticker(ticker: str) -> pd.DataFrame:
    path = CACHE / f"{ticker}.csv"
    if path.exists():
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
    else:
        frame = yf.download(
            ticker,
            start="2007-01-01",
            end="2026-10-25",
            auto_adjust=True,
            actions=False,
            progress=False,
            threads=False,
            timeout=45,
        )
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        frame.columns = [str(column).lower() for column in frame.columns]
        frame.to_csv(path)
    frame.columns = [str(column).lower() for column in frame.columns]
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    return frame.dropna(subset=["open", "high", "low", "close", "volume"])


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["atr"] = true_range.rolling(14).mean().shift(1)
    frame["sma20"] = frame["close"].rolling(20).mean().shift(1)
    frame["sma40"] = frame["close"].rolling(40).mean().shift(1)
    frame["avg_volume20"] = frame["volume"].rolling(20).mean().shift(1)
    frame["avg_dollar_volume20"] = (
        frame["close"] * frame["volume"]
    ).rolling(20).mean().shift(1)
    frame["previous_close"] = previous_close
    frame["gap"] = frame["open"] - previous_close
    frame["gap_atr"] = frame["gap"] / frame["atr"]
    frame["gap_pct"] = frame["open"] / previous_close - 1.0
    return frame


def commission(quantity: int) -> float:
    return max(MIN_COMMISSION, quantity * COMMISSION_PER_SHARE)


def adverse_fill(price: float, direction: int, is_entry: bool) -> float:
    sign = direction if is_entry else -direction
    return price * (1.0 + sign * SLIPPAGE_BPS / 10_000.0)


def build_trade(
    ticker: str,
    frame: pd.DataFrame,
    index: int,
    config: Config,
    shock_direction: int,
) -> dict | None:
    row = frame.iloc[index]
    trade_direction = shock_direction
    if config.family == "OPEN_FADE":
        trade_direction *= -1

    if config.family.startswith("OPEN_"):
        entry_date = frame.index[index]
        raw_entry = float(row["open"])
        entry_index = index
        last_index = index
    else:
        # The signal uses the completed daily close and volume. Entering at that
        # same close would be look-ahead, so execution is the next session open.
        entry_index = index + 1
        entry_date = frame.index[entry_index]
        raw_entry = float(frame.iloc[entry_index]["open"])
        last_index = min(entry_index + config.hold_days - 1, len(frame) - 1)

    risk_per_share = float(row["atr"])
    quantity = position_size(
        INITIAL_EQUITY, raw_entry, risk_per_share, 0.005, 0.10
    )
    if quantity <= 0:
        return None

    entry = adverse_fill(raw_entry, trade_direction, True)
    stop = entry - trade_direction * risk_per_share
    target = entry + trade_direction * 2.0 * risk_per_share
    exit_price = None
    exit_reason = "TIME"
    exit_index = last_index

    if config.family.startswith("OPEN_"):
        exit_price, exit_reason = choose_barrier_exit(
            stop,
            target,
            float(row["low"]),
            float(row["high"]),
            float(row["close"]),
            trade_direction,
        )
    else:
        for candidate_index in range(entry_index, last_index + 1):
            candidate = frame.iloc[candidate_index]
            candidate_open = float(candidate["open"])
            if (trade_direction == 1 and candidate_open <= stop) or (
                trade_direction == -1 and candidate_open >= stop
            ):
                selected, reason = candidate_open, "STOP_GAP"
            else:
                selected, reason = choose_barrier_exit(
                    stop,
                    target,
                    float(candidate["low"]),
                    float(candidate["high"]),
                    float(candidate["close"]),
                    trade_direction,
                )
            if reason != "HOLD":
                exit_price, exit_reason, exit_index = selected, reason, candidate_index
                break
        if exit_price is None:
            exit_price = float(frame.iloc[exit_index]["close"])

    exit_price = adverse_fill(float(exit_price), trade_direction, False)
    costs = 2.0 * commission(quantity)
    gross_pnl = trade_direction * quantity * (exit_price - entry)
    net_pnl = gross_pnl - costs
    daily_pnl = {}
    previous_cumulative = 0.0
    for mark_index in range(entry_index, exit_index + 1):
        mark_date = frame.index[mark_index]
        is_exit = mark_index == exit_index
        mark = exit_price if is_exit else float(frame.iloc[mark_index]["close"])
        cumulative = trade_direction * quantity * (mark - entry) - commission(quantity)
        if is_exit:
            cumulative -= commission(quantity)
        daily_pnl[mark_date.isoformat()] = cumulative - previous_cumulative
        previous_cumulative = cumulative
    return {
        "ticker": ticker,
        "config": config.key,
        "family": config.family,
        "threshold_atr": config.threshold_atr,
        "hold_days": config.hold_days,
        "entry_date": entry_date,
        "exit_date": frame.index[exit_index],
        "direction": trade_direction,
        "entry_price": entry,
        "exit_price": exit_price,
        "quantity": quantity,
        "exit_reason": exit_reason,
        "gross_pnl": gross_pnl,
        "costs": costs,
        "net_pnl": net_pnl,
        "return_on_equity": net_pnl / INITIAL_EQUITY,
        "_daily_pnl": daily_pnl,
    }


def generate_trades(ticker: str, frame: pd.DataFrame, configs: list[Config]) -> list[dict]:
    frame = prepare(frame)
    trades: list[dict] = []
    for index in range(45, len(frame) - 6):
        row = frame.iloc[index]
        if (
            not np.isfinite(row["atr"])
            or row["atr"] <= 0
            or row["previous_close"] < 5
            or row["avg_dollar_volume20"] < 20_000_000
            or abs(row["gap_pct"]) < 0.005
        ):
            continue
        shock_direction = 1 if row["gap"] > 0 else -1
        trend_ok = (
            row["sma20"] > row["sma40"] and row["previous_close"] > row["sma40"]
            if shock_direction == 1
            else row["sma20"] < row["sma40"] and row["previous_close"] < row["sma40"]
        )
        if not trend_ok:
            continue
        prior_shocks = frame["gap_atr"].abs().iloc[max(0, index - 5):index]
        for config in configs:
            if abs(row["gap_atr"]) < config.threshold_atr:
                continue
            if len(prior_shocks) and (prior_shocks >= config.threshold_atr).any():
                continue
            if config.family == "CLOSE_CONTINUATION":
                relative_volume = row["volume"] / row["avg_volume20"]
                directional_close = shock_direction * (row["close"] / row["open"] - 1)
                if relative_volume < 1.20 or directional_close <= 0:
                    continue
            trade = build_trade(ticker, frame, index, config, shock_direction)
            if trade:
                trades.append(trade)
    return trades


def segment_for(date: pd.Timestamp) -> str:
    if date.year <= 2017:
        return "IS"
    if date.year <= 2021:
        return "VALIDATION"
    return "OOS"


def limit_concurrency(frame: pd.DataFrame, maximum: int = 10) -> pd.DataFrame:
    accepted = []
    active_exits: list[pd.Timestamp] = []
    for row in frame.sort_values(["entry_date", "ticker"]).to_dict("records"):
        active_exits = [date for date in active_exits if date >= row["entry_date"]]
        if len(active_exits) >= maximum:
            continue
        accepted.append(row)
        active_exits.append(row["exit_date"])
    return pd.DataFrame(accepted)


def metrics(frame: pd.DataFrame, start_year: int, end_year: int) -> dict:
    if frame.empty:
        return {
            "total_return": 0.0, "cagr": 0.0, "sharpe": 0.0,
            "profit_factor": 0.0, "max_drawdown": 0.0, "trades": 0,
            "positive_year_fraction": 0.0, "positive_symbol_fraction": 0.0,
        }
    frame = limit_concurrency(frame)
    daily_values = defaultdict(float)
    for marks in frame["_daily_pnl"]:
        for date, value in marks.items():
            daily_values[pd.Timestamp(date)] += float(value)
    daily_pnl = pd.Series(daily_values, dtype=float)
    calendar = pd.date_range(f"{start_year}-01-01", f"{end_year}-12-31", freq="B")
    daily_pnl = daily_pnl.reindex(calendar, fill_value=0.0)
    equity = INITIAL_EQUITY + daily_pnl.cumsum()
    daily_return = daily_pnl / equity.shift(1).fillna(INITIAL_EQUITY)
    total_return = float(equity.iloc[-1] / INITIAL_EQUITY - 1.0)
    years = max((calendar[-1] - calendar[0]).days / 365.25, 1 / 365.25)
    cagr = float((max(equity.iloc[-1], 1.0) / INITIAL_EQUITY) ** (1 / years) - 1)
    std = float(daily_return.std(ddof=1))
    sharpe = float(math.sqrt(252) * daily_return.mean() / std) if std > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    gains = float(frame.loc[frame["net_pnl"] > 0, "net_pnl"].sum())
    losses = float(-frame.loc[frame["net_pnl"] < 0, "net_pnl"].sum())
    annual = frame.assign(year=frame["exit_date"].dt.year).groupby("year")["net_pnl"].sum()
    annual = annual.reindex(range(start_year, end_year + 1), fill_value=0.0)
    symbols = frame.groupby("ticker")["net_pnl"].sum()
    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "profit_factor": gains / losses if losses > 0 else float("inf"),
        "max_drawdown": float(drawdown.min()),
        "trades": int(len(frame)),
        "win_rate": float((frame["net_pnl"] > 0).mean()),
        "average_trade_pnl": float(frame["net_pnl"].mean()),
        "costs": float(frame["costs"].sum()),
        "positive_year_fraction": float((annual > 0).mean()),
        "positive_symbol_fraction": float((symbols > 0).mean()),
    }


def main() -> None:
    configs = []
    for threshold in (0.75, 1.0, 1.25):
        configs.extend([
            Config("OPEN_CONTINUATION", threshold, 0),
            Config("OPEN_FADE", threshold, 0),
            Config("CLOSE_CONTINUATION", threshold, 1),
            Config("CLOSE_CONTINUATION", threshold, 3),
            Config("CLOSE_CONTINUATION", threshold, 5),
        ])

    all_trades = []
    failures = {}
    loaded = {}
    for ticker in sorted(U2):
        try:
            frame = load_ticker(ticker)
            loaded[ticker] = len(frame)
            all_trades.extend(generate_trades(ticker, frame, configs))
        except Exception as exc:
            failures[ticker] = repr(exc)

    trades = pd.DataFrame(all_trades)
    if trades.empty:
        raise RuntimeError("No trades generated")
    trades["entry_date"] = pd.to_datetime(trades["entry_date"])
    trades["exit_date"] = pd.to_datetime(trades["exit_date"])
    trades["segment"] = trades["entry_date"].map(segment_for)
    trades.drop(columns=["_daily_pnl"]).to_csv(ROOT / "operability_trades.csv", index=False)

    period_years = {"IS": (2008, 2017), "VALIDATION": (2018, 2021), "OOS": (2022, 2025)}
    results = []
    for config in configs:
        for segment, (start, end) in period_years.items():
            subset = trades[(trades["config"] == config.key) & (trades["segment"] == segment)]
            results.append({
                "config": config.key,
                "family": config.family,
                "threshold_atr": config.threshold_atr,
                "hold_days": config.hold_days,
                "segment": segment,
                **metrics(subset, start, end),
            })

    results_frame = pd.DataFrame(results)
    finalists = {}
    for family, family_rows in results_frame.groupby("family"):
        validation = family_rows[family_rows["segment"] == "VALIDATION"].copy()
        is_lookup = family_rows[family_rows["segment"] == "IS"].set_index("config")
        validation = validation[validation["config"].map(is_lookup["total_return"]) > 0]
        if len(validation):
            finalists[family] = validation.sort_values(
                ["sharpe", "profit_factor", "total_return"], ascending=False
            ).iloc[0]["config"]

    oos_assessments = []
    for family, config_key in finalists.items():
        row = results_frame[
            (results_frame["segment"] == "OOS")
            & (results_frame["config"] == config_key)
        ].iloc[0].to_dict()
        threshold = row["threshold_atr"]
        neighbors = results_frame[
            (results_frame["segment"] == "OOS")
            & (results_frame["family"] == family)
            & (results_frame["hold_days"] == row["hold_days"])
            & (results_frame["threshold_atr"].isin([threshold - 0.25, threshold + 0.25]))
        ]
        row["neighbor_sign_consistent"] = bool(len(neighbors) and (neighbors["total_return"] > 0).all())
        row["portfolio_contribution"] = bool(row["cagr"] > 0 and row["max_drawdown"] > -0.20)
        row["passes_go_gate"] = passes_go_gate(row)
        oos_assessments.append(row)

    output = {
        "study": "post-shock operability independent daily engine",
        "cost_model": {
            "slippage_bps_each_side": SLIPPAGE_BPS,
            "commission_per_share_each_side": COMMISSION_PER_SHARE,
            "minimum_commission_each_side": MIN_COMMISSION,
        },
        "loaded_rows": loaded,
        "failures": failures,
        "finalists_selected_without_oos": finalists,
        "results": results,
        "oos_assessments": oos_assessments,
        "underlying_go": any(row["passes_go_gate"] for row in oos_assessments),
    }
    (ROOT / "operability_results.json").write_text(
        json.dumps(output, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({
        "finalists": finalists,
        "oos_assessments": oos_assessments,
        "underlying_go": output["underlying_go"],
        "failures": failures,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
