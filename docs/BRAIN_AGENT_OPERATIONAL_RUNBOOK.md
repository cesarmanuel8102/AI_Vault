# Brain Agent Operational Runbook

## Starting Brain 8091 (Agent V2 Backend)

### Manual Start
```powershell
cd C:\AI_VAULT_CANONICAL
$env:PYTHONPATH = "C:\AI_VAULT_CANONICAL"
python -m uvicorn brain_v9.main:app --host 127.0.0.1 --port 8091 --log-level info
```

### Scripted Start
```powershell
powershell -ExecutionPolicy Bypass -File scripts\brain\restart_brain_8091_agent_v2.ps1
```

## Starting Dashboard 8092

### Manual Start
```powershell
cd C:\AI_VAULT_CANONICAL
$env:PYTHONPATH = "C:\AI_VAULT_CANONICAL"
python -m uvicorn tmp_agent.brain_v9.dashboard.dashboard_app:app --host 127.0.0.1 --port 8092 --log-level info
```

### Scripted Start
```powershell
powershell -ExecutionPolicy Bypass -File scripts\brain\restart_dashboard_8092_agent_v2.ps1
```

## Testing /v2/chat/agent

```bash
curl -X POST http://127.0.0.1:8091/v2/chat/agent \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Audit git status and report",
    "mode": "read_only",
    "user_id": "operator_name"
  }'
```

Expected response:
```json
{
  "ok": true,
  "run_id": "agv2_xxxx",
  "final_answer": "...",
  "provider_metadata": {
    "model_used": "kimi-k2.6:cloud",
    "provider_degraded": false
  },
  "trace_url": "/v2/agent/runs/agv2_xxxx/trace"
}
```

## Testing 8092 Dashboard Agent V2

### If working (after zombie resolved)
```bash
curl http://127.0.0.1:8092/brain-dashboard/agent-v2/status
```

### If 404 (zombie active)
- **Symptom:** `HTTP Error 404: Not Found`
- **Cause:** Windows TCP socket zombie (PID 183024) holding port 8092 with dead process
- **Workaround:** Use 8091 endpoint: `curl http://127.0.0.1:8091/brain-dashboard/agent-v2/status`

## What to do if 8092 gives 404

1. **Check process:**
   ```powershell
   Get-NetTCPConnection -LocalPort 8092 -State Listen
   ```

2. **If PID not found by Get-Process:**
   - Windows TCP socket zombie detected
   - **Solution:** Reboot Windows
   - After reboot, run: `scripts\brain\restart_dashboard_8092_agent_v2.ps1`

3. **Verify after restart:**
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\brain\probe_dashboard_8092_agent_v2.ps1
   ```

## How to know what process occupies port 8092

```powershell
# Get listening PID
netstat -ano | findstr 8092

# Get process details (if PID exists)
Get-Process -Id <PID>

# If Get-Process fails = ZOMBIE
```

## Using Brain Agent V2 for Audit Tasks

Agent V2 is configured for read-only audit tasks:
- `repo_status_read`: Check git status
- `file_read`: Read safe text files
- `grep_search`: Search repository
- `route_probe`: Probe HTTP endpoints
- `semantic_retrieve`: Read-only memory retrieval

### Example audit task
```bash
curl -X POST http://127.0.0.1:8091/v2/chat/agent \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Audit repository state, check for dirty files and verify HEAD",
    "mode": "read_only",
    "user_id": "auditor"
  }'
```

## Limitations (Approval-Gated)

Agent V2 operates with these safety gates:

| Action | Requires Approval | Mode Required |
|---|---|---|
| Read files | No | read_only, dry_run |
| Search repo | No | read_only, dry_run |
| Probe routes | No | read_only, dry_run |
| Write reports | No | dry_run, approval_required |
| Apply patches | Yes | approval_required |
| Git commit | Yes | approval_required |
| File delete | Yes | approval_required |

**Important:** Agent V2 will NOT autonomously modify files, commit to git, or delete data without explicit human approval. All write operations require `mode: "approval_required"` or `mode: "write_allowed"`.

## Scripts Quick Reference

| Script | Purpose |
|---|---|
| `scripts/brain/restart_brain_8091_agent_v2.ps1` | Restart Brain on 8091 |
| `scripts/brain/restart_dashboard_8092_agent_v2.ps1` | Restart Dashboard on 8092 |
| `scripts/brain/probe_agent_v2_live.ps1` | Verify Agent V2 on 8091 |
| `scripts/brain/probe_dashboard_8092_agent_v2.ps1` | Verify Dashboard on 8092 |
| `scripts/brain/start_brain_stack_agent_v2.ps1` | Start both 8091 + 8092 |

## Legacy Compatibility
- 8091 `/chat` (legacy conversational) - preserved
- 8091 `/ui/` - Chat UI - preserved
- 8091 `/dashboard` - Command Center - preserved
- All legacy endpoints remain functional alongside Agent V2.

