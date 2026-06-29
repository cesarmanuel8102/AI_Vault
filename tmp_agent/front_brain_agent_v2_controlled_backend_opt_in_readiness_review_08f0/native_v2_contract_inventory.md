# Native V2 Production Contract Inventory

**Front**: FRONT-BRAIN-AGENT-V2-CONTROLLED-BACKEND-OPT-IN-READINESS-REVIEW-08F0  
**Source head**: 883df0a  
**Canonical/default backend**: `native_runtime`

## Production Files

| File | Role |
|------|------|
| `tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py` | Backend selector, fallback guard, production runtime compatibility check |
| `tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py` | `/v2/agent/*` and `/v2/chat/agent` endpoints |
| `tmp_agent/brain_v9/core/agent_kernel_v2/native_runtime.py` | Native Agent V2 runtime implementation |
| `tmp_agent/brain_v9/core/agent_kernel_v2/response_normalizer.py` | Normalizes any backend response into the stable `/v2/chat/agent` schema |
| `tmp_agent/brain_v9/dashboard/dashboard_routes.py` | Dashboard proxies to backend (chat + trace) |

## Runtime Interface Contract

### Class
`NativeAgentRuntimeV2`

### Required Methods (production `/v2/chat/agent` path needs these)

| Method | Signature | Description |
|--------|-----------|-------------|
| `create_run` | `(goal: str, mode: str = "read_only", user_id: str = "local") -> Dict[str, Any]` | Create run, validate mode, generate `agv2_<hash>` id, persist `run.json`, checkpoint, trace event |
| `execute_run` | `(run_id: str) -> Dict[str, Any]` | Load run, assemble context, route intent, plan/execute, finalize, persist, trace events |

### Optional Methods

| Method | Signature |
|--------|-----------|
| `plan_run` | `(run_id: str) -> Dict[str, Any]` |
| `pause_run` | `(run_id: str) -> Dict[str, Any]` |
| `resume_run` | `(run_id: str) -> Dict[str, Any]` |
| `cancel_run` | `(run_id: str) -> Dict[str, Any]` |
| `get_run` | `(run_id: str) -> Dict[str, Any]` |
| `get_trace` | `(run_id: str) -> List[Dict[str, Any]]` |
| `list_runs` | `() -> List[Dict[str, Any]]` |

## `/v2/chat/agent` Endpoint Contract

### Authentication
`require_strict_operator_access` — requires `X-Brain-Token` header.

### Request Payload

```json
{
  "message": "string (required)",
  "mode": "string (default 'read_only')",
  "user_id": "string (default 'local')"
}
```

### Pipeline

1. Validate `message` is non-empty.
2. Reject forbidden bypass/override fields in `message`.
3. Parse mode from natural language or request mode.
4. Assemble recent session context.
5. Select intent route via `AgentV2IntentAdapter`.
6. `rt.create_run(message, validated_mode, user_id)`.
7. If route is `mixed_brain_reasoning` or `operational_agent`: `rt.plan_run(run_id)`.
8. `rt.execute_run(run_id)`.
9. `trace_events = rt.get_trace(run_id)`.
10. Build `capability_metadata`.
11. `normalize_agent_v2_chat_response(...)`.

### Normalized Response Schema

Required top-level fields:
`ok`, `canonical_agent_v2`, `route`, `run_id`, `final_answer`, `provider_metadata`, `capability_metadata`, `mode_requested`, `mode_effective`, `mode_escalation_required`, `approval_required`, `confirmation_id`, `required_permission`, `expected_write_scope`, `trace_url`, `blocked_tools`, `intent_route`, `intent_detected`, `intent_confidence`, `classification`, `status`, `auto_decision`, `backend`, `backend_selected`, `backend_fallback_used`, `backend_fallback_reason`, `error`, `detail`.

`provider_metadata` must contain: `provider_used`, `model_used`, `provider_degraded`, `fallback_reason`.

`capability_metadata` must contain: `memory_used`, `retrieval_attempted`, `retrieval_no_results`, `retrieval_skipped`, `planner_used`, `evidence_routed`, `evidence_sources_count`, `tools_considered`, `tools_executed`, `tools_blocked`, `governance_checked`, `trace_events_count`, `intent_route`, `classification`.

`trace_url` format: `/v2/agent/runs/{run_id}/trace`

`run_id` format: `agv2_<16-char-hex-sha256>`

## Run Lifecycle Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v2/agent/runs` | POST | Create run |
| `/v2/agent/runs/{run_id}` | GET | Get run |
| `/v2/agent/runs/{run_id}/plan` | POST | Plan run |
| `/v2/agent/runs/{run_id}/execute` | POST | Execute run |
| `/v2/agent/runs/{run_id}/pause` | POST | Pause run |
| `/v2/agent/runs/{run_id}/resume` | POST | Resume run |
| `/v2/agent/runs/{run_id}/cancel` | POST | Cancel run |
| `/v2/agent/runs/{run_id}/trace` | GET | Get trace |

## Mode and Governance

- Mode validation: `tmp_agent/brain_v9/core/agent_kernel_v2/governance.py validate_mode(mode)`.
- `read_only`: write tools are blocked via `ToolGatewayV2`; mode escalation sets `required_permission='build'` and `confirmation_id`.
- `auto`: `infer_auto_decision(goal)` resolves to a concrete mode.
- Invalid backend env value: runtime selector falls back to Native with `backend_fallback_used=true`.

## Backend Selector Behavior

- Env var: `AGENT_V2_BACKEND`
- Native values: `""`, `"native"`, `"native_runtime"`
- LangGraph values: `"langgraph"`, `"langgraph_parity"`, `"langgraph_parity_runtime"`
- Invalid non-native/non-LangGraph values: safe fallback to `native_runtime` with metadata.
- Production compatibility check: `runtime.py` verifies `create_run` and `execute_run` exist and are callable. Optional methods (`plan_run`, `list_runs`, `get_run`, `get_trace`) only fail if present but not callable.

## Dashboard Proxy Expectations

| Dashboard path | Backend target |
|----------------|----------------|
| `POST /brain-dashboard/chat` | `POST http://127.0.0.1:8091/v2/chat/agent` |
| `GET /brain-dashboard/agent-v2/runs/{run_id}/trace` | `GET http://127.0.0.1:8091/v2/agent/runs/{run_id}/trace` |

Dashboard now forwards `X-Brain-Token` via `_strict_headers()` when `BRAIN_ADMIN_TOKEN` is configured (R3 fix).

## Key Implication for LangGraph

Any opt-in LangGraph backend must implement at least `create_run(goal, mode, user_id)` and `execute_run(run_id)` with signatures and side-effects compatible with the API adapter. The response will be normalized by `response_normalizer.py`, but the runtime must produce a run dict containing `run_id`, `final_answer`, `status`, and optional fields used by the normalizer.
