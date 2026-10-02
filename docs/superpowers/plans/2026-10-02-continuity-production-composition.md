# Continuity V3 Production Composition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the dormant Continuity V3 implementation so the default Day1 runtime has one concrete production composition, one write-capable PAPER session for every model and continuity action, enforceable model-authored liability bounds, and fail-closed production authority checks.

**Architecture:** Normal Codex decisions and continuity decisions become immutable discriminated requests on one `BrokerWriteCoordinator`. One `AuthoritativeBrokerWriter` thread owns the only write-capable broker connection and dispatches both request types. A separate read-only watchdog observes state and may submit only exact model-authored continuity commands. A production composition root wires all factories, authority checks, persistence, and critical alerts without choosing any economic action.

**Tech Stack:** Python 3.11, Pydantic v2, SQLite WAL, `ib_insync`, pytest, Windows execution lock, PowerShell AST validation.

**Spec:** `docs/superpowers/specs/2026-10-02-continuity-production-composition-design.md`

## Global Constraints

- Work only in `C:\AI_VAULT_IBKR_CONTINUITY_DEV` on `codex/agent-continuity-authority` during this plan.
- Do not modify `C:\AI_VAULT_IBKR`, production SQLite files, reports, scheduler state, `ApprovedHead`, IBKR orders, positions, or runtime installation.
- PAPER only. `LIVE_ALLOWED=false`, `REAL_MONEY_ALLOWED=false`, and real broker writes during implementation equal zero.
- Codex remains the sole economic decision maker. No host-authored retain, cancel, reprice, timing, instrument, strategy, or unavailable-data rule may be introduced.
- Every write path, including normal Codex trading, must use one typed coordinator and one writer-owned execution client. No production fallback may instantiate `AutonomousPaperExecutor` as a direct writer.
- The watchdog must use a separate database connection and read-only client ID `19762`; it never calls model execution or broker write methods.
- No SQLite write transaction may span broker network I/O.
- Liability checks must use instrument-aware, fresh broker evidence. Do not substitute an unproven `quantity * limit_price` calculation.
- No global cancel, cancel-and-replace, arbitrary broker method names, callables, shell text, or executable source may enter a queued command.
- Preserve existing serialized schemas and defer the Pydantic `schema` warning cleanup.
- Each task follows RED -> GREEN -> focused regression -> commit. Stop on a baseline failure, an unexplained production-state change, or evidence of a real broker write.

## Review Focus

- A normal model request can accidentally create a second execution connection: Tasks 2-4 prove that all three model operation types execute on the writer thread and injected writer-owned broker session.
- Liability evidence can be absent, stale, unbounded, incomplete for BAG legs, or invalidated by a DB race: Tasks 1 and 5 block every case before transmission.
- A partial startup can leave a live worker or authority ambiguous: Tasks 6 and 7 inject failure at each construction/start boundary and verify reverse-order shutdown.
- A provider timeout can leave the main caller blocked while continuity needs the writer: Tasks 2, 4, and 7 block the model caller and prove watchdog/writer progress.
- A validation or fallback path can silently select legacy direct writes: Tasks 3, 6, and 7 use architecture scans and write spies to prove the production graph is coordinator-only and zero-write in validation mode.

---

### Pre-Implementation Gate: Freeze the Baseline

**Files:**
- Verify only: `C:\AI_VAULT_IBKR`
- Work only: `C:\AI_VAULT_IBKR_CONTINUITY_DEV`
- Read: `C:\AI_VAULT_IBKR_CONTINUITY_EXTERNAL_AUDIT_GLM.md`

**Interfaces:**
- Consumes: approved design commit `ecdca2794d4d06c6c43476cfcc6785091542af1b` and dormant Continuity V3 implementation.
- Produces: a captured baseline proving implementation isolation and zero production side effects.

- [ ] **Step 1: Verify implementation workspace.** Assert the worktree root, branch, clean status, and HEAD. Record the merge base with operational `d1fc6d694b0326bb71c155b826ffec6fadd9712c`.
- [ ] **Step 2: Capture operational evidence read-only.** Record canonical HEAD, disabled scheduler state and action arguments, absence of a Day1 process, production V3 schema absence, execution-lock state, and PAPER open-order/position/execution counts. Do not repair or normalize anything.
- [ ] **Step 3: Run the baseline suite.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d`; expected: zero failures. Preserve skip reasons.
- [ ] **Step 4: Verify integrity gates.** Run the existing kernel-closure, runtime-provenance, PowerShell AST 3/3, forbidden LIVE-path, and `git diff --check` checks. Stop if the existing baseline fails.

---

### Task 1: Bind and Enforce Maximum Authorized Liability

**Files:**
- Create: `ibkr_paper_30d/continuity_liability.py`
- Create: `tests/ibkr_paper_30d/test_continuity_liability.py`
- Modify: `ibkr_paper_30d/continuity_models.py`
- Modify: `ibkr_paper_30d/continuity_binding.py`
- Modify: `ibkr_paper_30d/continuity_executor.py`
- Modify: `ibkr_paper_30d/broker_write_coordinator.py`
- Modify: `tests/ibkr_paper_30d/test_continuity_models.py`
- Modify: `tests/ibkr_paper_30d/test_continuity_binding.py`
- Modify: `tests/ibkr_paper_30d/test_continuity_executor.py`

**Interfaces:**
- Add immutable `MaximumLiabilityRequirement` and `MaximumLiabilityEvidence` Pydantic models.
- Extend `AuthorizedBrokerCommand` with plan bound, resolved order economics, exact contract/order hash, account/epoch binding, and liability-evidence requirements.
- Add `validate_resolved_liability_authority(...) -> LiabilityValidationResult` without broker I/O.

- [ ] **Step 1: Write RED plan-validation tests.** Add cases for a literal branch provably above `maximum_authorized_liability`, a literal branch within it, a dynamic fact expression that remains structurally valid, non-finite bounds, and a command that omits or raises the model-authored bound.
- [ ] **Step 2: Write RED evidence tests.** Cover fresh bounded single-instrument and BAG evidence, missing legs, stale collection time, wrong account/contract/command hash, unbounded maximum loss, unsupported instruments, liability above the plan bound, and liability above the experiment capital boundary.
- [ ] **Step 3: Run RED.** Run the five focused continuity test files; expected: failures because the liability models and command fields do not exist.
- [ ] **Step 4: Implement strict models.** Define evidence with source, collection timestamp, freshness deadline, PAPER account hash, contract hash, proposed-order hash, command hash, bounded/unbounded status, maximum loss, currency, and broker evidence hash. Reject partial or internally inconsistent evidence.
- [ ] **Step 5: Bind the resolved branch.** Carry the unchanged plan bound, plan hash, resolved quantity/price/TIF, contract identity, and evidence requirement into the command. Ensure command hashing includes every authority-bearing liability field.
- [ ] **Step 6: Add structural validation only.** Reject provable literal violations at plan/binding time, but do not invent an instrument formula or reject a valid dynamic expression merely because it requires fresh facts.
- [ ] **Step 7: Run GREEN and focused regression.** Run the focused test files plus `test_continuity_evaluator.py` and `test_continuity_store.py`; expected: zero failures.
- [ ] **Step 8: Commit.** Commit only Task 1 files with `feat(ibkr): bind continuity liability authority`.

### Task 2: Add the Typed Coordinated Model Request Path

**Files:**
- Create: `ibkr_paper_30d/coordinated_model_executor.py`
- Create: `tests/ibkr_paper_30d/test_coordinated_model_executor.py`
- Modify: `ibkr_paper_30d/broker_write_coordinator.py`
- Modify: `tests/ibkr_paper_30d/test_broker_writer_capability.py`

**Interfaces:**
- Define `ModelExecutionOperation = {NEW_TRADE, OPEN_ORDER_ACTION, POSITION_ACTION}`.
- Define immutable `ModelExecutionRequest` with request/execution IDs, sequence, launch/epoch/head/account/invocation binding, accepted typed payload, input bundle, optional continuity binding, and payload hashes.
- Implement `CoordinatedModelExecutor.execute(...)`, `.execute_open_order_action(...)`, and `.execute_position_action(...)` returning existing `PaperExecutionResult` values.

- [ ] **Step 1: Write RED request-schema tests.** Reject arbitrary broker method names, callables, source/shell text, missing accepted-decision binding, mutable payloads, hash mismatches, and wrong source. Verify all three operations serialize and hash deterministically.
- [ ] **Step 2: Write RED proxy tests.** Assert each public executor method emits exactly one typed request to the shared coordinator, waits with a bounded infrastructure timeout, returns the writer result, and performs no broker calls.
- [ ] **Step 3: Write RED concurrency tests.** Block a model caller waiting for a result, enqueue a continuity command, and prove the queue/writer can progress independently. Verify duplicate execution keys return the original result and do not enqueue twice.
- [ ] **Step 4: Run RED.** Run `test_coordinated_model_executor.py` and `test_broker_writer_capability.py`; expected: import/schema failures.
- [ ] **Step 5: Implement the discriminated queue union.** Preserve one consumer capability, durable monotonic sequence checks, execution-key idempotency, readiness, bounded waits, uncertainty results, and shutdown behavior for both request types.
- [ ] **Step 6: Implement the proxy.** Make `armed` explicit and true only after production factory validation. The proxy must not import `ib_insync`, open sockets, or expose the coordinator capability.
- [ ] **Step 7: Run GREEN and focused regression.** Include existing coordinator, continuity executor, and fault-injection tests; expected: zero failures.
- [ ] **Step 8: Commit.** Commit with `feat(ibkr): coordinate normal model execution`.

### Task 3: Extract a Writer-Owned Model Execution Engine

**Files:**
- Create: `ibkr_paper_30d/model_execution_engine.py`
- Create: `tests/ibkr_paper_30d/test_model_execution_engine.py`
- Modify: `ibkr_paper_30d/autonomous_execution.py`
- Modify: `ibkr_paper_30d/autonomous_service.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_execution.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_service.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_architecture_contract.py`

**Interfaces:**
- Extract `ModelExecutionEngine.execute(broker, request, authority_context) -> PaperExecutionResult`.
- Keep `AutonomousPaperExecutor` only as an explicit non-production adapter around the engine.
- Require a `CoordinatedModelExecutor`-compatible injected executor whenever `AutonomousExperimentService(execute_paper=True)` is constructed.

- [ ] **Step 1: Write RED parity tests.** For new trades, open-order actions, and position actions, assert the extracted engine preserves proposal validation, what-if, market evidence, ownership, registry, reconciliation, and result semantics using an injected fake broker.
- [ ] **Step 2: Write RED ownership tests.** Assert the engine never calls connect/disconnect and uses the exact injected broker object and current writer thread.
- [ ] **Step 3: Write RED service tests.** `execute_paper=True` must reject a missing executor, direct `AutonomousPaperExecutor`, and any unarmed or non-coordinated executor. Observation-only mode remains available without write authority.
- [ ] **Step 4: Write RED architecture tests.** Scan production imports/factories and fail if they reference the direct adapter, `_connect_execution`, or a second write-capable client ID. Preserve allowed test/observation-only references explicitly.
- [ ] **Step 5: Run RED.** Run the four focused files; expected: failures on missing engine and permissive service fallback.
- [ ] **Step 6: Extract without strategy changes.** Move broker-dependent mechanics behind the engine interface; do not alter accepted proposal/action fields, pricing, candidate choice, risk appetite, or current reconciliation behavior.
- [ ] **Step 7: Harden service construction.** Remove production fallback selection while keeping narrowly labeled test adapters usable only through explicit injection.
- [ ] **Step 8: Run GREEN and focused regression.** Include open-order management, broker feasibility, capital-boundary, and order-identity tests; expected: zero failures.
- [ ] **Step 9: Commit.** Commit with `refactor(ibkr): isolate writer-owned model engine`.

### Task 4: Dispatch Every Broker Write Through the Authoritative Writer

**Files:**
- Modify: `ibkr_paper_30d/authoritative_broker_writer.py`
- Modify: `ibkr_paper_30d/broker_write_coordinator.py`
- Modify: `ibkr_paper_30d/model_execution_engine.py`
- Modify: `tests/ibkr_paper_30d/test_authoritative_broker_writer.py`
- Modify: `tests/ibkr_paper_30d/test_continuity_fault_injection.py`

**Interfaces:**
- Extend the writer dispatch union to `AuthorizedBrokerCommand | ModelExecutionRequest`.
- Inject one `ModelExecutionEngine` and one already-connected writer-owned broker session.
- Preserve a single `BrokerWriterCapability` and client ID for the lifetime of the writer.

- [ ] **Step 1: Write RED dispatch tests.** Prove all three model operations and RETAIN/CANCEL/MODIFY continuity commands are handled on one writer thread and one broker object, with FIFO sequencing and shared idempotency.
- [ ] **Step 2: Write RED exclusivity tests.** Starting a second writer capability, changing client ID, reconnecting through the model engine, or dispatching an unknown request type must fail closed before a broker write.
- [ ] **Step 3: Write RED outage test.** Hold the model caller after request submission while the writer processes an already-authorized continuity command; prove no starvation and no parallel broker writer.
- [ ] **Step 4: Write RED uncertainty tests.** Inject disconnect before send, acknowledgement loss after send, worker crash, and shutdown with queued work. Require durable uncertainty and freeze; never retry a possibly transmitted write blindly.
- [ ] **Step 5: Run RED.** Run writer/coordinator/fault-injection files; expected: model requests are not yet dispatchable.
- [ ] **Step 6: Implement typed dispatch.** Keep broker connection ownership entirely in `AuthoritativeBrokerWriter`; pass the connected object into the engine; centralize result publication and terminal command state.
- [ ] **Step 7: Prohibit broad cancellation.** Add code and architecture assertions that neither dispatch branch calls global cancel or implements cancel-and-replace.
- [ ] **Step 8: Run GREEN and focused regression.** Include autonomous execution/service and continuity executor tests; expected: zero failures.
- [ ] **Step 9: Commit.** Commit with `feat(ibkr): unify model and continuity broker writes`.

### Task 5: Implement Fresh Production Authority and Liability Gates

**Files:**
- Create: `ibkr_paper_30d/production_authority.py`
- Create: `tests/ibkr_paper_30d/test_production_authority.py`
- Modify: `ibkr_paper_30d/authoritative_broker_writer.py`
- Modify: `ibkr_paper_30d/continuity_liability.py`
- Modify: `ibkr_paper_30d/continuity_store.py`
- Modify: `tests/ibkr_paper_30d/test_authoritative_broker_writer.py`

**Interfaces:**
- Define `ProductionAuthoritySnapshot`, `ProductionBrokerEvidence`, and `ProductionAuthorityValidator.validate_before_write(...)`.
- Inject exact readers for lock, head/provenance, PAPER identity, authorization/clock, kill switch, auditor/market gates, schema/chains, plan/binding/provider/review/order state, and experiment capital boundary.
- Collect final instrument-aware liability evidence for the exact proposed order.

- [ ] **Step 1: Write RED gate-matrix tests.** Parameterize every mutable authority: lock owner, approved HEAD, provenance, PAPER account, authorization, clock, kill switch, Auditor V2, market gate, V3 schema/chains, plan supersession/hash, binding/order identity, provider state, accepted decision, review gate, one-shot count, execution key, positions, executions, and all-order visibility.
- [ ] **Step 2: Write RED temporal-order tests.** Assert broker evidence is collected outside transactions; DB authority is read; final what-if/broker evidence is collected outside transactions; DB authority is reread; attempt is persisted in a short transaction; one broker write occurs; acknowledgement/result is persisted in a new transaction.
- [ ] **Step 3: Write RED race tests.** Mutate the plan, binding, review, lock, kill switch, order state, fill state, or capital boundary after evidence collection but before the final DB reread. Every mutation must block with a deterministic reason code and zero writes.
- [ ] **Step 4: Write RED liability tests.** Exercise exact BAG what-if maximum loss at, below, and above the plan bound; stale/missing/unbounded/wrong-hash evidence; and capital-boundary conflicts. Verify a formula is accepted only when its instrument validator proves it exact.
- [ ] **Step 5: Run RED.** Run production-authority, liability, writer, and fault-injection tests; expected: missing production validator and ordering failures.
- [ ] **Step 6: Implement the fail-closed validator.** Use typed readers and evidence, not narrative fields. Return structured reason codes and hashes. Do not hold a SQLite write transaction across any broker call.
- [ ] **Step 7: Integrate the writer sequence.** Persist immutable attempts before the write and results after reconciliation, with separate short transactions and exact command/evidence hashes.
- [ ] **Step 8: Run GREEN and focused regression.** Include execution lock, runtime provenance, owner authorization, successor clock, market policy, auditor gate, provider lifecycle, and order identity tests.
- [ ] **Step 9: Commit.** Commit with `feat(ibkr): enforce fresh production write authority`.

### Task 6: Build the Production Watchdog, Alerts, and Composition Root

**Files:**
- Create: `ibkr_paper_30d/production_continuity_runtime.py`
- Create: `tests/ibkr_paper_30d/test_production_continuity_runtime.py`
- Modify: `ibkr_paper_30d/continuity_watchdog.py`
- Modify: `ibkr_paper_30d/alerts.py`
- Modify: `ibkr_paper_30d/day1_launch.py`
- Modify: `tests/ibkr_paper_30d/test_continuity_watchdog.py`
- Modify: `tests/ibkr_paper_30d/test_alerts.py`
- Modify: `tests/ibkr_paper_30d/test_day1_launch.py`

**Interfaces:**
- Export concrete factories consumed by `day1_launch._default_dependencies()`.
- Compose one coordinator, proxy, reporter, store, authority validator, writer, and watchdog.
- Build the watchdog DB connection inside its thread and read-only PAPER observer session with client ID `19762`.

- [ ] **Step 1: Write RED default-factory tests.** Assert every production factory is concrete, importable, and constructs typed dependencies instead of returning `None`; missing runtime configuration fails with a deterministic configuration reason, not `CONTINUITY_RUNTIME_FACTORY_UNAVAILABLE`.
- [ ] **Step 2: Write RED watchdog tests.** Verify separate thread-local DB, observer client ID `19762`, read-only configuration, authenticated PAPER time, canonical facts, at-most-one exact continuity submission, and no model-engine or broker-write access.
- [ ] **Step 3: Write RED alert tests.** For writer startup/shutdown failure, result uncertainty, watchdog heartbeat failure, identity ambiguity, corrupt chain, broker uncertainty, and lock ambiguity: freeze new-order authority first, persist once, write Windows Event Log, send SMTP, and deduplicate unchanged repeats. Alert failure must not authorize a write.
- [ ] **Step 4: Write RED startup rollback tests.** Fail after each construction/start step. Assert watchdog stops before writer, both threads terminate, uncertainty/freeze is durable, and the lock is released only after known shutdown.
- [ ] **Step 5: Run RED.** Run production runtime, watchdog, alerts, and Day1 launch tests; expected: factories remain absent.
- [ ] **Step 6: Implement the composition root.** Keep it free of strategy, proposal selection, and continuity-plan invention. Inject verified configuration and preflight material only.
- [ ] **Step 7: Wire default dependencies.** Replace `None` factories with imports from the composition root while preserving fail-closed configuration validation.
- [ ] **Step 8: Run GREEN and focused regression.** Include continuity reporting/store/schema and existing launch fault-injection tests.
- [ ] **Step 9: Commit.** Commit with `feat(ibkr): compose continuity v3 production runtime`.

### Task 7: Add Authority-Visible Provider Timeout and Zero-Write Validation Mode

**Files:**
- Modify: `ibkr_paper_30d/day1_launch.py`
- Modify: `ibkr_paper_30d/epoch_manifest.py`
- Modify: `ibkr_paper_30d/autonomous_runtime.py`
- Modify: `ibkr_paper_30d/production_continuity_runtime.py`
- Modify: `tests/ibkr_paper_30d/test_day1_launch.py`
- Modify: `tests/ibkr_paper_30d/test_epoch_manifest.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_codex_provider.py`
- Modify: `tests/ibkr_paper_30d/test_production_continuity_runtime.py`

**Interfaces:**
- Add bounded positive `Day1LaunchConfig.model_turn_timeout_seconds` and bind its exact value into the epoch manifest.
- Add a production-composition `validate_only` path that constructs and verifies fake boundaries without arming or submitting orders.

- [ ] **Step 1: Write RED timeout tests.** Reject missing, non-finite, zero, negative, and out-of-policy values; prove the provider deadline and manifest hash change together; reject launch if plan authority references a different deadline.
- [ ] **Step 2: Write RED validation-mode tests.** Spy on every broker write method and assert zero calls while checking concrete factories, coordinated proxy, distinct client IDs, read-only watchdog, sole capability ownership, callable fail-closed gates, and complete shutdown.
- [ ] **Step 3: Write RED fallback tests.** Force missing/invalid config, schema absence, alert config failure, and partial component construction. Validation must report exact blockers and never fall back to the direct executor.
- [ ] **Step 4: Run RED.** Run the four focused files; expected: missing config/manifest field and validation mode.
- [ ] **Step 5: Implement timeout binding.** Remove the magic process-timeout constant from production use; keep one configuration value throughout launch, manifest, provider invocation, and continuity facts.
- [ ] **Step 6: Implement validation mode.** Use fake/no-write broker boundaries and real production composition code. Do not weaken gates simply to let validation pass.
- [ ] **Step 7: Run GREEN and architecture regression.** Run launch, provider, epoch, production runtime, architecture-contract, writer, and service tests.
- [ ] **Step 8: Commit.** Commit with `feat(ibkr): validate production continuity composition`.

### Task 8: Close Regression, Integrity, and Audit Evidence

**Files:**
- Modify: `IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`
- Create: `docs/audits/CONTINUITY_V3_PRODUCTION_COMPOSITION_IMPLEMENTATION_REPORT.md`
- Modify tests only if a genuine regression is discovered; do not widen scope.

**Interfaces:**
- Produces one immutable implementation HEAD for differential external audit.
- Produces no production installation, authorization, scheduler, or broker side effect.

- [ ] **Step 1: Run focused acceptance suites.** Run all new tests plus autonomous execution/service, broker writer/capability, continuity, Day1 launch, alerts, execution lock, runtime provenance, owner authorization, clock, market, auditor, and order-identity files. Expected: zero failures.
- [ ] **Step 2: Run full regression.** Run `python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d`; expected: zero failures with documented platform skips only.
- [ ] **Step 3: Regenerate and verify the kernel manifest.** Use the repository's existing manifest command, inspect the diff, and run kernel closure plus runtime provenance checks.
- [ ] **Step 4: Run static/integrity checks.** Require PowerShell AST 3/3, `git diff --check`, secret scan, forbidden LIVE-path scan, no production import of the direct executor, no global cancel, and no second write-capable connection.
- [ ] **Step 5: Recheck operational non-interference.** Read-only verify canonical HEAD and scheduler unchanged, Day1 process count zero, production V3 schema still absent, broker writes zero, and PAPER open orders/positions/executions unchanged from the baseline.
- [ ] **Step 6: Write the implementation report.** Record commit sequence, exact tests/counts/skips, integrity hashes, known residual risks, `RUNTIME_INSTALLED=false`, `SCHEDULER_ENABLED=false`, `REAL_BROKER_WRITES=0`, and the exact candidate audit SHA.
- [ ] **Step 7: Commit final evidence.** Commit manifest/report with `docs(ibkr): record continuity v3 composition evidence`.
- [ ] **Step 8: Bind the external audit target.** Record final `git rev-parse HEAD`, require a clean worktree and `git diff --check`, and stop. Do not deploy under this plan.

## Completion Report

Return exactly:

```text
CONTINUITY_V3_PRODUCTION_COMPOSITION_REPORT

BASE_HEAD:
FINAL_IMPLEMENTATION_HEAD:
BRANCH:
COMMITS:
FOCUSED_TESTS:
FULL_TESTS:
KERNEL_CLOSURE:
RUNTIME_PROVENANCE:
POWERSHELL_AST:
GIT_DIFF_CHECK:
DEFAULT_FACTORIES_CONCRETE:
MODEL_PATH_COORDINATED:
SOLE_WRITE_CAPABLE_SESSION:
LIABILITY_BOUND_ENFORCED:
VALIDATION_MODE_ZERO_WRITES:
EXTERNAL_AUDIT_REQUIRED: true
RUNTIME_INSTALLED: false
SCHEMA_V3_INSTALLED_IN_PRODUCTION: false
SCHEDULER_ENABLED: false
REAL_BROKER_WRITES: 0
DAY1_READY: false
NEXT_OWNER_DECISION_REQUIRED: true
```

