# FRONT-INGESTION-REVIEWED-DRY-RUN-EXECUTION-01

## Executive Summary

Created a reviewed dry-run execution planner (`brain/ingestion_reviewed_dry_run_execution.py`) that consumes approval decision results and determines which items are eligible for reviewed dry-run execution. In the default state, **zero items are approved** — all are either `more_context_required` or `blocked` — so the gate correctly reports zero execution candidates.

## Scope

This front filters approval decisions and classifies items into execution statuses. It does NOT execute real ingestion, does NOT read content, does NOT write to storage, and does NOT trigger any real actions.

## What This Front Does

1. **Reads approval decision results** from `brain/ingestion_approval_decision_dry_run.run_approval_decision_dry_run()`
2. **Maps decision statuses to execution statuses**:
   - `accepted_for_future_dry_run` -> `reviewed_dry_run_planned`
   - `more_context_required` -> `reviewed_dry_run_skipped_no_approval`
   - `kept_blocked` -> `blocked`
   - `no_action` -> `no_action`
   - `rejected` -> `rejected`
   - `denied_invalid_decision` -> `invalid`
3. **Sets allowed execution modes**:
   - `reviewed_dry_run_planned` -> `future_controlled_dry_run_only`
   - All others -> `none`
4. **Generates immutable safety flags** documenting no execution occurred
5. **Validates** count consistency and structure

## What This Front Explicitly Does NOT Do

- **No ingestion execution** — content is never read or parsed
- **No semantic memory write** — `memory_write_executed` is hardcoded to `False`
- **No FAISS write** — `faiss_write_executed` is hardcoded to `False`
- **No network calls** — no requests, httpx, aiohttp, or urllib usage
- **No connector calls** — no external APIs invoked
- **No file I/O** — URIs are referenced but never read
- **No real execution** — even `reviewed_dry_run_planned` is only a planning step
- **No promotion** — no knowledge is promoted to any storage

## Reviewed Dry-Run Execution Contract

### Input
- `brain.ingestion_approval_decision_dry_run.run_approval_decision_dry_run()` (6 records)

### Execution Item Fields
- `execution_id`: deterministic ID
- `decision_id`: original decision ID
- `source_id`: source identifier
- `decision_status`: status from decision phase
- `execution_status`: mapped execution status
- `execution_reason`: explanation
- `allowed_execution_mode`: allowed next execution mode
- `safety_flags`: immutable assertions

## Execution Statuses

- **reviewed_dry_run_planned**: Item approved for future controlled dry-run step
- **reviewed_dry_run_skipped_no_approval**: Item not approved, skipped
- **blocked**: Item is blocked
- **no_action**: No action needed
- **rejected**: Item was rejected
- **invalid**: Invalid decision

## Default Zero-Approval Behavior

In the default state with all default decisions (`request_more_context`):

| Status | Count | Records |
|--------|-------|---------|
| reviewed_dry_run_planned | 0 | — |
| reviewed_dry_run_skipped_no_approval | 4 | local_file, uploaded_document, connector_reference, web_reference |
| blocked | 1 | api_reference_blocked_until_credentials_policy |
| no_action | 1 | manual_text_low_risk |
| rejected | 0 | — |
| invalid | 0 | — |

**Zero items are approved for execution. All 6 items are accounted for.**

## Safety Flags

All execution items carry immutable safety flags:

```json
{
  "ingestion_executed": false,
  "content_read": false,
  "memory_write_executed": false,
  "faiss_write_executed": false,
  "network_called": false,
  "connector_called": false,
  "promotion_executed": false
}
```

## Tests Run

```
python -m py_compile brain/ingestion_reviewed_dry_run_execution.py
python -m py_compile tests/smoke/smoke_front_ingestion_reviewed_dry_run_execution_01.py
python -m pytest tests/smoke/smoke_front_ingestion_reviewed_dry_run_execution_01.py -q
```

**Result: 28 passed, 0 failed**

## Safety Guarantees

- Pure Python, no external dependencies
- No network access
- No file I/O (read or write)
- No environment variable reads
- No token logging or secret exposure
- No ingestion execution
- No promotion to semantic memory or FAISS
- Default result has **zero approved execution items**
- All 6 items are accounted for in execution statuses
- Deterministic and fully testable

## Files Created

- `brain/ingestion_reviewed_dry_run_execution.py` — reviewed dry-run execution module
- `tests/smoke/smoke_front_ingestion_reviewed_dry_run_execution_01.py` — 28 smoke tests
- `docs/FRONT_INGESTION_REVIEWED_DRY_RUN_EXECUTION_01.md` — this document

## Recommended Next Front

**FRONT-INGESTION-MANUAL-APPROVAL-SAMPLE-01** — Create a manual approval sample/test that demonstrates how an operator would manually approve an item, triggering the `reviewed_dry_run_planned` status for a single synthetic case.
