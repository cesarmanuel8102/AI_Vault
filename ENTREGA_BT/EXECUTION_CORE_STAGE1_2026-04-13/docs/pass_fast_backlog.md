# Pass-Fast Backlog (Separate from PF100)

Date: 2026-04-13

## Constraints

- Keep PF100 untouched as stable cashflow engine.
- Pass-fast strategy isolated in its own module/account.
- Same risk gate and firm-rule layer.

## Sprint 1

1. Opening-range breakout alpha (MNQ/MES).
2. Strict daily lock and trailing lock integration.
3. Backtests:
- IS: 2022-2024
- OOS: 2025-2026Q1
- STRESS: 2020

## Sprint 2

1. Parameter compression to 3-5 key knobs.
2. Walk-forward validation.
3. Execution rehearsal with paper adapter.

## Promotion Rule

- Pass-fast is promoted to manual challenge only if:
1. STRESS non-catastrophic (no hard breach).
2. OOS materially above PF100 baseline.
3. Execution behavior stable for 2 weeks in paper/live-sim.
