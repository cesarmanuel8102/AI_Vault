# /v2/chat/agent Schema Smoke — 08F2

## Environment

- `AGENT_V2_BACKEND`: `langgraph`
- `BRAIN_ADMIN_TOKEN`: `AGENTV2_08F2_TEST_TOKEN`

## Request

```json
{
  "message": "Give a concise Agent V2 status check. Do not write files.",
  "mode": "read_only",
  "user_id": "08f2_canary"
}
```

## Result

- Status: **PASS**
- HTTP status: 200
- `ok`: true
- `canonical_agent_v2`: true
- `run_id`: `agv2_94773981084674d1`
- `backend` / `backend_selected`: `langgraph_parity`
- `backend_fallback_used`: false
- `mode_effective`: `read_only`
- `approval_required`: false
- `trace_url`: `/v2/agent/runs/agv2_94773981084674d1/trace`

All required chat schema fields present.

## Notes

Strict operator access was bypassed with the same safe test-only patch used in 08F1. The ollama finalizer was faked to avoid external LLM calls. No source files were modified.
