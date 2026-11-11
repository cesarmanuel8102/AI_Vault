# Capital-Independent Signal Selector Design

## Intent

Replace the accidental affordability filter with an explicit causal quality
gate and daily ranking. Signal acceptance must not depend on account size;
capital only determines position quantity after a signal has been accepted.

## Goals

- Use only information available by the 10:31 ET decision time.
- Discover rules on 2022-2023, confirm them on 2024, then freeze them.
- Compare the frozen selector on 2025-2026 using the same capital and execution
  assumptions as its unfiltered control.
- Report annual and aggregate return, profit factor, drawdown, trade count,
  win rate, and fees.

## Non-Goals

- Do not change delta 0.70, 0DTE, TP 10%, exits, costs, or intraday closeout.
- Do not use affordability, future option behavior, or post-entry information
  as signal-quality inputs.
- Do not optimize thresholds on 2025-2026.

## Approach

Use a hybrid selector. First, a deterministic minimum-quality gate rejects
candidates whose causal features do not meet the frozen thresholds. Second,
surviving candidates receive a deterministic score and are ranked across the
day. The account value and contract premium are excluded from both functions.

Candidate features are limited to direction-normalized first-hour structure,
relative volume, close location, rebound distance from the selected moving
average, first-hour range normalized by ATR, alignment with the daily trend,
and option friction observed before submission. Any feature not already
available causally will be recorded in a trace-only discovery run before it is
eligible for selection.

## Validation

Thresholds and weights are selected using 2022-2023 only. A candidate must
remain economically positive in 2024 before it is frozen. The single frozen
configuration is then run on 2025-2026. A result is not promoted unless both
the discovery-confirmation aggregate and 2025-2026 have positive net profit
and profit factor above 1 after modeled fees and slippage.

## Considered Alternatives

- Rule-only gate: interpretable, but cannot choose among multiple valid daily
  signals.
- Ranking-only selector: preserves frequency, but can still trade universally
  weak days.
- Machine-learning classifier: rejected because the sample is too small and
  the overfit risk is disproportionate.

