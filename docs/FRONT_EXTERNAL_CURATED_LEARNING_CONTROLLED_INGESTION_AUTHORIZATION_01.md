# FRONT-EXTERNAL-CURATED-LEARNING-CONTROLLED-INGESTION-AUTHORIZATION-01

**Timestamp**: 2026-06-11T05:55Z  
**Status**: COMPLETE  
**Branch**: codex/own-capital-sustainable-return  
**Functional Commit**: pending  

## Objective

Create a canonical controlled ingestion authorization plan that defines exactly when, how, and under what human-approved conditions the Brain may ingest curated external sources into semantic memory and FAISS.

## Why Controlled Ingestion Authorization is Required Before Mass Ingestion

After six curated learning fronts (five horizontal + one vertical), the Brain has a rich inventory of safe, attributable sources. However, **none have been ingested into semantic memory yet**. Mass ingestion without controls risks:

- **Contamination**: financial or coding sources influencing governance queries
- **Signal leakage**: trading signals contaminating educational responses
- **Advice boundary violation**: personalized financial advice emerging from retrieved content
- **Copyright violation**: full copyrighted content entering memory
- **Credential leakage**: broker/API docs with credential references entering memory
- **Chain-of-thought exposure**: raw reasoning traces entering retrievable memory

This front creates the **authorization framework** that prevents all of the above.

## Prior Curated Learning State

| Domain | Sources | Accepted | Taxonomy | Capabilities |
|--------|---------|----------|----------|--------------|
| Agentic Systems | 21 | 19 | 14 | 12 |
| Evaluation & Benchmarking | 24 | 22 | 15 | 12 |
| Memory / RAG / Knowledge Architecture | 28 | 25 | 20 | 16 |
| Security / Governance / Sandboxing | 25 | 24 | 22 | 18 |
| Autonomous Coding & Patch Generation | 24 | 23 | 25 | 20 |
| Financial Motor / Trading Intelligence | 28 | 27 | 32 | 24 |

Total: **150 sources** across **6 domains**, **148 accepted**, **32 taxonomy categories**, **122 capabilities**.

## Current Memory / FAISS Baseline

- semantic_memory.jsonl: 1710 lines
- FAISS ids: 1611
- No external curated sources ingested yet

## Why Mass Ingestion is Rejected for Now

- All 150 sources at once would create unmanageable retrieval contamination risk
- No validation that retrieval quality improves rather than degrades
- No baseline for measuring retrieval before/after
- No rollback plan if contamination occurs
- No human approval framework for mutation
- Financial and coding domains must remain locked until governance is proven

## Authorized Domain Order

1. **security_governance_sandboxing** — authorized for future canary
2. **memory_rag_knowledge_architecture** — authorized for future canary
3. **evaluation_benchmarking** — authorized for future canary
4. **agentic_systems** — authorized for future canary
5. **autonomous_coding_patch_generation** — locked until later
6. **financial_motor_trading_intelligence** — locked until later

### Justification

- **Security/Governance first**: teaches constraints, not actions. Lowest contamination risk.
- **Memory/RAG second**: improves infrastructure. No external action risk.
- **Evaluation third**: teaches measurement. Useful for assessing all subsequent domains.
- **Agentic fourth**: expands capabilities. Moderate risk because teaches autonomous patterns.
- **Coding fifth**: locked until security governance ingestion is proven safe.
- **Financial sixth**: locked until all other domains are proven safe and explicit financial-action governance is in place.

## First Canary Recommendation

- **Domain**: security_governance_sandboxing
- **Record count**: 3–5
- **Source status**: accept only
- **Forbidden statuses**: hold, reject, candidate
- **Forbidden domains in canary**: financial_motor_trading_intelligence, autonomous_coding_patch_generation
- **Content type**: metadata summary only, non-executable governance knowledge
- **No full paper text, no full README, no copyrighted long content**

## Batch Limits

### Canary Batch
- Min: 3 records
- Max: 5 records
- One domain only: security_governance_sandboxing
- Requires prior approval: yes
- Requires backup: yes
- FAISS allowed: no (memory-only canary)

### Controlled Batch 01
- Min: 10 records
- Max: 20 records
- Allowed domains: security_governance_sandboxing, memory_rag_knowledge_architecture
- Requires canary pass: yes
- Requires prior approval: yes
- Requires backup: yes
- FAISS allowed: yes

### Controlled Batch 02
- Min: 20 records
- Max: 40 records
- Allowed domains: security_governance_sandboxing, memory_rag_knowledge_architecture, evaluation_benchmarking
- Requires batch 01 pass: yes
- Requires prior approval: yes
- Requires backup: yes
- FAISS allowed: yes

### Agentic / Coding / Financial Batches
- Status: locked
- Requires separate authorization: yes
- No records allowed until unlocked

## Memory Record Schema v1

**Schema version**: `controlled_ingestion_memory_record_v1`

### Required Fields

| Field | Type | Constraint |
|-------|------|------------|
| memory_id | string | extlearn::{domain}::{source_id}::{schema_version} |
| schema_version | string | Must be controlled_ingestion_memory_record_v1 |
| source_id | string | From curation module |
| source_title | string | Human-readable |
| source_group | string | paper, repo, docs, regulatory, etc. |
| source_url | string | Non-empty |
| source_license_or_status | string | License or legal status |
| domain | string | Curated learning domain |
| taxonomy_tags | list[str] | At least 1 tag |
| capability_target | string | Brain capability this targets |
| source_provenance | string | Authors, org, year, maintenance |
| safety_score_estimate | integer | 0-125 |
| acceptance_status | string | Must be accept |
| ingestion_status | string | Begins as proposed |
| ingestion_batch_id | string | Batch identifier |
| created_at_utc | string | ISO timestamp |
| content_summary | string | Max 1200 chars |
| retrieval_phrases | list[str] | 3-8 strings |
| evidence_type | string | paper_summary, repo_metadata, etc. |
| risk_flags | list[str] | Must exist even if empty |
| exclusion_notes | string | Why content was excluded |
| faiss_eligible | boolean | Whether embeddable |
| faiss_embedding_text | string | Max 1600 chars |

### Validation Rules

- schema_version == 'controlled_ingestion_memory_record_v1' (fatal)
- acceptance_status == 'accept' (fatal)
- ingestion_status in ['proposed', 'approved', 'ingested'] (fatal)
- source_url is not empty (fatal)
- len(content_summary) <= 1200 (error)
- len(faiss_embedding_text) <= 1600 (error)
- len(retrieval_phrases) between 3 and 8 (error)
- len(taxonomy_tags) >= 1 (error)
- risk_flags is not None (error)
- faiss_eligible is boolean (error)
- No chain-of-thought in any field (fatal)
- No credentials in any field (fatal)
- No broker/API credentials in any field (fatal)
- No trading signal in any field (fatal)
- No executable code in any field (fatal)

### Forbidden Field Names

- raw_full_text
- copyrighted_full_content
- credentials
- broker_api_data
- trading_signal
- executable_code
- chain_of_thought
- private_user_data

## Source-to-Record Policy

- Accept-only policy
- Hold/reject/candidate excluded
- Metadata summary only
- One memory record per source per domain in canary
- No chunking of full documents
- No recursive web crawling
- No full README ingestion
- No full paper ingestion
- No book content ingestion
- No broker/API docs in first canary
- No financial source in first canary
- No coding source in first canary
- Memory ID deterministic: `extlearn::{domain}::{source_id}::{schema_version}`
- Source provenance required
- Risk flags preserved

## Source Exclusion Policy

Automatically excluded:

- Rejected sources
- Hold sources in canary
- Candidate sources
- Unknown attribution
- No URL
- No license or legal status
- Guaranteed return claims
- Signal-selling claims
- Broker or API credential requirements
- Executable strategy code
- Untrusted external code execution
- Offensive security content not governance-framed
- Copyrighted full books or papers
- Private connector material
- User-private material
- Chain-of-thought content
- trading/* or B8/* content

## Pre-Ingestion Validation Rules

- Repo clean check
- Memory/FAISS baseline snapshot
- Backup requirements:
  - Copy semantic_memory.jsonl
  - Copy semantic_memory_faiss.index
  - Copy semantic_memory_faiss_ids.json
  - Verify backup integrity
- Schema validation
- Source acceptance validation
- Duplicate memory_id check
- Duplicate source_id within batch check
- Content length check
- Forbidden content check
- Domain authorization check
- Financial domain lock check
- Coding domain lock check
- FAISS id uniqueness check
- Dry-run preview required
- Human approval required before actual mutation

## Post-Ingestion Validation Rules

- Memory line count increases exactly by proposed record count
- FAISS ids count increases exactly by faiss_eligible record count
- Every new memory_id exists in semantic_memory.jsonl
- Every FAISS id maps to valid memory record
- No orphan memory records
- No orphan FAISS ids
- No duplicate memory_id
- No duplicate FAISS id
- Retrieval smoke tests pass
- Top-k eval run before/after
- Rollback script available
- Final git diff inspected before commit

## Retrieval Quality Evaluation Requirements

### Pre-Ingestion Baseline Queries
- What are the security governance controls?
- How does the brain evaluate sources?
- What is the memory architecture?

### Post-Ingestion Same Queries
- Must not regress on baseline

### Canary-Domain Target Queries
- What are the NIST AI RMF controls?
- What is the OWASP LLM top 10?
- How does gVisor sandboxing work?

### Required Metrics
- top_1_hit (boolean)
- top_3_hit (boolean)
- top_5_hit (boolean)
- top_10_hit (boolean)
- MRR (float)
- domain_precision (float)
- contamination_check (boolean)
- duplicate_retrieval_check (boolean)

### Pass Criteria
- No regression on existing baseline queries
- Canary records retrievable in top_5
- No financial source retrieved for governance query
- No coding source retrieved for governance query
- No rejected source retrievable
- No hold source retrievable

## Rollback Requirements

- Pre-mutation backup required
- Restore semantic_memory.jsonl
- Restore semantic_memory_faiss.index
- Restore semantic_memory_faiss_ids.json
- Verify SHA returns to baseline
- Verify line counts return to baseline
- Verify FAISS ids count returns to baseline

### Auto-Rollback Triggers
- Schema validation fails
- Line count mismatch
- FAISS id mismatch
- Retrieval regression
- Duplicate ids
- Forbidden content detected
- Wrong domain ingested
- Financial source ingested accidentally
- Coding source ingested accidentally
- Runtime smoke fails

## Human Approval Requirements

- This front does NOT grant actual mutation permission
- Future canary ingestion requires explicit user approval
- Approval must include:
  - domain
  - batch_id
  - source_ids
  - record_count
  - faiss_eligible_count
  - backup_path
  - rollback_path
  - expected_memory_line_count_after
  - expected_faiss_ids_count_after
- Without approval:
  - No memory mutation
  - No FAISS mutation

## Domain Authorization Matrix

| Domain | Canary | Batch 01 | Batch 02 | FAISS | Financial Risk | Execution Risk | Advice Risk | Signal Risk |
|--------|--------|----------|----------|-------|----------------|----------------|-------------|-------------|
| security_governance_sandboxing | yes | yes | yes | yes | low | low | low | low |
| memory_rag_knowledge_architecture | yes | yes | yes | yes | low | low | low | low |
| evaluation_benchmarking | no | no | yes | yes | low | low | low | low |
| agentic_systems | no | no | no | yes | low | medium | low | low |
| autonomous_coding_patch_generation | no | no | no | no | low | high | low | low |
| financial_motor_trading_intelligence | no | no | no | no | high | high | high | medium |

## No Mutation Confirmation

- This front created: authorization plan only
- No semantic memory lines added: 1710 unchanged
- No FAISS ids added: 1611 unchanged
- No actual ingestion executed
- No backup created (not needed for authorization-only front)
- No rollback executed (not needed)

## Memory / FAISS Immutability Proof

| Metric | Before | After | Status |
|--------|--------|-------|--------|
| semantic_memory.jsonl lines | 1710 | 1710 | unchanged |
| semantic_memory.jsonl SHA | 655d323... | 655d323... | unchanged |
| FAISS index SHA | b7b755c... | b7b755c... | unchanged |
| FAISS ids SHA | 0043623... | 0043623... | unchanged |
| FAISS ids count | 1611 | 1611 | unchanged |

## Tests Result

- py_compile: PASS
- smoke tests: 83 passed / 0 failed

## Limitations

- No actual ingestion performed
- No FAISS embeddings created
- No live market data fetched
- No broker APIs connected
- No strategies executed
- No backtests run
- No semantic memory mutation
- Authorization plan is conditional on future human approval
- Financial and coding domains remain locked
- Actual ingestion requires separate front with explicit approval

## Next Recommended Front

**FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-PREP-SECURITY-GOVERNANCE-01**

This front will remain LOCKED until explicitly approved by the operator. It would cover:
- Selecting 3-5 security/governance sources for first canary ingestion
- Creating memory records per schema v1
- Pre-ingestion validation
- Backup creation
- Human approval request
- No actual mutation without approval

---

*End of canonical document for FRONT-EXTERNAL-CURATED-LEARNING-CONTROLLED-INGESTION-AUTHORIZATION-01*
