# Phase 1 — Operations Diagnosis

Front: `FRONT-BRAIN-AGENT-V2-STABILIZE-LOCAL-OPERATION-RUNBOOK-AUTOSTART-01`

## 1. Processes

| Port | PID | Parent | Command | State |
|------|-----|--------|---------|-------|
| 8091 | 140052 | 143528 | `python.exe tmp_agent/brain_v9/start_safe_server.py` → uvicorn `brain_v9.main:app` | RUNNING |
| 8092 | 102348 | 128864 | `python.exe -c "import uvicorn; uvicorn.run('tmp_agent.brain_v9.dashboard.dashboard_app:app', host='127.0.0.1', port=8092, ...)"` | RUNNING |

## 2. Ports

| Port | Listening | Owner PID | Purpose |
|------|-----------|-----------|---------|
| 8091 | yes | 140052 | Brain API |
| 8092 | yes | 102348 | Dashboard |
| 8070 | **no** | — | Legacy dashboard port, **INACTIVE** |

## 3. PID files

| File | Recorded PID | Alive? | Verdict |
|------|--------------|--------|---------|
| `dashboard_only_8092.pid` | 102348 | yes (== 8092 owner) | **VALID** |
| `start_local_browser_operational_launcher.pid` | 73212 | **no** | **STALE** — safe to remove after operator confirmation |

## 4. Launchers

| Launcher | Role | Hardcoded token? | Verdict |
|----------|------|------------------|---------|
| `start_safe_server.py` | Canonical safe 8091 launcher (uvicorn `brain_v9.main:app`, host 127.0.0.1, WindowsSelectorEventLoopPolicy) | **no** | **CLEAN — use as canonical 8091 launcher** |
| `start_8091_wrapper.py` | Thin wrapper: sets `BRAIN_PORT=8091`, execs `start_safe_server.py` | no | CLEAN |
| `start_full_server.py` | Full/autonomy launcher, default port **8090**, enables unsafe dev endpoints + autonomy | no | **NOT for safe local ops** — reference only |
| `start_local_browser_operational.py` | Combined brain+dashboard launcher | **yes** (test token `LOCAL_TOKEN`, line 26 + 101) | **OBSERVATION — prohibited to modify in this front**; documented only |
| `_ops_scratch_dashboard_8092.ps1` | Pre-existing scratch dashboard launcher | yes (same test token) | Pre-existing scratch; not promoted into canonical runbook |
| `_ops_scratch_spawn_dashboard_8092.py` | Pre-existing scratch spawn helper | — | Pre-existing scratch; documented only |

## 5. Logs

| Log | Size | Verdict |
|-----|------|---------|
| `brain_server_stdout.log` | 0 B | empty / current, no crash |
| `brain_server_stderr.log` | 0 B | empty / current, no crash |
| `start_local_browser_operational_dashboard.err.log` | 203 B | clean uvicorn startup on 8092, no errors |
| `start_local_browser_operational_dashboard.log` | 0 B | empty |
| `start_local_browser_operational_brain.log` | 12495 B | no tracebacks, no actual HTTP 429 |

**Crash root cause: NONE.** Both services are running and listening. Logs are clean.

> Note: the literal substring `429` appears in the dashboard access log but only as remote **TCP port numbers** (e.g. `127.0.0.1:56429`), **not** as HTTP 429 status codes.

## 6. Auth / token

- `start_safe_server.py` does **not** hardcode a token — operator supplies `BRAIN_ADMIN_TOKEN` via environment. ✅
- `start_local_browser_operational.py` **does** hardcode a TEST token (`AGENTV2_TEST_ADMIN_TOKEN_*`) — **prohibited to modify in this front**; documented as observation.
- The runbook requires `BRAIN_ADMIN_TOKEN` to be supplied via environment only, never echoed in plaintext, redacted in all status output.

## 7. Provider degraded / HTTP 429

- **Not present in current logs.**
- Historical: provider returned HTTP 429 Too Many Requests in the Brain Chat UI; synthesis improved after funding the model account.
- **What 429 means:** the upstream model provider rejected the request because the account is out of quota / rate-limited / unfunded. It is a **provider-side** limit, **not** a local service failure.

**Safe recovery:**
1. Confirm local services are up (`/health` on 8091 and 8092). Do **not** restart local services unless they are actually down.
2. Check provider dashboard / account quota and funding.
3. Wait and apply exponential backoff before retrying.
4. If a second provider is configured, allow the runtime provider-selector to fail over — do **not** manually edit provider credentials.
5. Inspect the failing run trace (`GET /v2/agent/runs/<run_id>/trace`) to confirm the 429 came from the provider.
6. If degradation persists the runtime returns a deterministic parity finalizer fallback reply — safe (no writes). Continue read-only use until quota is restored.

## 8. Dashboard endpoint analysis observation

**Tag:** `DASHBOARD_ENDPOINT_ANALYSIS_INCOMPLETE_NO_ROUTE_PROBE`

The agent correctly **identified** the dashboard endpoints but did **not** actually execute a live `route_probe` against them, and it **honestly reported** that no live endpoint data was collected.

**Disposition:** operational/planner observation only. Planner logic is **not** repaired in this front. The runbook documents how to actually probe the live dashboard endpoints (Phase 2 + runbook section 16).

## Conclusion

**OPS_DIAGNOSIS_COMPLETED** — both services running, ports healthy, one stale launcher PID file identified (safe to remove after confirmation), one hardcoded test-token observation in a prohibited-to-modify file (documented, not fixed), no current crash, no current HTTP 429. Runbook will supply env-based token handling and a safe 429 recovery procedure.
