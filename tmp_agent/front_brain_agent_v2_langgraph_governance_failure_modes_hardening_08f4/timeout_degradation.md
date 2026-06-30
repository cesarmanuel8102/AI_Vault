## PHASE 12 - Timeout/degradation smoke

**Status:** FAIL (bug exposed, report only)

### Objective
Verify that `execute_run()` degrades safely when the graph invocation stalls or hangs.

### Evidence
- Forced `LangGraphParityRuntimeV2.run()` to loop forever.
- External 5-second watchdog expired before `execute_run()` returned.
- `execute_run()` did not return a `status=failed` response; it hung for the entire watchdog period.

### Bug Description
There is no internal timeout/circuit-breaker around the graph invocation in `execute_run()`. A long-running or stuck graph node can occupy the request thread indefinitely, relying solely on the caller (e.g., uvicorn/FastAPI timeout or reverse proxy) to abort the request. This is a failure-mode gap that could lead to resource exhaustion and poor observability.

### Conclusion
This bug is **reported only**; no source code was modified. A future front should add a bounded timeout around `self.run()` in `execute_run()` and, on timeout, persist `status=failed` with a descriptive error and return a safe final answer.
