# Runtime Dashboard and Chat Recovery Runbook

## Status
- **branch**: codex/own-capital-sustainable-return
- **head**: ba004f5c
- **date**: 2026-06-07

## Problem Statement
Dashboard and chat reported as "not alive" by operator.

## Root Cause
Process **not running** — no code bug detected.
- Server import works: `IMPORT_OK`
- Manual startup works: `/health` returns 200
- `start_brain_v9.bat` exists but was not launched

## Architecture

### Backend
- **Entry point**: `tmp_agent/brain_v9/main.py`
- **App**: `brain_v9.main:app` (FastAPI)
- **Host**: `127.0.0.1`
- **Port**: `8090`
- **Runners**:
  - `tmp_agent/brain_v9/start_full_server.py` — full mode
  - `tmp_agent/brain_v9/start_safe_server.py` — safe mode (WindowsSelectorEventLoopPolicy)
  - `tmp_agent/brain_v9/start_brain_v9.bat` — legacy bat

### Dashboard
- **Files**: `tmp_agent/brain_v9/ui/dashboard.html`, `index.html`
- **Endpoint**: `GET /dashboard` and `GET /dashboard-v2`
- **Static files**: served at `/ui` via FastAPI StaticFiles

### Chat
- **Endpoint**: `POST /chat`
- **Introspective endpoint**: `POST /chat/introspectivo`
- **Session**: `brain_v9/core/session.py`
- **Tools**: 113 tools registered

### Health
- `/health` → HTTP 200 when alive
- `/healthz`
- `/v1/agent/healthz`
- `/brain/health`

## Startup Scripts

### Simple (existing)
```batch
cd /d "C:\AI_VAULT\tmp_agent\brain_v9"
start "BrainV9" /MIN python -m uvicorn main:app --host 127.0.0.1 --port 8090
```

### New PowerShell (recommended)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\runtime\start_dashboard_and_chat.ps1
```

Features:
- Checks if already running
- Waits for health endpoint
- Logs output
- Safe restart flag

## Smoke Verification

After starting server, verify:
```bash
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8090/health     # expected: 200
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8090/dashboard  # expected: 200
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8090/docs       # expected: 200
```

## Files Changed
- `scripts/runtime/start_dashboard_and_chat.ps1` — NEW
- `tmp_agent/brain_v9/start_brain_v9.bat` — exists, not modified
- `tmp_agent/brain_v9/main.py` — NOT modified (only tracked preexisting changes)

## Protected Paths Status
- memory/semantic — NOT touched
- FAISS — NOT touched (faiss loads at runtime, no writes)
- tmp_agent/strategies — NOT touched
- trading/B8 — NOT touched
- tmp_agent/brain_v9/main.py — NOT modified beyond preexisting changes
- tmp_agent/brain_v9/core/session.py — NOT touched
- brain/curated_runtime_lookup.py — NOT touched

## Verification
- [x] Import OK
- [x] Health endpoint 200
- [x] Dashboard endpoint 200
- [x] No token leak
- [x] No persistent writes

## Next Steps
1. Start server with `scripts/runtime/start_dashboard_and_chat.ps1`
2. Verify dashboard at `http://127.0.0.1:8090/dashboard`
3. Verify chat at `POST http://127.0.0.1:8090/chat`
4. Optional: Create systemd service or Windows Task Scheduler entry for auto-restart

## Recommended Next Front
SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-GENERATION-PLAN-DRY-RUN-01
(runtime recovery complete; dashboard/chat now diagnosable and bootable)
