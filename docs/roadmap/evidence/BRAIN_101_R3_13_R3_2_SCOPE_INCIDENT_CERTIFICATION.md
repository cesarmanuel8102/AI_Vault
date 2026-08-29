# BRAIN-101-R3.13 R3.2 Scope Incident Certification

## Document Identifier

- **Front ID:** BRAIN-101-R3-13-R3-2-SCOPE-INCIDENT-CERTIFICATION-01
- **Cycle:** 0
- **Scope:** Certify the canonical Agent V2 cognitive pipeline contracts after preserving the R3.2 scope incident without treating PR #199 as contract-compliant
- **Domain:** governance_certification
- **Deployment:** NO_DEPLOY

## Purpose

This front certifies that the five canonical R3.2 Python contract suites and their evidence document remain intact and verifiable from the current immutable integration base, while preserving the R3.2 scope incident as a `SUPERSEDED_SCOPE_INCIDENT`. PR #199 is explicitly recorded as the historical merged PR that introduced out-of-contract paths; it is **not** represented as compliant with its original six-path contract.

## Preserved R3.2 Scope Incident

The incident record in `docs/roadmap/evidence/BRAIN_101_R3_2_SCOPE_INCIDENT.json` is preserved with:

- `incident_class`: `MERGED_PR_SCOPE_VIOLATION`
- `disposition`: `SUPERSEDED_SCOPE_INCIDENT`
- `historical_pr_treated_as_compliant`: `false`
- `historical_lifecycle_preserved`: `true`
- `replacement_item`: `R3.13`
- `replacement_front_id`: `BRAIN-101-R3-13-R3-2-SCOPE-INCIDENT-CERTIFICATION-01`

## PR #199 Path Audit

### Merge commit

- `merge_commit_sha`: `749ada1458e3092614b6e8c72380e350cbd46514`
- `original_base_sha`: `af17c6bc06c6a88465ecca054177f955c232afd2`
- `candidate_head_sha`: `28b2613adb5370865920ad0eae2b486e15f85f70`

### Originally authorized paths (six)

1. `docs/roadmap/evidence/BRAIN_101_R3_2_AGENT_V2_COGNITIVE_PIPELINE_CONTRACTS.md`
2. `tests/contract/test_brain_101_r3_2_evaluator_contract.py`
3. `tests/contract/test_brain_101_r3_2_intent_router_contract.py`
4. `tests/contract/test_brain_101_r3_2_planner_contract.py`
5. `tests/contract/test_brain_101_r3_2_runtime_lifecycle_contract.py`
6. `tests/contract/test_brain_101_r3_2_tool_gateway_contract.py`

### Observed PR #199 paths (nine)

1. `docs/roadmap/evidence/BRAIN_101_R3_2_AGENT_V2_COGNITIVE_PIPELINE_CONTRACTS.md`
2. `scripts/operator_proxy/autonomous_flow.ts`
3. `tests/contract/operator_proxy/autonomous_flow.test.ts`
4. `tests/contract/test_brain_101_r3_2_evaluator_contract.py`
5. `tests/contract/test_brain_101_r3_2_intent_router_contract.py`
6. `tests/contract/test_brain_101_r3_2_planner_contract.py`
7. `tests/contract/test_brain_101_r3_2_runtime_lifecycle_contract.py`
8. `tests/contract/test_brain_101_r3_2_tool_gateway_contract.py`
9. `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`

### Out-of-contract paths (three)

1. `scripts/operator_proxy/autonomous_flow.ts`
2. `tests/contract/operator_proxy/autonomous_flow.test.ts`
3. `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`

## Canonical Contract Suite Verification

The following five canonical R3.2 Python contract suites are present and unmodified in the current immutable integration base:

| Surface | Contract Test File | Status |
|---|---|---|
| C2 Intent Router | `tests/contract/test_brain_101_r3_2_intent_router_contract.py` | Verified present |
| C3 Planner | `tests/contract/test_brain_101_r3_2_planner_contract.py` | Verified present |
| C4 Evaluator | `tests/contract/test_brain_101_r3_2_evaluator_contract.py` | Verified present |
| C6 Tool Gateway | `tests/contract/test_brain_101_r3_2_tool_gateway_contract.py` | Verified present |
| C1 Runtime Lifecycle | `tests/contract/test_brain_101_r3_2_runtime_lifecycle_contract.py` | Verified present |

The canonical evidence document `docs/roadmap/evidence/BRAIN_101_R3_2_AGENT_V2_COGNITIVE_PIPELINE_CONTRACTS.md` is also present and unmodified.

## Certification Statement

- R3.2 is preserved as `SUPERSEDED_SCOPE_INCIDENT`.
- PR #199 is recorded as a historical merged PR that exceeded its authorized scope.
- PR #199 is **not** represented as contract-compliant with its original six-path authorization.
- The five canonical R3.2 Python contract suites and their evidence document are certified from the current immutable integration base.
- No runtime code, tests, governance logic, memory, FAISS, trading, financial autonomy, CI, environment files, or canonical local state were modified by this certification front.

## Preserved Invariants

- Human final authority: true
- Live trading enabled: false
- Real money enabled: false
- Canonical local sync: false
- Auto-merge: false
- Deployment mode: NO_DEPLOY

## Change Record

| Cycle | Date | Change | Author |
|---|---|---|---|
| 0 | 2026-08-29 | Created R3.13 scope incident certification evidence document. | OpenCode executor |

---
*End of certification document.*
