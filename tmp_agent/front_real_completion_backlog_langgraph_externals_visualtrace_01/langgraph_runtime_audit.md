# LangGraph Runtime Audit

## Files Inspected
- `tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py`
- `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_runtime.py`
- `tmp_agent/brain_v9/core/agent_kernel_v2/native_runtime.py`
- `tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py`
- `tmp_agent/brain_v9/main.py` (status endpoint)
- `tmp_agent/brain_v9/dashboard/dashboard_routes.py`

## Findings

### LangGraphAgentRuntimeV2 is a facade
- Line 6: `class LangGraphAgentRuntimeV2(NativeAgentRuntimeV2)` — inherits everything from native runtime
- Lines 13-24: Creates a `StateGraph` with 4 nodes (`plan`, `retrieve`, `tools`, `final`) that are **no-op lambdas** returning `{**s, "planned": True}` etc.
- Line 24: `self.graph = graph.compile()` — graph is compiled but **never invoked in the real execution path**.
- `execute_run()`, `plan_run()`, tool calls, memory retrieval, finalization, trace events — all inherited unchanged from `NativeAgentRuntimeV2`.
- The only method added is `graph_probe()` (lines 29-33), which is a debug/test helper not used in the canonical chat path.

### NativeAgentRuntimeV2 owns the real execution path
- `create_run()` (line 44): creates run, saves to disk, emits trace events — native code.
- `plan_run()` (line 58): calls `build_plan()` — native code.
- `execute_run()` (line 69): orchestrates intent routing, evidence bridge, tool execution, adaptive expansion, finalization — all native code.
- `_execute_step()` (line 410): calls `ToolGatewayV2().call()` directly — native code.
- `_trace()` (line 41): emits trace events to `TraceStore` — native code.

### False backend reporting
- `runtime.py` line 7: `LANGGRAPH_USED = True` when `langgraph_runtime.py` imports successfully.
- `api_adapter.py` lines 33, 53: reports `"langgraph_used": LANGGRAPH_USED`.
- `main.py` line 1137: reports `"backend": rt.backend` where `rt.backend = "langgraph"`.
- `dashboard_routes.py` line 187: same false reporting.
- This is **misleading** because the actual execution never traverses the LangGraph graph.

## Classification: LANGGRAPH_FACADE_ONLY

## Decision: PATH C — REMOVE FROM CRITICAL PATH

Rationale:
1. LangGraph is not the real orchestrator; native runtime does all work.
2. The graph is a toy with no-op nodes, never invoked in the canonical path.
3. Keeping it creates false claims and confusion.
4. Removing it simplifies the codebase and makes reporting truthful.

Required changes:
1. `runtime.py`: Always instantiate `NativeAgentRuntimeV2`, remove LangGraph import/try.
2. `__init__.py`: Export only native runtime symbols.
3. `api_adapter.py`: Report `backend="native_runtime"` and `langgraph_used=false`.
4. `main.py`: Same truthful reporting.
5. `dashboard_routes.py`: Same truthful reporting.
6. Tests: Verify no false LangGraph claims remain.
