# LangGraph Candidate Gap Analysis

**Front**: FRONT-BRAIN-AGENT-V2-CONTROLLED-BACKEND-OPT-IN-READINESS-REVIEW-08F0  
**Source head**: 883df0a  
**Candidate file**: `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`  
**Candidate class**: `LangGraphParityRuntimeV2`

## Candidate State

The module docstring explicitly states:

> Isolated LangGraph deep parity runtime for Brain V9 Agent Kernel V2. This module is intentionally NOT wired into `runtime.py`, `api_adapter.py`, or `main.py`. It is a test-only deep parity prototype.

## Public Methods Found

| Method | Signature |
|--------|-----------|
| `__init__` | `(self, run_root=None, finalizer_fn=None, evaluator_fn=None)` |
| `run` | `(self, message: str, mode: str = "read_only", user_id: str = "probe") -> Dict[str, Any]` |
| `graph_probe` | `() -> Dict[str, Any]` |
| `graph_stream_probe` | `() -> Dict[str, Any]` |
| `backend_flag_readiness_probe` | `() -> Dict[str, Any]` |
| `get_trace` | `(run_id: str) -> List[Dict[str, Any]]` |
| `get_checkpoint` | `(run_id: str) -> Optional[Dict[str, Any]]` |
| `get_run` | `(run_id: str) -> Optional[Dict[str, Any]]` |

## Production Runtime Method Gaps

| Required Method | Present in LangGraph Class | Notes |
|-----------------|---------------------------|-------|
| `create_run(goal, mode, user_id)` | ❌ **Missing** | `api_adapter.chat_agent` calls `rt.create_run(...)` directly. This is the primary blocker. |
| `execute_run(run_id)` | ❌ **Missing** | `api_adapter.chat_agent` calls `rt.execute_run(run_id)` directly. |
| `plan_run(run_id)` | ❌ Missing | `api_adapter` calls it for `mixed_brain_reasoning`/`operational_agent` routes. |
| `pause_run(run_id)` | ❌ Missing | Optional for chat endpoint but part of run lifecycle. |
| `resume_run(run_id)` | ❌ Missing | Optional for chat endpoint. |
| `cancel_run(run_id)` | ❌ Missing | Optional for chat endpoint. |
| `get_run(run_id)` | ✅ Present | Loads `run.json` from `_run_dir(run_id)`. |
| `get_trace(run_id)` | ✅ Present | Returns `TraceStore(...).read()`. Compatible shape. |
| `list_runs()` | ❌ Missing | `/v2/agent/status` and `/v2/agent/runs` use it. |

## Response Normalization Gap

- `api_adapter.chat_agent` builds a raw response dict from the Native run object and then calls `normalize_agent_v2_chat_response(...)`.
- `LangGraphParityRuntimeV2.run()` returns the final graph state dict. It does not necessarily contain the fields the normalizer needs (`final_answer`, `provider_metadata`, `mode_requested`, `mode_effective`, `blocked_tools`, etc.) unless the graph nodes populate them.
- Therefore, even if `create_run`/`execute_run` wrappers are added, the wrappers must translate the graph state into the Native-style run dict before normalization.

## Trace Contract

- Trace persistence: ✅ Uses `TraceStore(self._run_dir(run_id)).append(...)`.
- Trace retrieval: ✅ `get_trace` returns the same list-of-dicts shape as Native.
- The run directory layout must align with Native (`run_root/{run_id}/run.json`) for `get_run` and trace to work across backends.

## Security / Governance

- Strict operator access is enforced by `api_adapter` endpoints, not the runtime itself.
- Mode enforcement is implemented inside the graph via `validate_mode` and `mode_requires_escalation`.
- Read-only blocking relies on `ToolGatewayV2`, same as Native.
- Conclusion: if wired through `api_adapter`, existing security/governance layers apply.

## Fallback Metadata

- `backend_selected`, `backend_fallback_used`, `backend_fallback_reason` are not set by the LangGraph class itself.
- `runtime.py` sets them if it selects the runtime. Because the compatibility check currently fails, `runtime.py` falls back to Native and never reaches that point.

## Native-Only Assumption Risks

1. `api_adapter.chat_agent` assumes `rt.create_run` and `rt.execute_run` exist.
2. `api_adapter` decides whether to call `rt.plan_run` based on intent route.
3. `response_normalizer` expects a Native-like run dict.
4. Dashboard and status consumers rely on `backend_selected` / `backend_fallback_*` metadata.

## Top Gaps

1. **Missing `create_run` and `execute_run` methods** — primary production blockers.
2. **Missing run lifecycle methods** (`plan_run`, `list_runs`, `pause`, `resume`, `cancel`).
3. **Response translation layer** needed between graph final state and the normalized `/v2/chat/agent` schema.
4. **Not wired into `runtime.py`** — the compatibility guard correctly falls back to Native today.

## 08F1 Recommendation

The next front should add a thin adapter/wrapper to `langgraph_parity_runtime.py` (or a new file) that exposes the exact production runtime interface. It must:

- Implement `create_run(goal, mode, user_id)` and `execute_run(run_id)`.
- Internally call the existing graph via `run()` or `_graph.invoke()`.
- Translate graph final state into a Native-compatible run dict.
- Populate `backend_selected`, `backend_fallback_*` metadata.
- Keep Native as default and only activate when `AGENT_V2_BACKEND` requests LangGraph.

Until those wrappers exist, selecting LangGraph as backend will safely fall back to Native.
