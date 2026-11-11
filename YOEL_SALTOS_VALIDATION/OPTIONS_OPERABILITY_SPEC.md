# Options Operability Frozen Specification

## Question

Does expressing the already-selected post-shock continuation signal through long
weekly options produce a robust, tradeable advantage after realistic option fees
and execution, and does the course's reinforcement rule improve it?

## Frozen scope

- Test period: 2022-01-01 through 2025-12-31.
- Initial capital: USD 100,000, matching the stock comparison.
- Underlyings: AAPL, AMZN, COIN, DIA, GLD, IWM, META, NFLX, NIO, QQQ,
  SPY, TSLA, USO, XPEV, and LI.
- Signal: the pre-selected `CLOSE_CONTINUATION` post-shock rule from the stock
  study, unchanged.
- Direction: calls after bullish signals and puts after bearish signals.
- Contract expiry: earliest available expiry 2-10 calendar days away at entry.
  This operationalizes the transcript's "next Friday" instruction while avoiding
  same-day expiry.
- Strike: nearest out-of-the-money strike in the signal direction.
- Entry: one marketable order after a valid bid/ask is observed on the next
  session. Entry is costed at the modelled fill and Interactive Brokers option fee.
- Base allocation: at most 2% of current equity in premium per signal, one open
  position per underlying, at most ten open positions.
- Profit exit: GTC limit at 35% above the actual average option fill price.
- Time exit: market exit after three trading sessions or when DTE reaches one,
  whichever occurs first. Positions are not allowed to expire or exercise.
- No stop loss is used in the primary variant because the transcript says
  reinforcement replaces the stop.

## Variants

1. `BASE`: no reinforcement.
2. `REINFORCEMENT`: once per position, when the executable option value falls to
   20% or less of the initial fill, buy additional contracts using no more premium
   than the original entry outlay. Cancel and replace the target at 35% above the
   new weighted average cost.

## Anti-bias rules

- No parameter is changed after seeing the 2022-2025 results.
- Failed or unavailable chains are skips, not synthetic fills.
- Zero-bid contracts cannot be sold at their mark.
- Every result reports selection failures, entry failures, fees, time exits,
  target exits, reinforcements, and forced liquidations.
- Prior Yoel options versions are secondary evidence only and are not reused as
  strategy logic.

## Decision gate

`GO` requires positive total return and CAGR, Sharpe >= 0.75, profit factor >=
1.15, maximum drawdown <= 20%, at least 100 completed trades, positive results in
at least 60% of calendar years and 55% of traded underlyings, and no dependence on
the reinforcement variant for solvency.

