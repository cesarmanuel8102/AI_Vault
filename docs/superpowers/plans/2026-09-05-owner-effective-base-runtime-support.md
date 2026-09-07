# Owner Effective Base Runtime Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement task-by-task with a failing test before every production change.

**Goal:** Permit one already-authorized Owner payload-repair attempt to resume after an Operator Proxy SYSTEM_REPAIR advances the integration branch, without changing the frozen authority, original effective base, grant, receipt chain, or logical build attempt.

**Architecture:** Preserve `OwnerRepairEffectiveBaseBinding` as the immutable authority anchor. Add a separate append-only runtime-support record which binds the existing effective base to one exact installed canonical descendant and is valid only when the branch tip and installed runtime equal that descendant. The synchronization commit uses the support base, while every Owner provenance field continues to bind the original grant, attempt and `CONSUMED` receipt.

**Tech Stack:** TypeScript, Node test runner, Git plumbing, existing Operator Proxy append-only JSONL ledgers.

## Global Constraints

- `HUMAN_FINAL_AUTHORITY=true`; `AUTO_MERGE=false`; `CANONICAL_LOCAL_SYNC=false`; `LIVE_TRADING=false`; `REAL_MONEY=false`.
- Never mutate existing lifecycle or receipt records to recover this case.
- One logical Owner build attempt remains capped at one per front; `repair_cycles` remains exactly `2`.
- Runtime support accepts only an exact canonical tip/installed-runtime match that descends from the immutable effective base.

---

### Task 1: Append-only Runtime Support Ledger

**Files:**
- Create: `scripts/operator_proxy/owner_repair_runtime_support.ts`
- Test: `tests/contract/operator_proxy/owner_repair_runtime_support.test.ts`

**Interfaces:**
- Produces `OwnerRepairRuntimeSupportLedger.bind(binding, evidence)` and `load(grantKey)`.
- Consumes `OwnerRepairEffectiveBaseBinding` and the existing receipt ledger.

- [ ] Write a failing test that binds an immutable effective base `E` to a descendant runtime `R`, and asserts a stable event hash.
- [ ] Write failing negative tests for `R` not descending from `E`, branch tip not equal to `R`, installed runtime not equal to `R`, duplicate/conflicting support records, and wrong grant/attempt/dispatch anchor.
- [ ] Implement a JSONL-only ledger with exact-key validation, canonical SHA-256 event hashing, single-record-per-grant conflict rejection, and ancestry evidence checks.
- [ ] Run `npx tsx --test tests/contract/operator_proxy/owner_repair_runtime_support.test.ts`; expect all positive and negative cases to pass.

### Task 2: Guard and Synchronization Semantics

**Files:**
- Modify: `scripts/operator_proxy/external_effect_guard.ts`
- Modify: `scripts/operator_proxy/governed_builder.ts`
- Modify: `scripts/operator_proxy/production_effects.ts`
- Test: `tests/contract/operator_proxy/owner_payload_base_advance_flow.test.ts`
- Test: `tests/contract/operator_proxy/owner_payload_repair_effect_guard.test.ts`

**Interfaces:**
- Consumes `OwnerRepairRuntimeSupportLedger` result `{ effective_base_sha, runtime_support_sha, event_sha256 }`.
- Produces a transport capability carrying immutable effective-base provenance plus the support record hash.

- [ ] Write a failing flow test: an existing effective binding at `E` resumes exactly one attempt when current tip and installed runtime are descendant `R`; the deterministic sync commit parents are `[failed_head, R]`; original binding remains unchanged.
- [ ] Write failing tests that reject a foreign/non-ancestor runtime, different installed/tip SHA, a support record for a different attempt, and a second provider dispatch.
- [ ] Update the effect boundary so every privileged effect rechecks the support record, exact current tip/runtime equality, ancestor relation `E -> R`, PR identity, grant, attempt, and consumed anchor.
- [ ] Update the builder synchronization path to create/validate its deterministic sync commit against `runtime_support_sha`, while retaining original effective-base and receipt provenance in the candidate receipt.
- [ ] Update `ProductionEffects.resumeOwnerPayloadRepair` to create or replay support evidence before transport authorization and to reject any conflicting preexisting record.
- [ ] Run the two focal test files and `npm run typecheck`; expect PASS.

### Task 3: Crash, Accounting and Regression Verification

**Files:**
- Modify: `tests/contract/operator_proxy/owner_payload_repair_crash.test.ts`
- Modify: `tests/contract/operator_proxy/semantic_repair_accounting.test.ts`
- Modify: `tests/contract/operator_proxy/runtime.test.ts`

**Interfaces:**
- Consumes the support ledger and resumed Owner repair state from Tasks 1-2.
- Produces proof that no lifecycle counter or ordinary repair path is changed.

- [ ] Write a failing crash-boundary test for interruption after support binding and before provider invocation; rerun must reuse support evidence and the same build attempt.
- [ ] Write a failing accounting test proving `repair_cycles===2`, normal consummated repairs remain `2`, Owner exceptional attempts remain `1`, and no ordinary repair lifecycle event is added.
- [ ] Write a failing runtime test that rejects lifecycle/receipt adoption when support provenance is missing or mismatched.
- [ ] Implement only the validation necessary to make those tests pass.
- [ ] Run focal contracts, full Operator Proxy contract suite, `npm run typecheck`, and `git diff --check`; expect zero failures.

### Task 4: Governed Publication and Runtime Verification

**Files:**
- Modify only files changed by Tasks 1-3.

- [ ] Review `git diff --check`, `git diff --stat`, and the exact changed-file list; reject unrelated files.
- [ ] Commit the repair with a focused message after all tests pass.
- [ ] Push a normal `control-plane/` branch and create a SYSTEM_REPAIR Draft PR; wait for CI and independent reviewer before merge.
- [ ] Merge normally, install through the existing transaction with UAC, and verify source SHA equals installed SHA, config is byte-identical, doctor passes, tasks remain disabled, and workers remain zero.
- [ ] Execute exactly one governed recovery tick only after installed verification; it must reuse the existing Owner attempt and not create a second grant, receipt chain, Issue, PR, or build attempt.
