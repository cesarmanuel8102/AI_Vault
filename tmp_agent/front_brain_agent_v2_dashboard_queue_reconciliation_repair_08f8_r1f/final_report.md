# FRONT-BRAIN-AGENT-V2-DASHBOARD-QUEUE-RECONCILIATION-REPAIR-08F8-R1F

Status: IMPLEMENTED_VALIDATED

## Issue
The Agent V2 answer to the promotion queue question was honest but insufficient: it checked only canonical filesystem promotion queues and did not query the dashboard/learning candidate source that can drive visible dashboard counts.

## Fix
- `promotion_queue_status` now returns canonical queue evidence and dashboard-learning reconciliation.
- The reconciliation documents `/brain/learning/status`, `learning_status_latest.json`, and the frontend formula from `dashboard_secondary_panels.js`.
- Smoke coverage now requires this reconciliation to be present.

## Current Observed Values
- Canonical promotion/review queue dirs existing: 0
- Canonical promotion/review queue entries: 0
- Dashboard learning proposal count: 8
- Dashboard learning candidate_promote_count: 0
- Evaluation passed candidate count: 0

If the visible UI still shows `57`, that number is not from canonical promotion queues or the current learning candidate_promote count; it must come from another panel/cache/endpoint and should be probed by its exact DOM/API source.

## Validation
- py_compile: PASS
- pytest: 10 passed

## Safety
- No broker/IBKR touched.
- No real money used.
- No semantic memory writes.
- No FAISS writes.
