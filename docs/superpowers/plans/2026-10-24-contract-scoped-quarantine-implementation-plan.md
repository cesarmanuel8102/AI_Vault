# Contract-Scoped Quarantine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the uncertain SOL/PAXOS order isolated without blocking unrelated contracts, while replacing closed-session gate churn with bounded read-only monitoring.

**Architecture:** Preserve the existing exact-contract writer quarantine as the authority boundary. Add service-level regression coverage proving that an eligible unrelated sleeve/contract still reaches the autonomous decision path, then teach orchestration to idle at scan cadence when the only continuity obligation is the quarantined order and its authenticated family session is closed. Any other eligible family, non-quarantined order, or managed position continues through the normal autonomous cycle.

**Tech Stack:** Python 3.11, Pydantic v2, SQLite WAL, `ib_insync`, pytest, Windows execution lock, PowerShell launch/provenance checks.

**Spec:** `docs/superpowers/specs/2026-10-24-contract-scoped-quarantine-design.md`

## Global Constraints

- Develop only in `C:\AI_VAULT_IBKR\.worktrees\instrument-coverage-awareness`; production remains untouched until all tests and integrity checks pass.
- PAPER `127.0.0.1:4002` only. Never connect to LIVE `4001`, issue global cancel, or create a second writer.
- Preserve PBR 1, SLB 9, `AUTONOMY_EPOCH_2`, both USD 500 sleeve allocations, and the not-yet-started 30-day clock.
- Quarantine only SOL/PAXOS `conId=766137558`, order `964`, `permId=1166274319`, `clientId=19761`, and its exact `orderRef`.
- Never submit, modify, cancel, replace, or duplicate that SOL order. Continue read-only reconciliation.
- Do not bypass authenticated session evidence, broker feasibility, risk, continuity, or writer gates for any instrument.
- Every behavior change follows RED -> GREEN -> focused regression. If the isolation test is already GREEN, retain it as characterization evidence and do not manufacture a production change.

---

### Task 1: Prove Exact Isolation Across the Whole Service

**Files:**
- Modify: `tests/ibkr_paper_30d/test_autonomous_service.py`
- Modify only if the test exposes a defect: `ibkr_paper_30d/autonomous_service.py`
- Review: `tests/ibkr_paper_30d/test_authoritative_broker_writer.py`

- [ ] **Step 1: Add a service-level isolation test.** Activate the exact SOL quarantine, make the legacy regular gate BLOCK, provide an unrelated continuous family/contract with `entry_eligibility=PASS`, and assert the provider/executor path runs without `CONTRACT_ORDER_QUARANTINE` or `MARKET_DATA_GATE_BLOCK`.
- [ ] **Step 2: Pin the prohibited path.** Assert an action targeting the quarantined SOL identity remains blocked before broker submission and that an unrelated `conId` is not matched by the quarantine.
- [ ] **Step 3: Run focused tests.** Run the new service test and existing writer quarantine tests. If the new service test is already GREEN, record that exact-contract isolation already exists and make no production edit for this task.
- [ ] **Step 4: Implement only the demonstrated defect.** If RED, correct the narrow eligibility aggregation or quarantine identity comparison; do not weaken any global gate.
- [ ] **Step 5: Commit.** Commit as `test(ibkr): prove contract quarantine isolation`, or `fix(ibkr): scope quarantine to exact contract` only if production code changes.

---

### Task 2: Idle Efficiently When the Only Obligation Is Closed and Quarantined

**Files:**
- Modify: `ibkr_paper_30d/autonomous_service.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_service.py`

- [ ] **Step 1: Write RED orchestration tests.** Cover an authenticated closed SOL/PAXOS family with only the exact quarantined order: no model/provider call, one deduplicated monitor-idle event, read-only quarantine observation retained, and sleep at `scan_interval_seconds` rather than the position cadence.
- [ ] **Step 2: Protect actionable work.** Add tests proving the optimization does not idle when any unrelated family is authenticated open/eligible, any non-quarantined order exists, or regular-sleeve positions require management during their session.
- [ ] **Step 3: Protect uncertainty.** Add tests proving malformed/missing quarantine identity or unavailable session evidence remains fail closed and does not silently classify the obligation as idle.
- [ ] **Step 4: Implement a pure classification helper.** Classify `ONLY_CLOSED_QUARANTINED_OBLIGATION` from the loaded exact quarantine plus authoritative session/open-order evidence. Reuse the existing observation path; do not mutate the quarantine or broker state.
- [ ] **Step 5: Add deduplicated observability.** Record a neutral `CONTRACT_QUARANTINE_MONITOR_IDLE` transition once, including exact contract/order identity and authenticated family session, without authority or receipt claims.
- [ ] **Step 6: Run focused regression.** Run all session-orchestration, autonomous-service, quarantine-store, and authoritative-writer tests.
- [ ] **Step 7: Commit.** Commit as `fix(ibkr): idle closed quarantined obligation`.

---

### Task 3: Verify, Bind, and Relaunch the PAPER Runtime

**Files:**
- Regenerate if required: `IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`
- Update only through existing authorized release flow: canonical runtime binding/approved HEAD artifacts
- Do not edit: broker positions, orders, SQLite history, epoch identity, or experiment clock

- [ ] **Step 1: Run full regression.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d`; require zero failures with only documented platform skips.
- [ ] **Step 2: Verify integrity.** Run kernel closure, epoch manifest, runtime provenance, scheduler validation, PowerShell AST checks, forbidden LIVE-path scans, and `git diff --check`.
- [ ] **Step 3: Inspect broker read-only.** Confirm PAPER identity, PBR 1, SLB 9, SOL 4.5, exact order 964 identity/status, zero unexpected fills, and no duplicate SOL order. Abort deployment on ambiguity.
- [ ] **Step 4: Publish and bind.** Commit/push the verified branch, update canonical production only through the existing controlled release path, and preserve the current epoch and clock state.
- [ ] **Step 5: Relaunch once.** Start the single PAPER runtime with the new approved HEAD and confirm one execution lock, one writer, healthy watchdog, port 4002 only, and no order write during startup.
- [ ] **Step 6: Observe bounded behavior.** While PAXOS is authenticated closed and no other market is eligible, require read-only SOL monitoring without model churn. When an unrelated family becomes eligible, require autonomous research to resume while SOL remains quarantined.
- [ ] **Step 7: Report honestly.** Report exact process state, cycle/event counts, broker orders/fills/positions, and whether unrelated execution authority is proven. Do not claim end-to-end trading until a model-authored unrelated PAPER action actually passes all gates.

## Acceptance Criteria

- The exact SOL order/contract remains impossible to write, replace, or duplicate.
- An unrelated eligible contract is not blocked by the SOL quarantine.
- A closed quarantined-only obligation produces bounded read-only monitoring and no repeated LLM calls or critical-alert storm.
- PBR 1 and SLB 9 remain unchanged; both sleeve allocations, epoch, and clock are preserved.
- Full regression and integrity checks pass before production changes.
- Canonical runtime relaunches with one writer and no LIVE connectivity.
