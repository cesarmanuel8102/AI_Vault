# Forward Validation Protocol (Single Account)

Date: 2026-04-13

## Objective

Validate PF100 manually/semi-automated in one prop evaluation account before scaling.

## Duration

- Minimum: 4 weeks
- Target: 6 weeks

## Daily Controls

1. Confirm session window and market calendar.
2. Confirm account limits in platform (daily and trailing).
3. Dry-run signal in execution core (`accepted/rejected` reason).
4. Place/route order only if all gates pass.
5. Verify stop and target are acknowledged by platform.
6. End-of-day reconciliation:
- position flat status
- fills vs expected
- slippage snapshot
- rule violations (must be 0)

## Weekly Controls

1. Compare realized vs expected:
- net return
- max intraday drawdown
- win rate
- average R multiple
2. Verify no platform-rule breaches.
3. Verify no execution anomalies:
- rejected orders
- duplicate orders
- orphan positions

## Promotion Criteria (to multi-account copy)

1. 0 hard breaches for 20 trading days.
2. Positive weekly expectancy over rolling 4-week window.
3. No unresolved reconciliation incidents.
4. Stable execution latency and fill quality.
