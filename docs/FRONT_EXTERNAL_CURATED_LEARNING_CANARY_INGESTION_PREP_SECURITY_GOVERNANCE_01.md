# FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-PREP-SECURITY-GOVERNANCE-01

## Objective

Prepare the first canary ingestion package for the `security_governance_sandboxing` domain.
This is a **dry-run / preparatory front** — no actual ingestion into semantic memory or FAISS occurs.

## Why Security/Governance First

Per the controlled ingestion authorization policy:
- `security_governance_sandboxing` is the designated first canary domain
- It provides governance controls, execution gates, and sandboxing knowledge needed before any other domain is ingested
- Financial and autonomous coding domains are locked for this canary batch

## Selected Sources

| # | Source ID | Group | Title | Safety Score |
|---|-----------|-------|-------|--------------|
| 1 | nist_csf | standard | NIST Cybersecurity Framework (CSF 2.0) | 66 |
| 2 | nist_ai_rmf | standard | NIST AI Risk Management Framework | 65 |
| 3 | opa_docs | docs | Open Policy Agent (OPA) Docs | 63 |
| 4 | mitre_atlas | standard | MITRE ATLAS | 64 |
| 5 | gvisor_docs | docs | gVisor — Userspace Kernel for Containers | 64 |

**Batch ID:** `SEC_GOV_CANARY_001`
**Selected Count:** 5
**All acceptance_status:** `accept`

## Proposed Memory Record Schema

Each proposed record conforms to `controlled_ingestion_memory_record_v1`:

- `memory_id`: unique per record (`SEC_GOV_CANARY_001_<source_id>_<idx>`)
- `schema_version`: `controlled_ingestion_memory_record_v1`
- `domain`: `security_governance_sandboxing`
- `acceptance_status`: `accept`
- `ingestion_status`: `proposed_only`
- `faiss_eligible`: **false** (no FAISS in canary)
- `faiss_embedding_text`: **""** (empty)
- `content_summary`: ≤ 1200 chars
- `retrieval_phrases`: 3–8 phrases

## Human Approval Package

- **Approval phrase required:**
  `APPROVE_SECURITY_GOVERNANCE_CANARY_INGESTION_BATCH_SEC_GOV_CANARY_001`
- **Denial phrase:**
  `DENY_SECURITY_GOVERNANCE_CANARY_INGESTION_BATCH_SEC_GOV_CANARY_001`
- **Memory mutation authorized now:** false
- **FAISS mutation authorized now:** false
- **Requires user approval before mutation:** true
- **Expected memory line count before:** 1710
- **Expected memory line count after (if approved):** 1715
- **Expected FAISS ids count before:** 1611
- **Expected FAISS ids count after (if approved):** 1611

## Retrieval Evaluation Plan

Planned queries for post-ingestion eval:
- governance controls before autonomous financial actions
- AI risk management framework
- prompt injection defense for LLM agents
- sandboxing autonomous tools
- approval gates before high-risk actions
- canary ingestion security governance

Metrics: top_1_hit, top_3_hit, top_5_hit, MRR, domain_precision, contamination_check, duplicate_check, rejected_source_absence, hold_source_absence.

Pass criteria: no rejected/hold/financial/coding sources in top-3; no duplicates; no regression on baseline.

## Backup / Rollback Plan

Files to backup before execution:
- `memory/semantic/semantic_memory.jsonl`
- `memory/semantic/semantic_memory_faiss.index`
- `memory/semantic/semantic_memory_faiss_ids.json`

Planned backup dir:
`tmp_agent/front_external_curated_learning_canary_ingestion_prep_security_governance_01/backups/SEC_GOV_CANARY_001/`

Rollback triggers: schema failure, count mismatch, duplicate memory_id, rejected/hold source appears, retrieval contamination, test failure.

Validation after rollback: SHA equals baseline, memory lines = 1710, FAISS ids = 1611.

## Safety Proof

- **Memory mutated:** false
- **FAISS mutated:** false
- **Broker/API used:** false
- **Trading used:** false
- **Canary ingestion executed:** false

## Tests

- 50/50 smoke tests passed
- All py_compile checks passed
- No memory/FAISS/trading/B8/strategies/.env files staged

## Next Recommended Front

`FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-EXECUTE-SECURITY-GOVERNANCE-01` — **LOCKED** pending explicit user approval phrase.
