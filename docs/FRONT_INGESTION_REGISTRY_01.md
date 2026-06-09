# FRONT-INGESTION-REGISTRY-01

## Executive Summary

Created a read-only ingestion source registry (`brain/ingestion_registry.py`) that defines, validates, and classifies candidate sources for controlled ingestion without executing any ingestion, dry-runs, or storage writes.

## What This Front Does

1. **Defines a source schema** with fields: `source_id`, `source_type`, `uri`, `risk_level`, `allowed_mode`, `content_policy`, and governance flags.
2. **Validates source records** against business rules:
   - High risk cannot auto-ingest
   - Blocked cannot dry-run
   - Credential-sensitive cannot auto-ingest
   - Unknown content policy requires operator review
3. **Classifies sources** by residual risk and eligibility (dry-run, auto-ingest).
4. **Provides a default registry** with 6 safe example sources covering all types and risk levels.
5. **Summarizes registries** by risk level, allowed mode, and source type.

## What This Front Explicitly Does NOT Do

- **No ingestion execution** — the module does not read, parse, or ingest any content.
- **No semantic memory write** — `can_write_semantic_memory` is hardcoded to `False` for all records.
- **No FAISS write** — `can_promote_faiss` is hardcoded to `False` for all records.
- **No network calls** — no requests, httpx, aiohttp, or urllib usage.
- **No connector calls** — no external APIs invoked.
- **No file writes** — the module is pure Python with no I/O.
- **No dry-run execution** — this front only prepares the registry; dry-runs are the scope of the next front (`FRONT-INGESTION-DRY-RUN-01`).

## Source Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| source_id | str | Yes | Stable slug identifier |
| source_type | str | Yes | One of: local_file, local_directory, uploaded_document, manual_text, connector_reference, api_reference, web_reference |
| uri | str | Yes | Local path or logical reference (no secrets) |
| display_name | str | No | Human-readable name |
| description | str | No | Description |
| risk_level | str | Yes | low, medium, high, blocked |
| allowed_mode | str | Yes | registry_only, dry_run_only, operator_review_required, blocked |
| content_policy | str | Yes | public, user_private, credential_sensitive, unknown |
| requires_operator_approval | bool | Yes | Default: False |
| can_auto_ingest | bool | Yes | Default: False |
| can_write_semantic_memory | bool | Yes | **Always False in this front** |
| can_promote_faiss | bool | Yes | **Always False in this front** |
| notes | list[str] | No | Additional notes |

## Risk Levels

- **low**: Safe sources, may be eligible for dry-run
- **medium**: Requires operator review or dry-run only
- **high**: Cannot auto-ingest; requires explicit approval
- **blocked**: Completely blocked from any processing

## Allowed Modes

- **registry_only**: Listed in registry, no further action allowed
- **dry_run_only**: May be used in dry-run ingestion (next front)
- **operator_review_required**: Requires explicit human approval
- **blocked**: Not allowed for any use

## Default Registry

| source_id | source_type | risk_level | allowed_mode | content_policy |
|-----------|-------------|------------|--------------|----------------|
| manual_text_low_risk | manual_text | low | registry_only | public |
| uploaded_document_operator_review | uploaded_document | medium | operator_review_required | user_private |
| local_file_dry_run_only | local_file | low | dry_run_only | public |
| connector_reference_operator_review | connector_reference | medium | operator_review_required | public |
| api_reference_blocked_until_credentials_policy | api_reference | blocked | blocked | credential_sensitive |
| web_reference_operator_review | web_reference | medium | operator_review_required | public |

## Safety Guarantees

- Pure Python, no external dependencies
- No network access
- No file I/O (read or write)
- No environment variable reads
- No token logging or secret exposure
- No ingestion execution
- No promotion to semantic memory or FAISS
- Deterministic and fully testable

## Tests Run

```
python -m py_compile brain/ingestion_registry.py
python -m py_compile tests/smoke/smoke_front_ingestion_registry_01.py
python -m pytest tests/smoke/smoke_front_ingestion_registry_01.py -q
```

**Result: 27 passed, 0 failed**

## Files Created

- `brain/ingestion_registry.py` — registry module
- `tests/smoke/smoke_front_ingestion_registry_01.py` — 27 smoke tests
- `docs/FRONT_INGESTION_REGISTRY_01.md` — this document

## Evidence (not staged)

- `tmp_agent/front_ingestion_registry_01/ingestion_inventory.json`
- `tmp_agent/front_ingestion_registry_01/ingestion_inventory.md`
- `tmp_agent/front_ingestion_registry_01/ingestion_registry_contract.json`
- `tmp_agent/front_ingestion_registry_01/ingestion_registry_contract.md`
- `tmp_agent/front_ingestion_registry_01/static_safety_check.json`
- `tmp_agent/front_ingestion_registry_01/static_safety_check.md`
- `tmp_agent/front_ingestion_registry_01/test_results.txt`

## Recommended Next Front

**FRONT-INGESTION-DRY-RUN-01** — Execute controlled dry-run ingestion using the registry sources marked as `dry_run_only` or `operator_review_required`, without writing to semantic memory or FAISS.
