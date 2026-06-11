# FRONT-EXTERNAL-CURATED-LEARNING-CANARY-RETRIEVAL-EVAL-SECURITY-GOVERNANCE-01

## Objective

Evaluate if the 5 canary records from batch `SEC_GOV_CANARY_001` are recoverable and useful from semantic memory, without FAISS, without embeddings, and without mutating anything.

## Memory-Only Context

The 5 canary records were ingested as memory-only:
- `faiss_eligible`: false
- `faiss_embedding_text`: ""
- FAISS ids count remains 1611

Therefore, **FAISS retrieval is not expected yet**. This evaluation focuses on direct memory access from `semantic_memory.jsonl`.

## Batch Details

| Field | Value |
|-------|-------|
| batch_id | SEC_GOV_CANARY_001 |
| domain | security_governance_sandboxing |
| records_evaluated | 5 |
| source_ids | nist_csf, nist_ai_rmf, opa_docs, mitre_atlas, gvisor_docs |

## Direct Memory Retrieval Evaluation

| Metric | Value |
|--------|-------|
| Top-1 Hit Rate | 100% |
| Top-3 Hit Rate | 100% |
| Top-5 Hit Rate | 100% |
| Average MRR | 1.0000 |
| Domain Precision | 100% |

All 8 queries returned at least one canary record in top-5.
All 8 queries had top-3 hits.

### Queries Tested

1. AI risk management framework
2. cybersecurity framework governance controls
3. policy gates for autonomous actions
4. adversarial tactics against AI systems
5. sandboxing autonomous tools
6. security governance sandboxing
7. OPA policy enforcement
8. gVisor sandbox isolation

## Negative Query / Contamination Evaluation

- **contamination_detected**: false
- **forbidden_fields_found**: 0
- **domain_contamination**: 0

### Negative Queries Tested

1. best trading signal for SPY
2. broker API execute order
3. autonomous coding patch generation
4. guaranteed investment returns
5. bypass approval gate

All queries returned zero canary records.
No forbidden fields found.
No domain contamination.

## Chat/UI Read-Only Probe

- **Status**: PARTIAL
- **Successful**: 4/5
- **Note**: Not a hard failure because evaluation is memory-only direct retrieval

### Probes

1. Does batch SEC_GOV_CANARY_001 exist? — SUCCESS
2. What sources are in SEC_GOV_CANARY_001? — SUCCESS
3. What did Brain learn about AI risk management framework? — ERROR (timeout)
4. What did Brain learn about sandboxing autonomous tools? — SUCCESS
5. Was FAISS modified by this canary? — SUCCESS

## Immutability Proof

- **semantic_memory.jsonl lines**: 1715 (unchanged during eval)
- **FAISS ids count**: 1611 (unchanged during eval)
- **semantic memory SHA**: unchanged from baseline
- **FAISS index SHA**: unchanged from baseline
- **FAISS ids SHA**: unchanged from baseline
- **No staged/unstaged memory or FAISS changes**

## Tests

- 34/34 smoke tests passed
- All py_compile checks passed

## Safety Proof

- **Memory mutated during this front**: false
- **FAISS mutated**: false
- **Embeddings created**: false
- **Broker/API used**: false
- **Trading used**: false

## Next Recommended Front

`FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-PROMOTION-PREP-SECURITY-GOVERNANCE-01` — **LOCKED** pending explicit user approval.
