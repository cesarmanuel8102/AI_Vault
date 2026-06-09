# FRONT-INGESTION-MANUAL-APPROVAL-SAMPLE-02

## Executive Summary

Multi-source synthetic manual approval/rejection batch sample demonstrating mixed operator decisions across all 6 default registry sources.

## Scope

- Create `brain/ingestion_manual_approval_batch_sample.py` — multi-source batch orchestrator
- Create `tests/smoke/smoke_front_ingestion_manual_approval_sample_02.py` — smoke tests
- Create this document

## What This Front Does

1. Builds the operator review queue from the default registry (6 sources)
2. Applies a **mixed synthetic manual decision plan**:
   - `local_file_dry_run_only` → **approved** for future dry-run
   - `uploaded_document_operator_review` → **rejected**
   - `connector_reference_operator_review` → **more context required**
   - `web_reference_operator_review` → **more context required**
   - `api_reference_blocked_until_credentials_policy` → **kept blocked**
   - `manual_text_low_risk` → **no action**
3. Runs the approval decisions through reviewed dry-run execution
4. Reports counts at every stage

## What This Front Explicitly Does NOT Do

- Does NOT approve real sources
- Does NOT execute real ingestion
- Does NOT read content from URIs
- Does NOT write to semantic memory
- Does NOT promote FAISS
- Does NOT call networks
- Does NOT call connectors
- Does NOT apply patches

## Manual Approval Contract

### Decision Plan

| # | source_id | review_status | synthetic_decision | expected_decision_status |
|---|-----------|---------------|--------------------|--------------------------|
| 1 | local_file_dry_run_only | pending | approve_for_future_dry_run | accepted |
| 2 | uploaded_document_operator_review | pending | reject | rejected |
| 3 | connector_reference_operator_review | pending | request_more_context | more_context |
| 4 | web_reference_operator_review | pending | request_more_context | more_context |
| 5 | api_reference_blocked_until_credentials_policy | blocked | keep_blocked | kept_blocked |
| 6 | manual_text_low_risk | registry_only | no_action | no_action |

### Expected Result

| Status | Count |
|--------|-------|
| reviewed_dry_run_planned | 1 |
| reviewed_dry_run_skipped_no_approval | 2 |
| rejected | 1 |
| blocked | 1 |
| no_action | 1 |
| invalid | 0 |

## Safety Guarantees

- approval_authorizes_real_ingestion: false (all items)
- can_write_semantic_memory: false (all items)
- can_promote_faiss: false (all items)
- ingestion_executed: false
- content_read: false
- memory_write_executed: false
- faiss_write_executed: false
- network_called: false
- connector_called: false
- promotion_executed: false

## Tests

Run: `python -m pytest tests/smoke/smoke_front_ingestion_manual_approval_sample_02.py -q`

Expected: 42 tests passed

## Recommended Next Front

FRONT-INGESTION-MANUAL-APPROVAL-PERSISTENT-QUEUE-01
