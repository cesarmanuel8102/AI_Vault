# Supervision-First Continuous Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the implemented V4 multi-universe foundation into one operational PAPER successor that supervises inherited Day1 positions first, then certifies and activates a separate USD 500 continuous-market sleeve without creating a second agent or broker writer.

**Architecture:** Revise the durable transition to commit and bind the successor before the canary, atomically attribute every inherited position to the regular sleeve, and make broker authority phase- and operation-aware. Codex receives one unified opportunity bundle, selects any canary candidate and later trades autonomously, while one existing `BrokerWriteCoordinator` and `AuthoritativeBrokerWriter` enforce separate USD 500 sleeve economics. The final task performs a controlled PAPER-only pilot only after all code and integrity gates pass.

**Tech Stack:** Python 3.11, Pydantic v2, SQLite WAL with `BEGIN IMMEDIATE`, `ib_insync`, pytest, PowerShell 5.1/7, Windows Scheduled Tasks and named execution lock.

**Spec:** `docs/superpowers/specs/2026-10-10-supervision-first-continuous-pilot-design.md` (addendum to `docs/superpowers/specs/2026-10-09-continuous-multi-universe-sleeves-design.md`)

## Global Constraints

- Work only in `C:\AI_VAULT_IBKR_WHATIF_FIX` until the controlled pilot task; treat `C:\AI_VAULT_IBKR` and its broker state as read-only before that task.
- Start from implementation HEAD `1c2f62ebc7f9b325a6f44969a4846a1e667ceb86` plus approved specification commit `65836fc6b8c47e4c96cdf2eb20947fc64fd80e0f` on `codex/continuous-multi-universe-design`.
- PAPER endpoint `127.0.0.1:4002` only. Port `4001`, LIVE trading, real money, global cancel, and a second write-capable broker client are forbidden.
- Preserve exactly one autonomous Codex decision loop, one Windows execution mutex, one `BrokerWriteCoordinator`, one `AuthoritativeBrokerWriter`, and one write-capable PAPER client ID.
- Preserve Codex autonomy over product family, contract, thesis, timing, side, order type, price, quantity, holding period, and management. The host may validate and bound an exact model-authored action but may not invent one.
- `REGULAR_SLEEVE` and `CONTINUOUS_SLEEVE` each have USD 500 of independent authority. No transfer, margin subsidy, hedge credit, fee sharing, P&L offset, or ownership overlap is permitted.
- Existing Day1 positions retain exact quantity, basis, lineage, fees, and P&L in `REGULAR_SLEEVE`; `CONTINUOUS_SLEEVE` starts at USD 500 with no inherited exposure or P&L.
- Reuse the frozen regular-sleeve three-window market-data baseline. Ordinary successor launch/restart must not repeat those windows; fresh family/session evidence is collected only when the relevant authority or architecture actually changes.
- Preserve `AGGRESSIVE_CAPITAL_BOUNDARY_V1`: verified aggregate liability may reach but never exceed `1.00x` independently computed sleeve equity; the successor receipt records `daily_loss_limit_usd=DISABLED` and `drawdown_limit_usd=DISABLED`, matching the approved no-lower-cap policy rather than silently inventing thresholds.
- No broker or model network I/O may occur inside a SQLite write transaction. Collect external evidence first, then reread every database authority under a short `BEGIN IMMEDIATE` transaction.
- Before `ACTIVE`, ordinary new trades are forbidden. `SUPERVISION_BOUND` permits only exact inherited exposure management; `CANARY_EXCLUSIVE` additionally permits only the exact bounded canary request.
- A closed market never forces liquidation. Whole-runtime idle is legal only when no certified family is tradable and no position, open order, canary, or continuity deadline requires work.
- Every task follows RED -> GREEN -> focused regression -> commit. The pilot follows snapshot -> validate -> apply one phase -> reconcile -> record evidence; stop on ambiguity, possible LIVE connectivity, duplicate writer, or uncertain broker state.
- No further external audit is required. Final verification is the full local regression/integrity suite plus one whole-branch internal review before the controlled pilot.

## Review Focus

- A broker snapshot can change between read-only collection and DB commit: Task 2 tests a changed position/order snapshot and requires `SUPERVISION_BINDING_STALE` with no partial bootstrap.
- A management action can be misclassified as a new entry or vice versa: Task 3 tests every operation in every transition phase and requires exact allow/block results.
- A model candidate can become stale or be replaced after authorization: Tasks 5 and 6 bind invocation, family, contract, terms, expiry, account, successor, and candidate hash and reject any mismatch.
- A canary can fill partially or become uncertain during shutdown/restart: Task 6 tests partial fill, timeout, duplicate callback, crash recovery, and exact risk-reducing closure while all new entries remain frozen.
- An old scheduler/service can reacquire the writer after retirement: Tasks 7 and 8 test every managed launch path with old arguments/receipts and require rejection before any connection to port `4002`.

## File Map

New focused modules:

- `ibkr_paper_30d/successor_supervision.py`: pure inherited-position binding plus atomic regular-sleeve bootstrap and supervision receipt.
- `ibkr_paper_30d/canary_candidate.py`: immutable model-authored candidate/lifecycle proposal and exact authorization binding.
- `ibkr_paper_30d/canary_execution.py`: explicit canary request and same-writer lifecycle/recovery adapter.
- `ibkr_paper_30d/multi_universe_maintenance.py`: validate/apply operational transition orchestration with one phase per invocation.

Existing modules modified in place:

- `multi_universe_models.py`, `multi_universe_transition.py`, `sleeve_ledger.py`, `contract_ownership.py`, `sleeve_execution_authority.py`, `production_continuity_runtime.py`.
- `autonomous_research.py`, `autonomous_state.py`, `session_orchestration.py`, `autonomous_service.py`, `coordinated_model_executor.py`.
- `broker_write_coordinator.py`, `authoritative_broker_writer.py`, `canary_authority.py`, `product_capability.py`, `day1_launch.py`, `predecessor_retirement.py`, `reporting.py`.
- `INVOKE_IBKR_MULTI_UNIVERSE_MAINTENANCE.ps1`, `RUN_IBKR_MULTI_UNIVERSE_SERVICE.ps1`, `IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`.

---

### Pre-Implementation Gate: Freeze Development and Production Baselines

**Files:**
- Read: both specification files named in the plan header
- Verify only: `C:\AI_VAULT_IBKR_WHATIF_FIX`
- Verify read-only: `C:\AI_VAULT_IBKR`

**Interfaces:**
- Produces a timestamped baseline containing development HEAD/status/tests and production HEAD/status/schema/task/process/receipt hashes; Task 10 compares against it.

- [ ] **Step 1: Verify the development ancestry.** Run `git rev-parse HEAD`, `git status --short`, and `git merge-base --is-ancestor 1c2f62ebc7f9b325a6f44969a4846a1e667ceb86 HEAD`; require HEAD to contain `65836fc6b8c47e4c96cdf2eb20947fc64fd80e0f` and no unexplained tracked changes.
- [ ] **Step 2: Capture production read-only.** Record canonical HEAD/status, schema versions/tables, Scheduled Task XML, relevant process command lines, execution-lock projection, critical receipt hashes/timestamps, and broker order/position/execution counts without changing any file or connecting to port `4001`.
- [ ] **Step 3: Run the baseline suite.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d`; require zero failures and record exact pass/skip counts.
- [ ] **Step 4: Run baseline integrity.** Run `python -m pytest -q tests\ibkr_paper_30d\test_kernel_manifest_closure.py tests\ibkr_paper_30d\test_epoch_manifest.py tests\ibkr_paper_30d\test_runtime_provenance.py tests\ibkr_paper_30d\test_scheduler_validation.py` and `git diff --check`; require PASS.

---

### Task 1: Canonical Sleeve Vocabulary and Supervision-First Transition

**Files:**
- Modify: `ibkr_paper_30d/multi_universe_models.py`
- Modify: `ibkr_paper_30d/multi_universe_transition.py`
- Modify: `ibkr_paper_30d/day1_launch.py`
- Modify: `tests/ibkr_paper_30d/test_multi_universe_models.py`
- Modify: `tests/ibkr_paper_30d/test_multi_universe_transition.py`
- Modify: `tests/ibkr_paper_30d/test_day1_launch.py`

**Interfaces:**
- Produce canonical `CapitalSleeve = {REGULAR_SLEEVE, CONTINUOUS_SLEEVE}`; parse legacy serialized value `EXTENDED_SLEEVE` as `CONTINUOUS_SLEEVE` but never emit it in new receipts.
- Produce `TransitionPhase = {PREPARED, PREDECESSOR_QUIESCED, PREDECESSOR_RETIRED, SUCCESSOR_COMMITTED, SUPERVISION_BOUND, CANARY_EXCLUSIVE, CANARY_PASS, RUNTIME_BOUND, ACTIVE}` in that exact order.
- Extend `TransitionTarget` with canonical `continuous_sleeve_authority_sha256`; accept the legacy input key only as a pre-validation compatibility alias.
- Produce `require_predecessor_retired(db, transition_id, target_sha256) -> str` that accepts any durable phase at or after retirement while proving the exact retirement event.

- [ ] **Step 1: Write RED vocabulary tests.** Add `test_continuous_sleeve_is_canonical_and_legacy_extended_parses_only` and `test_transition_target_emits_continuous_authority_binding`; assert enum iteration has exactly two sleeves and new JSON contains no `EXTENDED_SLEEVE` key/value.
- [ ] **Step 2: Write RED transition-order tests.** Change `PHASES` expectations and add `test_successor_supervision_precedes_canary`, `test_supervision_binding_requires_exact_reconciliation_and_inherited_projection`, and `test_post_retirement_recovery_never_resumes_predecessor`.
- [ ] **Step 3: Run RED.** Run `python -m pytest -q tests\ibkr_paper_30d\test_multi_universe_models.py tests\ibkr_paper_30d\test_multi_universe_transition.py tests\ibkr_paper_30d\test_day1_launch.py`; expect enum/order and missing `SUPERVISION_BOUND` failures.
- [ ] **Step 4: Implement the canonical vocabulary and evidence rules.** Require `SUPERVISION_BOUND` evidence keys `reconciliation_status=PASS`, `inherited_position_projection_sha256`, `ownership_projection_sha256`, `writer_binding_sha256`, and `new_entry_authority=false`; preserve exact retry idempotence.
- [ ] **Step 5: Update launch eligibility.** Initial successor supervision may launch at `SUCCESSOR_COMMITTED`/`SUPERVISION_BOUND`; only `ACTIVE` may advertise ordinary new-entry authority. Remove the old “certified family within 24h before successor supervision” dependency.
- [ ] **Step 6: Run GREEN and focused regression.** Include `test_predecessor_retirement.py`, `test_multi_universe_service_script.py`, and `test_successor_authorization.py`; require zero failures.
- [ ] **Step 7: Commit.** `git commit -m "refactor(ibkr): make successor supervision precede canary"`.

### Task 2: Exact Inherited-Position Supervision Binding

**Files:**
- Create: `ibkr_paper_30d/successor_supervision.py`
- Create: `tests/ibkr_paper_30d/test_successor_supervision.py`
- Modify: `ibkr_paper_30d/sleeve_ledger.py`
- Modify: `ibkr_paper_30d/contract_ownership.py`
- Modify: `ibkr_paper_30d/sleeve_reconciliation.py`
- Modify: `tests/ibkr_paper_30d/test_sleeve_ledger.py`
- Modify: `tests/ibkr_paper_30d/test_contract_ownership.py`

**Interfaces:**
- Define immutable `InheritedPositionBinding`, `SupervisionBindingPlan`, and `SupervisionBindingReceipt` with hashes for account, broker observation, Day1 lineage, position set, regular authority, transition target, execution-lock generation, and sole-writer binding.
- Produce `build_supervision_binding_plan(*, broker_snapshot: Mapping[str, Any], day1_projection: Mapping[str, Any], account_identity_sha256: str, transition_target_sha256: str) -> SupervisionBindingPlan` as a broker-free pure function.
- Produce `SuccessorSupervisionBinder.bind(plan: SupervisionBindingPlan, fresh_snapshot: Mapping[str, Any]) -> SupervisionBindingReceipt`; it runs one `BEGIN IMMEDIATE` transaction and atomically bootstraps both sleeves, claims inherited ownership groups, records carry-forward economics, and appends `SUPERVISION_BOUND`.
- Add `SleeveLedgerStore.bootstrap_regular_in_transaction(...)` and `.bootstrap_continuous_in_transaction()` plus matching ownership in-transaction calls; public methods remain transaction-owning wrappers.

- [ ] **Step 1: Write RED exact-carry tests.** Add fixtures for single stock, multiple stocks, BAG/option legs, fractional quantity, fees, realized/unrealized P&L, and historical fill lineage; assert no rebase and continuous opening state exactly USD 500/zero.
- [ ] **Step 2: Write RED fail-closed tests.** Add `test_unattributed_position_blocks_before_retirement`, `test_quantity_or_basis_mismatch_blocks`, `test_open_order_blocks_preparation`, `test_execution_ambiguity_blocks`, and `test_duplicate_contract_across_sleeves_blocks`.
- [ ] **Step 3: Add the broker/DB race test.** Collect plan A, pass changed fresh snapshot B to `.bind`, and assert `SUPERVISION_BINDING_STALE`, zero V4 bootstrap events, and no transition advance.
- [ ] **Step 4: Run RED.** Run the new file plus sleeve ledger, ownership, and reconciliation tests; expect missing binder/in-transaction interfaces.
- [ ] **Step 5: Implement pure planning and atomic binding.** Hash canonical sorted contract identities and economics; do not open a broker connection from this module and do not commit any subset of the binding.
- [ ] **Step 6: Run GREEN and focused regression.** Include `test_experiment_ledger.py`, `test_sleeve_reconciliation.py`, and continuity binding tests; require zero failures.
- [ ] **Step 7: Commit.** `git commit -m "feat(ibkr): bind inherited positions to successor supervision"`.

### Task 3: Phase- and Operation-Aware Single-Writer Authority

**Files:**
- Modify: `ibkr_paper_30d/sleeve_execution_authority.py`
- Modify: `ibkr_paper_30d/production_continuity_runtime.py`
- Modify: `ibkr_paper_30d/coordinated_model_executor.py`
- Modify: `ibkr_paper_30d/authoritative_broker_writer.py`
- Modify: `tests/ibkr_paper_30d/test_sleeve_execution_authority.py`
- Modify: `tests/ibkr_paper_30d/test_production_continuity_runtime.py`
- Modify: `tests/ibkr_paper_30d/test_authoritative_broker_writer.py`

**Interfaces:**
- Extend `SleeveAuthoritySnapshot` with `supervision_bound: bool`, `inherited_position: bool`, `entry_authority: Literal["FROZEN", "CANARY_ONLY", "ACTIVE"]`, and `instrument_management_tradable: bool`.
- Produce `SleeveExecutionAuthorityValidator.validate_operation(request, broker_evidence, snapshot) -> SleeveExecutionAuthorityReceipt` and keep `.validate(...)` as a compatibility delegate.
- Operation matrix: inherited `POSITION_ACTION`/`OPEN_ORDER_ACTION` may pass from `SUPERVISION_BOUND` onward with exact ownership and current manageability; ordinary `NEW_TRADE` passes only at `ACTIVE`; canary writes never enter this ordinary model-request path.

- [ ] **Step 1: Write the RED phase matrix.** Parameterize all three `ModelExecutionOperation` values across all nine phases and both sleeves; assert only the specified management/entry cells PASS.
- [ ] **Step 2: Write RED identity and market tests.** Management requires exact same-sleeve ownership, position/order identity, and authenticated manageability; a closed instrument returns `INSTRUMENT_NOT_CURRENTLY_MANAGEABLE` without revoking supervision.
- [ ] **Step 3: Write RED safety tests.** Assert possible LIVE evidence, stale reconciliation, wrong writer, wrong target, cross-sleeve ownership, and request reclassification all BLOCK before `begin_write`.
- [ ] **Step 4: Run RED.** Run the three listed test modules; expect missing fields/matrix failures.
- [ ] **Step 5: Implement the authority matrix.** Apply family full-certification and sleeve capacity checks only to ordinary new entries; retain production authority, execution lock, broker freshness, idempotency, and immediate pre-write reread for every write.
- [ ] **Step 6: Run GREEN and focused regression.** Include coordinated executor, continuity executor, open-order management, and position-action tests; require zero failures.
- [ ] **Step 7: Commit.** `git commit -m "feat(ibkr): preserve management authority before activation"`.

### Task 4: One Unified Opportunity Bundle and Availability Scheduler

**Files:**
- Modify: `ibkr_paper_30d/autonomous_state.py`
- Modify: `ibkr_paper_30d/autonomous_research.py`
- Modify: `ibkr_paper_30d/session_orchestration.py`
- Modify: `ibkr_paper_30d/autonomous_service.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_state.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_research.py`
- Modify: `tests/ibkr_paper_30d/test_multi_universe_orchestration.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_service.py`

**Interfaces:**
- Add `entry_eligibility` per sleeve and `management_eligibility` per owned contract to `TraderInputBundle` V4 state; retain one `decision_cycle_id` and one globally ranked workspace.
- Produce `decide_multi_universe_orchestration(...) -> SessionOrchestrationDecision` where open continuous families run cycles during daytime or overnight, regular closure blocks only regular entries, any obligation keeps supervision cycles alive, and `MARKET_CLOSED_IDLE` is emitted only when every certified family is unavailable and no obligation exists.
- Codex prompt states the maximizing objective and facts, never a preferred market or mandatory trade.

- [ ] **Step 1: Write RED bundle tests.** Assert both USD 500 sleeves, all positions/orders, ownership, family certifications, authenticated sessions, transition phase, and per-action eligibility appear in one hash-bound bundle.
- [ ] **Step 2: Write RED orchestration tests.** Cover regular closed/continuous open, both open, continuous open in daytime, all closed/flat, all closed/position held, family opening soon, holiday restart, DST change, and unauthenticated evidence.
- [ ] **Step 3: Write RED autonomy tests.** Assert provider may select either sleeve when both are executable, may choose `NO_TRADE`, and is never prompted with host-preferred symbols/assets or a requirement to use one sleeve. A provider outage authorizes no new trade; only an exact unexpired pre-existing continuity action may reach the writer.
- [ ] **Step 4: Run RED.** Run the four listed test modules; expect missing eligibility and stale `extended` naming failures.
- [ ] **Step 5: Implement bundle and scheduler changes.** Normalize family session evidence by canonical family hash; do not let regular market-data gate failure hide a valid continuous family or suppress existing-position management.
- [ ] **Step 6: Run GREEN and focused regression.** Include trader invocation, research tools, market gate, and state-gate tests; require zero failures.
- [ ] **Step 7: Commit.** `git commit -m "feat(ibkr): unify regular and continuous opportunity cycles"`.

### Task 5: Model-Authored Continuous Canary Candidate

**Files:**
- Create: `ibkr_paper_30d/canary_candidate.py`
- Create: `tests/ibkr_paper_30d/test_canary_candidate.py`
- Modify: `ibkr_paper_30d/autonomous_research.py`
- Modify: `ibkr_paper_30d/product_capability.py`
- Modify: `tests/ibkr_paper_30d/test_product_capability.py`

**Interfaces:**
- Define immutable `CanaryCandidateProposal` with `candidate_id`, invocation/result hashes, account/successor/head bindings, `ProductFamilyKey`, canonical contract/group, entry terms, quantity, maximum debit/loss/fees, expiry, and an exact model-authored flat-return plan.
- Produce `validate_canary_candidate(proposal, *, read_only_capability_evidence, now_utc) -> CanaryCandidateValidationReceipt`.
- Produce `bind_canary_authorization(proposal, owner_pilot_authorization, now_utc) -> CanaryAuthorization`; authorization scope is the exact candidate hashes and cannot be broadened by maintenance code.

- [ ] **Step 1: Write RED model-output tests.** Assert Codex can propose any broker-qualified family/contract, `NO_CANDIDATE` is valid, and host code contains no symbol/security-type allowlist or fallback candidate.
- [ ] **Step 2: Write RED binding tests.** Wrong invocation, result, account, successor, HEAD, family, contract, order terms, quantity, economics, close plan, stale evidence, or expiry blocks with deterministic reason codes.
- [ ] **Step 3: Write RED no-implicit-certification tests.** Qualification/what-if/market-data PASS creates at most `RESEARCH_ONLY`; neither a proposal nor a transmission marks the family `FULL_LIFECYCLE_VERIFIED`.
- [ ] **Step 4: Run RED.** Run candidate, autonomous research, and product capability tests; expect missing proposal/validator failures.
- [ ] **Step 5: Implement dedicated discovery mode.** Reuse the existing Codex provider and read-only tools; persist every research event and the accepted candidate hash, without connecting a writer or creating a broker order.
- [ ] **Step 6: Run GREEN and focused regression.** Include broker-feasibility, scanner-capability, and trader-result attestation tests; require zero failures.
- [ ] **Step 7: Commit.** `git commit -m "feat(ibkr): let Codex select exact continuous canary"`.

### Task 6: Same-Writer Canary Lifecycle and Recovery

**Files:**
- Create: `ibkr_paper_30d/canary_execution.py`
- Create: `tests/ibkr_paper_30d/test_canary_execution.py`
- Modify: `ibkr_paper_30d/canary_authority.py`
- Modify: `ibkr_paper_30d/broker_write_coordinator.py`
- Modify: `ibkr_paper_30d/authoritative_broker_writer.py`
- Modify: `ibkr_paper_30d/product_capability.py`
- Modify: `tests/ibkr_paper_30d/test_canary_authority.py`
- Modify: `tests/ibkr_paper_30d/test_authoritative_broker_writer.py`

**Interfaces:**
- Define immutable `CanaryExecutionRequest` with durable sequence, execution key, candidate/authorization hashes, exact entry and flat-return terms, and account/successor/writer bindings.
- Extend `BrokerWriteCoordinator.submit(command)` to accept `CanaryExecutionRequest` without adding a consumer or broker session.
- Produce `CanaryExecutionAdapter.execute(request, broker, evidence) -> CanaryExecutionResult`; it records ordered `SUBMITTED -> BROKER_BOUND -> ENTRY_FILL -> POSITION_VISIBLE -> MANAGEMENT_OBSERVED -> EXIT_FILL -> FLAT_STATE -> ECONOMICS_RECONCILED` receipts.
- Produce `recover_canary(db, broker_snapshot, request) -> CanaryRecoveryDecision` with `RESUME_OBSERVATION`, `EXACT_RISK_REDUCTION`, `TERMINAL_NO_FILL`, `PASS`, or `UNCERTAIN_FREEZE`.

- [ ] **Step 1: Write RED topology tests.** Assert canary uses the existing writer capability/client ID/lock, a second writer attach fails, and no alternate executor directly calls `placeOrder`.
- [ ] **Step 2: Write RED authority tests.** Only `CANARY_EXCLUSIVE`, exact request/authorization/candidate hashes, bounded economics, fresh PAPER evidence, and zero ordinary entry authority may cross `begin_write`.
- [ ] **Step 3: Write RED lifecycle tests.** Cover full fill/management/exit/reconciliation, terminal no-fill (`ORDER_TRANSMIT_VERIFIED` only), partial fill, duplicate callback, cancel race, timeout before write, timeout after write, and broker rejection.
- [ ] **Step 4: Write RED crash-recovery tests.** Restart after every durable step; assert no duplicate order, exact broker reconciliation, all normal entries frozen, and only exact risk-reducing/flat-return action allowed when exposure is uncertain.
- [ ] **Step 5: Run RED.** Run canary, coordinator, writer, order identity, and product capability tests; expect unsupported request failures.
- [ ] **Step 6: Implement the same-writer adapter.** Collect broker evidence outside transactions, persist each receipt append-only, reread authorization immediately before each write, and promote the family only after exact full lifecycle economics.
- [ ] **Step 7: Run GREEN and focused regression.** Include model executor, continuity executor, writer timeout, duplicate-order, and reconciliation tests; require zero failures.
- [ ] **Step 8: Commit.** `git commit -m "feat(ibkr): execute bounded canary through sole writer"`.

### Task 7: Real Validate/Apply Maintenance Orchestrator

**Files:**
- Create: `ibkr_paper_30d/multi_universe_maintenance.py`
- Create: `tests/ibkr_paper_30d/test_multi_universe_maintenance.py`
- Modify: `INVOKE_IBKR_MULTI_UNIVERSE_MAINTENANCE.ps1`
- Modify: `tests/ibkr_paper_30d/test_multi_universe_maintenance_script.py`
- Modify: `ibkr_paper_30d/predecessor_retirement.py`
- Modify: `tests/ibkr_paper_30d/test_predecessor_retirement.py`

**Interfaces:**
- Produce `MaintenanceConfig`, `MaintenanceEvidence`, and `MaintenanceResult`.
- Produce `validate_maintenance(config, evidence) -> MaintenanceResult` with zero mutation and `apply_next_phase(config, evidence) -> MaintenanceResult` that advances exactly one legal phase.
- PowerShell remains a thin argument/head/path validator and invokes `python -B -m ibkr_paper_30d.multi_universe_maintenance --mode validate|apply --phase <phase>`.

- [ ] **Step 1: Write RED validate-only tests.** Default invocation makes no files/DB/task/process/broker changes; missing or mismatched receipts, dirty tracked tree, wrong HEAD, port `4001`, active duplicate writer, stale snapshot, or illegal phase BLOCK.
- [ ] **Step 2: Write RED phase-apply tests.** Use temp DB/files and fake process/task inventory to prove one invocation advances only one phase, exact retry is idempotent, changed retry conflicts, and no broker/model call occurs inside DB transactions.
- [ ] **Step 3: Write RED retirement tests.** Inventory Scheduled Tasks, services, startup entries, and known script paths; after tombstone, every old launch with old arguments/receipts fails before broker connection while successor supervision launch remains eligible.
- [ ] **Step 4: Write RED backup tests.** Require a hash manifest and recoverable copies of DB/WAL/SHM plus authority files before first production mutation; failed backup blocks apply.
- [ ] **Step 5: Run RED.** Run Python and script tests in `pwsh` and Windows PowerShell; expect current `APPLY_PREPARED` no-op behavior to fail.
- [ ] **Step 6: Implement one-phase orchestration.** Install V4 only in the target DB, use the Task 2 binder at `SUPERVISION_BOUND`, call Task 6 only at `CANARY_EXCLUSIVE`, and never edit scheduler configuration implicitly.
- [ ] **Step 7: Run GREEN and focused regression.** Include schema, transition, scheduler validation, execution lock, and predecessor retirement tests; require zero failures and AST PASS in both shells.
- [ ] **Step 8: Commit.** `git commit -m "feat(ibkr): operationalize supervised successor transition"`.

### Task 8: Successor Launch, Restart, and Irreversible Recovery

**Files:**
- Modify: `ibkr_paper_30d/day1_launch.py`
- Modify: `RUN_IBKR_MULTI_UNIVERSE_SERVICE.ps1`
- Modify: `ibkr_paper_30d/production_continuity_runtime.py`
- Modify: `ibkr_paper_30d/autonomous_service.py`
- Modify: `tests/ibkr_paper_30d/test_day1_launch.py`
- Modify: `tests/ibkr_paper_30d/test_multi_universe_service_script.py`
- Modify: `tests/ibkr_paper_30d/test_production_continuity_runtime.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_service.py`

**Interfaces:**
- Launch authority adds exact `transition_phase`, `supervision_binding_sha256`, canonical continuous authority hash, and `entry_authority_mode`.
- `evaluate_multi_universe_successor_launch(evidence, initial_activation) -> dict[str, object]` permits supervision startup after commit/retirement even if every continuous family is closed or uncertified; it exposes entry authority only from the durable phase.
- Restart always resumes the same committed successor and writer identity; it never offers predecessor fallback after retirement.

- [ ] **Step 1: Write RED launch matrix tests.** Cover each phase, initial/restart, family open/closed/uncertified, inherited position present, canary partial/flat/uncertain, and continuity action due; assert exact writer/entry/management flags and prove ordinary launch/restart reuses the frozen regular baseline without invoking three-window collection.
- [ ] **Step 2: Write RED restart tests.** Crash after every post-retirement phase; require same successor, same lock/writer identity, fresh reconciliation, no duplicate bootstrap/canary/order, and supervision preserved.
- [ ] **Step 3: Write RED old-path tests.** Invoke legacy Day1 launch scripts, task arguments, and receipts after retirement; assert rejection before port access.
- [ ] **Step 4: Run RED.** Run launch, service script, production composition, autonomous service, and execution-lock tests; expect stale phase rules.
- [ ] **Step 5: Implement launch/restart binding.** Start watchdog and state/research loops in supervision mode, inject the same V4 stores everywhere, and derive all authority flags from DB receipts rather than command-line claims.
- [ ] **Step 6: Run GREEN and focused regression.** Include successor clock, owner authorization, runtime integrity, production authority, and continuity watchdog tests; require zero failures.
- [ ] **Step 7: Commit.** `git commit -m "feat(ibkr): launch and recover supervision-first successor"`.

### Task 9: Operational Evidence and Failure Reporting

**Files:**
- Modify: `ibkr_paper_30d/reporting.py`
- Modify: `ibkr_paper_30d/alerts.py`
- Modify: `tests/ibkr_paper_30d/test_multi_universe_reporting.py`
- Modify: `tests/ibkr_paper_30d/test_alerts.py`
- Create: `docs/ibkr_paper_30d/SUPERVISION_FIRST_PILOT_RUNBOOK.md`

**Interfaces:**
- Produce `SUPERVISION_FIRST_PILOT_REPORT_V1` with exact HEAD, phase/event hashes, account, writer/lock, inherited bindings, sleeve economics, family/canary lifecycle, orders/fills/positions, accepted model cycles, alert delivery, and broker-write counts.
- Add critical reason mappings for `SUPERVISION_BINDING_AMBIGUOUS`, `CANARY_STATE_UNCERTAIN`, `PREDECESSOR_REACTIVATION_ATTEMPT`, and `CONTINUOUS_ENTRY_AUTHORITY_AMBIGUOUS`; existing deduplicated Event Log + external Owner delivery remains mandatory.

- [ ] **Step 1: Write RED report tests.** Missing, stale, contradictory, or unhashed evidence yields `BLOCK`; a report cannot claim `ACTIVE`, `CANARY_PASS`, or zero exposure without the matching DB and broker receipts.
- [ ] **Step 2: Write RED alert tests.** Each new critical event freezes normal entries, persists once, writes Event Log, calls external delivery once per changed reason set, and leaves exact risk-reducing actions available.
- [ ] **Step 3: Run RED.** Run reporting and alert tests; expect missing schema/reason mappings.
- [ ] **Step 4: Implement report and concise runbook.** Document validate/apply commands, one-phase checkpoints, rollback boundary, uncertainty handling, and stop conditions; do not add a manual trade recipe or preferred instrument.
- [ ] **Step 5: Run GREEN and focused regression.** Include continuity reporting, launch reporting, audit integrity, and alert integration tests; require zero failures.
- [ ] **Step 6: Commit.** `git commit -m "feat(ibkr): report supervision-first pilot evidence"`.

### Task 10: Full Regression, Kernel Closure, and Branch Review

**Files:**
- Modify: `IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`
- Modify: `ibkr_paper_30d/kernel_manifest.py` only if the manifest schema requires it
- Create: `docs/ibkr_paper_30d/SUPERVISION_FIRST_IMPLEMENTATION_REPORT.md`
- Test: `tests/ibkr_paper_30d`

**Interfaces:**
- Produce an implementation report bound to final HEAD and every verification command; no operational readiness claim is allowed from tests alone.

- [ ] **Step 1: Update kernel closure.** Add every new production Python/PowerShell file, then run `python -m ibkr_paper_30d.kernel_manifest --repo-root . --output IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`; do not hand-edit generated hashes.
- [ ] **Step 2: Run the full suite.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d`; require zero failures and explain every skip.
- [ ] **Step 3: Run integrity gates.** Run `python -m pytest -q tests\ibkr_paper_30d\test_kernel_manifest_closure.py tests\ibkr_paper_30d\test_epoch_manifest.py tests\ibkr_paper_30d\test_runtime_provenance.py tests\ibkr_paper_30d\test_scheduler_validation.py tests\ibkr_paper_30d\test_multi_universe_maintenance_script.py tests\ibkr_paper_30d\test_multi_universe_service_script.py`; then run `git diff --check` and `rg -n "127\.0\.0\.1:4001|reqGlobalCancel|globalCancel|LIVE_ALLOWED=true|REAL_MONEY_ALLOWED=true" ibkr_paper_30d *.ps1`. Require test PASS, no newly introduced forbidden hit, both PowerShell AST engines PASS, and no untracked generated runtime files.
- [ ] **Step 4: Prove production remained untouched.** Compare the pre-implementation snapshot: canonical HEAD, schema versions, scheduler XML, receipts, DB/file hashes, process set, broker order/position/execution evidence, and broker write count must show no implementation-caused mutation.
- [ ] **Step 5: Run one whole-branch internal review.** Review the diff against both specs, prioritize authority widening, transaction/network overlap, duplicate writer/order paths, state-machine recovery, and missing adversarial tests; fix findings with RED/GREEN commits.
- [ ] **Step 6: Re-run Steps 2-4 after review fixes.** Bind final evidence to the resulting implementation HEAD.
- [ ] **Step 7: Commit.** `git commit -m "docs(ibkr): record supervision-first implementation evidence"`.

### Task 11: Controlled PAPER Pilot and Result Capture

**Files:**
- Operate: `C:\AI_VAULT_IBKR` only after Task 10 PASS
- Execute: `INVOKE_IBKR_MULTI_UNIVERSE_MAINTENANCE.ps1`
- Execute: `RUN_IBKR_MULTI_UNIVERSE_SERVICE.ps1`
- Create at runtime: canonical backup/evidence/authority receipts under `state/ibkr_paper_30d/reports/`
- Update after observation: `docs/ibkr_paper_30d/SUPERVISION_FIRST_PILOT_REPORT.md`

**Interfaces:**
- Consumes the final reviewed implementation HEAD, existing Owner-approved two-sleeve pilot authority, fresh PAPER evidence, and the Task 9 runbook.
- Produces one durable successor transition, one exact canary outcome, and a unified autonomous runtime state; does not guarantee or force an economic trade.

- [ ] **Step 1: Freeze the operational preflight.** Require final approved HEAD, clean tracked tree, PAPER `4002` authenticated, `4001` absent, Read-Only API disabled, one account identity, zero open orders, certain executions, exact current positions, fresh lock/process inventory, external alerts available, and a complete backup manifest.
- [ ] **Step 2: Apply through `PREDECESSOR_RETIRED` one phase at a time.** After each phase, rerun validate-only and reconcile; before retirement, abort/restore only if flat/certain and permitted. Never manually delete the lock or edit DB state.
- [ ] **Step 3: Commit and bind successor supervision.** Advance `SUCCESSOR_COMMITTED`, start the sole successor writer, then advance `SUPERVISION_BOUND`; prove every current Day1 position is owned by `REGULAR_SLEEVE`, both sleeves have entry authority frozen, and a model-authored regular risk-reducing action receives a PASS authority receipt in a no-submit dry run.
- [ ] **Step 4: Let Codex select the canary candidate.** Run dedicated read-only discovery until Codex returns an accepted exact candidate or `NO_CANDIDATE`; never substitute a host-selected contract. If no safe candidate exists, leave supervision operational and report `PILOT_WAITING_FOR_CANDIDATE`.
- [ ] **Step 5: Execute the bounded canary through the same writer.** Advance `CANARY_EXCLUSIVE`, submit only the exact authorized candidate, and observe to a terminal state. No-fill remains transmission-only; uncertainty freezes entries and triggers recovery; only full ordered lifecycle plus exact flat economics may advance `CANARY_PASS`.
- [ ] **Step 6: Bind runtime and activate.** After `CANARY_PASS`, reconcile fresh, advance `RUNTIME_BOUND` then `ACTIVE`, and prove regular entry eligibility is session-gated while continuous eligibility follows the certified family’s authenticated tradability.
- [ ] **Step 7: Observe the unified agent.** Require at least one accepted autonomous cycle containing both sleeves and all current obligations. If Codex independently chooses a trade, prove `ISSUED_PRE_SEND -> BROKER_BOUND`, broker-visible reconciliation, exact sleeve attribution, and a later accepted management decision; do not force a trade to satisfy the report.
- [ ] **Step 8: Publish the exact pilot report.** Record ET/UTC timestamps, final HEAD, transition hashes, writer/lock/client ID, canary candidate and lifecycle, orders/fills/positions, sleeve equity/P&L/liability, accepted cycles, alerts, broker write count, and one of `ACTIVE`, `SUPERVISION_ONLY`, `WAITING_FOR_CANDIDATE`, or `UNCERTAIN_FREEZE`.
- [ ] **Step 9: Stop changing the system.** Leave the successor running only when reconciliation, writer heartbeat, alerts, and authority projections are all PASS; otherwise preserve supervision/risk-reduction mode and report the exact Owner action required.
