# Final Report — FRONT-BRAIN-AGENT-V2-LANGGRAPH-OPT-IN-CANARY-SMOKE-08F2

**Front**: FRONT-BRAIN-AGENT-V2-LANGGRAPH-OPT-IN-CANARY-SMOKE-08F2  
**Branch**: codex/own-capital-sustainable-return  
**Starting baseline**: abb3c91  
**Final head**: 271a201  
**Status**: ACCEPTED_08F2

## Scope

This front executed a **controlled, reports-only LangGraph opt-in canary smoke**. No source code, tests, dashboard, frontend, memory, FAISS, trading, or env files were modified. NativeAgentRuntimeV2 remains the default backend.

## Baseline confirmation

- Previous accepted front: FRONT-BRAIN-AGENT-V2-LANGGRAPH-RUNTIME-CONTRACT-PARITY-08F1 at `abb3c91`.
- 08F1 contract parity was accepted and CI green.

## Phase smoke results

| Phase | Result |
|-------|--------|
| Native default smoke | PASS |
| LangGraph opt-in direct runtime smoke | PASS |
| `/v2/chat/agent` schema smoke with LangGraph opt-in | PASS |
| Trace smoke | PASS |
| Read-only governance smoke | PASS |
| Fallback smoke | PASS |
| Dashboard proxy smoke | PASS (routes reachable, no token leak; backend was not live) |

## Key findings

- `AGENT_V2_BACKEND=langgraph` correctly selects `LangGraphParityRuntimeV2`.
- `AGENT_V2_BACKEND` unset correctly keeps `NativeAgentRuntimeV2` as default.
- LangGraph opt-in `create_run` / `execute_run` return Native-style run dicts with all required fields.
- `/v2/chat/agent` returns 200 and normalized schema when LangGraph is opt-in.
- `get_trace(run_id)` returns a list and contains no leaked tokens.
- Read-only governance escalates write intent; no source files were modified by smoke runs.
- Simulated LangGraph unavailability falls back safely to Native with `backend_fallback_used=true`.
- Dashboard chat proxy route is reachable and does not leak `X-Brain-Token`; proxied backend was not running on 8091, so it returned `ok:false` from the error handler.

## Validation

- py_compile: PASS for inspected runtime files.
- 08F1 contract tests: 10 passed.
- Runtime selector guard tests: 14 passed.
- Response normalization tests: 12 passed.
- Dashboard R3 token proxy tests: 3 passed in isolation. In the batched run with 08F1 tests, 2 failed due to test isolation/environment state; this was documented, not patched.
- Git hygiene guard: SAFE.

## Scope audit

- Source files modified: no
- Test files modified: no
- Dashboard/frontend/security/main/api_adapter/native_runtime/response_normalizer: unchanged
- Memory/FAISS/trading/broker/env: untouched

## Commit/push status

- Commit created: 271a201
- Pushed: origin/codex/own-capital-sustainable-return
- CI verified: all success (Phase 1 baseline (Windows), Security Smoke Tests, Dashboard / Trace Tests, Memory / Retrieval Regression, Roadmap / Policy Regression, Hygiene Guard)

## Recommended next front

**FRONT-BRAIN-AGENT-V2-LANGGRAPH-DASHBOARD-LIVE-SMOKE-08F3**

Run deeper dashboard/live smoke and trace UX verification with the backend running on 8091. Keep Native default. Do not activate LangGraph globally.
