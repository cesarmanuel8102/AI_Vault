# Delta 0.70 0DTE Profit-Ladder Design

## Cause

The fixed 10% target monetizes the attainable move, while full-position TP15,
TP30 and trailing exits lose because 0DTE reversals are too abrupt. Every trade
in the accepted sample has at least 11 contracts, so partial realization is
operationally testable without synthetic fractional contracts.

## Countermeasure candidates

Preserve the accepted TP10 as the first realization point and test only:

1. close 50% at +10%, close the runner at +15%;
2. close 75% at +10%, close the runner at +15%;
3. close 75% at +10%, close the runner at +20%.

Use integer contracts, always leave at least one runner, and retain the causal
failure exit and 15:55 liquidation for the remainder. Do not combine this test
with whole-position trailing.

Screen candidates on 2025 only. Select one using net return, net profit factor
and drawdown, then run it unchanged on 2026 and combined 2025-2026.

If all broad ladders fail, one final causal candidate may scale 75% only when
the first observable profitable quote is already at or above +15%, otherwise
retaining the full TP10 exit. Its runner target is +20%. This tests quote-level
momentum overshoot without changing ordinary winners.
