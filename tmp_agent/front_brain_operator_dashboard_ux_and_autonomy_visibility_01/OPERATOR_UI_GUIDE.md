# OPERATOR_UI_GUIDE.md
## FRONT-BRAIN-OPERATOR-DASHBOARD-UX-AND-AUTONOMY-VISIBILITY-01

## Dashboard URL
http://127.0.0.1:8092/

## Quick Start

Open the URL in a browser. The dashboard auto-refreshes every 10 seconds.

## Understanding Panels

### Status Cards
Green = healthy, Yellow = attention, Red = blocked.

### What Brain is Doing Now
- **Idle**: waiting for next cycle
- **Running**: currently processing
- **Paused**: stopped temporarily, can resume
- **Stopped**: halted, needs resume

### Recent Activity
Timeline shows last 10 autonomous journal events. No raw JSON — just human-readable summaries.

### Memory
Read-only counts. The green safety message confirms canonical memory is NOT being modified automatically.

### Promotion Queue
Candidates waiting for human review. DO NOT auto-promote from dashboard.

### Scheduler
Shows if BrainGovernedAutonomy task exists and is enabled.

### Controls
- **Run Once**: safe, triggers single cycle
- **Pause/Stop**: require confirmation
- **Resume**: clears pause and stop flags

### Chat
Ask Brain questions. Metadata shows provider, model, fallback, CoT leak protection.

## Alerts

Yellow alerts = review recommended.
Red alerts = action required.
Green = all clear.

## Restart Instructions

If dashboard freezes:
```powershell
# In PowerShell
Get-Process python | Where-Object {$_.CommandLine -like "*dashboard_app:app*"} | Stop-Process -Force
$env:PYTHONPATH="C:\AI_VAULT_CANONICAL;C:\AI_VAULT_CANONICAL\tmp_agent"
cd C:\AI_VAULT_CANONICAL
python -m uvicorn tmp_agent.brain_v9.dashboard.dashboard_app:app --host 127.0.0.1 --port 8092
```
