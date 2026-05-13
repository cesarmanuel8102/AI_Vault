# Phase 0 Paper Next Steps (MFFU Flex 50)

Date: 2026-04-14

## Objective

Validate the execution pipeline before buying an evaluation:

1. Signal -> risk gate -> route decision.
2. Stable paper execution behavior.
3. Zero hard-rule violations in internal controls.

## Step 1 - Gate Suite (local)

Run:

```powershell
cd C:\AI_VAULT\ENTREGA_BT\EXECUTION_CORE_STAGE1_2026-04-13
python run_phase0_gate_suite.py
```

Expected:

- `summary.passed == summary.total`
- file in `artifacts/phase0_gate_suite_*.json`
- append-only log in `artifacts/audit.jsonl`

## Step 2 - Manual Order Lifecycle (paper adapter)

Run:

```powershell
cd C:\AI_VAULT\ENTREGA_BT\EXECUTION_CORE_STAGE1_2026-04-13
python run_manual_sim.py
```

Verify:

- one accepted order on leader account
- no copier fanout until explicitly enabled
- decision and routed payload written to audit log

## Step 3 - 5-Day Micro Forward Paper

Daily acceptance checks:

1. no rejected orders due to malformed signals
2. no out-of-session order attempts
3. no daily-loss or trailing guard bypasses
4. EOD flat confirmation

Promote only if all 5 days are clean.

## Step 3.1 - Daily Session Runner

Run:

```powershell
cd C:\AI_VAULT\ENTREGA_BT\EXECUTION_CORE_STAGE1_2026-04-13
python run_phase0_paper_day.py --profile config/firm_profiles.mffu_flex50.paper.json --signals config/paper_day_signals.sample.json
```

What it produces:

1. `artifacts/paper_day_report_*.json` with accepted/rejected summary and reasons.
2. `artifacts/audit.jsonl` append-only execution audit.

For real daily run:

1. replace `config/paper_day_signals.sample.json` with your generated signal file for the day.
2. keep profile unchanged in phase 0.

## Step 3.2 - QC Bridge (real signals from live/paper deployment)

Set in `config/qc_signal_bridge.sample.json`:

1. `project_id` of the PF100 deployment.
2. `deploy_id` if available.
3. `allowed_symbols` to futures roots used by the strategy (MNQ/MES/M2K).

For PF100 use:

- `config/qc_signal_bridge.pf100.template.json`

Inspect what QC is returning:

```powershell
cd C:\AI_VAULT\ENTREGA_BT\EXECUTION_CORE_STAGE1_2026-04-13
python inspect_qc_live_orders.py --config config/qc_signal_bridge.sample.json
```

Build daily signal file from QC orders:

```powershell
python build_phase0_signals_from_qc.py --config config/qc_signal_bridge.sample.json
```

Troubleshooting:

1. If `orders_fetched > 0` but `signals_built = 0`, run `inspect_qc_live_orders.py`.
2. If `by_symbol` is not MNQ/MES/M2K, you are pointing to the wrong project/deploy.
3. If timestamps are old, adjust `deploy_id` to the active paper deployment.
4. Keep `allowed_symbols` restricted to the futures roots in your strategy.

Run the full daily bridge->paper pipeline:

```powershell
python run_phase0_qc_pipeline.py --bridge-config config/qc_signal_bridge.sample.json --profile config/firm_profiles.mffu_flex50.paper.json --outdir artifacts
```

## Step 4 - Pre-Eval Go/No-Go

Go only if:

1. Gate suite 100% pass.
2. 5 clean paper days.
3. Incident register empty (no unresolved recon issues).

Review command:

```powershell
cd C:\AI_VAULT\ENTREGA_BT\EXECUTION_CORE_STAGE1_2026-04-13
python run_phase0_paper_review.py --window 5
```

Promotion gate:

- `pass = true` and `hard_violations = 0`
