# Agent Continuity Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve Codex-authored order authority through temporary provider outages without allowing the host runtime to invent an economic decision.

**Architecture:** Codex emits a strict, hash-bound continuity plan with any accepted decision that can leave an order actionable. Append-only stores reconstruct plan, provider, watchdog, evaluation, execution, and review state; a deterministic watchdog with its own SQLite connection and read-only PAPER broker client evaluates that prior authority outside the blocking Codex call. Model and watchdog paths submit exact commands to one authoritative broker-writer worker that exclusively owns the experiment execution `clientId`; the existing process-level execution lock continues to exclude other runtime processes.

**Tech Stack:** Python 3.11, Pydantic v2, SQLite WAL, `ib_insync`, pytest, Windows named execution lock, PowerShell AST validation.

**Spec:** `docs/superpowers/specs/2026-10-01-agent-continuity-authority-design.md`

## Global Constraints

- PAPER account only; `LIVE_ALLOWED=false`, `REAL_MONEY_ALLOWED=false`.
- Codex remains the sole economic decision maker. Runtime code may evaluate only finite model-authored predicates and execute only exact model-authored actions.
- No host-authored universal retain, cancel, reprice, timeout, expiry disposition, or unavailable-data fallback.
- No adversarial agent is part of this architecture.
- Continuity broker writes are limited to `RETAIN`, exact-order `CANCEL`, and exact same-order `MODIFY_EXISTING_ORDER`; global cancel and cancel-and-replace are prohibited.
- Account, epoch, authorization, order identity, contract/BAG legs, direction, order type, and routing remain immutable.
- Broker network I/O must never occur while a SQLite write transaction is open.
- The watchdog must own a separate SQLite connection and separate read-only PAPER broker client/session. It may share only immutable configuration, stop/liveness signals, and the command interface to one authoritative broker writer.
- Exactly one authoritative broker-writer worker owns the execution `clientId`; neither the model path nor watchdog may open another write-capable broker session or treat `reqAllOpenOrders()` visibility as modification authority.
- Authenticated PAPER broker time is authoritative for continuity elapsed-time and expiry decisions. Host and monotonic clocks are diagnostic only.
- A pending continuity review mechanically blocks new/increased maximum liability and extended temporal authority; reconciliation, observation, cancellation, closing/reduction, nonexpanding fresh Codex actions, and already-authorized continuity actions remain available.
- All implementation edits, commits, tests, and manifest generation occur only in `C:\AI_VAULT_IBKR_CONTINUITY_DEV` on `codex/agent-continuity-authority`. Do not modify HEAD, tracked files, runtime files, manifests, scheduler state, or `ApprovedHead` in `C:\AI_VAULT_IBKR`.
- Existing untracked runtime/state artifacts are not modified or deleted.
- This implementation phase does not install schema V3 into production, deploy runtime files, update or enable the scheduler, modify any broker order, or launch the experiment.

## Review Focus

- A blocking provider call must not starve continuity: Task 8 deliberately blocks `next_turn()` while the watchdog evaluates and the independent authoritative writer performs one authorized action.
- Broker state can change between evaluation and write: Tasks 6 and 7 test fills, partial fills, supersession, model recovery, and stale evidence at the final authority re-read.
- A crash can occur after `placeOrder()` but before `BROKER_BOUND`: Task 6 reconstructs only an exact unique pre-send binding and freezes ambiguity.
- Provider elapsed-time authority can be forged or lost across restart: Task 3 tests predecessor hashes, broker timestamps, conflicting terminal events, and abandoned processes.
- Review gating can accidentally immobilize risk reduction or allow new exposure: Task 9 tests every authority class and all four review dispositions.

---

### Pre-Implementation Gate: IBKR Writer Ownership and Workspace Isolation

**Files:**
- Modify: `docs/superpowers/specs/2026-10-01-agent-continuity-authority-design.md`
- Verify only: `C:\AI_VAULT_IBKR`
- Work only: `C:\AI_VAULT_IBKR_CONTINUITY_DEV`

**Interfaces:**
- Consumes: IBKR's documented API-order ownership semantics and current scheduler/checkout evidence.
- Produces: a fixed architectural invariant for Tasks 6-10 and proof that implementation occurs outside the operational checkout.

- [ ] **Step 1: Record the broker capability invariant.** Bind the design to IBKR's documented rules: an API order is modified/cancelled by the same submitting `clientId`; `reqAllOpenOrders()` does not bind or transfer authority; a simultaneous second connection using that ID fails with error 326. Primary references: `https://interactivebrokers.github.io/tws-api/modifying_orders.html`, `open_orders.html`, `cancel_order.html`, and `message_codes.html`.

- [ ] **Step 2: Resolve the zero-write proof boundary.** Do not claim an empirical cancel/modify proof without an order. Treat the official rule as the implementation invariant, prove it with deterministic fake-broker contract tests in Task 7, and create a disabled PAPER capability harness for later deployment validation. Running that harness with `placeOrder`, including `transmit=False`, requires separate Owner authorization and is not part of this plan.

- [ ] **Step 3: Verify workspace isolation.** Assert implementation worktree root is exactly `C:\AI_VAULT_IBKR_CONTINUITY_DEV`, branch is `codex/agent-continuity-authority`, and its merge base contains operational head `d1fc6d694b0326bb71c155b826ffec6fadd9712c`. Capture read-only operational HEAD, scheduler state, scheduler `ApprovedHead`, process IDs, and broker-order counts before edits; do not normalize or mutate them.

- [ ] **Step 4: Run the baseline suite in the worktree.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d`; expected: zero failures before implementation. If it fails, stop and report the baseline failure rather than attributing it to continuity work.

---

### Task 1: Define the Strict Continuity Authority Contract

**Files:**
- Create: `ibkr_paper_30d/continuity_models.py`
- Create: `tests/ibkr_paper_30d/test_continuity_models.py`

**Interfaces:**
- Consumes: Pydantic v2, `sha256_json()`, and existing proposal/open-order identity fields.
- Produces: `ContinuityCondition`, `ContinuityValueExpression`, `ContinuityExecutableAction`, `ContinuityContingency`, `ContinuityOrderBinding`, `CodexOrderContinuityPlan`, `ContinuityFactEvidence`, `ContinuityFactSnapshot`, `ContinuityEvaluation`, `ContinuityReview`, and the enums used by all later tasks.

- [ ] **Step 1: Write RED tests for valid materially different plans.** Add `test_accepts_distinct_retain_cancel_and_modify_plans`, `test_accepts_provider_failure_decision_age_and_in_flight_activation_conditions`, and `test_accepts_both_expiry_authority_modes`. Assert the schema is exactly `CODEX_ORDER_CONTINUITY_PLAN_V1`, plan hashes differ when policy differs, and both `WHEN_CONTINUITY_ACTIVE` and `ALWAYS_AT_EXPIRY` require an explicit model selection.

- [ ] **Step 2: Write RED tests for structural rejection.** Parameterize missing validity, terminal disposition, unavailable-data action, partial-fill branch, provenance hash, activation condition, expiry mode, and maximum execution count. Add rejection tests for arbitrary code/SQL/shell/network facts, qualitative predicates, cyclic or over-depth expressions, non-finite decimals, unbounded action values, and `REQUIRES_AGENT` without an exact interim disposition.

- [ ] **Step 3: Run the focused RED tests.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_continuity_models.py`; expected: collection fails because `continuity_models` does not exist.

- [ ] **Step 4: Implement the frozen Pydantic contract.** Define:
  - `ExpiryAuthorityMode = {WHEN_CONTINUITY_ACTIVE, ALWAYS_AT_EXPIRY}`;
  - `ContinuityActionType = {RETAIN, CANCEL, MODIFY_EXISTING_ORDER, REQUIRES_AGENT}`;
  - `ProviderInvocationState = {IDLE, IN_FLIGHT, TIMEOUT_CONFIRMED, PROCESS_ERROR, COMPLETED_UNACCEPTED, COMPLETED_ACCEPTED, ABANDONED}`;
  - `ContinuityReviewDisposition = {ACK_NO_METHOD_CHANGE, REFLECTION_RECORDED, POLICY_SUPERSEDED, MORE_RESEARCH_REQUIRED}`;
  - `ContinuityAuthorityClass = {NEW_EXPOSURE, INCREASED_MAXIMUM_LIABILITY, EXTENDED_TEMPORAL_AUTHORITY, NONEXPANDING_EXISTING_AUTHORITY, RECONCILIATION, OBSERVATION, CANCEL_ORDER, REDUCE_POSITION, CLOSE_POSITION, PREAUTHORIZED_CONTINUITY}`.

  Use a finite condition AST with `PREDICATE`, `ALL`, `ANY`, and `NOT`; approved fact names only; explicit freshness; and explicit unavailable-data action. Use a bounded numeric expression AST with literals, approved numeric facts, `ADD`, `SUBTRACT`, `MULTIPLY`, `MIN`, `MAX`, and tick rounding, capped by depth and node count. Do not evaluate in this module.

- [ ] **Step 5: Add immutable-versus-mutable validation.** Permit model-authored changes only to `limitPrice`, total quantity, `TIF`, and associated good-till timestamp. Require exact immutable identity for an existing order and a proposal hash for a new order. Reject `GTD` without a timestamp, a timestamp without `GTD`, and any TIF beyond the experiment/epoch authority bound. Permit TIF beyond `plan_valid_until` only when the exact terminal disposition authorizes `RETAIN_UNTIL_ORDER_TIF`; otherwise reject it. Require explicit branches for `UNFILLED`, `PARTIALLY_FILLED`, `FILLED`, `PENDING_CANCEL`, `CANCELLED`, `REJECTED`, `ABSENT`, and `EVIDENCE_UNAVAILABLE` where reachable.

- [ ] **Step 6: Run GREEN and commit.** Run the focused test file; expected: zero failures. Commit only these files with `feat(ibkr): define continuity authority contract`.

### Task 2: Add Explicit Append-Only Continuity Schema and Store

**Files:**
- Create: `ibkr_paper_30d/continuity_schema.py`
- Create: `ibkr_paper_30d/continuity_store.py`
- Create: `tests/ibkr_paper_30d/test_continuity_schema.py`
- Create: `tests/ibkr_paper_30d/test_continuity_store.py`
- Modify: `ibkr_paper_30d/persistence.py`
- Modify: `tests/ibkr_paper_30d/test_persistence.py`

**Interfaces:**
- Consumes: Task 1 models, `Database`, `canonical_bytes()`, `sha256_json()`, `new_uuid7()`, and `utc_now()`.
- Produces: `install_continuity_schema_v3(db)`, `verify_continuity_schema_v3(db)`, and `ContinuityStore` methods `append_plan_event()`, `active_plan()`, `append_provider_event()`, `provider_projection()`, `append_watchdog_event()`, `append_evaluation()`, `append_execution_event()`, `append_report()`, `pending_reports()`, `append_review()`, and `append_reflection()`.

- [ ] **Step 1: Write RED schema tests.** Require explicit schema version 3 and exact immutable tables `continuity_plan_events`, `provider_invocation_events`, `continuity_watchdog_events`, `continuity_evaluation_events`, `continuity_execution_events`, `continuity_report_events`, `continuity_review_events`, and `continuity_reflection_events`, with indexes for plan/order/invocation/report lookup and UPDATE/DELETE rejection triggers.

- [ ] **Step 2: Prove migration locality before implementation.** Add `test_database_open_does_not_implicitly_install_continuity_schema_v3`, `test_install_is_idempotent`, `test_partial_or_malformed_v3_schema_blocks`, and `test_install_changes_no_epoch_clock_authorization_order_or_ledger_rows`.

- [ ] **Step 3: Write RED store tests.** Cover hash/predecessor validation, duplicate/conflicting active plans, exact idempotent replay, corrupt payloads, supersession chain reconstruction, one-shot execution uniqueness, report/review exact hash binding, and concurrent SQLite contenders where exactly one transition commits.

- [ ] **Step 4: Run the focused RED tests.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_continuity_schema.py tests\ibkr_paper_30d\test_continuity_store.py tests\ibkr_paper_30d\test_persistence.py`; expected: new schema/store tests fail.

- [ ] **Step 5: Implement the explicit V3 installer.** Keep `Database.open()` and base `SCHEMA` free of V3 tables. Require and verify successor schema V2 before installation; install all V3 objects in one `BEGIN IMMEDIATE`, verify exact columns/indexes/triggers/version, and fail closed on a partial installation. Split persistence classification into the existing base tables and new `CONTINUITY_CANONICAL_TABLES`/`CONTINUITY_APPEND_ONLY_TABLES`; `Database.open()` must install triggers only for base tables, while the V3 installer installs continuity triggers. This prevents ordinary V1/V2 database opens from referencing absent V3 tables.

- [ ] **Step 6: Implement `ContinuityStore`.** Every payload is canonical JSON with SHA-256 and a predecessor hash where ordering matters. Projections must recompute from immutable rows and reject gaps, forks, duplicate terminals, hash mismatch, and more than one active plan. Do not hold a write transaction around any callback or broker operation.

- [ ] **Step 7: Run GREEN and commit.** Run the three focused files; expected: zero failures. Commit with `feat(ibkr): persist continuity authority events`.

### Task 3: Persist Canonical Provider and Invocation State

**Files:**
- Create: `ibkr_paper_30d/provider_lifecycle.py`
- Create: `tests/ibkr_paper_30d/test_provider_lifecycle.py`
- Modify: `ibkr_paper_30d/autonomous_runtime.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_runtime.py`

**Interfaces:**
- Consumes: `ContinuityStore`, `InvocationRequest`, broker-time reader, launch attempt ID, PID, boot-session identity, and execution-lock owner projection.
- Produces: `ProviderLifecycleRecorder.begin(request, broker_time_utc) -> ProviderInvocationToken`, `complete(token, state, broker_time_utc, result_sha256=None)`, `fail(token, failure_code, broker_time_utc)`, and `recover_abandoned(current_lock_owner, broker_time_utc)`.

- [ ] **Step 1: Write RED lifecycle tests.** Exercise all seven canonical states, start-to-terminal predecessor linkage, duplicate exact replay, conflicting terminals, accepted completion before result durability, missing/naive/non-PAPER broker time, and broker time moving backwards.

- [ ] **Step 2: Write RED restart tests.** Prove an `IN_FLIGHT` event becomes `ABANDONED` only when its PID/boot-session is not the current execution-lock owner; a live matching owner remains `IN_FLIGHT`; uncertain lock ownership remains unavailable, not abandoned.

- [ ] **Step 3: Write RED runtime ordering tests.** Assert `IN_FLIGHT` is durable before `AutonomousResearchLoop.run()`, `TIMEOUT_CONFIRMED` follows an observed `TimeoutError`, `PROCESS_ERROR` follows a non-timeout provider failure, and `COMPLETED_ACCEPTED` is appended only after the matching accepted `trader_results` row is durable. A rejected final outcome ends as `COMPLETED_UNACCEPTED`.

- [ ] **Step 4: Run RED.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_provider_lifecycle.py tests\ibkr_paper_30d\test_autonomous_runtime.py`; expected: lifecycle APIs are missing.

- [ ] **Step 5: Implement lifecycle recording and runtime hooks.** Treat the complete multi-round research loop as one invocation. Persist the broker-time start anchor and declared deadline before calling the provider. On successful outcome, persist existing outcome/result records first, then append the terminal provider event. Never infer timeout or acceptance from missing rows.

- [ ] **Step 6: Run GREEN and commit.** Run the focused files; expected: zero failures. Commit with `feat(ibkr): record canonical provider lifecycle`.

### Task 4: Implement Deterministic Fact Collection and Evaluation

**Files:**
- Create: `ibkr_paper_30d/continuity_evaluator.py`
- Create: `tests/ibkr_paper_30d/test_continuity_evaluator.py`

**Interfaces:**
- Consumes: Task 1 models, `ContinuityStore.provider_projection()`, active-plan projection, authenticated PAPER broker adapter, experiment ledger/clock, and canonical open-order helpers.
- Produces: `ContinuityFactCollector.collect(plan, *, broker_time_utc) -> ContinuityFactSnapshot`, `evaluate_condition(condition, facts) -> bool | None`, `evaluate_value(expression, facts) -> Decimal`, and `ContinuityEvaluator.evaluate(plan, facts) -> ContinuityEvaluation`.

- [ ] **Step 1: Write RED condition tests.** Cover equality, inequality, range, membership, elapsed-time, Boolean nesting, deterministic priority, one-shot/finite sequence limits, price/volume/session/order/fill/position/equity facts, and numeric expression tick rounding.

- [ ] **Step 2: Write RED authority and expiry tests.** Prove an in-flight invocation blocks continuity unless the plan explicitly activates in that state. Prove `WHEN_CONTINUITY_ACTIVE` requires the activation condition at expiry and `ALWAYS_AT_EXPIRY` does not. No host fallback may select an action.

- [ ] **Step 3: Write RED evidence tests.** Require every fact to carry source, broker collection time, freshness limit, canonical value, and evidence hash. Missing broker time, stale quote, conflicting provider state, unavailable all-order visibility, or absent required fact must reach only the exact model-authored unavailable-data branch.

- [ ] **Step 4: Run RED.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_continuity_evaluator.py`; expected: evaluator APIs are missing.

- [ ] **Step 5: Implement collection and pure evaluation.** The collector may perform read-only broker I/O before any DB write transaction. The evaluator is pure: no database writes, broker calls, shell commands, model calls, or narrative parsing. Select at most one contingency by explicit numeric priority and stable contingency ID tie-break; duplicate priority without a declared tie-break is invalid at plan validation.

- [ ] **Step 6: Prove narrative non-authority and no policy constants.** Add a test changing `why_i_chose_this_contingency` and expectations while holding predicates/actions constant; assert identical evaluation hashes except narrative provenance and identical selected action. Add a source scan test proving no universal continuity duration, cancellation threshold, or repricing percentage appears in evaluator/runtime constants.

- [ ] **Step 7: Run GREEN and commit.** Run the focused file; expected: zero failures. Commit with `feat(ibkr): evaluate model-authored continuity plans`.

### Task 5: Extend the Codex Turn Contract and Model Context

**Files:**
- Modify: `ibkr_paper_30d/autonomous_research.py`
- Modify: `ibkr_paper_30d/autonomous_runtime.py`
- Modify: `ibkr_paper_30d/trader_invocation.py`
- Modify: `ibkr_paper_30d/autonomous_state.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_research.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_codex_provider.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_runtime.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_state.py`

**Interfaces:**
- Consumes: `CodexOrderContinuityPlan`, `ContinuityReview`, active plan/report projections, and existing `AutonomousTurn`/`TraderInputBundle` contracts.
- Produces: `AutonomousTurn.continuity_plan`, `AutonomousTurn.continuity_reviews`, `AutonomousResearchOutcome.continuity_plan`, `AutonomousResearchOutcome.continuity_reviews`, and `TraderInputBundle.continuity_context`.

- [ ] **Step 1: Write RED turn-validation tests.** Require a complete plan for `PROPOSE_TRADE`; require a replacement plan for `MODIFY_ORDER` when an actionable remainder can persist; forbid a plan on `CANCEL_ORDER`; allow `NO_TRADE` plus a plan only as an exact existing-order plan creation/supersession; reject plan/proposal/order identity mismatch.

- [ ] **Step 2: Write RED context and schema tests.** Assert the provider prompt and strict JSON schema expose active plan lifecycle, provider state, pending factual reports, prior reflections marked untrusted, and the instruction that the model itself chooses activation, expiry, conditions, and actions. Assert no prompt text recommends a timeout, cancel, retain, price, symbol, strategy, or adversarial reviewer.

- [ ] **Step 3: Write RED persistence tests.** An accepted plan must be hash-bound to invocation, input bundle, result, proposal/action, epoch, clock, owner authorization, and model attestation. A rejected turn, invalid plan, or unaccepted result creates no executable plan authority.

- [ ] **Step 4: Run RED.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_autonomous_research.py tests\ibkr_paper_30d\test_autonomous_codex_provider.py tests\ibkr_paper_30d\test_autonomous_runtime.py tests\ibkr_paper_30d\test_autonomous_state.py`; expected: continuity fields/validation are missing.

- [ ] **Step 5: Implement the contract and persistence ordering.** Extend `AutonomousTurn` and outcome payloads without adding a new strategic decision enum. Plan-only `NO_TRADE` is accepted only when exact existing-order ownership is proven. Persist the accepted model result before creating a `VALIDATED` plan event; a plan remains non-executable until Task 6 binding succeeds.

- [ ] **Step 6: Run GREEN and commit.** Run the focused files; expected: zero failures. Commit with `feat(ibkr): accept Codex continuity authority`.

### Task 6: Bind Plans to Broker Orders and Recover Pending Sends

**Files:**
- Create: `ibkr_paper_30d/continuity_binding.py`
- Create: `tests/ibkr_paper_30d/test_continuity_binding.py`
- Modify: `ibkr_paper_30d/autonomous_execution.py`
- Modify: `ibkr_paper_30d/open_order_management.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_execution.py`
- Modify: `tests/ibkr_paper_30d/test_open_order_management.py`

**Interfaces:**
- Consumes: validated plan, accepted proposal/action hashes, existing registry identity, `reqAllOpenOrders`, executions, positions, and `ContinuityStore`.
- Produces: `ContinuityBindingService.stage_new_order(...) -> PendingContinuityBinding`, `activate_broker_binding(...) -> ActiveContinuityBinding`, `supersede_existing_order_plan(...)`, and `PendingBindingReconciler.reconcile(plan_id) -> BindingRecoveryResult`.

- [ ] **Step 1: Write RED atomic pre-send tests.** Assert the generated `orderRef`, order/client IDs, proposal hash, immutable contract/BAG identity, plan hash, invocation ID, and attempt ID enter `CONTINUITY_BIND_PENDING` in the same transaction as `ISSUED_PRE_SEND`. Inject persistence failure and assert `placeOrder()` is never called.

- [ ] **Step 2: Write RED post-send tests.** Broker acknowledgement with a positive exact `permId` appends `BROKER_BOUND` and `ACTIVE` predecessor-linked events. Mismatched account, order IDs, contract/BAG legs, direction, order type, routing, or plan hash blocks activation.

- [ ] **Step 3: Write RED crash-recovery matrix.** Simulate death after broker acceptance and before local binding. Test one exact open order, exact execution/fill, terminal cancellation/rejection, no broker evidence, and two ambiguous candidates. Only one exact identity may complete binding; absence/terminal state records the observed terminal branch; ambiguity freezes writes and emits the reconciliation-critical result without cancelling.

- [ ] **Step 4: Write RED supersession/race tests.** An active plan can be superseded only by a later accepted Codex result naming the prior hash. Two contenders must not leave two active plans. A stale pending or active plan cannot execute after supersession.

- [ ] **Step 5: Run RED.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_continuity_binding.py tests\ibkr_paper_30d\test_autonomous_execution.py tests\ibkr_paper_30d\test_open_order_management.py`; expected: binding APIs and events are missing.

- [ ] **Step 6: Implement binding and recovery.** Refactor the registry insert into a transaction-compatible helper; do no broker I/O inside that transaction. Use `reqAllOpenOrders` for recovery visibility. Bind only an exact unique identity and preserve the existing prohibition on global cancellation.

- [ ] **Step 7: Run GREEN and commit.** Run the focused files; expected: zero failures. Commit with `feat(ibkr): bind continuity plans to broker orders`.

### Task 7: Serialize and Execute Exact Continuity Actions

**Files:**
- Create: `ibkr_paper_30d/broker_write_coordinator.py`
- Create: `ibkr_paper_30d/authoritative_broker_writer.py`
- Create: `ibkr_paper_30d/broker_writer_capability.py`
- Create: `ibkr_paper_30d/continuity_executor.py`
- Create: `tests/ibkr_paper_30d/test_authoritative_broker_writer.py`
- Create: `tests/ibkr_paper_30d/test_continuity_executor.py`
- Modify: `ibkr_paper_30d/autonomous_execution.py`
- Modify: `ibkr_paper_30d/autonomous_research.py`
- Modify: `ibkr_paper_30d/ibkr_research_tools.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_execution.py`
- Modify: `tests/ibkr_paper_30d/test_ibkr_research_tools.py`

**Interfaces:**
- Consumes: `ContinuityEvaluation`, exact active binding, fresh broker evidence, current external gates, and one writer-owned execution `clientId`.
- Produces: `AuthorizedBrokerCommand`, `BrokerWriteCoordinator.submit(command) -> Future[PaperExecutionResult]`, `AuthoritativeBrokerWriter.start()/stop()`, `ContinuityExecutor.build_command(evaluation) -> AuthorizedBrokerCommand`, and same-order support for exact `new_total_quantity`, `new_limit_price`, `new_tif`, and `new_good_till_date_utc`.

- [ ] **Step 1: Write RED writer-ownership tests.** Use a deterministic fake Gateway that associates each API order with its submitting client ID, rejects cancel/modify from another ID, returns cross-client visibility from `reqAllOpenOrders()`, and rejects a duplicate simultaneous connection with error 326. Assert model and watchdog commands both execute through one writer-owned client ID while watchdog reads use a distinct read-only ID.

- [ ] **Step 2: Write RED queue/concurrency tests.** Block the model caller independently of the writer worker, submit one watchdog command, and prove the writer remains live. Two commands serialize FIFO by durable command sequence, but the second must re-read authority and block when plan/order/provider state changed. The process execution lock remains required and the queue cannot be bypassed by calling `placeOrder`/`cancelOrder` directly.

- [ ] **Step 3: Write RED `RETAIN` and `CANCEL` tests.** `RETAIN` persists evidence and sends no broker command. `CANCEL` reaches only exact-order `cancelOrder` through the owning writer; identity/state/hash mismatch, duplicate execution key, uncertain all-order visibility, non-owner client ID, or non-active status blocks. Assert no path references `reqGlobalCancel`.

- [ ] **Step 4: Write RED modification tests.** Permit only exact preauthorized mutable fields on the same order ID through the owning writer. Cover limit, quantity increase/decrease, `DAY`/`GTC`/`GTD` transitions, timestamp binding, broker capability rejection, experiment-clock overrun, partial fill, stale state hash, immutable field drift, and rejection when a non-owner session attempts the write.

- [ ] **Step 5: Write RED fresh-risk tests.** An action increasing maximum liability requires fresh PAPER identity, authorization, kill-switch clear, runtime integrity, reconciliation, quotes, market-data policy, current equity/liability, and IBKR what-if PASS. A nonexpanding action still requires identity/integrity and is classified only by liability and temporal-authority deltas, never by a host label such as defensive.

- [ ] **Step 6: Write RED uncertain-outcome tests.** Disconnect before write produces no result claiming a send. Disconnect after write or before confirmation records `CONTINUITY_ORDER_STATE_UNCERTAIN`, blocks further writes for that order, and routes to critical alert/reconciliation. Result-persistence failure after acknowledgement is also uncertain, never an automatic retry. Writer reconnect uses the same client ID exclusively and requires reconciliation before dequeuing another command.

- [ ] **Step 7: Run RED.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_authoritative_broker_writer.py tests\ibkr_paper_30d\test_continuity_executor.py tests\ibkr_paper_30d\test_autonomous_execution.py tests\ibkr_paper_30d\test_ibkr_research_tools.py`; expected: writer/coordinator/executor and TIF support are missing.

- [ ] **Step 8: Implement the single writer and final re-read.** The writer thread owns the only write-capable broker connection for the full service lifetime. Model and continuity executors build immutable commands and submit them to `BrokerWriteCoordinator`; they do not connect directly. Inside the writer, collect fresh broker evidence outside SQLite transactions, then re-read plan, provider state, last accepted decision, order lifecycle, kill switch, clock, and one-shot count before appending the attempt and sending. Never derive a price, quantity, or TIF not contained in the command.

- [ ] **Step 9: Add the disabled capability harness.** `python -m ibkr_paper_30d.broker_writer_capability --describe` prints the required same-client checks and performs zero connections/writes. A separate `--paper-probe` path must require an explicit one-use authorization receipt, refuse while the experiment runtime/order set is active, and remain unexecuted in this implementation phase.

- [ ] **Step 10: Run GREEN and commit.** Run the focused files; expected: zero failures and zero real broker calls. Commit with `feat(ibkr): route writes through authoritative broker worker`.

### Task 8: Run an Independent Continuity Watchdog

**Files:**
- Create: `ibkr_paper_30d/continuity_watchdog.py`
- Create: `tests/ibkr_paper_30d/test_continuity_watchdog.py`
- Modify: `ibkr_paper_30d/autonomous_service.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_service.py`

**Interfaces:**
- Consumes: DB-path/factory, dedicated read-only PAPER toolbox factory, evaluator factory, `BrokerWriteCoordinator` command interface, service stop signal, launch/epoch authority, and infrastructure-only polling/heartbeat intervals.
- Produces: `ContinuityWatchdog.start()`, `stop(timeout_seconds) -> WatchdogShutdownResult`, `is_healthy(broker_time_utc)`, and watchdog lifecycle/heartbeat events.

- [ ] **Step 1: Write the decisive blocked-provider RED test.** Make `provider.next_turn()` wait on an event indefinitely. Start one service cycle in a separate thread, assert it remains blocked, then advance broker facts so an active plan matches. Assert the watchdog, on its own thread, own `Database.open()` connection, and own read-only PAPER toolbox/client, evaluates and submits one exact command that the independent authoritative writer executes before the provider is released.

- [ ] **Step 2: Write RED isolation tests.** Assert the service and watchdog SQLite connection objects differ, the watchdog broker client is read-only with a distinct client ID, and mutable toolbox/workspace objects are not shared. Assert only the authoritative writer owns the execution client ID and only its command interface plus stop/liveness signals cross execution contexts.

- [ ] **Step 3: Write RED lifecycle and health tests.** Persist `STARTED`, periodic `HEARTBEAT`, `FAILED`, `STOPPING`, and `STOPPED`. A missing/stale heartbeat blocks `NEW_EXPOSURE` and emits one deduplicated critical alert, but does not synthesize cancel/modify/retain. Recovery emits a state change and clears only the infrastructure block.

- [ ] **Step 4: Write RED shutdown tests.** Service shutdown asks the watchdog to stop, permits an in-progress reconciliation to reach a known state, and enforces a bounded infrastructure timeout. Timeout records continuity uncertainty and alerts without hanging shutdown or inventing an economic action.

- [ ] **Step 5: Run RED.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_continuity_watchdog.py tests\ibkr_paper_30d\test_autonomous_service.py`; expected: watchdog APIs/wiring are missing.

- [ ] **Step 6: Implement the watchdog loop.** Open its DB and read-only broker resources inside its own execution context. Polling cadence is infrastructure scheduling only and never activates authority; only the active plan condition does. On each pass, recover projections, collect one canonical snapshot, persist evaluation, and submit at most one exact selected command to the Task 7 writer.

- [ ] **Step 7: Integrate lifecycle with the service.** For both `run_once()` and `run_forever()`, start the watchdog before a provider invocation can block, verify health before allowing new exposure, and always stop it in `finally`. Keep normal model cycles and provider retry behavior intact.

- [ ] **Step 8: Run GREEN and commit.** Run the focused files; expected: zero failures including the deliberately blocked provider test. Commit with `feat(ibkr): run independent continuity watchdog`.

### Task 9: Build Factual Recovery Reports and Review Gating

**Files:**
- Create: `ibkr_paper_30d/continuity_reporting.py`
- Create: `tests/ibkr_paper_30d/test_continuity_reporting.py`
- Modify: `ibkr_paper_30d/autonomous_runtime.py`
- Modify: `ibkr_paper_30d/autonomy_bootstrap.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_runtime.py`
- Modify: `tests/ibkr_paper_30d/test_autonomy_bootstrap.py`

**Interfaces:**
- Consumes: provider outage interval, plan/evaluation/execution rows, broker/order/position/market observations, model expectations, accepted turn reviews, and reconciliation receipt.
- Produces: `ContinuityReportBuilder.build(outage_id) -> ContinuityReport`, `ContinuityReviewGate.classify(outcome, bundle) -> ContinuityAuthorityClass`, and `authorize(outcome, pending_reports, reconciliation) -> AuthorityDecision`.

- [ ] **Step 1: Write RED factual-report tests.** Require outage start/end/duration, failure codes, plan/evidence/action hashes, executed/blocked/uncertain results, order/execution/position state, expectations copied verbatim, arithmetic differences, and unresolved questions. Reject strategic labels such as good/bad/aggressive/conservative/rational/irrational generated by the observer.

- [ ] **Step 2: Write RED review-binding tests.** Every `CONTINUITY_REVIEW_V1` must bind exact report ID/hash and accepted invocation/result. Exercise `ACK_NO_METHOD_CHANGE`, `REFLECTION_RECORDED`, `POLICY_SUPERSEDED`, and `MORE_RESEARCH_REQUIRED`; reject stale or unknown reports and executable reflections without a later accepted plan.

- [ ] **Step 3: Write RED authority-class tests.** With a pending report, allow reconciliation, observation, cancellation, reduction, closing, pre-outage continuity, and any fresh Codex action that neither creates nor increases maximum experiment liability and does not extend temporal authority. Block new exposure, increased maximum liability, and extended temporal authority. Assert classification depends only on before/after liability and temporal-authority evidence, never labels such as defensive or prudent. `MORE_RESEARCH_REQUIRED` permits research but keeps authority expansion blocked.

- [ ] **Step 4: Write RED recovery-ordering tests.** A successful provider return receives the report before it can propose authority expansion. A review cannot release the block until fresh broker reconciliation passes and the review itself is durable. A mechanically nonexpanding action can execute before reflection without being characterized strategically.

- [ ] **Step 5: Run RED.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_continuity_reporting.py tests\ibkr_paper_30d\test_autonomous_runtime.py tests\ibkr_paper_30d\test_autonomy_bootstrap.py`; expected: reporting/gating APIs are missing.

- [ ] **Step 6: Implement reporting and gate integration.** Generate reports from append-only facts only. Include reports/reflections in bounded bootstrap/current context and mark reflections `UNTRUSTED_MODEL_AUTHORED`. Persist reviews before re-evaluating new-exposure authority.

- [ ] **Step 7: Run GREEN and commit.** Run the focused files; expected: zero failures. Commit with `feat(ibkr): require factual continuity review`.

### Task 10: Wire Launch, Restart Recovery, Alerts, and Kernel Authority

**Files:**
- Modify: `ibkr_paper_30d/day1_launch.py`
- Modify: `ibkr_paper_30d/kernel_manifest.py`
- Modify: `ibkr_paper_30d/alerts.py`
- Modify: `tests/ibkr_paper_30d/test_day1_launch.py`
- Modify: `tests/ibkr_paper_30d/test_kernel_manifest_closure.py`
- Modify: `tests/ibkr_paper_30d/test_alerts.py`
- Modify: `IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`

**Interfaces:**
- Consumes: explicit schema verifier, provider abandonment recovery, pending-binding reconciler, watchdog factory, broker-write coordinator, existing external Owner alert channels, runtime integrity gate, and process-level execution lock.
- Produces: fail-closed launch ordering and a kernel manifest that covers every continuity authority module.

- [ ] **Step 1: Write RED launch-order tests.** Before constructing the service, require schema V3 verification, current approved HEAD/runtime integrity, process-level execution lock, provider-state recovery, pending-binding reconciliation, and no unresolved continuity uncertainty. Assert all checks occur before starting the watchdog or invoking Codex.

- [ ] **Step 2: Write RED operational-boundary tests.** A missing V3 schema, stale watchdog, ambiguous pending binding, corrupt chain, or unresolved uncertain write blocks authority expansion with deterministic reason codes. Read-only reconciliation and mechanically nonexpanding authorized paths remain available. Tests perform zero real broker writes.

- [ ] **Step 3: Write RED critical-alert tests.** `CONTINUITY_ORDER_STATE_UNCERTAIN`, watchdog failure/staleness, identity ambiguity, and corrupt authority state use the existing durable Windows Event Log plus external Owner channel path and deduplicate unchanged repeated failures.

- [ ] **Step 4: Write RED kernel tests.** Require `continuity_schema.py`, `continuity_models.py`, `continuity_store.py`, `provider_lifecycle.py`, `continuity_evaluator.py`, `continuity_binding.py`, `broker_write_coordinator.py`, `authoritative_broker_writer.py`, `broker_writer_capability.py`, `continuity_executor.py`, `continuity_watchdog.py`, and `continuity_reporting.py` in the deterministic authority closure with non-empty roles and exact hashes.

- [ ] **Step 5: Run RED.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_day1_launch.py tests\ibkr_paper_30d\test_kernel_manifest_closure.py tests\ibkr_paper_30d\test_alerts.py`; expected: launch/kernel continuity wiring is missing.

- [ ] **Step 6: Implement launch wiring and restart recovery.** Extend `LaunchDependencies` with injected continuity factories for tests. Start one authoritative broker writer with the execution client ID, then the read-only watchdog, only after all recovery gates pass. Pass only the writer command interface to model and watchdog paths. Stop watchdog first and writer second before releasing the process-level lock. Do not add schema installation to launch.

- [ ] **Step 7: Regenerate the checked-in kernel manifest.** Use `python -m ibkr_paper_30d.kernel_manifest --repo-root . --output IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json` only after all new tracked authority files are staged so AST closure validation can resolve them.

- [ ] **Step 8: Run GREEN and commit.** Run the focused files; expected: zero failures. Commit with `feat(ibkr): wire continuity authority into launch`.

### Task 11: Complete the Fault Matrix and Full Regression

**Files:**
- Create: `tests/ibkr_paper_30d/test_continuity_fault_injection.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_architecture_contract.py`
- Modify: `tests/ibkr_paper_30d/test_remediation_invariants.py`
- Modify: `IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json` only if test-driven fixes change authority files.

**Interfaces:**
- Consumes: all Task 1-10 public interfaces.
- Produces: end-to-end evidence that the implementation matches the approved design without production deployment.

- [ ] **Step 1: Add the cross-module RED failure matrix.** Cover fill between evaluation/write, partial fill before/during modify, supersession while evaluator waits, model recovery concurrent with contingency, model completion immediately before final activation check, broker disconnect before/after write and before confirmation, duplicate evaluator, restart, conflicting broker identities, stale facts, missing broker time, and DB lock contention.

- [ ] **Step 2: Add architecture-source assertions.** Prove no adversarial-agent import/role, no global cancel, no cancel-and-replace, no direct research or watchdog broker write, no second write-capable client, no host strategic threshold/default, no strategic `DEFENSIVE_MODIFY` classification, no SQLite transaction spanning broker I/O, and no shared watchdog DB/read-only-broker/toolbox object.

- [ ] **Step 3: Run the complete continuity suite.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d -k "continuity or provider_lifecycle"`; expected: zero failures and no real broker connection/write.

- [ ] **Step 4: Run focused affected regressions.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_autonomous_research.py tests\ibkr_paper_30d\test_autonomous_runtime.py tests\ibkr_paper_30d\test_autonomous_execution.py tests\ibkr_paper_30d\test_open_order_management.py tests\ibkr_paper_30d\test_autonomous_service.py tests\ibkr_paper_30d\test_autonomy_bootstrap.py tests\ibkr_paper_30d\test_day1_launch.py tests\ibkr_paper_30d\test_kernel_manifest_closure.py`; expected: zero failures.

- [ ] **Step 5: Run the full experiment suite.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d`; expected: zero failures.

- [ ] **Step 6: Verify kernel, provenance, PowerShell, and diff integrity.** Run the checked-in kernel-manifest verification test and the repository's runtime-provenance tests. Parse `FINALIZE_IBKR_PREREQUISITES.ps1`, `RUN_IBKR_DAY1_SERVICE.ps1`, and `RUN_IBKR_MARKET_DATA_GATE.ps1` with `[System.Management.Automation.Language.Parser]::ParseFile`; expected: 3/3 with zero parse errors. Run `git diff --check`; expected: no output.

- [ ] **Step 7: Prove production remained untouched.** From the isolated worktree, compare final read-only evidence to the pre-implementation snapshot: no continuity V3 schema/table was installed in the production database, operational checkout HEAD/tracked files were not changed by implementation, scheduler state/arguments/`ApprovedHead` are unchanged, no launch occurred, and `REAL_BROKER_WRITE_CALLS=0` for this implementation phase.

- [ ] **Step 8: Commit the final test closure.** Commit only tracked implementation/test/manifest files with `test(ibkr): close continuity authority fault matrix`.

## Implementation Completion Report

After Task 11, return an `AGENT_CONTINUITY_AUTHORITY_IMPLEMENTATION_REPORT` containing exact final worktree HEAD, commits, focused/full test counts, kernel/provenance/PowerShell/diff results, single-writer ownership proof, blocked-provider watchdog/writer proof, crash-binding recovery proof, `REAL_BROKER_WRITE_CALLS`, operational-checkout HEAD comparison, production schema/deployment/scheduler status, and remaining deployment/capability-probe decision. The expected operational state remains `NOT_DEPLOYED` and the scheduler remains unchanged until separate Owner authorization.
