# BR2 — Post-Audit Brain Functional Coherence and Integration Readiness (Design)

**Status:** OWNER_AUTHORIZED (this session)
**Track:** BRAIN (GLM/OpenCode)
**Roadmap anchor:** BRAIN-101-REMEDIATION (`docs/roadmap/BRAIN_101_SCORECARD.json`: external certification `REJECTED_PENDING_REMEDIATION`); BR2 is the second remediation front after BR1 (Semantic Completion / Evidence Integrity, PR #391, merge `ae3be637`).

## Purpose

Close the Brain-side gaps that remain REAL in the current bytes after the
BR0 certification-state reconciliation and the BR1 semantic-completion
authority merge, so that a FUTURE Brain ↔ HIVE integration can be built on
immutable receipt contracts without re-opening the false-certification
pattern.

## Non-goals

- No HIVE integration, transport, or execution.
- No strategy code, backtesting, selector, parameter, or QC campaign logic
  in Brain (those are HIVE-owned under the boundary defined by this
  authorization).
- No persistent Agent Loop activation, scheduler activation, canonical
  local sync, installation, deployment, trading, or real money.
- No second semantic evaluator: `evaluateSemanticCompletion()` in
  `scripts/operator_proxy/semantic_completion_gate.ts` remains the single
  semantic PASS/BLOCK authority (PR #391).
- No rewrite of historical receipts (R0–R19) or of the BR0/BR1 records.

## Ownership boundary (authoritative for BR2)

HIVE owns: strategy research, datasets/manifests, backtesting, strategy
validation execution, parameter surfaces, sleeve/selector research, QC
prospective paper evidence production.

Brain owns: cognition, governance, policy, operator authority, future
portfolio consumption, compliance enforcement, and VALIDATION/CONSUMPTION
of immutable incoming receipts produced by HIVE.

## Findings rebaselined (PHASE 1/2 classifications)

| # | Prior audit area | Classification | Current evidence |
|---|---|---|---|
| 1 | Canonical certification metadata coherence | CLOSED | `docs/roadmap/BRAIN_101_SCORECARD.json` `external_certification.status=REJECTED_PENDING_REMEDIATION`; `BRAIN_101_MANIFEST.json` `certification_status=REJECTED_PENDING_REMEDIATION`; contract test `tests/contract/test_br0_canonical_certification_reconciliation.py` (lines 30–49) enforces coherence; roadmap header (lines 3–8) carries the historical note. |
| 2 | MemoryService single-writer ownership | CLOSED | `tmp_agent/brain_v9/core/memory_service.py:110` owns candidate parsing; `tmp_agent/brain_v9/memory/promotion_candidate_promoter.py` is a delegating facade with NO direct JSONL/FAISS/snapshot writes (verified: no `open(`/`json.dump` in write path; `write_performed: False` receipt, line 29). |
| 3 | Agent V2 vs legacy cognitive-stack duplication | CLOSED (as governed convergence) | `tmp_agent/brain_v9/main.py:32,232` routes chat through `agent_kernel_v2.api_adapter`; contract `tests/contract/test_r5_4_agent_v2_cognitive_route_convergence.py` enforces one canonical runtime route owner; legacy `brain_v9/agent/` tools remain executor utilities, not a parallel route. |
| 4 | PortfolioManager Brain-side responsibility | CLOSED (baseline) / OPEN (receipt provenance) | `tmp_agent/brain_v9/core/portfolio_manager_paper_baseline.py` implements deterministic paper-only allocation/ledger; BUT its `PaperEligibleStrategyValidationReceipt` (lines 51–58) carries no provenance binding (no issuer, no evidence hash, no source SHA). → BR2-1. |
| 5 | Compliance Brain-side responsibility | CLOSED | `tmp_agent/brain_v9/core/paper_trading_compliance_policy.py` — deterministic evaluator, paper-only boundary cannot be changed by a non-paper request (line 43 `paper_only: True`), receipt_sha256-bound; integration contract `tests/contract/test_r15_2_paper_portfolio_compliance_risk_integration.py`. |
| 6 | Receipt-consumer interfaces | PARTIAL → OPEN | Only `PaperEligibleStrategyValidationReceipt` exists; no generic `StrategyValidationReceipt` consumer contract and no `PaperExecutionReceipt` interface for the future HIVE boundary. → BR2-1/BR2-2. |
| 7 | financial_autonomy wiring | CLOSED | `financial_autonomy_paper_inventory.py` (`PAPER_ONLY`, line 42) + `financial_autonomy_paper_audit.py` (`_RISK_GATE_STATE = "PAPER_ONLY_APPROVED"`, line 15); no runtime effects (`*_no_effects` guards). |
| 8 | Governance/policy wiring | CLOSED | `agent_kernel_v2/governance_policy.py` explicit policy decisions; `governance.py` tool-level gate; permanent tests under `tests/contract/test_r5_*`. |
| 9 | Paper-only safety gates | CLOSED | `paper_soak_incident_evidence.py` forbids broker/provider/network/runtime/scheduler/live/real-money effects by construction; `portfolio_manager_paper_baseline._FORBIDDEN_EFFECTS` (lines 18–33). |
| 10 | Semantic completion authority | CLOSED (BR1) | Single authority `scripts/operator_proxy/semantic_completion_gate.ts` (PR #391, CI step "Semantic completion regression"); R15 truthful decision BLOCK `[MISSING_EVIDENCE, PARENT_REQUIREMENT_UNSATISFIED]`; AGENTS.md persistent completion rule. |
| 11 | Persistent loop state | CLOSED (deferred, truthful) | Scorecard records `persistent_agent_loop_deferred` in the truthful deferred-capability inventory; no loop is running. |
| 12 | Canonical runtime state | CLOSED (unchanged) | Canonical `C:\AI_VAULT` remains at `766142d0` — no local sync performed by this front. |
| 13 | Strategy research / backtesting / selector gaps | SUPERSEDED_BY_HIVE_BOUNDARY | All strategy-execution concerns are HIVE-owned under this authorization; Brain must not rebuild them. |

## BR2 requirements (only currently-real Brain-side gaps)

### BR2-1 — Immutable receipt provenance for the existing paper-portfolio consumer

- requirement_id: `BR2-1-RECEIPT-PROVENANCE`
- source finding: Rebaseline item 4/6 — the existing
  `PaperEligibleStrategyValidationReceipt` accepts any caller-supplied
  dataclass instance with no proof of origin.
- current evidence:
  `tmp_agent/brain_v9/core/portfolio_manager_paper_baseline.py:51-58`
  (fields: receipt_id, strategy_id, eligibility, asset_bucket,
  correlation_group, expected_attribution_bps — no issuer, no evidence
  digest, no source identity).
- acceptance criteria:
  1. The receipt type gains mandatory provenance fields
     (`issuer_id`, `validation_evidence_sha256`) with strict format
     validation (issuer identifier grammar; lowercase hex SHA-256).
  2. `_validated_receipts` rejects receipts missing or malformed
     provenance (structural fail-closed, not silent acceptance).
  3. Duplicate detection extends unchanged.
  4. Existing allocation/ledger math, hashes, and outputs for valid
     receipts are unchanged (byte-stable canonical sha for valid inputs).
  5. No network, HIVE, QC, broker, or runtime import is added.
- tests:
  `tests/contract/test_br2_receipt_provenance.py` (RED first): malformed
  issuer, malformed digest, missing fields rejected; valid provenance
  passes; canonical portfolio/ledger hashes unchanged; regression on
  `test_r12_1_portfolio_manager_allocation_ledger_baseline.py`.
- allowed paths:
  `tmp_agent/brain_v9/core/portfolio_manager_paper_baseline.py`,
  `tests/contract/test_br2_receipt_provenance.py`,
  `tests/contract/test_r12_1_portfolio_manager_allocation_ledger_baseline.py` (fixture updates only),
  `tests/contract/test_r12_3_portfolio_regime_rebalance_risk_attribution_validation.py` (fixture updates only),
  `tests/contract/test_r15_2_paper_portfolio_compliance_risk_integration.py` (fixture updates only).
- forbidden paths: everything else; especially no `scripts/operator_proxy`
  semantic authority changes, no HIVE paths, no scheduler/broker/runtime.
- activation impact: NONE — pure library-level contract; nothing runs in
  any runtime until a future owner decision.

### BR2-2 — Brain-side immutable receipt consumer boundary contract

- requirement_id: `BR2-2-RECEIPT-CONSUMER-BOUNDARY`
- source finding: Rebaseline item 6 — no documented Brain-side contract
  defining WHAT Brain may consume from HIVE and what may never cross.
- current evidence: absence of any `StrategyValidationReceipt` /
  `PaperExecutionReceipt` interface in `tmp_agent/` (rg over the tree);
  roadmap header requirement that future integration is receipt-based.
- acceptance criteria:
  1. A new Brain-owned module defines ONLY schema/validator/consumer
     contracts for immutable incoming receipts: a generic
     `StrategyValidationReceipt` (superset contract with provenance
     fields aligned with BR2-1) and a `PaperExecutionReceipt` interface
     (frozen dataclass, strict formats, fail-closed validation).
  2. The module documents and enforces the import boundary: receipts are
     immutable data + hash bindings; Brain must NOT import raw strategy
     code, mutable QC experiment state, HIVE optimizer/selector state.
  3. A `reject_receipt_transport` guard mirrors the paper-only
     `_FORBIDDEN_EFFECTS` pattern: any attempt to move mutable state or
     code through this boundary fails closed.
  4. No end-to-end transport exists: validation is pure; there is no
     producer, queue, network, or HIVE call.
  5. Consumers are wired nowhere by default; the contracts exist for the
     future owner-authorized integration.
- tests:
  `tests/contract/test_br2_receipt_consumer_boundary.py` (RED first):
  valid receipts validate; malformed/duplicated fail closed; forbidden
  transport operations raise; schema is closed (no unknown fields).
- allowed paths:
  `tmp_agent/brain_v9/core/hive_receipt_boundary.py` (new),
  `tests/contract/test_br2_receipt_consumer_boundary.py` (new).
- forbidden paths: all HIVE/QC/strategy paths; no transport, no network.
- activation impact: NONE — dormant contract; no runtime wiring.

### BR2-3 — Brain-side record of BR1 semantic authority (consumption pointer, not re-implementation)

- requirement_id: `BR2-3-SEMANTIC-AUTHORITY-POINTER`
- source finding: Rebaseline item 10 follow-through — Brain-side soak/
  closeout helpers do not record which authority governs semantic
  completion, leaving future integration free to invent a second
  evaluator.
- current evidence: no reference to the BR1 registry/manifest/authority
  in `tmp_agent/brain_v9/core/paper_*` modules; single authority lives in
  `scripts/operator_proxy/semantic_completion_gate.ts` (PR #391).
- acceptance criteria:
  1. A documentation-only Brain-side evidence record binds the future
     receipt-consumption boundary to the EXISTING BR1 semantic authority
     path (registry, manifest, classifier contracts) — pointer only.
  2. The record explicitly states Brain does not re-evaluate semantics and
     that any semantic PASS/BLOCK question routes through the BR1 gate.
  3. A contract test asserts the record exists, names the authority files,
     and forbids the creation of a second evaluator path inside
     `tmp_agent/brain_v9/core/`.
- tests: `tests/contract/test_br2_semantic_authority_pointer.py` (new).
- allowed paths: `docs/roadmap/evidence/BRAIN_101_BR2_SEMANTIC_AUTHORITY_POINTER.json` (new),
  `tests/contract/test_br2_semantic_authority_pointer.py` (new).
- forbidden paths: `scripts/operator_proxy/**` (authority untouched), all
  HIVE paths.
- activation impact: NONE — documentation contract only.

## Certification discipline

Every BR2 item is reported as IMPLEMENTED + TESTED (merged) and NOT
RUNTIME_ACTIVATED. R15 semantic truth remains
`BLOCK [MISSING_EVIDENCE, PARENT_REQUIREMENT_UNSATISFIED]` until real
qualifying soak evidence exists; BR2 must not fabricate or start that
soak. Roadmap-closed ≠ capability-certified remains the standing rule
(`AGENTS.md` persistent completion rule; BR0 contract).