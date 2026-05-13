# Prop Execution Core (Pre-Brain)

Date: 2026-04-13

This module is the intermediate execution layer between strategy signals (PF100 / pass-fast) and prop-firm accounts.

## Goal

1. Run manual and semi-automatic validation on 1 account.
2. Enforce firm rules before sending orders.
3. Support multi-account copy when the first account is funded.
4. Integrate with Brain only after stable execution.

## Current Scope

- Rule engine for firm-specific constraints.
- Risk gate (daily/trailing, max contracts, allowed session).
- Router abstraction (paper adapter included; live adapters pending).
- Copier abstraction for leader-follower replication.
- Event/audit log for every decision.

## Confirmed Connectivity (as of 2026-04-13)

- QuantConnect Cloud supported live brokerages list does **not** show Tradovate.
- Topstep uses TopstepX as primary platform for new combines.
- Apex policy page states no automation/algorithm usage allowed.
- MFFU allows automation with restrictions and supports copy-trading workflows.

Links:
- https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages
- https://help.topstep.com/en/articles/11667498-important-changes-to-topstep-supported-platforms
- https://help.topstep.com/en/articles/11187768-topstepx-api-access
- https://apextraderfunding.com/help-center/getting-started/prohibited-activities/
- https://help.myfundedfutures.com/en/articles/8444599-fair-play-and-prohibited-trading-practices
- https://help.myfundedfutures.com/en/articles/10771500-copy-trading-at-myfundedfutures

## Runbook

1. Configure one profile in `config/firm_profiles.sample.json`.
2. Run `python run_manual_sim.py` for dry-run.
3. Connect one live adapter (TopstepX API or Tradovate API) and keep copy mode off.
4. Run 4-6 weeks forward validation on one account.
5. Enable copier only after stable risk metrics.

## Phase 0 Paper Commands (new)

1. Gate suite: `python run_phase0_gate_suite.py`
2. Daily paper day from file: `python run_phase0_paper_day.py --profile config/firm_profiles.mffu_flex50.paper.json --signals config/paper_day_signals.sample.json`
3. 5-day promotion review: `python run_phase0_paper_review.py --window 5`
4. Inspect QC live orders: `python inspect_qc_live_orders.py --config config/qc_signal_bridge.sample.json`
5. Build signals from QC: `python build_phase0_signals_from_qc.py --config config/qc_signal_bridge.sample.json`
6. Full QC->paper pipeline: `python run_phase0_qc_pipeline.py --bridge-config config/qc_signal_bridge.sample.json --profile config/firm_profiles.mffu_flex50.paper.json --outdir artifacts`
