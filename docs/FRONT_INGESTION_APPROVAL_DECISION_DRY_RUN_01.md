# FRONT-INGESTION-APPROVAL-DECISION-DRY-RUN-01

## Executive Summary

Created an approval decision dry-run simulator (`brain/ingestion_approval_decision_dry_run.py`) that consumes the operator review queue and simulates operator decisions without executing real ingestion, reading content, or triggering any external action.

## Scope

This front simulates operator approval decisions on all items in the review queue. It does NOT execute ingestion, does NOT read content, does NOT write to storage, and does NOT trigger any real actions.

## What This Front Does

1. **Reads operator review queue** from `brain/ingestion_operator_review.build_review_queue()`
2. **Applies default decisions** to each review item:
   - `pending_operator_review` -> `request_more_context` -> `more_context_required`
   - `blocked` -> `keep_blocked` -> `kept_blocked`
   - `registry_only` -> `no_action` -> `no_action`
3. **Validates requested decisions** against allowed decisions list
4. **Maps decisions to statuses**:
   - `approve_for_future_dry_run` -> `accepted_for_future_dry_run`
   - `reject` -> `rejected`
   - `request_more_context` -> `more_context_required`
   - `keep_blocked` -> `kept_blocked`
   - `no_action` -> `no_action`
   - Invalid decision -> `denied_invalid_decision`
5. **Generates immutable safety flags** documenting no execution occurred
6. **Validates** that no decision claims real ingestion authorization

## What This Front Explicitly Does NOT Do

- **No ingestion execution** — content is never read or parsed
- **No semantic memory write** — `memory_write_executed` is hardcoded to `False`
- **No FAISS write** — `faiss_write_executed` is hardcoded to `False`
- **No network calls** — no requests, httpx, aiohttp, or urllib usage
- **No connector calls** — no external APIs invoked
- **No file I/O** — URIs are referenced but never read
- **No real approval** — `accepted_for_future_dry_run` only prepares for a future controlled dry-run step, NOT real ingestion
- **No promotion** — no knowledge is promoted to any storage

## Approval Decision Contract

### Input
- `brain.ingestion_operator_review.build_review_queue()` (6 records)

### Decision Item Fields
- `decision_id`: deterministic ID
- `review_id`: original review item ID
- `source_id`: source identifier
- `review_status`: status from review phase
- `requested_decision`: decision requested
- `applied_decision`: decision actually applied
- `decision_status`: result of decision application
- `decision_reason`: explanation
- `allowed_next_step`: next allowed action
- `approval_authorizes_real_ingestion`: always `False`
- `can_write_semantic_memory`: always `False`
- `can_promote_faiss`: always `False`
- `safety_flags`: immutable assertions

## Decision Statuses

- **accepted_for_future_dry_run**: Approved for future controlled dry-run (NOT real ingestion)
- **rejected**: Operator rejected
- **more_context_required**: Operator requested more information
- **kept_blocked**: Remains blocked
- **no_action**: No action needed
- **denied_invalid_decision**: Requested decision not allowed

## Safety Flags

All decisions carry immutable safety flags:

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

## Decision Result Summary (from 6 records with default decisions)

| Status | Count | Records |
|--------|-------|---------|
| accepted_for_future_dry_run | 0 | — |
| rejected | 0 | — |
| more_context_required | 4 | local_file, uploaded_document, connector_reference, web_reference |
| kept_blocked | 1 | api_reference_blocked_until_credentials_policy |
| no_action | 1 | manual_text_low_risk |
| denied_invalid_decision | 0 | — |

## Tests Run

```
python -m py_compile brain/ingestion_approval_decision_dry_run.py
python -m py_compile tests/smoke/smoke_front_ingestion_approval_decision_dry_run_01.py
python -m pytest tests/smoke/smoke_front_ingestion_approval_decision_dry_run_01.py -q
```

**Result: 27 passed, 0 failed**

## Safety Guarantees

- Pure Python, no external dependencies
- No network access
- No file I/O (read or write)
- No environment variable reads
- No token logging or secret exposure
- No ingestion execution
- No promotion to semantic memory or FAISS
- `approval_authorizes_real_ingestion` is `False` for all decisions
- `can_write_semantic_memory` is `False` for all decisions
- `can_promote_faiss` is `False` for all decisions
- Deterministic and fully testable

## Files Created

- `brain/ingestion_approval_decision_dry_run.py` — approval decision module
- `tests/smoke/smoke_front_ingestion_approval_decision_dry_run_01.py` — 27 smoke tests
- `docs/FRONT_INGESTION_APPROVAL_DECISION_DRY_RUN_01.md` — this document

## Recommended Next Front

**FRONT-INGESTION-REVIEWED-DRY-RUN-EXECUTION-01** — Execute a controlled dry-run for items that have been accepted_for_future_dry_run, without writing to semantic memory or FAISS.
