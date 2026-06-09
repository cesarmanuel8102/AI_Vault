# FRONT-INGESTION-MANUAL-APPROVAL-SAMPLE-01

## Purpose

Demonstrate the complete ingestion pipeline end-to-end with a manually-approved
synthetic source. This is a teaching and validation module that shows how an
operator can approve a source and watch it flow through every stage of the
ingestion pipeline.

## Scope

- Create `brain/ingestion_manual_approval_sample.py` — pipeline orchestrator
- Create `tests/smoke/smoke_front_ingestion_manual_approval_sample_01.py` — smoke tests
- Create this document

## What this module does

1. Builds a synthetic low-risk source record (`synthetic_approved_document`)
2. Runs it through the full pipeline:
   - Registry validation
   - Dry-run planning
   - Operator review queue
   - Approval decision (default + synthetic override)
   - Reviewed dry-run execution
3. Also provides a denied sample (`synthetic_denied_document`) to show rejection flow
4. Reports counts at every stage
5. Does NOT execute real ingestion, does NOT read content, does NOT write storage

## Pipeline stages

| Stage | Module | Output |
|-------|--------|--------|
| Registry | `ingestion_registry` | Validated record |
| Dry-run | `ingestion_dry_run` | `candidate` status |
| Review queue | `ingestion_operator_review` | `pending_operator_review` |
| Decision (default) | `ingestion_approval_decision_dry_run` | `more_context_required` |
| Decision (approved) | `ingestion_approval_decision_dry_run` | `accepted_for_future_dry_run` |
| Execution | `ingestion_reviewed_dry_run_execution` | `reviewed_dry_run_planned` |

## Default vs approved result

### Default decision (no operator action)
- All pending items → `more_context_required` → skipped
- Result: 0 planned, 1 skipped

### Synthetic approval override
- Operator clicks "approve" → `accepted_for_future_dry_run`
- Result: 1 planned, 0 skipped

## Guarantees

- No real ingestion executed
- No content read
- No semantic memory writes
- No FAISS writes
- No network calls
- No connector activation
- Pure Python, no external deps

## Files

- `brain/ingestion_manual_approval_sample.py`
- `tests/smoke/smoke_front_ingestion_manual_approval_sample_01.py`
- `docs/FRONT_INGESTION_MANUAL_APPROVAL_SAMPLE_01.md`

## Tests

Run: `python -m pytest tests/smoke/smoke_front_ingestion_manual_approval_sample_01.py -q`

Expected: 28 tests passed

## Next recommended front

FRONT-INGESTION-MANUAL-APPROVAL-SAMPLE-02 — expand to multi-source batch with mixed approvals/rejections
