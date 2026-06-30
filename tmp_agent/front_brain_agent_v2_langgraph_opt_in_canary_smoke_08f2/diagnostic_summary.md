# Diagnostic Summary — FRONT-BRAIN-AGENT-V2-LANGGRAPH-OPT-IN-CANARY-SMOKE-08F2

**Front**: FRONT-BRAIN-AGENT-V2-LANGGRAPH-OPT-IN-CANARY-SMOKE-08F2  
**Branch**: codex/own-capital-sustainable-return  
**Starting baseline**: abb3c91  
**Status**: CANARY_SMOKE_COMPLETE

## Purpose

Execute a controlled LangGraph opt-in canary smoke using `AGENT_V2_BACKEND=langgraph`. Verify Native default, opt-in selection, response schema, trace, fallback, read-only governance, and dashboard proxy behavior.

## Scope confirmation

- This is a **reports-only** front.
- No source code or tests modified.
- Native default preserved.
- LangGraph not activated by default.
- No dashboard/frontend/security/main/api_adapter/native_runtime/response_normalizer changes.
- No memory/FAISS/trading/env changes.

## High-level results

| Area | Result |
|------|--------|
| Native default | PASS |
| LangGraph opt-in runtime | PASS |
| `/v2/chat/agent` schema | PASS |
| Trace contract | PASS |
| Read-only governance | PASS |
| Fallback to Native | PASS |
| Dashboard proxy (routes/no leak) | PASS |

## Notes

- Dashboard chat proxy returned `ok:false` only because no live backend was running on 8091. The route itself responded HTTP 200 and did not leak `X-Brain-Token`.
- Two R3 dashboard token proxy tests failed when run in the same pytest session as the LangGraph opt-in tests; this is a test-isolation artifact. Running R3 in isolation yields 3 passes.
