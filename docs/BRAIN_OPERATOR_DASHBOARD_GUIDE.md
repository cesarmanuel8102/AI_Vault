# Brain Operator Dashboard Guide

## Overview

The Brain Operator Dashboard provides a human-friendly view into the Brain Persistent Autonomy system. It replaces raw JSON dumps with operator-readable panels, cards, timelines, and explicit safety messages.

## URL

http://127.0.0.1:8092/

## Panels

### Header
- **Mode badge**: Shows Running (green), Paused (yellow), Stopped (red), or Safe Mode (yellow).
- **Scheduler badge**: Enabled or Disabled.
- **Heartbeat badge**: Time since last Brain heartbeat.
- **Next run badge**: Next scheduled autonomy run if available.

### Status Cards
Six cards show the health of:
1. Brain API
2. Kimi Provider
3. Dashboard itself
4. Scheduler
5. Autonomy state
6. Memory (journal event count)

### What Brain is Doing Now
- Current state (idle/running/paused/stopped)
- Cycle identifier
- Last run time and result
- Next scheduled run
- Last error if any

### Recent Activity Timeline
- Last 10 autonomous journal events
- Color-coded by severity
- Shows category, source cycle, summary, confidence
- No raw chain-of-thought exposed

### Memory Panel
- Autonomous journal count
- Promotion queue count
- Semantic staging count
- Promotion audit count
- Canonical semantic lines (read-only)
- FAISS IDs (read-only)
- Explicit safety message confirming canonical memory is NOT modified automatically

### Promotion Queue
- Lists pending candidates awaiting human review
- Shows ID, category, confidence
- Status badge: "Pending human review"
- Does NOT auto-promote

### Scheduler Panel
- Task exists: Yes/No
- Enabled: Yes/No
- State: Ready/Running/Disabled
- Action path to script

### Controls
- **Run Once**: Triggers a single autonomy cycle
- **Pause**: Stops autonomy until resumed (requires confirmation)
- **Resume**: Clears pause and stop flags
- **Stop**: Halts autonomy (requires confirmation)
- **Refresh**: Reloads all panels

### Chat with Brain
- Type a message and click Send
- Displays answer and metadata:
  - Provider selected
  - Model selected
  - Fallback used
  - CoT leak blocked

### Operator Recommendation
- Dynamic suggestions based on current state
- Alerts for promotion queue, stale heartbeat, high fallback rate
- Green/yellow/red severity badges

## How to Restart Dashboard

If the dashboard is not responding:

```powershell
# Find process
Get-Process python | Where-Object {$_.CommandLine -like "*dashboard_app:app*"}

# Stop it
Stop-Process -Name python -Force

# Restart
$env:PYTHONPATH="C:\AI_VAULT_CANONICAL;C:\AI_VAULT_CANONICAL\tmp_agent"
cd C:\AI_VAULT_CANONICAL
python -m uvicorn tmp_agent.brain_v9.dashboard.dashboard_app:app --host 127.0.0.1 --port 8092
```

## Safety Guarantees

- Canonical semantic memory lines: 1715 (unchanged)
- FAISS IDs: 1616 (unchanged)
- Trading module: untouched
- B8 module: untouched
- Secrets: not exposed
- No raw chain-of-thought in UI

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| /brain-dashboard/status | GET | Full operator status |
| /brain-dashboard/activity | GET | Last 10 journal events |
| /brain-dashboard/scheduler | GET | Scheduler task details |
| /brain-dashboard/safety | GET | Safety snapshot |
| /brain-dashboard/promotion-queue | GET | Pending candidates |
| /brain-dashboard/control/run-once | POST | Trigger run |
| /brain-dashboard/control/pause | POST | Pause autonomy |
| /brain-dashboard/control/resume | POST | Resume autonomy |
| /brain-dashboard/control/stop | POST | Stop autonomy |
| /brain-dashboard/chat | POST | Chat with Brain |
