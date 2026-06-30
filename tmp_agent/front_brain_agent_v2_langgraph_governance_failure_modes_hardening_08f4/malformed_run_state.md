## PHASE 7 - Malformed run state smoke

**Status:** FAIL (bug exposed, report only)

### Objective
Stress-test `LangGraphParityRuntimeV2.execute_run()` with malformed persisted run state: missing `run.json`, invalid JSON, and `run.json` missing required fields.

### Evidence
| Case | Behavior | Assessment |
|------|----------|------------|
| Missing `run.json` for unknown run_id | Raised `KeyError` | Acceptable (run does not exist) |
| Invalid JSON `run.json` | Raised `JSONDecodeError` | Acceptable (corrupt file) |
| `run.json` missing required fields (`goal`, `mode`) | Returned `status="completed"`, no error | **BUG** |

### Bug Description
When a persisted `run.json` exists but lacks required fields (e.g. only contains `{"run_id": "..."}`), `execute_run` does not validate the minimum run schema and proceeds to invoke the graph. It returns `status="completed"` with `error: null`. This is a governance/failure-mode gap because a malformed run state can silently complete instead of being rejected with `status="failed"` and a descriptive error.

### Conclusion
This bug is **reported only**; no source code was modified in this front. The issue should be addressed in a subsequent front by adding run-state schema validation in `execute_run` before graph invocation.
