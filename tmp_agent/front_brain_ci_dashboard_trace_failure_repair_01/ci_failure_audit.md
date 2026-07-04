# FRONT-BRAIN-CI-DASHBOARD-TRACE-FAILURE-REPAIR-01 — CI Failure Audit

## Status

`CI_FAILURE_REPAIR_APPLIED_ON_GITHUB`

## Workflow

Workflow: `nontrading-smoke-regression`

Failed job reported by GitHub notification: `Dashboard / Trace Tests`.

The workflow definition shows that this job runs only one test command:

```powershell
python tests/smoke/test_visual_trace_8092_canonical_path_fix_01.py
```

## Local / log context

The local continuation became incomplete after a worker token limit. Before interruption, the branch was at:

`9d0df55e63cb10b392a3fa9c8b31f5fb2de58913`

That commit contained the sanitizer hardening front:

`fix(agent_v2): strip finalizer boilerplate from chat answers`

## Root causes addressed

### 1. False positive live regression

The live regression artifact showed `Brain API unreachable.` responses marked as `clean=true`. That is invalid. A connectivity failure must be a failing live regression, not a clean result.

Corrective action:

- Updated `_live_regression.py` so a result is clean only when:
  - transport succeeds
  - response is a JSON object
  - `ok is True`
  - content is non-empty
  - no dashboard/backend error text is present
  - no finalizer boilerplate pattern is present
- The script now exits non-zero when not all prompts are clean.
- Updated `live_regression.json` to invalidate the earlier false positive.

### 2. Brittle dashboard static test

The dashboard trace smoke test required the exact JavaScript expression:

```javascript
replace('/v2/agent/runs/', '/brain-dashboard/agent-v2/runs/')
```

to appear at least twice in `app.js`.

After the UI live-execution work, the dashboard still uses the same-origin trace proxy, but trace loading was split between direct proxy fetches and UI trace link mapping. The old exact-count assertion became too brittle.

Corrective action:

- Kept the real contract:
  - `/brain-dashboard/agent-v2/runs/` must be present in `app.js`.
  - trace-related lines must not hardcode `http://127.0.0.1:8091`.
  - trace-related client logic must exist.
- Removed the brittle exact-count requirement.

## Files modified

- `tmp_agent/front_brain_chat_answer_quality_hardening_02/_live_regression.py`
- `tmp_agent/front_brain_chat_answer_quality_hardening_02/live_regression.json`
- `tests/smoke/test_visual_trace_8092_canonical_path_fix_01.py`

## Safety scope

No security, governance, memory, FAISS, broker, trading, R2, or provider credential files were intentionally modified.

## Remaining verification

The GitHub push should trigger `nontrading-smoke-regression`. The next checkpoint is confirming `Dashboard / Trace Tests` is green.
