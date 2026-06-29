# Native Backend Contract Results

**Front:** FRONT-BRAIN-AGENT-V2-BACKEND-FLAG-CONTRACT-TESTS-08D  
**Test File:** `tests/smoke/test_brain_agent_v2_backend_flag_contracts_08d.py`  
**Backend:** `native_runtime` (default)  
**Result:** **14 passed, 0 failed**

## Key Findings

1. **Runtime selector is locked to Native.** `get_agent_runtime_v2()` returns `NativeAgentRuntimeV2` and `backend == 'native_runtime'`.
2. **No opt-in wiring exists yet.** `runtime.py` and `api_adapter.py` contain no references to `LangGraphParityRuntimeV2`, `langgraph_parity_runtime`, or `AGENT_V2_BACKEND`.
3. **`/v2/chat/agent` schema is stable.** All fields required by `ui/index.html` and the dashboard are present:
   - `ok`, `canonical_agent_v2`, `route`, `run_id`, `final_answer`
   - `provider_metadata`, `capability_metadata`
   - `mode_requested`, `mode_effective`, `auto_decision`
   - `mode_escalation_required`, `required_permission`, `confirmation_id`, `expected_write_scope`
   - `trace_url`, `blocked_tools`
   - `intent_route`, `intent_detected`, `intent_confidence`
4. **Mode contracts are satisfied for Native.**
   - `read_only` blocks or escalates write intents.
   - `build` returns escalation metadata.
   - `auto` exposes `auto_decision`.
5. **Legacy endpoints remain independent.** `/chat` and `/v1/chat/completions` do not expose Agent V2 canonical fields.
6. **Source code untouched.** The scope guard confirms no production files were modified.

## Evidence

- Baseline: `af5636b`
- Final head after test commit: `4adab4d`
- pytest output: `14 passed in ~11.6s`
- Bandit scan: 0 issues

## LangGraph Gaps Recorded for Future Wiring

- `expected_write_scope` and `auto_decision` must be normalized by adapter or runtime.
- Trace event types must be adapted to match dashboard filters (`plan_created`, `tool_call_*`).
- `run_root` must be unified or trace endpoint must search both roots.
- Runtime selector must guard against missing `langgraph` package.
