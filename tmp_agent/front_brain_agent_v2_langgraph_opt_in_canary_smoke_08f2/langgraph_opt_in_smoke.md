# LangGraph Opt-In Direct Runtime Smoke — 08F2

## Environment

- `AGENT_V2_BACKEND`: `langgraph`
- `BRAIN_ADMIN_TOKEN`: `AGENTV2_08F2_TEST_TOKEN`

## Result

- Status: **PASS**
- Runtime class: `LangGraphParityRuntimeV2`
- `backend_selected`: `langgraph_parity`
- `backend_fallback_used`: false
- `backend_fallback_reason`: null
- `run_id`: `agv2_893f07899f7c7fa0`

## Contract checks

All required run fields present after both `create_run` and `execute_run`:

- `run_id`
- `status`
- `final_answer`
- `provider_metadata`
- `capability_metadata`
- `mode_requested`
- `mode_effective`
- `backend_selected`
- `backend_fallback_used`
- `backend_fallback_reason`
- `trace_url`

`run_id` starts with `agv2_`. `trace_url` starts with `/v2/agent/runs/`.

`get_trace(run_id)` returned a list of length 2.

## Notes

Smoke used a temporary `run_root`. The first attempt hit a path-type issue because the runtime returned by `get_agent_runtime_v2()` inherited a string `run_root`; wrapping it with `Path` allowed the smoke to proceed. No source code was modified.
