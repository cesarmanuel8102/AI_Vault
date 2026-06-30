## PHASE 5 - Incompatible runtime fallback smoke

**Status:** PASS

### Objective
Verify that when `AGENT_V2_BACKEND=langgraph` is set and `_try_build_langgraph_runtime` returns an object missing the production interface (`create_run`/`execute_run`), the runtime selector rejects it and falls back to `NativeAgentRuntimeV2`.

### Evidence
- Environment: `AGENT_V2_BACKEND=langgraph`
- Injected runtime class: `IncompatibleRuntime` (lacked `create_run` and `execute_run`)
- Fallback runtime class: `NativeAgentRuntimeV2`
- `backend_fallback_used`: `true`
- `backend_fallback_reason`: `AGENT_V2_BACKEND='langgraph' requested but selected backend 'IncompatibleRuntime' is not production runtime compatible (missing methods: ['create_run', 'execute_run']); falling back to native_runtime`

### Assertions
- Fallback to Native class: PASS
- Fallback reason cites missing production methods: PASS
- `backend_fallback_used == true`: PASS

### Conclusion
The production-runtime compatibility guard prevents an incompatible backend from being exposed to `/v2/chat/agent`. No source code was modified.
