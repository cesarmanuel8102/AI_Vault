# BR2 — Post-Audit Brain Functional Coherence Implementation Plan

**Spec:** `docs/superpowers/specs/2026-09-19-br2-brain-functional-coherence-design.md`
**Track:** BRAIN (GLM/OpenCode). HIVE, QC, strategy work: FORBIDDEN.
**Runtime activation:** FORBIDDEN (Phase 6 of the authorization).

## Global constraints

- Only the allowed paths of each BR2 item may be touched; every commit is
  verified with `git diff --cached --name-only` against the item's list.
- RED test first, minimal implementation, focused GREEN, full relevant
  regression, self-review, then commit.
- No second semantic evaluator; no HIVE transport; no network; no runtime
  effects; no scheduler/loop/live/money.
- R15 semantic truth remains BLOCK; nothing in BR2 fabricates evidence.

## Task 1 — BR2-1 Receipt provenance (RED → GREEN)

- [ ] RED: `tests/contract/test_br2_receipt_provenance.py` — malformed
      issuer/digest/missing provenance rejected; valid passes; hashes stable.
- [ ] Implement provenance fields + validation in
      `tmp_agent/brain_v9/core/portfolio_manager_paper_baseline.py`.
- [ ] Update affected fixtures in the three R1x contract tests (receipts now
      require provenance).
- [ ] GREEN: new tests + `test_r12_1`, `test_r12_3`, `test_r15_2`.
- [ ] Self-review; scoped commit.

## Task 2 — BR2-2 Receipt consumer boundary (RED → GREEN)

- [ ] RED: `tests/contract/test_br2_receipt_consumer_boundary.py`.
- [ ] Implement `tmp_agent/brain_v9/core/hive_receipt_boundary.py`
      (StrategyValidationReceipt + PaperExecutionReceipt frozen contracts,
      closed schemas, fail-closed validation, `reject_receipt_transport`).
- [ ] GREEN + regression; self-review; scoped commit.

## Task 3 — BR2-3 Semantic authority pointer (RED → GREEN)

- [ ] RED: `tests/contract/test_br2_semantic_authority_pointer.py`.
- [ ] Write the pointer record
      `docs/roadmap/evidence/BRAIN_101_BR2_SEMANTIC_AUTHORITY_POINTER.json`.
- [ ] GREEN; self-review; scoped commit.

## Task 4 — Full regression + final report

- [ ] `python -m pytest -q` over the affected Brain contract tests.
- [ ] `git diff --check`.
- [ ] Final BR2 status report (IMPLEMENTED+TESTED, NOT ACTIVATED).