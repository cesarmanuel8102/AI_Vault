# Delta/DTE First-Rebound Study

## Objective

Measure whether changing option delta and time to expiry improves the economics
of the frozen Yoel first-rebound signal without changing the signal itself.

## Frozen experiment

- Period: 2025-01-01 through 2026-10-25.
- Universe, signal, hourly timing and daily confirmation remain unchanged.
- Initial capital: USD 100,000.
- Maximum premium per entry: 10% of available cash/equity.
- No stop loss.
- Exit at 15:55 ET if the profit target has not filled.
- QuantConnect Interactive Brokers fee model and USD 0.01 per-contract slippage.
- Profit targets: 10% and 15%, tested independently.

## Contract variants

1. Absolute delta 0.50, target DTE 0.
2. Absolute delta 0.70, target DTE 0.
3. Absolute delta 0.70, target DTE 7.
4. Absolute delta 0.70, target DTE 14.

For DTE 0, only same-day expiry is valid. For DTE 7 and 14, choose the listed
non-expired expiry nearest the target calendar DTE. From that expiry and the
signal direction, choose the quoted contract whose absolute QuantConnect delta
is nearest the target. Record actual entry delta and actual DTE.

## Decision rule

Compare net profit, CAGR, drawdown, Sharpe, profit factor, completed trades,
win rate, target-hit rate, fees and effective selected delta/DTE. A high hit
rate is not sufficient if net expectancy after costs is negative.
