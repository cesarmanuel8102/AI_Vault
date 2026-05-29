# VTC-F2 SSE E2E Automated Test Plan

## Scope
Design automated test for `/brain/agent-trace/stream` endpoint that verifies redaction of sensitive events without requiring server restart or real token.

## Recommended Test File
```
tests/unit/test_agent_trace_sse_e2e.py
```

## Approach

### Preferred Approach: Functional Textual Test
1. **Avoid FastAPI TestClient** — importing FastAPI/httpx adds heavy dependencies that some existing tests explicitly forbid.
2. **Avoid real server** — no `uvicorn` process to manage.
3. **Alternative: Call `_emit_agent_trace_internal` directly** (as done in VTC-C2 smoke) to inject events bypassing auth.
4. **Then use internal `_read_trace_events` to verify persisted events are sanitized.**

### Fallback Approach (if direct internal call insufficient):
- Use `FastAPI TestClient` only in the test file.
- The test file imports `app` from `main`.
- TestClient makes GET request to `/brain/agent-trace/stream`.
- Inject event via direct call before GET.
- Read SSE streaming response line-by-line.
- Assert redaction in streamed text.

### Internal Emitter (recommended)
```python
from brain_v9.main import _emit_agent_trace_internal

_emit_agent_trace_internal(
    room_id="vtc_f_sse_test",
    run_id="sse_redaction_test",
    type_="tool",
    title="Sensitive event",
    text="password=supersecret123 token=ghp_test path memory/semantic/state.json",
    severity="warning",
    data={
        "chain_of_thought": "should not appear",
        "api_key": "sk-test",
        "detail": "bearer abcdefghijklmnopqrstuvwxyz123456"
    }
)
```

## Assertions

### Payload Redaction
```text
- "supersecret123" NOT in any event text
- "ghp_" NOT in any event text
- "sk-" NOT in any event text
- "memory/semantic" NOT in any event text
- "tmp_agent/strategies" NOT in any event text
- "chain_of_thought" NOT present as key
- "[REDACTED_SECRET]" MUST appear
- "[REDACTED_PATH]" MUST appear
```

### Field Removal
```text
- event["data"] must NOT contain "chain_of_thought"
- event["data"] must NOT contain "api_key"
- event["data"] must NOT contain "password"
- event["data"] must NOT contain "token"
```

### Stream Sanity
```text
- Stream endpoint responds without error
- At least one event received
- Each event is valid dict
```

## Token Requirements
- **NO real X-Brain-Token required** — test uses internal emitter
- **NO BRAIN_ADMIN_TOKEN needed** — test runs in-process
- **NO server restart** — test imports from working tree

## Files Touched (future commit)
```
 tests/unit/test_agent_trace_sse_e2e.py (NEW)
```

## No-Go
- Do NOT modify main.py
- Do NOT modify trace_redactor.py
- Do NOT modify UI files
- Do NOT commit changes to memory/semantic
- Do NOT commit changes to strategies/reports

## Expected Duration
1 session (1 phase) — test design + execution + validation.

## Rollback
Delete test file and re-run existing tests to verify no regression.
