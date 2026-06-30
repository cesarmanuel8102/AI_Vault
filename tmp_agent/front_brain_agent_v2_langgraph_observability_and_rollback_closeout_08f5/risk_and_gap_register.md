# Risk and Gap Register — FRONT-BRAIN-AGENT-V2-LANGGRAPH-OBSERVABILITY-AND-ROLLBACK-CLOSEOUT-08F5

## Risks

| ID | Area | Description | Severity | Likelihood | Mitigation | Residual |
|---|---|---|---|---|---|---|
| RISK-08F5-01 | Runtime selection | Operator accidentally sets `AGENT_V2_BACKEND` at machine scope | MEDIUM | LOW | Runbook restricts machine-level changes; verify via `/v2/agent/status` | LOW |
| RISK-08F5-02 | LangGraph parity runtime | LangGraph package version drift causes graph failures | MEDIUM | LOW | `runtime.py` falls back to Native on import/init failure; CI smoke tests exercise installed version | LOW |
| RISK-08F5-03 | Timeout | 30s timeout too short for very large evidence plans | LOW | LOW | `execute_timeout_seconds` configurable per instance | LOW |
| RISK-08F5-04 | Dashboard observability | Dashboard status does not expose `backend_fallback_reason` | LOW | MEDIUM | Inspect `/v2/chat/agent` response or logs; gap accepted for 08F5 | LOW |
| RISK-08F5-05 | Default backend policy | Future front inadvertently changes default to LangGraph | HIGH | LOW | Scope guard in smoke tests and hygiene script; explicit acceptance front required | LOW |

## Gaps

| ID | Area | Description | Impact | Acceptance |
|---|---|---|---|---|
| GAP-08F5-01 | Metrics | No Prometheus-style counter for backend selection / fallback events | Operators rely on endpoint responses and logs | Accepted for 08F5 |
| GAP-08F5-02 | UI toggle | No runtime UI toggle to switch backend | Operators must restart server or set env var | Accepted for 08F5 |
| GAP-08F5-03 | Streaming | `graph_stream_supported` tracked but `graph.stream()` not wired to production | Streaming observability is metadata only | Accepted for 08F5 |

## Phase result

PHASE 7 — Risk and gap register: **COMPLETED**

## Recorded

`2026-06-30T17:10:00+00:00`
