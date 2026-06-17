# Retrieval Evaluation Plan
**Batch ID:** SEC_GOV_CANARY_001
**Domain:** security_governance_sandboxing

## Planned Queries
- governance controls before autonomous financial actions
- AI risk management framework
- prompt injection defense for LLM agents
- sandboxing autonomous tools
- approval gates before high-risk actions
- canary ingestion security governance

## Metrics
- **top_1_hit**: Relevant record in top-1 result
- **top_3_hit**: Relevant record in top-3 results
- **top_5_hit**: Relevant record in top-5 results
- **top_10_hit**: Relevant record in top-10 results
- **mrr**: Mean Reciprocal Rank for first relevant result
- **domain_precision**: Fraction of retrieved results matching security_governance_sandboxing domain
- **contamination_check**: No rejected or hold sources appear in results
- **duplicate_check**: No duplicate memory_id in retrieved results
- **rejected_source_absence**: Zero rejected sources retrieved
- **hold_source_absence**: Zero hold sources retrieved

## Pass Criteria
- No Rejected Source Retrieved: True
- No Hold Source Retrieved: True
- No Financial Source In Top 3: True
- No Coding Source In Top 3: True
- No Duplicate Memory Id: True
- No Regression On Baseline: True
- Top 3 Hit Rate Min: 0.8
- Domain Precision Min: 0.9

## Schedule
After canary ingestion is approved and executed, before controlled_batch_01

**Eval Front:** FRONT-EXTERNAL-CURATED-LEARNING-CANARY-RETRIEVAL-EVAL-01
