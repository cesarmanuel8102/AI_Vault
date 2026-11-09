# V4 BAG Options Continuity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make broker-qualified option combos produce and consume complete V4 continuity ownership evidence.

**Architecture:** Preserve the exact BAG parent and broker-qualified leg identities at what-if time, derive a deterministic ownership group, and verify the same group at final authority. All failures remain fail-closed.

**Tech Stack:** Python 3, Pydantic v2, ib_insync, SQLite, pytest.

**Spec:** `docs/superpowers/specs/2026-11-09-v4-bag-options-continuity-design.md`

## Global Constraints

- PAPER only; no broker writes in tests.
- Do not modify the canonical production checkout until verification and deployment are separately justified.
- Do not weaken freshness, continuity, ownership, sleeve, or economic controls.
- Use the exact successful what-if contracts; never silently substitute instruments.

## Review Focus

- BAG parent `con_id=0` must remain valid only with at least two exact legs.
- Member evidence must reject missing, duplicate, extra, or mismatched leg identities.
- Combo-leg ordering/direction must remain bound by the parent identity.
- Ownership-group hash must be rechecked at final authority.
- Non-BAG behavior must remain byte-for-byte compatible where practical.

---

### Task 1: Emit complete broker-qualified BAG evidence

**Files:**
- Modify: `ibkr_paper_30d/ibkr_research_tools.py`
- Test: `tests/ibkr_paper_30d/test_broker_feasibility_runtime.py`

**Interfaces:**
- Produces: `continuity_host_bindings.canonical_contract_identity_v4`
- Produces: `continuity_host_bindings.ownership_contracts_v4`

- [ ] Write a failing HIMS-like BAG what-if test.
- [ ] Run it and verify failure is missing BAG V4 identity/member evidence.
- [ ] Preserve qualified leg contracts and emit canonical parent/member evidence.
- [ ] Run the focused test and existing broker-feasibility tests.

### Task 2: Derive deterministic V4 BAG ownership bindings

**Files:**
- Modify: `ibkr_paper_30d/continuity_binding.py`
- Test: `tests/ibkr_paper_30d/test_v4_continuity_host_bindings.py`

**Interfaces:**
- Consumes: parent/member evidence from Task 1.
- Produces: `ownership_group_sha256` bound to parent and every leg.

- [ ] Write failing tests for valid, missing, duplicate, extra, and mismatched members.
- [ ] Run tests and verify expected failures.
- [ ] Validate exact BAG closure and build `ContractOwnershipGroup`.
- [ ] Run focused binding tests.

### Task 3: Enforce the group at final write authority

**Files:**
- Modify: `ibkr_paper_30d/sleeve_execution_authority.py`
- Test: `tests/ibkr_paper_30d/test_sleeve_execution_authority.py`

**Interfaces:**
- Consumes: live `ownership_contracts` and continuity plan hashes.
- Produces: PASS only when live BAG parent/member group equals the plan.

- [ ] Write a failing test for a BAG plan/group mismatch.
- [ ] Verify it currently passes incorrectly or reports the wrong reason.
- [ ] Compare parent and ownership-group hashes before reservation.
- [ ] Run focused authority tests.

### Task 4: Regression and release evidence

**Files:**
- Modify if required: `ibkr_paper_30d/kernel_manifest.py`
- Verify: production PowerShell AST, kernel manifest, targeted and full pytest suites.

- [ ] Run the three focused test modules.
- [ ] Run continuity/execution integration tests.
- [ ] Run the full test suite and `git diff --check`.
- [ ] Record exact residual limitation: live quote/economic certification still requires an open option market.
