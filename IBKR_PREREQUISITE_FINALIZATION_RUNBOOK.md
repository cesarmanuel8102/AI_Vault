# IBKR Autonomous Experiment — Prerequisite Finalization Runbook

## Current scope

This runbook completes the two remaining local prerequisites for the 30-day
Codex IBKR paper experiment:

1. Auditor Gate V2 real restricted-token receipt.
2. Market Data Policy freeze + real market-data validation.

It does **not** arm paper execution and does **not** start the experiment.

## Before running

- Windows repository path must be `C:\AI_VAULT`.
- IB Gateway must be logged into the PAPER account.
- IB API endpoint must be listening locally on port 4002.
- Run Windows PowerShell as Administrator.

## Admin command

```powershell
Set-Location C:\AI_VAULT
git fetch origin
git switch codex/ibkr-paper-auditor-gate-v2
git pull --ff-only origin codex/ibkr-paper-auditor-gate-v2
Set-ExecutionPolicy -Scope Process Bypass -Force
.\FINALIZE_IBKR_PREREQUISITES.ps1
```

Expected successful Auditor output includes:

- `auditor_gate_v2 = PASS`
- `paper_execution_armed = false`
- `autonomous_experiment_started = false`

If Market Data is not already PASS, the finalizer registers:

`CodexIBKRMarketDataGate`

The task runs weekdays at 09:35 local time. On the intended Miami/ET workstation,
it starts at 09:35 ET and requires the user session plus IB Gateway PAPER to
remain available.

## Market-data protocol

The scheduled task:

- re-proves PAPER read-only identity;
- archives incomplete prior market-gate evidence;
- collects SPY, QQQ and IEF;
- uses their verified primary exchanges:
  - SPY: ARCA
  - QQQ: NASDAQ
  - IEF: NASDAQ
- collects three 330-second REALTIME windows;
- separates window starts by 31 minutes;
- produces 67 samples per symbol per window, 201 per symbol total;
- freezes `MARKET_DATA_POLICY_V1`;
- validates a fresh real market snapshot against the frozen policy;
- unregisters itself after `MARKET_DATA_GATE=PASS`.

Typical elapsed wall-clock time is about 68 minutes from the first window start.

The task does not place, modify or cancel orders.

## Manual market-data run

During a regular weekday session, the same protocol can be run interactively:

```powershell
Set-Location C:\AI_VAULT
.\RUN_IBKR_MARKET_DATA_GATE.ps1
```

## Verify final prerequisite state

```powershell
Set-Location C:\AI_VAULT
python -m ibkr_paper_30d.prerequisite_tools readiness --report-root state\ibkr_paper_30d\reports
```

A fully completed prerequisite state reports:

- `auditor_receipt_present: true`
- `market_policy_present: true`
- `market_data_gate: PASS`
- `prerequisites_structurally_present: true`
- `paper_execution_armed: false`

The experiment remains deliberately unarmed after both prerequisites pass.
