# Continuity V3 Operational Deployment Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to execute this plan sequentially after the implementation plan and differential external audit are complete. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the exact externally audited Continuity V3 production-composition HEAD to the canonical PAPER experiment, install and verify schema V3, rebind authority, prove zero-exposure readiness, and enable the existing scheduler without manually launching Day1.

**Architecture:** Deployment is a fail-closed promotion of an immutable audited SHA. The scheduler remains disabled while code, schema, manifests, receipts, authorization, alerts, composition validation, and read-only broker reconciliation are verified. Enabling the scheduler is the final reversible control-plane action; it is never used to compensate for a failed readiness gate.

**Tech Stack:** Git fast-forward deployment, Python 3.11, SQLite WAL, existing finalizer and launch scripts, Windows Task Scheduler, PowerShell 7, read-only IBKR PAPER reconciliation.

**Spec:** `docs/superpowers/specs/2026-10-02-continuity-production-composition-design.md`

**Consumes:** `docs/superpowers/plans/2026-10-02-continuity-production-composition.md` and an external differential audit bound to its exact final HEAD.

## Global Constraints

- Do not begin unless the implementation report is complete, the worktree is clean, and an independent differential audit reports no activation blocker against the exact candidate SHA.
- PAPER only. `LIVE_ALLOWED=false`, `REAL_MONEY_ALLOWED=false`.
- Do not rebase, squash, amend, cherry-pick around, or otherwise rewrite the audited implementation commits.
- Do not reset or delete canonical untracked runtime/state/report artifacts.
- No manual IBKR submit, modify, cancel, global cancel, or position action is authorized by this plan.
- No Day1 manual launch. Scheduler enablement is the final step and preserves its approved schedule.
- No SQLite write transaction spans broker network I/O.
- Stop on any head/hash mismatch, dirty tracked state, active Day1 process, nonzero or uncertain broker exposure, unresolved execution lock, failed mandatory alert channel, schema-chain failure, or changed audit target.
- Preserve before/after hashes and receipts for every authority mutation.

## Review Focus

- The external audit may reference a different SHA than the deployment candidate: Task 1 requires exact SHA equality before any mutation.
- Canonical untracked state can be overwritten or conflict with deployment: Tasks 1-2 inventory and preserve it before fast-forwarding.
- Schema installation can partially apply or be rerun: Task 3 requires explicit receipt, transactionality, chain verification, and idempotent recheck.
- Rebinding can authorize the wrong HEAD, account, epoch, or scheduler arguments: Task 4 recomputes and cross-checks all bindings.
- A scheduler can be enabled while validation, alerts, lock recovery, or broker state remain uncertain: Tasks 5-6 require independent PASS evidence and zero exposure before the enable action.

---

### Task 1: Establish the Immutable Deployment Gate

**Files:**
- Read: `docs/audits/CONTINUITY_V3_PRODUCTION_COMPOSITION_IMPLEMENTATION_REPORT.md`
- Read: external differential audit report supplied by the Owner
- Read only: `C:\AI_VAULT_IBKR`
- Create under reports only after preconditions pass: `state/ibkr_paper_30d/reports/continuity-v3-deployment/`

**Interfaces:**
- Consumes exact `FINAL_IMPLEMENTATION_HEAD` and audit verdict.
- Produces a predeployment evidence bundle and an explicit go/no-go result.

- [ ] **Step 1: Verify audit identity.** Require audit target SHA equals the clean implementation HEAD and report candidate SHA. Require no BLOCKER/HIGH activation finding and no condition that would be invalidated by deployment.
- [ ] **Step 2: Freeze the scheduler.** Verify `CodexIBKRMarketDataGate` is disabled and record action, arguments, principal, triggers, last result, and configured `ApprovedHead`. If enabled, disable it through the approved scheduler control and verify the new state before continuing.
- [ ] **Step 3: Prove runtime quiescence.** Require zero `RUN_IBKR_DAY1_SERVICE`/`day1_launch` processes and no live writer/watchdog threads belonging to the experiment.
- [ ] **Step 4: Capture canonical Git state.** Record HEAD, branch, worktrees, tracked status, untracked inventory, reflog tail, and object existence for the audited SHA. Stop on tracked modifications.
- [ ] **Step 5: Reconcile PAPER read-only.** Use authenticated all-order visibility, positions, executions, and account identity. Require zero open orders, zero positions, zero executions in the active epoch, and no uncertain/pending registry binding. Never infer zero from one client view.
- [ ] **Step 6: Preserve state.** Copy the canonical SQLite database plus WAL/SHM consistently using the existing backup mechanism, export relevant reports/receipts, and hash the bundle. Do not mutate or delete originals.
- [ ] **Step 7: Emit predeployment gate.** Record `DEPLOYMENT_GATE=PASS` only if every prior check passes; otherwise stop with exact reason codes and leave scheduler disabled.

### Task 2: Fast-Forward the Canonical Checkout to the Audited SHA

**Files:**
- Modify only by Git fast-forward: `C:\AI_VAULT_IBKR` tracked repository files
- Preserve: `C:\AI_VAULT_IBKR\state\ibkr_paper_30d\**`

**Interfaces:**
- Consumes audited implementation SHA.
- Produces canonical `HEAD == audited SHA` without history rewriting or runtime-state loss.

- [ ] **Step 1: Verify fast-forward ancestry.** Require current canonical HEAD is an ancestor of the audited SHA. Stop if not; do not merge or cherry-pick as a workaround.
- [ ] **Step 2: Detect untracked collisions.** Dry-run/check whether target tracked files collide with existing untracked files. Stop and report exact paths rather than moving or overwriting them ad hoc.
- [ ] **Step 3: Fast-forward only.** Update the approved canonical branch/reference and switch/fast-forward the canonical checkout to the audited SHA with no force operation.
- [ ] **Step 4: Verify exact content.** Require `git rev-parse HEAD` equals the audited SHA, tracked status is clean, expected untracked runtime files remain, and `git diff --check` passes.
- [ ] **Step 5: Re-run immutable code gates.** Run focused production-composition tests, kernel closure, runtime provenance, PowerShell AST 3/3, secret scan, and forbidden LIVE-path scan at the deployed HEAD. Stop before schema work on any failure.

### Task 3: Install and Verify Continuity Schema V3 Explicitly

**Files:**
- Modify through approved installer: `state/ibkr_paper_30d/autonomous.sqlite3`
- Create: `state/ibkr_paper_30d/reports/continuity-v3-deployment/schema-v3-install-receipt.json`

**Interfaces:**
- Uses `install_continuity_schema_v3` and `verify_continuity_schema_v3` through the approved one-use deployment entry point.
- Produces an append-only, hash-valid installation receipt bound to database identity, schema version, audited HEAD, owner authorization, and timestamp.

- [ ] **Step 1: Prove precondition.** Verify schema V3 is absent or exactly at the documented preinstall state. Record DB file hash/identity and continuity-table inventory.
- [ ] **Step 2: Validate one-use authority.** Require a deployment authorization bound to audited HEAD, PAPER account hash, epoch, database identity, and `INSTALL_CONTINUITY_SCHEMA_V3` only. Do not reuse trading authorization.
- [ ] **Step 3: Run the explicit installer.** Install transactionally. Any exception must roll back fully and leave scheduler disabled.
- [ ] **Step 4: Verify chains and constraints.** Run schema verification, foreign-key/integrity checks, append-only protections, hash-chain roots, expected indexes, and exact schema version.
- [ ] **Step 5: Verify idempotence.** A second verification/install check must report already installed with identical schema/hash state and no duplicate roots or rows.
- [ ] **Step 6: Persist receipt.** Hash and save the installation receipt. Require `SCHEMA_V3_INSTALLED=true` and `SCHEMA_V3_VERIFIED=true` before continuing.

### Task 4: Rebind Runtime Integrity and Owner Authority to the Deployed HEAD

**Files:**
- Modify through approved tools: runtime/kernel provenance receipts and owner authorization under `state/ibkr_paper_30d/reports/`
- Modify through approved task-registration path: scheduler action arguments while task remains disabled

**Interfaces:**
- Consumes deployed audited SHA, PAPER identity, active epoch/clock, schema receipt, and existing finalizer scripts.
- Produces fresh hash-bound runtime receipts, owner authorization, launch binding, and scheduler `ApprovedHead` for one exact deployment.

- [ ] **Step 1: Regenerate and verify runtime evidence.** Recompute immutable kernel and runtime provenance for the exact deployed tree. Preserve prior receipts; do not overwrite history invisibly.
- [ ] **Step 2: Revalidate experiment authority.** Verify active successor epoch/clock, account identity, market-data policy, Auditor V2 receipt, kill-switch state, capital allocation, and residual-risk acceptance.
- [ ] **Step 3: Create fresh Owner authorization.** Bind audited HEAD, epoch, PAPER account, schema receipt, runtime hashes, model timeout, permitted schedule, and PAPER-only constraints. Reject any wildcard or mismatched field.
- [ ] **Step 4: Create fresh launch binding.** Bind the launch attempt material and exact receipt hashes without starting Day1.
- [ ] **Step 5: Re-register/update the scheduler while disabled.** Set exact repository path, PowerShell/Python executables, task principal, and `ApprovedHead` equal to the audited SHA. Preserve approved 09:35 ET schedule and do not trigger the task.
- [ ] **Step 6: Cross-check all hashes.** Independently parse scheduler arguments and every receipt; require exact SHA/account/epoch/schema/runtime agreement and scheduler state `Disabled`.

### Task 5: Prove Zero-Write Production Readiness

**Files:**
- Create: `state/ibkr_paper_30d/reports/continuity-v3-deployment/production-composition-validation.json`
- Create: `state/ibkr_paper_30d/reports/continuity-v3-deployment/final-readonly-reconciliation.json`
- Create: `state/ibkr_paper_30d/reports/continuity-v3-deployment/critical-alert-simulation.json`

**Interfaces:**
- Uses production composition validation mode and authenticated read-only broker reconciliation.
- Produces PASS evidence with real broker writes equal to zero.

- [ ] **Step 1: Validate production composition.** Run the deployed `validate_only` path against real configuration with no arming. Require concrete factories, coordinated model executor, one writer capability, distinct writer/observer IDs, read-only watchdog, callable fail-closed gates, and clean shutdown.
- [ ] **Step 2: Prove no write calls.** Require instrumentation/result evidence that `placeOrder`, `cancelOrder`, global cancel, and modify transmission counts are all zero during validation.
- [ ] **Step 3: Exercise mandatory alert simulations.** Simulate `BROKER_2FA_REAUTH_REQUIRED`, `KILL_SWITCH_TRIGGERED`, and `BROKER_HEARTBEAT_TIMEOUT`. Require authority freeze, local persistence, Windows Event Log delivery, external SMTP delivery, deduplication, and explicit Owner-action wording for 2FA.
- [ ] **Step 4: Verify lock behavior.** Validate stale-lock recovery and active-owner exclusion through approved nontrading checks. Stop on ambiguity; do not delete the lock manually.
- [ ] **Step 5: Reconcile PAPER again.** Require authenticated account identity, all-order visibility, zero open orders, zero positions, zero executions in the active epoch, coherent registry, and no pending/uncertain writer result.
- [ ] **Step 6: Validate scheduler path without launch.** Run market-gate and Day1 prerequisite validation modes only. Require exact approved HEAD, receipts, clock, market policy, schema, alerts, lock, and composition gates.
- [ ] **Step 7: Emit readiness decision.** Set `DAY1_READY=true` only when all validations pass and real broker writes remain zero. Keep scheduler disabled until Task 6.

### Task 6: Enable the Existing Scheduler and Stop

**Files:**
- Modify: Windows Task Scheduler state for `CodexIBKRMarketDataGate`
- Create: `state/ibkr_paper_30d/reports/continuity-v3-deployment/day1-ready-report.json`

**Interfaces:**
- Consumes `DAY1_READY=true` evidence bound to the audited SHA.
- Produces an enabled scheduler for the approved future trigger, without starting Day1.

- [ ] **Step 1: Recheck last-mile invariants.** Immediately before enablement require unchanged HEAD/receipts, clean tracked status, no Day1 process, zero broker exposure/uncertainty, valid lock state, mandatory alert channels PASS, and next trigger still the approved schedule.
- [ ] **Step 2: Enable only.** Enable `CodexIBKRMarketDataGate`. Do not run it manually and do not alter its trigger time to force an immediate launch.
- [ ] **Step 3: Verify scheduler state.** Read back enabled state, exact action/arguments/principal/triggers, `ApprovedHead`, and next run time. Require no process spawned as a side effect.
- [ ] **Step 4: Persist final report.** Record all evidence hashes, deployed SHA, schema receipt, authorization/launch binding, validation results, alert delivery IDs, reconciliation counts, scheduler configuration, and `REAL_BROKER_WRITES=0`.
- [ ] **Step 5: Stop.** Do not launch Day1, place a test order, or continue into market operation under this plan.

## Completion Report

Return exactly:

```text
CONTINUITY_V3_OPERATIONAL_DEPLOYMENT_REPORT

AUDITED_IMPLEMENTATION_HEAD:
DEPLOYED_HEAD:
EXTERNAL_AUDIT_VERDICT:
CANONICAL_BRANCH:
SCHEMA_V3_INSTALLED:
SCHEMA_V3_VERIFIED:
SCHEMA_RECEIPT_SHA256:
KERNEL_CLOSURE:
RUNTIME_PROVENANCE:
OWNER_AUTHORIZATION_SHA256:
LAUNCH_BINDING_SHA256:
PRODUCTION_COMPOSITION_VALIDATION:
OWNER_ALERT_GATE:
WINDOWS_EVENT_LOG_DELIVERY:
EXTERNAL_OWNER_DELIVERY:
EXECUTION_LOCK_GATE:
PAPER_ACCOUNT_IDENTITY:
OPEN_ORDERS:
POSITIONS:
EXECUTIONS:
REAL_BROKER_WRITES:
SCHEDULER_TASK:
SCHEDULER_STATE:
SCHEDULER_APPROVED_HEAD:
NEXT_RUN_TIME:
DAY1_PROCESS_COUNT:
DAY1_READY:
DAY1_LAUNCHED: false
AUTONOMOUS_TRADING_STATUS: READY_FOR_SCHEDULED_START
NEXT_OWNER_DECISION_REQUIRED: false
```
