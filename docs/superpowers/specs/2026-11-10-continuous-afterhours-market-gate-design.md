# Continuous After-Hours Market Gate Design

## Intent

Prevent the model-visible market-data snapshot from describing the entire V4 runtime as blocked merely because the regular US session is closed when a certified continuous family is authenticated and currently tradable.

## Goals

- Preserve the frozen regular-session gate and its reason codes as evidence.
- Publish an effective V4 gate that is `PASS` when at least one sleeve has entry or management eligibility.
- Publish explicit per-sleeve status so the model sees that `REGULAR_SLEEVE` remains blocked while `CONTINUOUS_SLEEVE` is eligible.
- Preserve candidate-specific quote, feasibility, sleeve, family, reconciliation, and kill-switch enforcement.

## Non-goals

- Do not alter trading strategy, risk limits, capital, session certification, order authority, or broker state.
- Do not make a closed or uncertified family eligible.
- Do not convert a missing continuous session into a pass.

## Approaches

1. Change the generic `MarketDataGate` to accept after-hours quotes. Rejected because it would weaken Day1 regular-session protection globally.
2. Keep the global block and only change prompt wording. Rejected because downstream model reasoning would continue receiving contradictory machine-readable state.
3. Derive a V4 effective snapshot after sleeve eligibility is computed. Selected because it preserves the original gate, exposes exact per-sleeve status, and relies on existing proposal-level sleeve/family validation.

## Selected behavior

For V4 bundles, retain the original frozen gate under `regular_market_gate`. Add `sleeve_gate_status` from the durable portfolio eligibility projection. Set top-level `gate_status=PASS` and clear top-level reason codes only when at least one entry or management route is `PASS`; otherwise retain the original block. The regular sleeve remains ineligible outside its authenticated session and any regular proposal continues to fail `validate_multi_sleeve_payload`.
