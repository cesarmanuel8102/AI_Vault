:
# Contract Requirements — FRONT-BRAIN-FRONTEND-DASHBOARD-CHAT-CONTRACT-GATE-08C

**Baseline:** `979c277`

This document defines the minimum contracts that any future `AGENT_V2_BACKEND` opt-in wiring must preserve.

## Goal

Before wiring `LangGraphParityRuntimeV2` as an opt-in backend, ensure that existing frontend, dashboard, chat, trace, approval, status, and proxy surfaces continue to work without modification.

## REQ-01 — `/v2/chat/agent` response contract

The response MUST contain the following fields with stable semantics:

- `ok`
- `route`
- `run_id`
- `final_answer`
- `capability_metadata`
- `provider_metadata`
- `mode_requested`
- `mode_effective`
- `mode_escalation_required`
- `confirmation_id`
- `required_permission`
- `expected_write_scope`
- `trace_url`
- `blocked_tools`
- `auto_decision` (should be present; may be `'n/a'`)

**Frontend consumers:** `ui/index.html` and `dashboard/static/app.js`.

**LangGraph gap:** missing `expected_write_scope` and `auto_decision`; `provider_metadata` shape differs.

**Required adapter:** normalize response in `api_adapter.py` or runtime selector.

**Test required:** TestClient POST `/v2/chat/agent` with monkeypatched finalizer asserts all fields present across scenarios.

## REQ-02 — Trace contract

A `run_id` returned by `/v2/chat/agent` MUST resolve via `GET /v2/agent/runs/{run_id}/trace` returning `{ok, run_id, trace[], event_count}`.

The dashboard 8092 proxy MUST resolve the same `run_id` through `/brain-dashboard/agent-v2/runs/{run_id}/trace`.

**Frontend consumers:** `ui/index.html` execution trace panel, `dashboard/static/app.js` trace rendering.

**LangGraph gap:** default `run_root` differs; trace event types are node-based.

**Required adapter:** use production `RUN_ROOT` for opt-in backend; emit Native-equivalent trace event types or dual event types.

**Test required:** fetch `trace_url` after chat for both backends; assert `ok=true`, `trace` non-empty, `event_count > 0`, and Native-style event types present.

## REQ-03 — Dashboard 8092 proxy contract

`POST /brain-dashboard/chat` MUST proxy to the same Agent V2 backend that `8090/v2/chat/agent` uses, and MUST return a stable error shape `{ok:false, error, content}` on failure.

**Frontend consumer:** `dashboard/static/app.js` chat widget.

**LangGraph gap:** 8091 and 8090 backend selection could diverge.

**Required adapter:** document and enforce identical `AGENT_V2_BACKEND` flag parsing on 8091.

**Test required:** contract test against `dashboard_routes.py` chat and trace proxy functions.

## REQ-04 — Mode contract

- `read_only` mode MUST remain safe: write tools blocked, no side effects.
- `build` mode MUST require approval: `mode_escalation_required=true`, `required_permission='build'`, `confirmation_id` present, `expected_write_scope` present.
- `auto` mode MUST NOT silently mutate to write; it MUST expose `auto_decision` in response.

**Frontend consumers:** `ui/index.html` and `dashboard/static/app.js` mode switches.

**LangGraph gap:** missing `expected_write_scope` and `auto_decision`; build mode may skip unsupported write tools.

**Required adapter:** add `expected_write_scope` generation in LangGraph `_governance_gate_node`; add `auto_decision` fallback.

**Test required:** TestClient scenarios for all three modes under both backends.

## REQ-05 — Approval contract

When `mode_escalation_required` is true, the frontend MUST receive `expected_write_scope` and `confirmation_id`.

There is no requirement that `/gate/approve` resolves the escalation immediately, but the UI MUST degrade gracefully.

**Frontend consumers:** `ui/index.html renderEscalationPanel`, `dashboard/static/app.js` metadata line.

**LangGraph gap:** `confirmation_id` exists but `expected_write_scope` missing.

**Required adapter:** add `expected_write_scope` to response normalization.

## REQ-06 — Error contract

If LangGraph is unavailable or the opt-in flag is not set, the system MUST fall back to `NativeAgentRuntimeV2` and MUST NOT return a malformed `/v2/chat/agent` response.

**Frontend consumers:** all Agent V2 callers.

**LangGraph gap:** `run()` can return dict without `run_id`/`trace_url` when `graph_available=false`.

**Required adapter:** runtime selector MUST verify package and explicit flag; `api_adapter.py` MUST guard `trace_url` construction.

**Test required:** unit tests for runtime selector under flag/package combinations.

## REQ-07 — Streaming / progress contract

`/v2/chat/agent` MAY remain synchronous JSON. Visual trace streaming through `/brain/agent-trace/stream` MUST remain operational and independent of the runtime backend.

**Frontend consumers:** `ui/index.html connectAw`, `ui/agent_trace_console.html connectSSE`.

**LangGraph gap:** none.

**Required adapter:** none.

## REQ-08 — Legacy chat contract

`/chat` and `/v1/chat/completions` MUST continue to route through `handle_user_message` → `BrainSession.chat` regardless of `AGENT_V2_BACKEND` flag.

**Frontend consumers:** legacy integrations, Open WebUI.

**LangGraph gap:** none by design.

**Required adapter:** explicitly exclude these endpoints from backend switching.

**Test required:** regression tests with flag set to `langgraph`.

## REQ-09 — Status panel contract

`/v2/agent/status`, `/brain-dashboard/status`, and `/brain-dashboard/agent-v2/status` MUST return a `backend` string that dashboards tolerate (no hardcoded checks for `native_runtime`).

**Frontend consumers:** ops dashboards.

**LangGraph gap:** backend becomes `langgraph_parity`.

**Required adapter:** verify no hardcoded string checks.

**Test required:** grep frontend files for hardcoded `native_runtime`.

## REQ-10 — Embedded dashboard contract

All endpoints consumed by `ui/dashboard_*.js` on `/dashboard` and `/dashboard-v2` MUST remain independent of Agent V2 runtime.

**Frontend consumers:** embedded Command Center v2.

**LangGraph gap:** none.

**Required adapter:** none.

## Minimum test matrix before wiring

| Test | Backend | What to assert |
|------|---------|----------------|
| `v2_chat_agent_schema_parity` | both | All required fields present across scenarios |
| `v2_trace_resolution` | both | `trace_url` resolves, events present, Native-style event types for LangGraph |
| `dashboard_8092_proxy_contract` | both | `/brain-dashboard/chat` and trace proxy work |
| `mode_switch_contract` | both | read_only safe, build escalates, auto returns auto_decision |
| `runtime_fallback_when_langgraph_unavailable` | mocked missing | flag ignored, Native returned, no crash |
| `legacy_chat_unchanged` | flag=langgraph | `/chat` and `/v1/chat/completions` still use BrainSession |

## Recommended next action

**B. Add endpoint contract tests before blueprint.**

Three incompatible items and one blocking item were identified. No source modifications are required yet, but contract tests are the prerequisite for safe opt-in backend wiring.
