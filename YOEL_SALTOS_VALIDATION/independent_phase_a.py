"""Independent daily-data cross-check for the Yoel Sardinas gap claim."""

from pathlib import Path
import json

import pandas as pd
import yfinance as yf

from importlib.util import module_from_spec, spec_from_file_location


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "Yoel Saltos Validation 20261025"
spec = spec_from_file_location("analysis_core", PROJECT / "analysis_core.py")
analysis_core = module_from_spec(spec)
spec.loader.exec_module(analysis_core)

U1 = {
    "TSLA", "AAPL", "AMZN", "NFLX", "META", "COIN", "NIO", "XPEV", "LI",
    "SPY", "IWM", "QQQ", "DIA", "GLD", "USO",
}
U2 = U1 | {
    "MSFT", "GOOG", "NVDA", "AMD", "AVGO", "JPM", "BAC", "WMT", "COST",
    "HD", "UNH", "JNJ", "XOM", "CVX", "CAT", "BA", "DIS", "TLT", "XLF",
    "XLE", "XBI", "XLK", "XLV", "EEM", "SMH",
}


def load_ticker(ticker):
    frame = yf.download(
        ticker,
        start="2008-01-01",
        end="2026-10-25",
        auto_adjust=True,
        actions=False,
        progress=False,
        threads=False,
        timeout=30,
    )
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    return frame.rename(columns=str.lower).dropna(subset=["open", "close"])


def observations(frame, threshold, lookback, strict, exclude_high_volume):
    close = frame["close"]
    gap = frame["open"] / close.shift(1) - 1
    prior_close = close.shift(1)
    sma20 = close.rolling(20).mean().shift(1)
    sma40 = close.rolling(40).mean().shift(1)
    sma100 = close.rolling(100).mean().shift(1)
    no_recent_gap = gap.abs().shift(1).rolling(lookback).max() < threshold
    volume_mean = frame["volume"].rolling(20).mean().shift(1)
    eligible = pd.Series(True, index=frame.index)
    if exclude_high_volume:
        eligible &= frame["volume"] <= 2.5 * volume_mean

    trend_up = (sma20 > sma40) & (prior_close > sma40)
    trend_down = (sma20 < sma40) & (prior_close < sma40)
    if strict:
        trend_up &= prior_close > sma100
        trend_down &= prior_close < sma100

    next_gap = gap.shift(-1)
    next_intraday = (frame["close"] / frame["open"] - 1).shift(-1)
    rows = []
    for direction, trend in ((1, trend_up), (-1, trend_down)):
        signal = eligible & trend & no_recent_gap & (gap * direction >= threshold)
        control = eligible & trend & ~signal
        outcome = next_gap * direction >= threshold
        for timestamp in frame.index[signal.fillna(False)]:
            rows.append({
                "date": timestamp,
                "kind": "signal",
                "success": bool(outcome.loc[timestamp]),
                "return": float(next_intraday.loc[timestamp] * direction),
            })
        for timestamp in frame.index[control.fillna(False) & next_gap.notna()]:
            rows.append({
                "date": timestamp,
                "kind": "control",
                "success": bool(outcome.loc[timestamp]),
                "return": None,
            })
    return rows


def main():
    ticker_frames = {}
    failures = {}
    for ticker in sorted(U2):
        try:
            frame = load_ticker(ticker)
            if len(frame) >= 200:
                ticker_frames[ticker] = frame
            else:
                failures[ticker] = f"only {len(frame)} rows"
        except Exception as exc:
            failures[ticker] = repr(exc)

    detailed = []
    configs = []
    for threshold in (0.005, 0.01, 0.015, 0.02):
        for lookback in (5, 10):
            for strict in (False, True):
                for exclude_high_volume in (False, True):
                    configs.append((threshold, lookback, strict, exclude_high_volume))

    for ticker, frame in ticker_frames.items():
        for threshold, lookback, strict, exclude_high_volume in configs:
            for row in observations(frame, threshold, lookback, strict, exclude_high_volume):
                detailed.append({
                    "ticker": ticker,
                    "instructor_universe": ticker in U1,
                    "threshold": threshold,
                    "lookback": lookback,
                    "strict": strict,
                    "exclude_high_volume": exclude_high_volume,
                    **row,
                })

    details = pd.DataFrame(detailed)
    details.to_csv(ROOT / "phase_a_observations.csv", index=False)
    results = []
    for universe in ("U1", "U2"):
        universe_mask = details["instructor_universe"] if universe == "U1" else pd.Series(True, index=details.index)
        for segment in ("IS", "OOS", "ALL"):
            if segment == "IS":
                segment_mask = details["date"].dt.year < 2022
            elif segment == "OOS":
                segment_mask = details["date"].dt.year >= 2022
            else:
                segment_mask = pd.Series(True, index=details.index)
            for threshold, lookback, strict, exclude_high_volume in configs:
                subset = details[
                    universe_mask
                    & segment_mask
                    & (details["threshold"] == threshold)
                    & (details["lookback"] == lookback)
                    & (details["strict"] == strict)
                    & (details["exclude_high_volume"] == exclude_high_volume)
                ]
                signal = subset[subset["kind"] == "signal"]
                control = subset[subset["kind"] == "control"]
                summary = analysis_core.summarize_binary_outcomes(
                    int(signal["success"].sum()), len(signal),
                    int(control["success"].sum()), len(control),
                )
                ticker_lifts = []
                for _, ticker_rows in subset.groupby("ticker"):
                    ticker_signal = ticker_rows[ticker_rows["kind"] == "signal"]
                    ticker_control = ticker_rows[ticker_rows["kind"] == "control"]
                    if len(ticker_signal) >= 5 and len(ticker_control):
                        ticker_lifts.append(
                            ticker_signal["success"].mean() - ticker_control["success"].mean()
                        )
                results.append({
                    "universe": universe,
                    "segment": segment,
                    "threshold": threshold,
                    "lookback": lookback,
                    "strict": strict,
                    "exclude_high_volume": exclude_high_volume,
                    "signal_successes": int(signal["success"].sum()),
                    "signal_total": len(signal),
                    "control_successes": int(control["success"].sum()),
                    "control_total": len(control),
                    **summary,
                    "next_day_directional_intraday_mean": float(signal["return"].mean()) if len(signal) else None,
                    "tickers_with_sample": len(ticker_lifts),
                    "positive_ticker_fraction": sum(value > 0 for value in ticker_lifts) / len(ticker_lifts) if ticker_lifts else None,
                })

    output = {
        "source": "Yahoo Finance adjusted daily OHLCV independent cross-check",
        "tickers_loaded": sorted(ticker_frames),
        "failures": failures,
        "results": results,
    }
    (ROOT / "phase_a_results.json").write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    principal = next(item for item in results if (
        item["universe"] == "U2"
        and item["segment"] == "OOS"
        and item["threshold"] == 0.01
        and item["lookback"] == 5
        and item["strict"] is False
        and item["exclude_high_volume"] is True
    ))
    print(json.dumps({"principal": principal, "failures": failures}, indent=2))


if __name__ == "__main__":
    main()
