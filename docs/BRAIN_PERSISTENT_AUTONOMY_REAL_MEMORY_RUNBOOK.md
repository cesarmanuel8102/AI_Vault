# Brain Persistent Autonomy And Real Memory Operations Runbook

## Current Mode

Persistent autonomy is implemented as a bounded, operator-controlled run-once system. Scheduler tooling exists but is not enabled automatically by this front.

## Commands

```powershell
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_status.ps1
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_run_once.ps1
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_pause.ps1
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_resume.ps1
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_stop.ps1
```

## Dashboard

Run manually:

```powershell
$env:PYTHONPATH="C:\AI_VAULT_CANONICAL;C:\AI_VAULT_CANONICAL\tmp_agent"
python -m uvicorn tmp_agent.brain_v9.dashboard.dashboard_app:app --host 127.0.0.1 --port 8092
```

Open: `http://127.0.0.1:8092/`

## Memory Policy

- Autonomous journal writes are allowed under `memory/autonomous_journal.jsonl`.
- Promotion candidates are queued under `memory/promotion_queue/`.
- Semantic staging is allowed under `memory/semantic_staging/`.
- Canonical semantic memory and FAISS promotion require snapshot, shadow index, rollback verification, tests, and batch size <= 5.

## Scheduler

Installer exists but is not enabled by default:

```powershell
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_install_scheduled_task.ps1
```

Use `-Enable` only after operator review.
