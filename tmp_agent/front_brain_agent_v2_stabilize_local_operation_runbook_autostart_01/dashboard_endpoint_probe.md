# Phase 2 — Dashboard Endpoint Probe

Front: `FRONT-BRAIN-AGENT-V2-STABILIZE-LOCAL-OPERATION-RUNBOOK-AUTOSTART-01`

**Method:** read-only HTTP GET probes via `_probe_endpoints.ps1` (Invoke-WebRequest, 8s timeout).
**Auth header used:** `X-Brain-Token` (the canonical header per `tmp_agent/brain_v9/api_security.py`).
**Token handling:** supplied via `$env:BRAIN_ADMIN_TOKEN`; never printed in full; only redacted prefix shown.

## Results

| Endpoint | Status | Exists | Auth | Notes |
|----------|--------|--------|------|-------|
| `8091/health` | **200** | yes | no | healthy, v9.0.0, safe_mode off |
| `8091/v2/agent/status` | **200** | yes | `X-Brain-Token` required | langgraph_parity canonical |
| `8091/v2/agent/capabilities` | **200** | yes | `X-Brain-Token` required | capabilities 08F8-R1, LangGraphParityRuntimeV2 |
| `8092/` | **200** | yes | no | dashboard index.html |
| `8092/health` | **200** | yes | no | online on 8092 |
| `8092/brain-dashboard/status` | **200** | yes | no | **not degraded**, brain healthy, **kimi available** |
| `8092/brain-dashboard/agent-v2/status` | **200** | yes | no | langgraph_parity canonical |
| `8092/brain-dashboard/chat` | **405** | yes (POST-only) | no | GET rejected as designed — endpoint exists, do not treat 405 as missing |
| `8070/` | conn refused | **no** | — | legacy dashboard **CONFIRMED INACTIVE** |

## Body previews

- `8091/health` → `{"status":"healthy","sessions":1,"version":"9.0.0","safe_mode":false}`
- `8092/health` → `{"ok":true,"dashboard":"brain_persistent_autonomy","port":8092}`
- `8092/brain-dashboard/status` → `{"ok":true,"degraded":false,"brain":{...,"status":"healthy"},"kimi":{"ok":true,"status":"available_via_provider_probe"},...}`

## Auth note

Strict operator endpoints require the header **`X-Brain-Token: <BRAIN_ADMIN_TOKEN>`**.
- An earlier probe used `Authorization` / `X-Admin-Token` headers and correctly received **403**.
- Switching to the canonical `X-Brain-Token` header returned **200**.
- `require_operator_access` allows a localhost bypass; `require_strict_operator_access` does **not**. Always send `X-Brain-Token` for v2 admin endpoints.

## Conclusion

**DASHBOARD_ENDPOINT_PROBE_COMPLETED** — all live endpoints recorded honestly. 8091 healthy, 8092 online and not degraded, provider available, legacy 8070 confirmed inactive.
