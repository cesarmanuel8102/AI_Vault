# FRONT-CEI-FDOT-EVALUATION-PACK-01

## Status
`CEI_FDOT_EVALUATION_PACK_CREATED`

This front adds a behavior-focused CEI/FDOT evaluation pack. It does not embed or invent official FDOT specification requirements. The pack tests whether Brain asks for evidence, states uncertainty, requests missing spec year or project context, avoids fabricated section citations, and distinguishes field guidance from official specifications.

## Files
- `tests/fixtures/cei_fdot_eval_pack_v1.json`
- `tests/smoke/smoke_front_cei_fdot_evaluation_pack_01.py`

## Safety
- internet_used: `false`
- memory_mutated: `false`
- faiss_mutated: `false`
- trading_touched: `false`
- official_fdot_facts_embedded: `false`

## Intended Next Use
Run this pack through the Codex-to-Brain evaluation harness to score CEI answer behavior before any external FDOT document ingestion is promoted.
