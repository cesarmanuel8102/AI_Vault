# FRONT-BRAIN-AGENT-V2-DASHBOARD-MEMORY-QUEUE-57-ROOTCAUSE-08F8-R1G

Status: IMPLEMENTED_VALIDATED

## Root Cause
The dashboard value `57` is real. It comes from:

`/brain-dashboard/status -> memory.promotion_queue_count -> len(memory/promotion_queue/*.json)`

Agent V2 previously checked only `tmp_agent/state/*` promotion queues and `/brain/learning/status`, so it could not explain the dashboard count.

## Correct Reconciliation
- Canonical `tmp_agent/state` promotion queue entries: 0
- Dashboard 8092 `memory.promotion_queue_count`: 57
- Dashboard learning `candidate_promote_count`: 0
- Source of 57: `memory/promotion_queue/*.json`
- Code source: `tmp_agent/brain_v9/memory/memory_auditor.py:audit_memory_state`
- Frontend source: `tmp_agent/brain_v9/dashboard/static/app.js`

## Validation
- py_compile: PASS
- pytest: 10 passed

## Safety
- Read-only inspection only.
- No memory/semantic writes.
- No FAISS writes.
- No broker/IBKR.
- No real money.
