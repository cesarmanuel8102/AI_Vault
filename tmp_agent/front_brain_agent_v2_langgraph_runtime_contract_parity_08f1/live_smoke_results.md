# Live Smoke Results — FRONT-BRAIN-AGENT-V2-LANGGRAPH-RUNTIME-CONTRACT-PARITY-08F1

## Method

Local pytest using `TestClient` and direct `LangGraphParityRuntimeV2` invocation. No long-running services were started.

## Results

| Scenario | Status | Evidence |
|----------|--------|----------|
| Native default when env unset | PASS | `test_native_default_when_env_unset`: `get_agent_runtime_v2().backend == native_runtime` |
| LangGraph selected with `AGENT_V2_BACKEND=langgraph` | PASS | `test_langgraph_selected_when_env_set`: `backend_selected == langgraph_parity`; `test_chat_agent_normalized_schema_with_langgraph`: `/v2/chat/agent` returns 200 and normalized schema |
| Fallback to Native when LangGraph incompatible | PASS | `test_fallback_to_native_when_langgraph_incompatible`: `backend_fallback_used` true, backend == `native_runtime` |
| Trace retrieval after LangGraph run | PASS | `test_trace_contract_after_langgraph_run`: `get_trace(run_id)` returns list |
| Read-only governance blocks write intent | PASS | `test_read_only_blocks_write_intent`: `mode_escalation_required` or `blocked_tools` or `required_permission` present |

## Notes

No production canary was started. All live smoke exercised through isolated temp `run_root` or `TestClient`.
