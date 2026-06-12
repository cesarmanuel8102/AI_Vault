# Brain Daily Autonomous Dry-Run Runbook

## Purpose

Run a manual, operator-triggered autonomy dry-run that produces evidence without enabling a scheduler and without writing semantic memory, FAISS, trading, B8, or secrets.

## Command

```powershell
powershell -ExecutionPolicy Bypass -File tools/brain_daily_autonomous_dryrun.ps1 -Cycles 3
```

## Guarantees

- No semantic memory writes.
- No FAISS writes or reindexing.
- No trading, broker API, paper trading, or live trading.
- No B8 access.
- No scheduler is installed or enabled.
- Output is an operational report under `tmp_agent/brain_v9/operations/daily_autonomy_reports/`.

## Operator Review

Review provider fallback rate, lessons, mistakes, promotion candidates, and recommended human actions before authorizing any next front.
