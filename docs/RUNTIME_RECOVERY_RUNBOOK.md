# Runtime Recovery and Real Execution Gate Runbook

## Purpose

Recover observability (dashboard/chat/runtime) before any real execution. This
runbook does NOT execute real ingestion, does NOT modify memory/semantic, does
NOT modify FAISS, does NOT execute trading/B8.

## Current State (as of 2026-06-09)

| Service | Port | Status |
|---------|------|--------|
| Ollama | 11434 | UP |
| Brain V9 Server | 8090 | DOWN |
| Open WebUI / Dashboard | 3000 | DOWN |
| Brain Legacy Server | 8010 | DOWN |
| Docker Desktop | N/A | OFF |

Root cause: **services not started** — no code bug detected.

## Recovery Steps

### Step 1 — Verify Prerequisites

```powershell
# Git Bash or PowerShell
curl -sS http://127.0.0.1:11434/api/tags    # Ollama OK
curl -sS http://127.0.0.1:8090/health       # Brain V9 DOWN expected
curl -sS http://127.0.0.1:3000              # Open WebUI DOWN expected
```

### Step 2 — Start Brain V9 Server (port 8090)

```powershell
cd C:\AI_VAULT
python tmp_agent/brain_v9/start_full_server.py
```

Alternative (safe mode on Windows):

```powershell
cd C:\AI_VAULT
python tmp_agent/brain_v9/start_safe_server.py
```

Wait 5-10 seconds, then verify:

```bash
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8090/health     # expect 200
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8090/dashboard  # expect 200
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8090/docs       # expect 200
```

### Step 3 — Start Open WebUI / Dashboard (port 3000)

Requires Docker Desktop running.

1. Start Docker Desktop from Windows Start menu.
2. Wait for Docker daemon ready.
3. Start Open WebUI container:

```powershell
docker start open-webui  # if container exists and was stopped
```

If container does not exist, see existing deployment docs; do NOT recreate
destructively in this runbook.

Verify:

```bash
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:3000  # expect 200
```

### Step 4 — Run Health Check

```powershell
.\scripts\ops\runtime_health_check.ps1
```

Expected output: all services green.

### Step 5 — Confirm Real Execution Gate

Before any real execution, verify:

1. dashboard/chat reachable
2. brain server health 200
3. ollama reachable
4. git working tree clean
5. ROADMAP valid
6. operator approval visible
7. evidence path exists

All conditions must be true for `real_execution_allowed` to become true.

## Architecture Reminder

- **Brain V9 entry**: `tmp_agent/brain_v9/main.py`
- **App**: `brain_v9.main:app` (FastAPI)
- **Host**: `127.0.0.1`
- **Port**: `8090`
- **Health**: `GET /health`, `GET /healthz`, `GET /v1/agent/healthz`
- **Dashboard**: `GET /dashboard`, `GET /dashboard-v2`
- **Chat**: `POST /chat`, `POST /chat/introspectivo`
- **Session**: `tmp_agent/brain_v9/core/session.py`
- **Known launchers**:
  - `tmp_agent/brain_v9/start_full_server.py`
  - `tmp_agent/brain_v9/start_safe_server.py`
  - `tmp_agent/brain_v9/start_brain_v9.bat`

## Startup Order

1. Ollama (usually already running as service)
2. Brain V9 server (port 8090)
3. Open WebUI (port 3000, requires Docker)
4. Health check verification
5. Real execution gate confirmation

## Emergency Contacts / References

- Existing runbook: `docs/runtime_dashboard_chat_runbook.md`
- Runtime entrypoints: `docs/RUNTIME_ENTRYPOINTS.md`
- Real execution policy: `docs/REAL_EXECUTION_POLICY.md`

## Next Front

After recovery complete and health check passes:
FRONT-FIRST-REAL-LOCAL-INGESTION-DRY-RUN-01
