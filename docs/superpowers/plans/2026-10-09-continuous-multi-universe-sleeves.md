# Continuous Multi-Universe Sleeves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing autonomous IBKR PAPER runtime into one continuous agent with one writer and two economically isolated USD 500 sleeves, while preserving Day1 history and leaving production untouched until a later authorized transition.

**Architecture:** Add an explicitly installed append-only V4 authority schema for sleeve economics, contract ownership, product-family certification, canary authority, and transition phases. Existing research, continuity, coordinator, writer, reconciliation, successor-clock, and launch paths become sleeve-aware; no second process, model, broker writer, or strategy layer is introduced. Implementation and simulated verification stop before any production schema installation, real PAPER canary, scheduler mutation, or successor activation.

**Tech Stack:** Python 3.11, Pydantic v2, SQLite WAL with `BEGIN IMMEDIATE`, `ib_insync`, pytest, Windows Scheduled Tasks and named execution lock, PowerShell 5.1/7 AST validation.

**Spec:** `docs/superpowers/specs/2026-10-09-continuous-multi-universe-sleeves-design.md`

## Global Constraints

- Work only in `C:\AI_VAULT_IBKR_WHATIF_FIX` on `codex/continuous-multi-universe-design`; the approved design commit is `c923765574c1dda57789ecfa5c408ed9fd619464`.
- Treat `C:\AI_VAULT_IBKR` as read-only evidence. Do not alter its checkout, scheduler, receipts, SQLite files, reports, processes, IB Gateway settings, orders, positions, or executions.
- PAPER only on port `4002`. Never connect to LIVE port `4001`; `LIVE_ALLOWED=false`, `REAL_MONEY_ALLOWED=false`.
- Implementation-time broker writes are zero. Do not run a real canary, install V4 in production, retire Day1, create the successor epoch, or start its 30-day clock under this plan.
- Preserve one Codex provider lifecycle, one Windows execution mutex, one `BrokerWriteCoordinator`, one `AuthoritativeBrokerWriter`, and one write-capable PAPER session.
- Preserve Codex autonomy over instruments, markets, strategies, timing, sizing, and management. Do not add a symbol allowlist, preferred asset class, trading schedule, or host-authored economic action.
- Preserve `AGGRESSIVE_CAPITAL_BOUNDARY_V1`: verified aggregate liability may reach but never exceed `1.00x` the independently computed equity of its owning sleeve.
- `REGULAR_SLEEVE` carries exact Day1 economics; `EXTENDED_SLEEVE` opens with USD 500 and zero P&L. Capital, loss, fees, collateral, and currency subledgers never transfer between them.
- The frozen regular-sleeve three-window baseline remains reusable. Ordinary startup must not recollect it.
- No SQLite write transaction may span broker or model network I/O. Collect external evidence first, then reread every database authority inside a short `BEGIN IMMEDIATE` transaction.
- Preserve old serialized Day1 inputs during implementation; successor-only fields may default absent in legacy mode but are mandatory once V4 authority is active.
- Every task follows RED -> GREEN -> focused regression -> commit. Stop on unexplained baseline failure, production-state mutation, a real broker write, or any attempt to use port `4001`.

## Review Focus

- A broker margin offset or shared USD balance can silently lend one sleeve the other's capital: Tasks 2, 3, and 7 test standalone solvency, per-currency reconciliation, and cross-sleeve race attempts.
- Exercise, assignment, BAG legs, settlement, or a corporate action can create a position that lacks an owner: Tasks 3 and 8 test deterministic lineage and fail-closed unattributed events.
- A family that only transmitted an order can be mistaken for fully executable: Tasks 4 and 10 require entry fill, position management, closing fill, and exact economics before `FULL_LIFECYCLE_VERIFIED`.
- A crash between predecessor retirement, successor commit, and runtime binding can revive the old writer: Tasks 9-11 inject every phase failure and prove managed old launch paths cannot reach port `4002`.
- Provider loss with an open position can leave risk unmanaged or let the host invent a trade: Tasks 5, 8, and 11 require an unexpired model-authored plan and allow only its exact deterministic actions.

## File Map

New focused modules:

- `ibkr_paper_30d/multi_universe_models.py`: immutable sleeve, contract, family, canary, and transition contracts.
- `ibkr_paper_30d/multi_universe_schema.py`: explicit append-only schema V4 installer and verifier.
- `ibkr_paper_30d/sleeve_ledger.py`: dual-ledger projection, currency subledgers, carry-forward, and performance formulas.
- `ibkr_paper_30d/contract_ownership.py`: exclusive contract/group ownership and broker-generated lineage.
- `ibkr_paper_30d/product_capability.py`: family capability evidence and lifecycle certification projection.
- `ibkr_paper_30d/sleeve_execution_authority.py`: pure final risk, ownership, family, and binding validation.
- `ibkr_paper_30d/sleeve_reconciliation.py`: account-to-sleeve positions, cash, orders, executions, and lineage reconciliation.
- `ibkr_paper_30d/multi_universe_transition.py`: durable transition state machine and recovery.
- `ibkr_paper_30d/canary_authority.py`: bounded maintenance reserve, lifecycle evidence, and rollback envelope.
- `ibkr_paper_30d/predecessor_retirement.py`: managed Windows launch inventory and retirement evidence.
- `RUN_IBKR_MULTI_UNIVERSE_SERVICE.ps1`: successor-only launcher used by a later authorized scheduler transition.
- `INVOKE_IBKR_MULTI_UNIVERSE_MAINTENANCE.ps1`: validate-first maintenance/canary/transition orchestrator; never run under this plan.

Existing modules extended in place:

- `persistence.py`, `risk.py`, `trader_invocation.py`, `autonomous_research.py`, `autonomous_state.py`, `session_orchestration.py`, `autonomous_service.py`.
- `coordinated_model_executor.py`, `autonomous_execution.py`, `authoritative_broker_writer.py`, `open_order_management.py`, `experiment_ledger.py`, `continuity_models.py`, `continuity_binding.py`, `continuity_executor.py`.
- `successor_authorization.py`, `successor_epoch.py`, `day1_launch.py`, `scheduler_validation.py`, `reporting.py`, `alerts.py`, `kernel_manifest.py`, and `IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`.

---

### Pre-Implementation Gate: Freeze the Approved Baseline

**Files:**
- Read: `docs/superpowers/specs/2026-10-09-continuous-multi-universe-sleeves-design.md`
- Verify only: `C:\AI_VAULT_IBKR`
- Work only: `C:\AI_VAULT_IBKR_WHATIF_FIX`

**Interfaces:**
- Consumes: approved specification commit `c923765574c1dda57789ecfa5c408ed9fd619464` and operational base `1e3286dc336ca8ca01930044b124f45884aab257`.
- Produces: a read-only baseline record proving isolation and zero production side effects.

- [ ] **Step 1: Verify the development checkout.** Record `git rev-parse --show-toplevel`, branch, HEAD, status, and merge base with `1e3286d`; require the worktree to contain `c923765` and have no unexplained changes.
- [ ] **Step 2: Capture canonical state read-only.** Record canonical HEAD/branch, Day1 process IDs, scheduler task definitions, execution-lock projection, schema versions, and file hashes. Do not connect to IBKR or normalize any state.
- [ ] **Step 3: Run the baseline suite.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d`; require zero failures and preserve all skip reasons.
- [ ] **Step 4: Run baseline integrity checks.** Run kernel closure, runtime provenance, PowerShell AST for current production scripts, forbidden `4001`/LIVE scans, and `git diff --check`; require PASS before editing code.

---

### Task 1: Add Immutable Sleeve and Transition Contracts with Schema V4

**Files:**
- Create: `ibkr_paper_30d/multi_universe_models.py`
- Create: `ibkr_paper_30d/multi_universe_schema.py`
- Create: `tests/ibkr_paper_30d/test_multi_universe_models.py`
- Create: `tests/ibkr_paper_30d/test_multi_universe_schema.py`
- Modify: `ibkr_paper_30d/persistence.py`
- Modify: `tests/ibkr_paper_30d/test_persistence.py`

**Interfaces:**
- Produce `CapitalSleeve = {REGULAR_SLEEVE, EXTENDED_SLEEVE}` and `TransitionPhase = {PREPARED, PREDECESSOR_QUIESCED, CANARY_EXCLUSIVE, CANARY_PASS, PREDECESSOR_RETIRED, SUCCESSOR_COMMITTED, RUNTIME_BOUND, ACTIVE}`.
- Produce immutable `CanonicalContractIdentity`, `ContractOwnershipGroup`, `ProductFamilyKey`, `SleeveAuthorityDefinition`, `CanaryAuthorization`, and `TransitionTarget` Pydantic models with canonical `.sha256` properties.
- Produce `install_multi_universe_schema_v4(db: Database) -> dict[str, Any]` and `verify_multi_universe_schema_v4(db: Database) -> dict[str, Any]`.
- Schema V4 owns append-only tables `sleeve_authority_events`, `sleeve_ledger_events`, `contract_ownership_events`, `product_family_certification_events`, `canary_authorization_events`, and `successor_transition_events`.

- [ ] **Step 1: Write RED model tests.** Add `test_only_two_economic_sleeves_exist`, `test_contract_identity_hash_includes_bag_legs`, `test_currency_is_not_an_exclusive_contract_identity`, and `test_transition_target_hash_binds_all_authority`; assert invalid enums, duplicate legs, non-SHA bindings, and mutable extras are rejected.
- [ ] **Step 2: Write RED schema tests.** Assert `Database.open()` does not install V4, V4 requires verified versions 2 and 3, explicit install is idempotent, every table rejects UPDATE/DELETE, partial schemas fail, and production-compatible databases remain byte-for-byte unchanged until install.
- [ ] **Step 3: Run RED.** Run `python -m pytest -q tests\ibkr_paper_30d\test_multi_universe_models.py tests\ibkr_paper_30d\test_multi_universe_schema.py tests\ibkr_paper_30d\test_persistence.py`; expect import and missing-schema failures.
- [ ] **Step 4: Implement the models and explicit installer.** Follow `successor_schema.py` and `continuity_schema.py`; use schema version `4`, exact column verification, named indexes, immutable triggers, integrity checks, and no implicit migration.
- [ ] **Step 5: Run GREEN and focused regression.** Add successor/continuity schema tests; require zero failures and exact `[1,2,3,4]` only in V4 test databases.
- [ ] **Step 6: Commit.** Commit only Task 1 files with `feat(ibkr): add multi-universe authority schema`.

### Task 2: Implement Dual Sleeve Ledgers and Quantitative Risk Authority

**Files:**
- Create: `ibkr_paper_30d/sleeve_ledger.py`
- Create: `tests/ibkr_paper_30d/test_sleeve_ledger.py`
- Modify: `ibkr_paper_30d/risk.py`
- Modify: `tests/ibkr_paper_30d/test_capital_boundary_risk.py`
- Modify: `ibkr_paper_30d/experiment_ledger.py`

**Interfaces:**
- Define immutable `RegularCarryForward`, `SleeveLedgerReceipt`, `SleeveLedgerState`, and `MultiSleeveLedgerState` in `sleeve_ledger.py`.
- Produce `SleeveLedgerStore.bootstrap_regular(carry: RegularCarryForward) -> SleeveLedgerReceipt`, `.bootstrap_extended() -> SleeveLedgerReceipt`, `.append(sleeve, event_type, payload) -> str`, `.project(sleeve) -> SleeveLedgerState`, and `.project_all() -> MultiSleeveLedgerState`.
- Produce `SleeveCapitalBoundaryInputs` and `SleeveCapitalBoundaryRiskEngine.evaluate(inputs) -> SleeveCapitalBoundaryDecision`.
- `AVAILABLE_s = max(0, EQUITY_s - RESERVED_s)`; proposed maximum loss must be `<= AVAILABLE_s`; aggregate reserved authority must be `<= EQUITY_s`; no cross-sleeve or non-experiment offset is permitted.

- [ ] **Step 1: Write RED opening-state tests.** Assert regular carry-forward preserves allocation, cost basis, fills, fees, realized/unrealized P&L, and historical hashes; extended opens at exactly USD 500, zero P&L, zero positions, and zero orders; retries are idempotent only for identical carry hashes.
- [ ] **Step 2: Write RED boundary tests.** Parameterize proposed and aggregate liability immediately below, exactly at (PASS), and USD 0.01 above (BLOCK); cover zero/negative equity, unbounded liability, external capital, and a broker margin offset from the other sleeve.
- [ ] **Step 3: Write RED currency tests.** Let both sleeves hold USD and EUR virtual balances, assert aggregate-by-currency reconciliation, and block one sleeve spending or pledging the other's balance.
- [ ] **Step 4: Run RED.** Run the new files plus `test_experiment_ledger.py`; expect missing store/engine failures.
- [ ] **Step 5: Implement append-only projection and risk evaluation.** Reuse canonical hashing and fill normalization from `AutonomousExperimentLedger`; never infer authority from account buying power. Keep the old ledger readable for Day1 and route successor events through the sleeve store only after V4 activation.
- [ ] **Step 6: Run GREEN and focused regression.** Include `test_risk.py`, risk diagnostics, and autonomous state tests; require zero failures.
- [ ] **Step 7: Commit.** Commit with `feat(ibkr): isolate sleeve economics and risk`.

### Task 3: Add Exclusive Contract Ownership and Broker-Generated Lineage

**Files:**
- Create: `ibkr_paper_30d/contract_ownership.py`
- Create: `tests/ibkr_paper_30d/test_contract_ownership.py`
- Modify: `ibkr_paper_30d/open_order_management.py`
- Modify: `tests/ibkr_paper_30d/test_open_order_management.py`

**Interfaces:**
- Produce `canonical_contract_identity(contract: Mapping[str, Any], legs: Sequence[Mapping[str, Any]] = ()) -> CanonicalContractIdentity` without replacing the existing order-snapshot helper until parity is proven.
- Define immutable `OwnershipReceipt` and `OwnershipProjection` in `contract_ownership.py`.
- Produce `ContractOwnershipStore.claim(...) -> OwnershipReceipt`, `.reserve_group(...)`, `.record_descendant(...)`, `.release(...)`, and `.projection() -> OwnershipProjection`.
- A claim transaction rereads current ownership under `BEGIN IMMEDIATE`; release requires zero position, zero open order, zero pending execution, and exact broker reconciliation.

- [ ] **Step 1: Write RED identity and race tests.** Assert the same conId cannot be claimed by both sleeves, simultaneous contenders yield exactly one claim, BAG parent/legs reserve one group, currency codes remain non-exclusive, and opposite-side netting is blocked.
- [ ] **Step 2: Write RED lineage tests.** Cover option exercise/assignment, expiration settlement, futures settlement, split, merger, spin-off, symbol/conId replacement, and broker correction; verified source lineage inherits the sleeve, while an unverifiable event returns `UNATTRIBUTED_ACCOUNT_EVENT`.
- [ ] **Step 3: Write RED release tests.** Any remaining order, fill ambiguity, execution, child position, or stale broker snapshot blocks release; exact terminal reconciliation permits one idempotent release.
- [ ] **Step 4: Run RED.** Run ownership and open-order files; expect missing interfaces.
- [ ] **Step 5: Implement ownership projection.** Use canonical broker identities and group hashes, not model prose or ticker alone. Keep all writes append-only and transactions broker-free.
- [ ] **Step 6: Run GREEN and focused regression.** Include order identity, reconciliation, authoritative writer, and execution tests.
- [ ] **Step 7: Commit.** Commit with `feat(ibkr): enforce sleeve contract ownership`.

### Task 4: Build Dynamic Product Capability and Full-Lifecycle Certification

**Files:**
- Create: `ibkr_paper_30d/product_capability.py`
- Create: `tests/ibkr_paper_30d/test_product_capability.py`
- Modify: `ibkr_paper_30d/ibkr_research_tools.py`
- Modify: `ibkr_paper_30d/scanner_capability.py`
- Modify: `tests/ibkr_paper_30d/test_ibkr_research_tools.py`
- Modify: `tests/ibkr_paper_30d/test_scanner_capability.py`

**Interfaces:**
- Produce `ProductCapabilityEvidence`, `ProductExecutionCapability`, `AvailabilityDecision`, `ProductFamilyCertificationStatus = {RESEARCH_ONLY, ORDER_TRANSMIT_VERIFIED, FULL_LIFECYCLE_VERIFIED, REVOKED}`, and `ProductFamilyCertificationStore`.
- Produce `.record_step(family, step, evidence_sha256)`, `.projection(family)`, and `.assert_executable(family, now_utc, account_sha256) -> ProductExecutionCapability`.
- Produce `ExtendedAvailabilityGate.evaluate(certifications, session_evidence, now_utc) -> AvailabilityDecision`; PASS requires at least one extended family fully verified and tradable now or within 24 authenticated hours.

- [ ] **Step 1: Write RED separation tests.** Assert Codex can discover an arbitrary candidate without host allowlists, while execution remains blocked until IBKR qualifies the exact contract, permissions, market data, order/quantity semantics, and bounded economics.
- [ ] **Step 2: Write RED certification tests.** A no-fill terminal order reaches only `ORDER_TRANSMIT_VERIFIED`; only ordered evidence for entry fill, visible position, management observation, closing fill, flat state, and economics reconciliation reaches `FULL_LIFECYCLE_VERIFIED`.
- [ ] **Step 3: Write RED family-scope tests.** Certification for one security type/venue/quantity/order representation does not authorize another; stale, wrong-account, changed-adapter, or revoked evidence blocks only that family.
- [ ] **Step 4: Run RED.** Run the new test plus toolbox/scanner/session evidence tests.
- [ ] **Step 5: Implement capability confirmation.** Reuse read-only toolbox qualification and session evidence. Persist PAPER limitations on every certification; never represent PAPER evidence as LIVE readiness.
- [ ] **Step 6: Run GREEN and focused regression.** Include broker feasibility, session evidence, and market policy tests.
- [ ] **Step 7: Commit.** Commit with `feat(ibkr): certify executable product families`.

### Task 5: Make the Model Contract Sleeve- and Portfolio-Aware

**Files:**
- Modify: `ibkr_paper_30d/trader_invocation.py`
- Modify: `ibkr_paper_30d/autonomous_research.py`
- Modify: `ibkr_paper_30d/autonomy_bootstrap.py`
- Modify: `tests/ibkr_paper_30d/test_trader_invocation.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_research.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_codex_provider.py`
- Modify: `tests/ibkr_paper_30d/test_autonomy_bootstrap.py`

**Interfaces:**
- Extend `TraderInputBundle` with optional legacy-compatible `multi_sleeve_portfolio`, `contract_ownership_snapshot`, and `product_capability_snapshot` fields.
- Extend `AutonomousTradeProposal`, `AutonomousPositionAction`, and `AutonomousOpenOrderAction` with `capital_sleeve: CapitalSleeve | None` and `product_family_sha256: str | None`; V4 validation requires both, legacy Day1 permits absence.
- Bind the selected sleeve and family into strict output schema, prompt payload, result hash, and `ModelExecutionRequest`.

- [ ] **Step 1: Write RED serialization tests.** Assert new fields hash deterministically, old Day1 fixtures still parse, V4 bundles reject missing sleeve/family, and unknown sleeve values fail schema validation.
- [ ] **Step 2: Write RED autonomy tests.** Assert the prompt presents both sleeve states and capabilities without recommending crypto, FX, futures, symbols, sessions, or constant trading; Codex may select either sleeve, research further, or return `NO_TRADE`.
- [ ] **Step 3: Write RED ownership tests.** A management action naming a sleeve different from durable ownership blocks; account-wide context remains visible but cannot transfer authority.
- [ ] **Step 4: Run RED.** Run the four focused files; expect schema and binding failures.
- [ ] **Step 5: Implement compatibility and strict V4 validation.** Use the active epoch/schema projection to choose legacy versus V4 requirements; do not infer a missing sleeve from ticker or strategy.
- [ ] **Step 6: Run GREEN and focused regression.** Include real provider, autonomy charter/wiring, and coordinated executor tests.
- [ ] **Step 7: Commit.** Commit with `feat(ibkr): expose multi-sleeve portfolio authority`.

### Task 6: Generalize State Building and Session Orchestration

**Files:**
- Modify: `ibkr_paper_30d/autonomous_state.py`
- Modify: `ibkr_paper_30d/session_orchestration.py`
- Modify: `ibkr_paper_30d/autonomous_service.py`
- Create: `tests/ibkr_paper_30d/test_multi_universe_orchestration.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_state.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_service.py`

**Interfaces:**
- Add `AutonomousStateBuilder` dependencies for `SleeveLedgerStore`, `ContractOwnershipStore`, and `ProductFamilyCertificationStore` when V4 is active.
- Produce `decide_multi_universe_orchestration(now_utc, family_sessions, open_orders, positions, continuity_deadlines) -> SessionOrchestrationDecision`.
- `MARKET_CLOSED_IDLE` is allowed only when no certified family is open, no opening occurs within the adaptive wake horizon, and no order/position continuity obligation is due.

- [ ] **Step 1: Write RED portfolio-state tests.** Assert one bundle contains exact separate sleeve economics, full account observations, ownership, capabilities, per-contract sessions, continuity, and the common successor clock; any reconciliation ambiguity freezes new entries.
- [ ] **Step 2: Write RED session tests.** Cover regular closed/extended open, both open, both closed, maintenance, unknown calendar, open order, position deadline, and daylight-saving transitions. One closed market must not idle the other.
- [ ] **Step 3: Write RED baseline-reuse tests.** Ordinary successor starts reuse the frozen regular baseline and collect only fresh candidate-specific extended evidence; no path starts the legacy three-window collector without a structural-change receipt.
- [ ] **Step 4: Run RED.** Run state, service, session, and market cadence files.
- [ ] **Step 5: Implement adaptive orchestration.** Preserve the single loop and provider lifecycle; adjust cadence from positions, orders, sessions, and deadlines without adding a second service.
- [ ] **Step 6: Run GREEN and focused regression.** Include market-data, observation, provider-lifecycle, and continuity watchdog tests.
- [ ] **Step 7: Commit.** Commit with `feat(ibkr): orchestrate continuous multi-universe cycles`.

### Task 7: Enforce Sleeve Authority in the Single Broker Writer

**Files:**
- Create: `ibkr_paper_30d/sleeve_execution_authority.py`
- Create: `tests/ibkr_paper_30d/test_sleeve_execution_authority.py`
- Modify: `ibkr_paper_30d/coordinated_model_executor.py`
- Modify: `ibkr_paper_30d/autonomous_execution.py`
- Modify: `ibkr_paper_30d/authoritative_broker_writer.py`
- Modify: `ibkr_paper_30d/broker_write_coordinator.py`
- Modify: `tests/ibkr_paper_30d/test_authoritative_broker_writer.py`
- Modify: `tests/ibkr_paper_30d/test_coordinated_model_executor.py`

**Interfaces:**
- Define immutable `SleeveAuthoritySnapshot` and `SleeveExecutionAuthorityReceipt` in `sleeve_execution_authority.py`.
- Produce `SleeveExecutionAuthorityValidator.validate(request, broker_evidence, db_snapshot: SleeveAuthoritySnapshot) -> SleeveExecutionAuthorityReceipt`.
- Extend `ModelExecutionRequest` with `capital_sleeve`, `sleeve_authority_sha256`, `ownership_projection_sha256`, `product_family_sha256`, and `continuity_plan_sha256` bindings.
- Exactly one transaction reserves sleeve capital and ownership for one accepted intent before `ISSUED_PRE_SEND`; broker send and reconciliation remain outside that transaction.

- [ ] **Step 1: Write RED gate-matrix tests.** Block wrong/missing sleeve, uncertified family, stale capability, ownership conflict, cross-sleeve cash/margin, unbounded liability, aggregate liability above equity, missing continuity plan, wrong account/head/epoch, and non-PAPER evidence.
- [ ] **Step 2: Write RED race tests.** Mutate ledger equity, ownership, family certification, transition phase, authorization, or plan after broker evidence collection but before `BEGIN IMMEDIATE`; every case blocks with zero broker writes.
- [ ] **Step 3: Write RED idempotency tests.** Two identical contenders create one reservation/send; a different sleeve, successor, family, definition, or payload cannot become idempotent success.
- [ ] **Step 4: Run RED.** Run authority, coordinator, writer, execution, and fault-injection tests.
- [ ] **Step 5: Implement pure validation and short reservation transaction.** Collect exact PAPER feasibility outside SQLite, reread all database authority inside `BEGIN IMMEDIATE`, persist hashes, commit, then let the existing writer send once.
- [ ] **Step 6: Preserve writer exclusivity.** Add architecture tests proving no new connection, client ID, direct executor, global cancel, or callable broker command was introduced.
- [ ] **Step 7: Run GREEN and focused regression.** Include broker feasibility, open-order management, order identity, execution lock, and production authority tests.
- [ ] **Step 8: Commit.** Commit with `feat(ibkr): gate writes by sleeve authority`.

### Task 8: Reconcile Sleeve State and Extend Model-Authored Continuity

**Files:**
- Create: `ibkr_paper_30d/sleeve_reconciliation.py`
- Create: `tests/ibkr_paper_30d/test_sleeve_reconciliation.py`
- Modify: `ibkr_paper_30d/continuity_models.py`
- Modify: `ibkr_paper_30d/continuity_binding.py`
- Modify: `ibkr_paper_30d/continuity_evaluator.py`
- Modify: `ibkr_paper_30d/continuity_executor.py`
- Modify: `ibkr_paper_30d/continuity_watchdog.py`
- Modify: `tests/ibkr_paper_30d/test_continuity_fault_injection.py`

**Interfaces:**
- Define immutable `MultiSleeveReconciliationReceipt` in `sleeve_reconciliation.py`.
- Produce `SleeveReconciler.reconcile(account_snapshot, sleeve_ledgers, ownership) -> MultiSleeveReconciliationReceipt`.
- Extend `CodexOrderContinuityPlan` with legacy-compatible sleeve, canonical contract/group, family, position, next-decision deadline, and authority hashes; V4 plans require them.
- Provider outage permits only the exact still-valid plan action; absent, stale, exhausted, or mismatched plans freeze new risk and alert without inventing management.

- [ ] **Step 1: Write RED reconciliation tests.** Cover fills, commissions, financing, currency cash, positions, orders, and executions across both sleeves; any aggregate mismatch or unexplained item yields `UNATTRIBUTED_ACCOUNT_EVENT` and freezes new entries.
- [ ] **Step 2: Write RED descendant tests.** Exercise assignment, exercise, BAG leg materialization, settlement, split, merger, spin-off, and contract replacement; assert inherited ownership and economics.
- [ ] **Step 3: Write RED outage tests.** With an open position, prove only an exact model-authored reduce/cancel/close action can execute before its deadline; missing or expired coverage creates no write. Include simultaneous positions in both sleeves.
- [ ] **Step 4: Run RED.** Run reconciliation and all continuity model/binding/evaluator/executor/watchdog files.
- [ ] **Step 5: Implement reconciliation and bindings.** Keep the watchdog read-only and the writer as sole executor. Do not derive a strategy from thresholds, marks, or time remaining.
- [ ] **Step 6: Run GREEN and focused regression.** Include ledger, state builder, provider lifecycle, alerts, and production continuity runtime tests.
- [ ] **Step 7: Commit.** Commit with `feat(ibkr): reconcile sleeves and continuity`.

### Task 9: Implement the Recoverable Successor Transition and Predecessor Retirement

**Files:**
- Create: `ibkr_paper_30d/multi_universe_transition.py`
- Create: `ibkr_paper_30d/predecessor_retirement.py`
- Create: `tests/ibkr_paper_30d/test_multi_universe_transition.py`
- Create: `tests/ibkr_paper_30d/test_predecessor_retirement.py`
- Modify: `ibkr_paper_30d/successor_authorization.py`
- Modify: `ibkr_paper_30d/successor_epoch.py`
- Modify: `tests/ibkr_paper_30d/test_successor_transition.py`

**Interfaces:**
- Define immutable `TransitionRecoveryResult` in `multi_universe_transition.py`.
- Produce `MultiUniverseTransitionCoordinator.prepare(target)`, `.advance(expected_phase, evidence)`, and `.recover(target) -> TransitionRecoveryResult`.
- Produce `PredecessorLaunchInventory`, `PredecessorRetirementReceipt`, and pure `validate_retirement(inventory, observations) -> RetirementDecision`.
- Every transition append uses one immutable `transition_id`, expected phase/hash compare-and-swap, target definition/head/Owner/clock/sleeve/certification hashes, and exact writer binding.

- [ ] **Step 1: Write RED phase tests.** Assert only the eight ordered phases are legal, exact retries are idempotent, different targets block, and no phase can skip predecessor quiescence, canary PASS, or retirement.
- [ ] **Step 2: Write RED crash matrix.** Stop after every durable phase, including after successor DB commit before runtime binding; recovery must neither duplicate events/canaries nor reauthorize the predecessor.
- [ ] **Step 3: Write RED retirement tests.** Inventory Scheduled Tasks, AtLogOn triggers, services, startup entries, launch bindings, and active receipt. Missing inventory, a still-enabled path, or a managed direct invocation capable of reaching `4002` blocks `PREDECESSOR_RETIRED`.
- [ ] **Step 4: Write RED broker-ordering tests.** Execution lock -> fresh PAPER identity/time/account evidence -> `BEGIN IMMEDIATE` -> reread DB authority -> freshness/hash checks -> atomic commit. Assert no broker I/O while the transaction is open.
- [ ] **Step 5: Run RED.** Run new transition/retirement files plus existing successor clock/graph/authorization tests.
- [ ] **Step 6: Implement state machine and recovery.** Before commit, audited rollback may restore the predecessor only when canary is flat and continuity exact. At/after `SUCCESSOR_COMMITTED`, startup must resume the successor and cannot select Day1. Any ambiguous transition phase, predecessor-retirement state, or recovery projection must freeze new order authority, persist one deduplicated critical event, write Windows Event Log, and send the configured external Owner alert before awaiting reconciliation.
- [ ] **Step 7: Run GREEN and focused regression.** Include launch, scheduler validation, execution lock, kill-switch recovery, and production compatibility tests.
- [ ] **Step 8: Commit.** Commit with `feat(ibkr): add recoverable multi-universe transition`.

### Task 10: Implement Bounded Canary and Maintenance Controls

**Files:**
- Create: `ibkr_paper_30d/canary_authority.py`
- Create: `tests/ibkr_paper_30d/test_canary_authority.py`
- Create: `INVOKE_IBKR_MULTI_UNIVERSE_MAINTENANCE.ps1`
- Create: `tests/ibkr_paper_30d/test_multi_universe_maintenance_script.py`
- Modify: `ibkr_paper_30d/product_capability.py`
- Modify: `ibkr_paper_30d/alerts.py`

**Interfaces:**
- Define immutable `CanaryAuthorityReceipt`, `CanaryLifecycleProjection`, and `RollbackDecision` in `canary_authority.py`.
- Produce `CanaryAuthorityValidator.validate(authorization, target, now_utc) -> CanaryAuthorityReceipt` and `CanaryLifecycleRecorder.record_*` methods for submit, bind, entry fill, position, management, exit fill, flat state, and economics.
- Produce `RollbackEnvelope.evaluate(detection_latency, restoration_latency, safety_margin, earliest_deadline) -> RollbackDecision`.
- The PowerShell script defaults to `-ValidateOnly`; mutation requires `-Apply`, exact Owner/canary/successor receipts, approved HEAD, exclusive lock evidence, and an explicit phase target.

- [ ] **Step 1: Write RED budget tests.** Reject missing/expired/wrong-family authorization, debit/loss/fees/order count at one cent/count beyond the exact maximum, replenishment, sleeve transfer, and any LIVE endpoint.
- [ ] **Step 2: Write RED lifecycle tests.** A no-fill terminal order cannot certify a family; actual entry fill, broker-visible position, management observation, closing fill, flat orders/positions, and reconciled economics are all mandatory and ordered.
- [ ] **Step 3: Write RED maintenance tests.** Block any Day1 open order, uncovered position, rollback envelope equal to or longer than the earliest deadline, second writer, or uncertain broker state. Prove no test liquidates Day1 for convenience.
- [ ] **Step 4: Write RED script tests.** Parse with Windows PowerShell and `pwsh`; default invocation must report only and make zero task/file/database/broker mutations. Source scans forbid port `4001`, global cancel, implicit `-Apply`, and unbounded task deletion.
- [ ] **Step 5: Run RED.** Run canary, capability, alert, and script tests.
- [ ] **Step 6: Implement validation-only orchestration.** The script may prepare exact commands/receipts for later Owner review but must not be executed in apply mode under this plan. Any ambiguous canary authority, lifecycle identity, cleanup state, or rollback decision must freeze new order authority, persist one deduplicated critical event, write Windows Event Log, and send the configured external Owner alert before awaiting reconciliation.
- [ ] **Step 7: Run GREEN and focused regression.** Include product capability, ownership, transition, continuity, and PowerShell finalizer tests.
- [ ] **Step 8: Commit.** Commit with `feat(ibkr): prepare bounded paper canaries`.

### Task 11: Wire One Continuous Production Composition and Successor Launcher

**Files:**
- Create: `RUN_IBKR_MULTI_UNIVERSE_SERVICE.ps1`
- Create: `tests/ibkr_paper_30d/test_multi_universe_service_script.py`
- Modify: `ibkr_paper_30d/day1_launch.py`
- Modify: `ibkr_paper_30d/production_continuity_runtime.py`
- Modify: `ibkr_paper_30d/scheduler_validation.py`
- Modify: `ibkr_paper_30d/reporting.py`
- Modify: `tests/ibkr_paper_30d/test_day1_launch.py`
- Modify: `tests/ibkr_paper_30d/test_production_continuity_runtime.py`
- Modify: `tests/ibkr_paper_30d/test_scheduler_validation.py`

**Interfaces:**
- Extend the existing production composition; do not create a second autonomous service. Inject dual ledger, ownership, capability, reconciliation, and transition stores into the one state builder, provider, coordinator, writer, and watchdog.
- Successor startup requires V4 schema, `ACTIVE` transition, exact approved HEAD/account/Owner/clock/sleeve/risk/certification hashes, at least one extended family available within 24 hours, and retired predecessor launch evidence.
- `RUN_IBKR_MULTI_UNIVERSE_SERVICE.ps1` launches the successor directly and never invokes the legacy three-window collection.

- [ ] **Step 1: Write RED composition tests.** Assert one provider, one service loop, one coordinator, one writer, one write-capable client, and one execution lock. Reject any fallback to direct execution or second session.
- [ ] **Step 2: Write RED launch tests.** Parameterize every prerequisite, including V4 absence, non-ACTIVE phase, mismatched hashes, no extended family, predecessor path active, continuity gap, and regular baseline misuse; each blocks before writer startup.
- [ ] **Step 3: Write RED restart tests.** After `SUCCESSOR_COMMITTED`, simulated Windows restart resumes the exact successor; invoking old task arguments or old receipts cannot reach broker connection construction.
- [ ] **Step 4: Write RED reporting tests.** Report regular historical P&L, each successor sleeve, combined successor/lifetime P&L, currency balances, canary adjustment, ownership, certified families, and PAPER limitations without rebasing or mixing capital.
- [ ] **Step 5: Run RED.** Run composition, launch, scheduler, reporting, and script files.
- [ ] **Step 6: Implement successor wiring.** Reuse Day1 preflight/provenance/lock helpers and Continuity V3 composition. Keep legacy Day1 behavior unchanged when V4 is absent and no successor target is requested.
- [ ] **Step 7: Run GREEN and focused regression.** Include autonomous service/state/runtime, market policy, continuity, writer, successor, and alert tests.
- [ ] **Step 8: Commit.** Commit with `feat(ibkr): compose continuous multi-universe runtime`.

### Task 12: Close Full Regression, Integrity, and Implementation Evidence

**Files:**
- Modify: `ibkr_paper_30d/kernel_manifest.py`
- Modify: `IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`
- Create: `docs/audits/CONTINUOUS_MULTI_UNIVERSE_IMPLEMENTATION_REPORT.md`
- Modify tests only for genuine defects discovered during verification.

**Interfaces:**
- Produces one clean implementation HEAD suitable for independent differential audit.
- Produces no runtime installation, production V4 schema, canary write, scheduler mutation, or successor activation.

- [ ] **Step 1: Run all new and directly affected tests.** Require zero failures across schema, ledgers, risk, ownership, capability, model contract, state/orchestration, writer, reconciliation/continuity, transition, canary, launch, scheduler, reporting, and PowerShell tests.
- [ ] **Step 2: Run the complete suite.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d`; require zero failures and document only known platform skips.
- [ ] **Step 3: Regenerate and verify kernel closure.** Run `python -m ibkr_paper_30d.kernel_manifest --repo-root . --output IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`, inspect every added authority path, and run kernel-manifest and runtime-provenance tests.
- [ ] **Step 4: Run PowerShell and static integrity.** Parse all production `.ps1` files with Windows PowerShell and `pwsh`; run `git diff --check`, secret scan, forbidden LIVE/`4001` scan, no-global-cancel scan, no-second-writer scan, and no-host-strategy scan.
- [ ] **Step 5: Recheck production non-interference read-only.** Compare canonical HEAD, scheduler definitions, runtime PIDs, schema versions, receipt hashes, execution-lock state, and broker-write counter to the pre-implementation baseline. Require `SCHEMA_V4_INSTALLED_IN_PRODUCTION=false`, `CANARY_EXECUTED=false`, and `REAL_BROKER_WRITES=0`.
- [ ] **Step 6: Write the implementation report.** Record base/final SHAs, commits, tests/counts/skips, integrity hashes, unexecuted operational gates, residual PAPER limitations, and exact next authorization required.
- [ ] **Step 7: Commit final evidence.** Commit manifest/report with `docs(ibkr): record multi-universe implementation evidence`.
- [ ] **Step 8: Final clean gate.** Require clean status, `git diff --check`, exact final HEAD, and no unfinished markers. Stop; do not install, canary, retire Day1, change the scheduler, or activate the successor.

## Completion Report

Return exactly:

```text
CONTINUOUS_MULTI_UNIVERSE_IMPLEMENTATION_REPORT

DESIGN_HEAD: c923765574c1dda57789ecfa5c408ed9fd619464
BASE_OPERATIONAL_HEAD: 1e3286dc336ca8ca01930044b124f45884aab257
FINAL_IMPLEMENTATION_HEAD:
BRANCH: codex/continuous-multi-universe-design
COMMITS:
FOCUSED_TESTS:
FULL_TESTS:
KERNEL_CLOSURE:
RUNTIME_PROVENANCE:
POWERSHELL_AST:
GIT_DIFF_CHECK:
SLEEVE_SCHEMA_V4:
DUAL_LEDGER:
STANDALONE_SOLVENCY:
CONTRACT_OWNERSHIP:
PRODUCT_FAMILY_CERTIFICATION:
MODEL_AUTONOMY_PRESERVED:
SOLE_WRITE_CAPABLE_SESSION:
CONTINUITY_COVERAGE:
TRANSITION_FAULT_INJECTION:
PREDECESSOR_RETIREMENT_SIMULATION:
CANARY_VALIDATION_SIMULATION:
THREE_WINDOW_DAILY_RECOLLECTION: false
RUNTIME_INSTALLED: false
SCHEMA_V4_INSTALLED_IN_PRODUCTION: false
CANARY_EXECUTED: false
PREDECESSOR_RETIRED: false
SUCCESSOR_EPOCH_ACTIVE: false
SCHEDULER_CHANGED: false
REAL_BROKER_WRITES: 0
LIVE_CONNECTIONS: 0
DAY1_PRODUCTION_TOUCHED: false
EXTERNAL_AUDIT_REQUIRED: true
NEXT_OWNER_DECISION_REQUIRED: true
```
