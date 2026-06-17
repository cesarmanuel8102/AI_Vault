# Operator Commands

## Dashboard

Open:

`http://127.0.0.1:8092/`

If dashboard is not running, start it:

```powershell
$env:PYTHONPATH="C:\AI_VAULT_CANONICAL;C:\AI_VAULT_CANONICAL\tmp_agent"
cd C:\AI_VAULT_CANONICAL
python -m uvicorn tmp_agent.brain_v9.dashboard.dashboard_app:app --host 127.0.0.1 --port 8092
```

## Autonomy Control

```powershell
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_status.ps1
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_run_once.ps1
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_pause.ps1
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_resume.ps1
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_stop.ps1
```

## Scheduler Tooling

Create disabled scheduled task:

```powershell
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_install_scheduled_task.ps1
```

Create enabled scheduled task only after review:

```powershell
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_install_scheduled_task.ps1 -Enable
```

Uninstall:

```powershell
powershell -ExecutionPolicy Bypass -File tools/brain_autonomy_uninstall_scheduled_task.ps1
```

## Memory Review

- Journal: `memory/autonomous_journal.jsonl`
- Queue: `memory/promotion_queue/`
- Staging: `memory/semantic_staging/semantic_memory_candidate.jsonl`
- Audit: `memory/semantic/promotion_audit.jsonl`
