# Exposed gaps review - 08F4

## Gaps extracted from 08F4 reports

### BUG-08F4-01 — Malformed run state accepted silently
- **Severity:** medium
- **Safety blocking:** No
- **Hardening required:** Yes
- **Description:** A `run.json` missing required fields (`goal`, `mode`) is not rejected by `execute_run`. It returns `status='completed'` with no error.

### BUG-08F4-02 — Auto write-intent escalation not reflected in run state
- **Severity:** medium
- **Safety blocking:** No
- **Hardening required:** Yes
- **Description:** `governance.mode_requires_escalation` correctly detects `auto` + write intent, but `LangGraphParityRuntimeV2` keeps `mode_effective=auto` after `create_run`/`execute_run`.

### BUG-08F4-03 — No internal timeout/circuit-breaker for graph invocation
- **Severity:** high
- **Safety blocking:** **Yes**
- **Hardening required:** Yes
- **Description:** `execute_run` invokes the graph without an internal timeout. A stalled node causes the call to hang until the external client times out or the process is killed.

### BUG-08F4-04 — Test-harness artifact for missing token header
- **Severity:** low
- **Safety blocking:** No
- **Hardening required:** No
- **Description:** `require_strict_operator_access` is an async FastAPI dependency. Direct synchronous invocation returns a coroutine instead of raising 401/403. Real FastAPI awaits it correctly.

## Classification
| Metric | Value |
|--------|-------|
| Safety-blocking gaps | BUG-08F4-03 |
| Hardening required before 100% rollout | Yes |
| Safe to continue to 08F5 closeout | **No** |

## Recommended next front
**FRONT-BRAIN-AGENT-V2-LANGGRAPH-GOVERNANCE-FAILURE-MODES-HARDENING-08F4-R1**

## Recommended next action
Repair the safety gaps in a new scoped source-patch front. **No amend. No force push. Native remains default.** Start with **BUG-08F4-03** (timeout/circuit-breaker), then **BUG-08F4-01** and **BUG-08F4-02**.
