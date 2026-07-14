# FRONT-BRAIN-MAIN-ROUTERS-STARTUP-IMPORT-AUDIT-12G

## Executive verdict

Auditoría **docs-only** sobre import/startup side effects en el sistema
Brain V9. No se modifica runtime, tests, ni workflows.

Objetivo: mapear todos los startup entrypoints, import side effects,
browser/server launchers y superficies de startup antes de cualquier
migración real de `main.py`.

- No trading.
- No dashboard runtime changes.
- No main.py changes.
- No session.py changes.
- No SCVL changes.

## Base state

| Campo | Valor |
|-------|-------|
| Repo | `C:\AI_VAULT_CANONICAL` |
| Branch | `codex/own-capital-sustainable-return` |
| HEAD esperado | `e4beedd` (after 12F commit) |
| Último frente cerrado | 12F (side-effect boundary contract) |
| Frentes 12A–12F | CLOSED / PUSHED / CI GREEN |

## Startup entrypoints

### Core server — `tmp_agent/brain_v9/main.py`

| Element | Line | Type | Risk |
|---------|------|------|------|
| `app = FastAPI(..., lifespan=lifespan)` | 170 | FastAPI app | HIGH |
| `async def lifespan(app)` | 164 | Lifespan context manager | HIGH |
| `asyncio.create_task(_startup_background())` | 165 | Background task on startup | HIGH |
| `_startup_background()` | 4119 | Global mutation: `_agent_executor`, `_startup_done`, `_startup_error` | HIGH |
| `_startup_done` / `_startup_error` | 150-151 | Global mutable state | HIGH |
| `subprocess.run(...)` | 334, 353, 1021 | PowerShell/external calls | HIGH |
| `uvicorn.run(...)` | 4600 | Server launch at `__main__` | HIGH |
| `import subprocess` | 11 | Import with potential side effects | MEDIUM |

**Side effects on import:**
- Module-level globals (`_agent_executor`, `_startup_error`, `_startup_done`,
  `_warmup_task`) are initialized at import time.
- `lifespan` creates a background task that mutates globals.
- `if __name__ == "__main__"` block launches uvicorn.
- `subprocess.run` calls in dashboard helper functions.

### Safe launcher — `tmp_agent/brain_v9/start_safe_server.py`

| Element | Line | Type | Risk |
|---------|------|------|------|
| `uvicorn.run(...)` | 37 | Server launch | MEDIUM |
| ProactorEventLoop setup | 5-12 | Windows event loop config | MEDIUM |

### Browser launcher — `tmp_agent/brain_v9/start_local_browser_operational.py`

| Element | Line | Type | Risk |
|---------|------|------|------|
| `subprocess.Popen(...)` | 60 | Launch child processes | HIGH |
| `subprocess.CREATE_NO_WINDOW` | 68 | Windows-specific flag | MEDIUM |
| `uvicorn.run(...)` via `-c` | 121 | Launch dashboard 8092 | HIGH |
| `subprocess.TimeoutExpired` | 158, 176 | Timeout handling | MEDIUM |

**Side effects on execution:**
- Launches dashboard server as child process.
- Opens browser to dashboard URL.
- Creates log files.

### Dashboard app — `tmp_agent/brain_v9/dashboard/dashboard_app.py`

| Element | Line | Type | Risk |
|---------|------|------|------|
| `app = FastAPI(...)` | 14 | FastAPI app (port 8092) | MEDIUM |
| `app.include_router(router)` | 15 | Router inclusion | MEDIUM |
| `@app.get("/")` | 19 | Root endpoint | LOW |
| `@app.get("/health")` | 24 | Health endpoint | LOW |

### UI proxy — `tmp_agent/ui_proxy_server.py`

| Element | Line | Type | Risk |
|---------|------|------|------|
| `app = FastAPI(...)` | 9 | FastAPI app (port 8010) | MEDIUM |
| `OLLAMA_BASE` / `BRAIN_BASE` | 10-11 | Module-level env vars | LOW |
| `@app.api_route("/proxy/{full_path:path}")` | 529 | Generic proxy | MEDIUM |

## Import side-effect candidates

### High risk — module-level mutation or subprocess

| File | Pattern | Risk |
|------|---------|------|
| `main.py` | Module-level globals (`_startup_done`, etc.) | HIGH |
| `main.py` | `subprocess.run` in dashboard helpers | HIGH |
| `main.py` | `uvicorn.run()` at `__main__` | HIGH |
| `start_local_browser_operational.py` | `subprocess.Popen` for child processes | HIGH |
| `start_safe_server.py` | `uvicorn.run` at module level | MEDIUM |

### Medium risk — FastAPI app definition (import-time side effects)

| File | Pattern | Risk |
|------|---------|------|
| `main.py` | `app = FastAPI(...)` at module level | MEDIUM |
| `dashboard_app.py` | `app = FastAPI(...)` at module level | MEDIUM |
| `ui_proxy_server.py` | `app = FastAPI(...)` at module level | MEDIUM |

### Low risk — read-only module definitions

| File | Pattern | Risk |
|------|---------|------|
| `main.py` | Router imports (trading, autonomy, etc.) | LOW |
| `api_adapter.py` | `APIRouter` definitions | LOW |
| `openai_compat.py` | `APIRouter` definitions | LOW |
| `autonomy/router.py` | `APIRouter` definitions | LOW |
| `dashboard_routes.py` | `APIRouter` definitions | LOW |
| `canary_lookup_read_only.py` | `APIRouter` definitions | LOW |
| `knowledge_read_api.py` | `APIRouter` definitions | LOW |

## Browser/server launchers

| File | Behavior | Risk |
|------|----------|------|
| `start_local_browser_operational.py` | Launches dashboard 8092 + opens browser | HIGH |
| `start_safe_server.py` | Launches uvicorn with ProactorEventLoop | MEDIUM |
| `main.py` `__main__` block | `uvicorn.run(app, ...)` | HIGH |

## Dashboard startup surface

- `dashboard_app.py` defines FastAPI app + includes `dashboard_routes.router`.
- `start_local_browser_operational.py` launches dashboard as child process
  via `uvicorn.run('tmp_agent.brain_v9.dashboard.dashboard_app:app', ...)`.
- No lifespan or startup event in dashboard_app itself.

## UI proxy startup surface

- `ui_proxy_server.py` defines FastAPI app at module level.
- No lifespan, no startup events, no uvicorn.run (launched externally).
- Module-level env var reads: `BRAIN_BASE`, `OLLAMA_BASE`.

## Blocked trading startup surface

| File | Element | Risk |
|------|---------|------|
| `trading/pocketoption_bridge_server.py` | `FastAPI(...)` | BLOCKED |
| `trading/pocketoption_bridge_server.py` | `@app.on_event("startup")` | BLOCKED |
| `trading/pocketoption_bridge_server.py` | `uvicorn.run(app, ...)` | BLOCKED |

Trading servers are **BLOCKED** and must not be touched during
non-trading fronts.

## Legacy/archive startup files

| File | Risk |
|------|------|
| `brain_server.py` | LOW (legacy, not V9) |
| `brain_server_clean.py` | LOW |
| `brain_server_simple.py` | LOW |
| `brain_server_working.py` | LOW |
| `brain_server_backup_*.py` | LOW |
| `advisor_server_clean.py` | LOW |
| `dashboard_enhanced.py` | LOW |
| `00_identity/*` | LOW (legacy identity system) |

These files should not guide runtime decisions. They are historical
artifacts.

## No-touch confirmation

Esta auditoría **no toca**:

- Runtime Python productivo
- Tests
- Workflows
- `session.py`
- SCVL
- Semantic memory
- FAISS
- Dashboard runtime
- `main.py`
- Trading/QC/IBKR
- Memory/semantic runtime data
- Curated ingestion/promotion
- `dry_run_only`
- Rooms
- Untracked preexistentes

Único archivo creado: `docs/audit/STARTUP_IMPORT_SIDE_EFFECT_AUDIT_12G.md`

## Recommended next front

```
FRONT-BRAIN-MAIN-ROUTES-HEALTH-STATUS-SPLIT-13A
```

**Tipo:** Runtime migration (small extraction only).

**Requisitos:**
- Contract green (12B–12F all PASS).
- One small extraction only — move health/status endpoints from `main.py`
  to a new `routes/health_status.py` router module.
- No behavior change.
- No dashboard.
- No session.py.
- No trading.
- No SCVL.
- Full parity tests required.
- No new endpoints.
- No new side effects.