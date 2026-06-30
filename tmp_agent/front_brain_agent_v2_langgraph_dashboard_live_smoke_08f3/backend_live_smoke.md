# Backend Live Smoke — 08F3

## Goal
Verify that the backend process starts with `AGENT_V2_BACKEND=langgraph`, responds to `/health`, and `/v2/chat/agent` returns the normalized Agent V2 schema with LangGraph selected.

## Results

| Check | Result |
|-------|--------|
| Backend started on 127.0.0.1:8091 | PASS |
| `/health` reachable | PASS (HTTP 200) |
| `/v2/chat/agent` reachable | PASS (HTTP 200) |
| `ok` == true | PASS |
| `canonical_agent_v2` == true | PASS |
| `run_id` starts with `agv2_` | PASS (`agv2_f3b5b20d9599b514`) |
| `backend_selected` == `langgraph_parity` | PASS |
| `backend_fallback_used` == false | PASS |
| `mode_effective` == `read_only` | PASS |
| `trace_url` present | PASS |
| `final_answer` present | PASS |
| `provider_metadata` present | PASS |
| `capability_metadata` present | PASS |

## Sample
- Run ID: `agv2_f3b5b20d9599b514`
- Backend: `langgraph_parity`
- Fallback: `false`

## Notes
The backend was started with `AGENT_V2_BACKEND=langgraph` and a test-only `BRAIN_ADMIN_TOKEN` only in the backend subprocess environment. `/health` responded 200. `/v2/chat/agent` returned 200 with normalized schema and LangGraph backend selected. No fallback.
