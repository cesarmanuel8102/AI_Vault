## PHASE 4 - Missing LangGraph fallback smoke

**Status:** PASS

### Objective
Verify that when `AGENT_V2_BACKEND=langgraph` is set but LangGraph cannot be built (simulated by returning `None` from `_try_build_langgraph_runtime`), the runtime selector safely falls back to `NativeAgentRuntimeV2` with `backend_fallback_used=true` and a clear reason.

### Evidence
- Environment: `AGENT_V2_BACKEND=langgraph`
- Runtime class: `NativeAgentRuntimeV2`
- `backend_selected`: `native_runtime`
- `backend_fallback_used`: `true`
- `backend_fallback_reason`: `AGENT_V2_BACKEND='langgraph' requested but LangGraph is unavailable or failed to initialize; falling back to native_runtime`

### Assertions
- Fallback to Native class: PASS
- `backend_fallback_used == true`: PASS
- Reason cites LangGraph unavailability: PASS

### Conclusion
The opt-in LangGraph path degrades safely to Native when the LangGraph runtime is unavailable. No source code was modified.
