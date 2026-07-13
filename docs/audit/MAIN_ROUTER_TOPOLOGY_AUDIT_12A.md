# FRONT-BRAIN-MAIN-ROUTERS-TOPOLOGY-AUDIT-12A

## Executive verdict

Auditoría **docs-only**. No se modifica runtime, tests, ni workflows.
Objetivo: preparar el próximo batch de router/entrypoint hardening.

- No trading.
- No dashboard runtime changes.
- No main.py changes.
- No session.py changes.
- No SCVL changes.

Esta auditoría mapea la topología de routers, entrypoints y superficies
HTTP del sistema Brain V9 para identificar candidatos seguros para
futuros batches de refactor/hardening.

## Base state

| Campo | Valor |
|-------|-------|
| Repo | `C:\AI_VAULT_CANONICAL` |
| Branch | `codex/own-capital-sustainable-return` |
| HEAD esperado | `2b417ce` |
| origin esperado | `2b417ce` |
| Último frente cerrado | 11D-C (Ollama session diagnostic hint) |
| Frente diferido | 11D-D (trading/qc_iteration_engine.py — BLOCKED) |

## Router / entrypoint inventory

| File | Category | Evidence | Risk | Notes |
|------|----------|----------|------|-------|
| `tmp_agent/brain_v9/main.py` | CANONICAL_SERVER_ENTRYPOINT | `FastAPI(title="Brain Chat V9")` + 169 `@app.` endpoints + `uvicorn.run()` | HIGH | Monolito principal: 4600+ líneas, define app + 7 `include_router` + ~40 endpoints directos |
| `tmp_agent/brain_v9/start_safe_server.py` | CANONICAL_SERVER_ENTRYPOINT | `uvicorn.run(...)` launcher | MEDIUM | Launcher alternativo con ProactorEventLoop |
| `tmp_agent/brain_v9/start_local_browser_operational.py` | CHAT_UI_ENTRYPOINT | Lanza dashboard en 8092 + browser | MEDIUM | Startup side effects: abre browser, arranca servidor |
| `tmp_agent/ui_proxy_server.py` | CHAT_UI_ENTRYPOINT | `FastAPI(title="BrainLab UI Proxy")` + 6 endpoints | MEDIUM | Proxy UI con `/ui`, `/healthz`, `/proxy/{path}`, `/ui/ollama_plan` |
| `tmp_agent/brain_v9/dashboard/dashboard_app.py` | DASHBOARD_SURFACE | `FastAPI(title="Brain Persistent Autonomy Dashboard")` + `include_router` + 2 endpoints | MEDIUM | App FastAPI separada para dashboard 8092 |
| `tmp_agent/brain_v9/dashboard/dashboard_routes.py` | DASHBOARD_SURFACE | `APIRouter(prefix="/brain-dashboard")` + 14 endpoints | MEDIUM | Rutas de dashboard: status, activity, chat, chat/stream, agent-v2 |
| `tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py` | AGENT_API_SURFACE | `APIRouter(prefix="/v2/agent")` + `APIRouter(prefix="/v2/chat")` + 15 endpoints | MEDIUM | Agent V2 API: capabilities, status, runs CRUD, trace, chat |
| `tmp_agent/brain_v9/api/openai_compat.py` | AGENT_API_SURFACE | `APIRouter(prefix="/v1")` + 2 endpoints | MEDIUM | OpenAI-compatible: `/v1/models`, `/v1/chat/completions` |
| `tmp_agent/brain_v9/autonomy/router.py` | AGENT_API_SURFACE | `APIRouter(prefix="/autonomy")` + 6 endpoints | MEDIUM | Autonomy: status, cycle, reports, start, stop |
| `tmp_agent/brain_v9/routes/canary_lookup_read_only.py` | HEALTH_STATUS_SURFACE | `APIRouter(tags=["read-only"])` + 1 endpoint | LOW | Read-only canary lookup |
| `tmp_agent/brain_v9/routes/knowledge_read_api.py` | HEALTH_STATUS_SURFACE | `APIRouter(tags=["knowledge"])` + 1 endpoint | LOW | Knowledge read API |
| `tmp_agent/brain_v9/trading/router.py` | BLOCKED_TRADING | `APIRouter(prefix="/trading")` + 11 endpoints | BLOCKED | Trading: health, policy, IBKR, orders, market — BLOCKED |
| `tmp_agent/brain_v9/trading/pocketoption_bridge_server.py` | BLOCKED_TRADING | `FastAPI(title="PocketOption Bridge")` | BLOCKED | Bridge server — BLOCKED |
| `tmp_agent/brain_server.py` | LEGACY_OR_ARCHIVE | `FastAPI(...)` legacy | LOW | Legacy brain server (no V9) |
| `tmp_agent/brain_server_clean.py` | LEGACY_OR_ARCHIVE | `FastAPI(...)` legacy | LOW | Legacy |
| `tmp_agent/brain_server_simple.py` | LEGACY_OR_ARCHIVE | `FastAPI(...)` legacy | LOW | Legacy |
| `tmp_agent/brain_server_working.py` | LEGACY_OR_ARCHIVE | `FastAPI(...)` legacy | LOW | Legacy |
| `tmp_agent/brain_server_backup_*.py` | LEGACY_OR_ARCHIVE | Backup files | LOW | Backups históricos |
| `tmp_agent/advisor_server_clean.py` | LEGACY_OR_ARCHIVE | `FastAPI(...)` legacy | LOW | Legacy advisor |
| `tmp_agent/dashboard_enhanced.py` | LEGACY_OR_ARCHIVE | `FastAPI(...)` legacy | LOW | Legacy dashboard |
| `00_identity/*` | LEGACY_OR_ARCHIVE | Sistema de identidad legacy | LOW | No runtime V9 |
| `tmp_agent/brain_v9/_debug_server.py` | DEV_OR_DEBUG_SURFACE | Debug server (untracked) | HIGH | Debug — debe quedar controlado |

## Endpoint map

| Endpoint / Pattern | File | Handler / Symbol | Surface | Risk |
|--------------------|------|-----------------|---------|------|
| `POST /chat` | `main.py:1438` | `@app.post` | Chat | HIGH |
| `POST /chat/introspectivo` | `main.py:1213` | `@app.post` | Chat | HIGH |
| `GET /chat/introspectivo/debug` | `main.py:1187` | `@app.get` | Dev/Debug | HIGH |
| `GET /health` | `main.py:1078` | `@app.get` | Health | LOW |
| `GET /status` | `main.py:1091` | `@app.get` | Health | LOW |
| `GET /healthz` | `main.py:1101` | `@app.get` | Health | LOW |
| `GET /v1/agent/healthz` | `main.py:1106` | `@app.get` | Health | LOW |
| `GET /v1/agent/status` | `main.py:1111` | `@app.get` | Health | LOW |
| `GET /dashboard` | `main.py:242` | `@app.get` | UI | MEDIUM |
| `GET /dashboard-v2` | `main.py:252` | `@app.get` | UI | MEDIUM |
| `GET /brain-dashboard/agent-v2/status` | `main.py:1125` | `@app.get` | Dashboard | MEDIUM |
| `GET /brain/operating-context` | `main.py:1147` | `@app.get` | Health | LOW |
| `GET /brain/maintenance/status` | `main.py:1155` | `@app.get` | Health | LOW |
| `POST /brain/maintenance/action` | `main.py:1160` | `@app.post` | Dev | MEDIUM |
| `DELETE /sessions/{session_id}` | `main.py:1920` | `@app.delete` | Session mgmt | MEDIUM |
| `POST /gate/approve/{pending_id}` | `main.py:1934` | `@app.post` | Governance | HIGH |
| `POST /gate/reject/{pending_id}` | `main.py:1974` | `@app.post` | Governance | HIGH |
| `POST /tool01/permission/approve` | `main.py:1985` | `@app.post` | Tool01 | HIGH |
| `GET /tool01/permission/pending/{session_id}` | `main.py:2028` | `@app.get` | Tool01 | MEDIUM |
| `GET /tool01/permission/grants/{session_id}` | `main.py:2040` | `@app.get` | Tool01 | MEDIUM |
| `DELETE /sessions/{session_id}/memory` | `main.py:2059` | `@app.delete` | Memory | HIGH |
| `GET /brain/health` | `main.py:2071` | `@app.get` | Health | LOW |
| `GET /brain/security/posture` | `main.py:2076` | `@app.get` | Health | LOW |
| `GET /brain/risk/status` | `main.py:2087` | `@app.get` | Health | LOW |
| `GET /brain/governance/health` | `main.py:2092` | `@app.get` | Health | LOW |
| `GET /brain/metrics` | `main.py:2096` | `@app.get` | Metrics | LOW |
| `GET /brain/validators` | `main.py:2104` | `@app.get` | Health | LOW |
| `GET /brain/learned/patterns` | `main.py:2154` | `@app.get` | Knowledge | LOW |
| `GET /tools/coverage` | `main.py:2305` | `@app.get` | Health | LOW |
| `GET /brain/mutations` | `main.py:2325` | `@app.get` | Mutation audit | MEDIUM |
| `POST /brain/mutations/{id}/rollback` | `main.py:2353` | `@app.post` | Mutation | HIGH |
| `GET /brain/health_gate/status` | `main.py:2369` | `@app.get` | Health | LOW |
| `GET /brain/reasoning/history` | `main.py:2380` | `@app.get` | Health | LOW |
| `POST /brain/mutations/test_apply` | `main.py:2392` | `@app.post` | Mutation | HIGH |
| `GET /v2/agent/capabilities` | `api_adapter.py:68` | `@router.get` | Agent V2 | MEDIUM |
| `GET /v2/agent/status` | `api_adapter.py:88` | `@router.get` | Agent V2 | MEDIUM |
| `GET/POST /v2/agent/runs` | `api_adapter.py:115,119` | `@router` | Agent V2 | MEDIUM |
| `POST /v2/agent/runs/{id}/execute` | `api_adapter.py:135` | `@router.post` | Agent V2 | HIGH |
| `POST /v2/chat/agent` | `api_adapter.py:187` | `@chat_router.post` | Agent V2 Chat | HIGH |
| `GET /v1/models` | `openai_compat.py:125` | `@router.get` | OpenAI compat | LOW |
| `POST /v1/chat/completions` | `openai_compat.py:136` | `@router.post` | OpenAI compat | MEDIUM |
| `GET /autonomy/status` | `autonomy/router.py:20` | `@router.get` | Autonomy | LOW |
| `POST /autonomy/start` | `autonomy/router.py:35` | `@router.post` | Autonomy | HIGH |
| `POST /autonomy/stop` | `autonomy/router.py:41` | `@router.post` | Autonomy | HIGH |
| `GET /brain-dashboard/status` | `dashboard_routes.py:602` | `@router.get` | Dashboard | LOW |
| `POST /brain-dashboard/chat` | `dashboard_routes.py:727` | `@router.post` | Dashboard | MEDIUM |
| `POST /brain-dashboard/chat/stream` | `dashboard_routes.py:853` | `@router.post` | Dashboard | MEDIUM |
| `GET /brain-dashboard/agent-v2/status` | `dashboard_routes.py:1040` | `@router.get` | Dashboard | LOW |
| `GET /brain/read-only/canary` | `canary_lookup_read_only.py:35` | `@router.get` | Read-only | LOW |
| `GET /brain/knowledge/read` | `knowledge_read_api.py:34` | `@router.get` | Knowledge | LOW |
| `GET /ui` | `ui_proxy_server.py:519` | `@app.get` | UI Proxy | MEDIUM |
| `GET /healthz` | `ui_proxy_server.py:525` | `@app.get` | UI Proxy | LOW |
| `* /proxy/{path}` | `ui_proxy_server.py:529` | `@app.api_route` | UI Proxy | MEDIUM |
| `POST /ui/ollama_plan` | `ui_proxy_server.py:546` | `@app.post` | UI Proxy | MEDIUM |
| `GET /` | `dashboard_app.py:19` | `@app.get` | Dashboard 8092 | LOW |
| `GET /health` | `dashboard_app.py:24` | `@app.get` | Dashboard 8092 | LOW |
| `GET /trading/health` | `trading/router.py:57` | `@router.get` | Trading | BLOCKED |
| `POST /trading/trade` | `trading/router.py:151` | `@router.post` | Trading | BLOCKED |

## Runtime surface map

### Core server

- **`tmp_agent/brain_v9/main.py`** — FastAPI app principal (port 8090/8091).
  Define `app = FastAPI(title="Brain Chat V9")`, incluye 7 routers via
  `include_router`, y define ~40 endpoints directos (`@app.get/post/delete`).
  Arranca con `uvicorn.run()` al final del archivo. **4600+ líneas.**
- **`tmp_agent/brain_v9/start_safe_server.py`** — Launcher alternativo que
  usa `uvicorn.run` con ProactorEventLoop para Windows.
- **Imports de routers en main.py:**
  - `trading_router` from `brain_v9.trading.router`
  - `autonomy_router` from `brain_v9.autonomy.router`
  - `canary_lookup_read_only_router` from `brain_v9.routes.canary_lookup_read_only`
  - `knowledge_read_api_router` from `brain_v9.routes.knowledge_read_api`
  - `openai_compat_router` from `brain_v9.api.openai_compat`
  - `agent_v2_router` + `agent_v2_chat_router` from `brain_v9.core.agent_kernel_v2.api_adapter`
  - `upgrade_router` (conditional)

### Chat/UI

- **`tmp_agent/ui_proxy_server.py`** — Proxy FastAPI para UI (port 8010).
  Sirve `/ui` (HTML), `/healthz`, `/proxy/{path}` (proxy genérico),
  `/ui/ollama_plan`, `/ui/api/apply`, `/ui/api/reject`.
- **`tmp_agent/brain_v9/start_local_browser_operational.py`** — Launcher
  que arranca dashboard en 8092 y abre browser.

### Dashboard

- **`tmp_agent/brain_v9/dashboard/dashboard_app.py`** — FastAPI app separada
  para dashboard (port 8092). Incluye `dashboard_routes.router`.
  Endpoints: `/`, `/health`.
- **`tmp_agent/brain_v9/dashboard/dashboard_routes.py`** — Router con
  prefix `/brain-dashboard`, 14 endpoints: status, activity,
  promotion-queue, scheduler, safety, trading-live, control (run/pause/
  resume/stop), chat, chat/stream, agent-v2 runs/trace/status.

### Agent API

- **`tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py`** — Router
  `/v2/agent` (15 endpoints) + `/v2/chat` (1 endpoint). Requiere
  `require_strict_operator_access`. Capacabilities, status, runs CRUD,
  trace, operator-presets, maintenance/modes, chat.
- **`tmp_agent/brain_v9/api/openai_compat.py`** — Router `/v1`
  (2 endpoints). OpenAI-compatible: models, chat/completions. Requiere
  `require_strict_operator_access`.
- **`tmp_agent/brain_v9/autonomy/router.py`** — Router `/autonomy`
  (6 endpoints). Status, cycle, reports, start, stop.

### Health/status

- Endpoints directos en `main.py`: `/health`, `/status`, `/healthz`,
  `/v1/agent/healthz`, `/v1/agent/status`, `/brain/health`,
  `/brain/security/posture`, `/brain/risk/status`,
  `/brain/governance/health`, `/brain/metrics`, `/brain/validators`,
  `/brain/health_gate/status`, `/tools/coverage`.
- Read-only routers: `canary_lookup_read_only.py` (1 endpoint),
  `knowledge_read_api.py` (1 endpoint).

### Dev/debug

- **`tmp_agent/brain_v9/_debug_server.py`** — Debug server (untracked).
  Debe quedar controlado/bloqueado.
- **`/chat/introspectivo/debug`** — Endpoint de debug en main.py.
- **`/brain/maintenance/action`** — Action endpoint con side effects.
- **`/brain/mutations/test_apply`** — Test apply de mutaciones.
- **`/brain/mutations/{id}/rollback`** — Rollback de mutaciones.

### Legacy/archive

- `tmp_agent/brain_server.py`, `brain_server_clean.py`,
  `brain_server_simple.py`, `brain_server_working.py`,
  `brain_server_backup_*.py` — Legacy servers (no V9).
- `tmp_agent/advisor_server_clean.py` — Legacy advisor.
- `tmp_agent/dashboard_enhanced.py` — Legacy dashboard.
- `00_identity/*` — Sistema de identidad legacy completo.
- `tmp_agent/dashboard_v2_r105_audit_evidence/` — Evidence dump histórico.

### Trading blocked

- **`tmp_agent/brain_v9/trading/router.py`** — Router `/trading`
  (11 endpoints): health, policy, IBKR health, paper-order-check, market,
  balance, trades, trade, pocket-option demo. **BLOCKED.**
- **`tmp_agent/brain_v9/trading/pocketoption_bridge_server.py`** —
  FastAPI bridge server. **BLOCKED.**

## Risk classification

### LOW

- Docs/test-only files.
- Simple health/status endpoints (`/health`, `/healthz`, `/status`).
- Read-only diagnostics (`/brain/metrics`, `/brain/validators`).
- Read-only routers (`canary_lookup_read_only`, `knowledge_read_api`).
- Legacy/archive files (no runtime V9).

### MEDIUM

- UI proxy (`ui_proxy_server.py`) — proxy con endpoints genéricos.
- Chat route (`POST /chat`) —入口 principal con session/memory side effects.
- Dashboard routes — chat/stream, control de autonomy.
- Agent V2 API read endpoints (capabilities, status, runs list).
- OpenAI compat `/v1/chat/completions` — LLM proxy.

### HIGH

- `main.py` monolito — 4600+ líneas, 169 `@app.` decorators, mezcla
  app definition + endpoints + routers + startup + uvicorn.run.
- Startup side effects (`start_local_browser_operational.py`).
- Governance endpoints (`/gate/approve`, `/gate/reject`).
- Tool01 permission endpoints (`/tool01/permission/approve`).
- Memory mutation endpoints (`DELETE /sessions/{id}/memory`).
- Mutation endpoints (`/brain/mutations/test_apply`, rollback).
- Autonomy control (`/autonomy/start`, `/autonomy/stop`).
- Agent V2 execute (`POST /v2/agent/runs/{id}/execute`).
- Dev/debug endpoints (`/chat/introspectivo/debug`).

### BLOCKED

- `tmp_agent/brain_v9/trading/router.py` — Trading/QC/IBKR.
- `tmp_agent/brain_v9/trading/pocketoption_bridge_server.py` — Bridge.
- Cualquier archivo bajo `tmp_agent/brain_v9/trading/`.
- Execution gates, real order placement, financial autonomy.

## No-touch confirmation

Esta auditoría **no toca**:

- Runtime Python productivo
- Tests
- Workflows
- `session.py`
- SCVL (`session_scvl_gate.py`, `scvl_promotion_gate.py`)
- Semantic memory (`semantic_memory_faiss.py`)
- FAISS files
- Dashboard runtime (`dashboard_app.py`, `dashboard_routes.py`)
- `main.py`
- Trading/QC/IBKR
- Memory/semantic runtime data
- Curated ingestion/promotion
- `dry_run_only`
- Rooms
- Untracked preexistentes

Único archivo creado: `docs/audit/MAIN_ROUTER_TOPOLOGY_AUDIT_12A.md`

## Recommended next front

```
FRONT-BRAIN-MAIN-ROUTERS-READONLY-CONTRACT-12B
```

**Objetivo futuro:**
- Crear test/contract read-only que valide el inventario de routers.
- No refactor todavía.
- Bloquear dev/debug accidental.
- Confirmar qué endpoints existen y cuáles son read-only.
- Validar que routers bloqueados (trading) no se hayan activado
  accidentalmente.

**Reglas futuras:**
- No tocar main.py.
- No tocar trading.
- No tocar dashboard runtime.
- No tocar session.py.
- Sólo crear test/contract + opcionalmente workflow update.

**Alternativa si la superficie está muy dispersa:**
`FRONT-BRAIN-MAIN-ROUTERS-DECISION-MATRIX-12B` — docs-only matrix
para decidir si se ataca main.py, UI proxy o dashboard primero.