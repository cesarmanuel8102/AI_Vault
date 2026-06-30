# Fallback Smoke — 08F2

## Environment

- `AGENT_V2_BACKEND`: `langgraph`
- `BRAIN_ADMIN_TOKEN`: `AGENTV2_08F2_TEST_TOKEN`

## Simulation

Monkey-patched `runtime._try_build_langgraph_runtime` to return `None` in an isolated Python process.

## Result

- Status: **PASS**
- Runtime class: `NativeAgentRuntimeV2`
- `backend`: `native_runtime`
- `backend_selected`: `native_runtime`
- `backend_fallback_used`: true
- `backend_fallback_reason`: non-empty, explains LangGraph unavailable

## Conclusion

Safe fallback to NativeAgentRuntimeV2 is preserved when LangGraph cannot be constructed.
