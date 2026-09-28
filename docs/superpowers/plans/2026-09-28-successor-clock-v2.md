# Successor Epoch and Clock V2 Implementation Plan

> Execute in `C:\AI_VAULT_IBKR_REMEDIATION` on branch
> `codex/successor-clock-architecture`. The production database, production
> V2 schema, production successor state, scheduler state, and broker order
> state must remain untouched until final read-only verification.

**Spec:**
`docs/superpowers/specs/2026-09-28-successor-clock-architecture-design.md`

**Canonical base:** `81fd236403632b2e2de4e9ebb86e14e02024770f`

**Goal:** Implement general append-only successor epoch and epoch-scoped clock
semantics, late-bind every fresh 30-day clock to authenticated PAPER broker
time during the locked launch, and integrate the verified code while leaving
production frozen for external audit.

**Architecture:** V1 remains immutable. An explicit schema installer creates
purpose-specific V2 clock and Owner-authorization tables. Successor definitions
and transitions use the existing hash-chained state-event log. A graph verifier
resolves the sole terminal epoch. The Day1 launcher binds one explicit target,
revalidates eligibility and Owner authority inside an immediate transaction,
then atomically appends clock start, predecessor supersession, and successor
activation.

**Tech stack:** Python 3.11, SQLite WAL, pytest, Pydantic, Windows PowerShell
5.1/7, Git.

---

## Global Constraints

- No production `Database.open()` call during development or final checks.
- No production schema installation or successor control event.
- No scheduler enablement, Day1 launch, Codex invocation, or broker write.
- No generic `AutonomyToolbox.__getattr__` or private broker-surface expansion.
- Every task follows RED -> GREEN -> focused regression -> commit.
- Use only deterministic reason codes in persisted failure evidence.
- The final canonical integration is fast-forward only.

## File Map

- Create `ibkr_paper_30d/successor_schema.py`: explicit V2 DDL installer and
  verifier; no implicit migration.
- Create `ibkr_paper_30d/successor_clock.py`: epoch-scoped clock store,
  historical V1 adapter, broker-time validation, exact duration enforcement.
- Create `ibkr_paper_30d/successor_authorization.py`: V2 Owner authorization
  and receipt validation bound to a successor definition.
- Create `ibkr_paper_30d/successor_epoch.py`: successor definition,
  eligibility, graph validation, and atomic transition.
- Modify `ibkr_paper_30d/experiment_control.py`: explicit `clock_for_epoch()`
  authority routing and ambiguous `load()` rejection.
- Modify `ibkr_paper_30d/experiment_epoch.py`: V1/V2 event parsing and
  graph-based `current()`/projection delegation.
- Modify `ibkr_paper_30d/prerequisite_tools.py`: explicit target successor in
  launch-attempt bindings.
- Modify `ibkr_paper_30d/day1_launch.py`: target binding, late clock start,
  transactional transition, dynamic service clock, and pre-start failure event.
- Modify `ibkr_paper_30d/epoch_manifest.py`: dynamic epoch, definition, and
  clock bindings.
- Modify `ibkr_paper_30d/autonomy_bootstrap.py`: require and propagate the
  successor epoch ID, definition SHA-256, and clock-event SHA-256 in the
  first-process context.
- Modify `ibkr_paper_30d/autonomous_service.py`: accept/use the explicitly
  resolved epoch clock without changing the narrow broker-time capability.
- Regenerate `IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json` after authority edits.
- Create focused V2 tests listed in the tasks below.

## Shared Interfaces

```python
install_successor_schema_v2(db: Database) -> dict[str, object]
verify_successor_schema_v2(db: Database) -> dict[str, object]

@dataclass(frozen=True)
class BrokerTimeObservation:
    server_time_utc: datetime
    observed_at_utc: datetime
    authenticated: bool
    paper_session: bool
    preceding_server_time_utc: datetime | None

validate_broker_time_observation(
    observation: BrokerTimeObservation,
    *,
    max_age_seconds: float = 30.0,
    max_future_skew_seconds: float = 5.0,
    backward_tolerance_seconds: float = 2.0,
) -> datetime

clock_for_epoch(db: Database, epoch_id: str) -> ExperimentClock

create_successor_definition(
    db: Database,
    *,
    target_successor_epoch_id: str,
    predecessor_epoch_id: str,
    supersession_reason: str,
    approved_git_head: str,
    duration_days: int,
    initial_allocation: Decimal,
    objective_sha256: str,
    configuration_sha256: str,
) -> dict[str, object]

create_successor_owner_authorization(...definition binding...) -> dict[str, object]
validate_successor_owner_authorization(...exact target...) -> dict[str, object]

commit_successor_transition(
    db: Database,
    *,
    target_successor_epoch_id: str,
    target_successor_definition_sha256: str,
    owner_authorization_receipt: dict[str, object],
    broker_time_observation: BrokerTimeObservation,
    fresh_broker_evidence: SuccessorBrokerEvidence,
    approved_git_head: str,
) -> SuccessorTransitionResult
```

The implementation may refine parameter grouping with frozen dataclasses, but
must preserve the explicit target ID/hash, fresh broker observation, and
transactional revalidation boundaries.

---

## Task 1: Add Explicit, Idempotent V2 Schema Installation

**Files:**
- Create: `ibkr_paper_30d/successor_schema.py`
- Create: `tests/ibkr_paper_30d/test_successor_schema_v2.py`
- Modify: `tests/ibkr_paper_30d/test_persistence.py`

1. Write tests proving `Database.open()` on a production-shaped V1 database
   leaves `schema_versions=[1]` and creates neither V2 table (case AC).
2. Write RED tests for exact V2 table columns, unique constraints, indexes,
   schema version 2, and immutable UPDATE/DELETE triggers.
3. Add RED tests for installer integrity failure, malformed partial schema,
   and repeated installation with no epoch/clock/auth/state row changes (AB).
4. Implement `install_successor_schema_v2()` as one explicit immediate
   transaction and `verify_successor_schema_v2()` as read-only verification.
5. Ensure `Database.open()` and `persistence.SCHEMA` remain V1-only.
6. Run:

   ```powershell
   python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_successor_schema_v2.py tests\ibkr_paper_30d\test_persistence.py
   ```

   Expected: zero failures; installation twice produces one schema-version-2
   row and zero control-state rows.
7. Commit: `feat(ibkr): add explicit successor schema v2 installer`.

## Task 2: Implement Epoch-Scoped Clocks and Broker-Time Authority

**Files:**
- Create: `ibkr_paper_30d/successor_clock.py`
- Create: `tests/ibkr_paper_30d/test_successor_clock_v2.py`
- Modify: `ibkr_paper_30d/experiment_control.py`
- Modify: `tests/ibkr_paper_30d/test_owner_authorization.py`

1. Add RED tests for `clock_for_epoch()` reading the unchanged September 23
   V1 clock through its V1 epoch definition (K, L).
2. Add RED tests creating a V2 clock from a fresh UTC broker timestamp and
   proving exact `end-start == 30 days` (M, N).
3. Add RED tests for stale, future-skewed, malformed/naive, unauthenticated,
   non-PAPER, and backward-moving broker observations (Y, Z, AA).
4. Add RED tests proving deployment/audit/scheduler helper calls and repeated
   validation create no clock rows (O, P, Q, R).
5. Implement canonical V2 clock payload/hash chaining and the unique one-start
   per epoch insertion.
6. Implement broker-time constants: maximum age 30 seconds, maximum future
   skew 5 seconds, and backward tolerance 2 seconds. Never use host time as the
   start value; use it only to prove freshness of broker time.
7. Keep V1 `load()` for legacy-only callers, but raise
   `EXPERIMENT_CLOCK_EPOCH_REQUIRED` when V2 rows make it ambiguous.
8. Run:

   ```powershell
   python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_successor_clock_v2.py tests\ibkr_paper_30d\test_owner_authorization.py
   ```

   Expected: zero failures; no clock exists until the explicit start method.
9. Commit: `feat(ibkr): add epoch scoped successor clocks`.

## Task 3: Define Successors and Verify the Epoch Graph

**Files:**
- Create: `ibkr_paper_30d/successor_epoch.py`
- Create: `tests/ibkr_paper_30d/test_successor_epoch_graph.py`
- Modify: `ibkr_paper_30d/experiment_epoch.py`
- Modify: `tests/ibkr_paper_30d/test_experiment_epoch.py`

1. Create a production-shaped fixture with internally valid state sequences
   536-539, V1 definition/activation/launch/manifest, no `EPOCH_STARTED`, and
   the September 23 V1 clock.
2. Snapshot every authoritative V1 row as raw tuples/bytes before V2 fixture
   operations.
3. Add RED tests for eligibility of the observed incident (A), plus blocks for
   `EPOCH_STARTED`, attributed/global PAPER positions, open orders, broker
   writes, and post-baseline runtime activity (B-E).
4. Add RED tests proving a V2 definition binds predecessor definition,
   activation event/receipt, clock, manifest, reason, approved HEAD, and full
   history commitment (F).
5. Add RED graph tests for one terminal successor, two independent active
   epochs, broken predecessor hashes, insertion-order traps, branches, missing
   edges, and repeated explicit successor chaining (G-J, T).
6. Implement V1/V2 graph reconstruction. `ExperimentEpochStore.current()`
   must return only the terminal node reached from the verified root.
7. Keep successor definition creation clock-free and current-epoch neutral.
8. Prove all snapshotted V1 rows and hashes remain byte-identical (U).
9. Run:

   ```powershell
   python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_successor_epoch_graph.py tests\ibkr_paper_30d\test_experiment_epoch.py
   ```

   Expected: zero failures; unchained or post-start succession blocks.
10. Commit: `feat(ibkr): verify append only successor epoch graphs`.

## Task 4: Add Successor Owner Authorization V2

**Files:**
- Create: `ibkr_paper_30d/successor_authorization.py`
- Create: `tests/ibkr_paper_30d/test_successor_authorization_v2.py`
- Modify: `ibkr_paper_30d/owner_authorization.py`

1. Add RED tests requiring elevation, exact phrase, Owner SID, target epoch,
   definition SHA, predecessor, approved HEAD, duration, allocation, reason,
   and late-bound start policy.
2. Add RED tests rejecting V1 authorization reuse, another epoch's receipt,
   modified definition/head, revoked latest state, malformed hashes, and raw
   account/credential fields.
3. Add RED tests proving authorization creation does not create a clock,
   supersession, activation, or `EPOCH_STARTED` (AF).
4. Implement append-only V2 authorization rows and atomic canonical receipt
   writes. Validation must be read-only and idempotent.
5. Run:

   ```powershell
   python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_successor_authorization_v2.py tests\ibkr_paper_30d\test_owner_authorization.py
   ```

   Expected: zero failures; Owner authorization alone consumes no horizon.
6. Commit: `feat(ibkr): bind owner authority to successor definitions`.

## Task 5: Implement the Atomic Successor Transition

**Files:**
- Modify: `ibkr_paper_30d/successor_epoch.py`
- Modify: `ibkr_paper_30d/successor_clock.py`
- Create: `tests/ibkr_paper_30d/test_successor_transition.py`

1. Add RED tests for one transaction appending exactly one V2 clock,
   `EXPERIMENT_EPOCH_SUPERSEDED`, and V2 activation with complete mutual hash
   bindings.
2. Add RED tests that mutate every prerequisite immediately before commit and
   require in-transaction rejection: predecessor current, target definition,
   Owner authority, `EPOCH_STARTED`, runtime activity, broker evidence, and
   conflicting clock.
3. Add a two-connection/thread contender test with a barrier (W). Exactly one
   transaction may append; the other must return idempotent exact-success or a
   deterministic closed result. Counts remain one clock, one supersession, one
   activation, and one current epoch.
4. Add failure-at-each-write-boundary tests by wrapping the test connection's
   insert execution. Require complete rollback with no partial edge (AG).
5. Implement `BEGIN IMMEDIATE` transition revalidation and append all three
   records before commit. Do not accept cached eligibility as authority.
6. Implement exact idempotency only when target, definition, clock, Owner
   authorization, and all edge hashes match; conflicts block.
7. Run:

   ```powershell
   python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_successor_transition.py tests\ibkr_paper_30d\test_successor_epoch_graph.py tests\ibkr_paper_30d\test_successor_clock_v2.py
   ```

   Expected: zero failures; concurrent single winner; no partial transitions.
8. Commit: `feat(ibkr): commit successor transitions atomically`.

## Task 6: Bind Launch Attempts to One Explicit Successor

**Files:**
- Modify: `ibkr_paper_30d/prerequisite_tools.py`
- Modify: `ibkr_paper_30d/day1_launch.py`
- Modify: `tests/ibkr_paper_30d/test_prerequisite_tools.py`
- Modify: `tests/ibkr_paper_30d/test_day1_launch.py`

1. Add RED tests requiring `target_successor_epoch_id` and
   `target_successor_definition_sha256` in config, launch-attempt binding,
   preflight result, accepted-attempt event, and every pre-clock receipt.
2. Add case X: bind successor A, append successor B, and prove the launch can
   activate only A or block; it must never infer B from `current()` or sequence.
3. Add RED tests for target definition mutation/replacement, absent V2 schema,
   mismatched authorization, stale broker time, gate changes, and eligibility
   changes before the locked transaction.
4. Refactor launch preparation so the host toolbox can provide fresh broker
   time and read-only eligibility evidence after lock acquisition without model
   invocation.
5. Wire `commit_successor_transition()` with the explicit target. Pass the
   returned exact clock to service construction; never reload a global clock.
6. Preserve the legacy V1 test path, but make successor mode explicit and
   fail-closed. No production default may silently select a pending definition.
7. Run:

   ```powershell
   python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_prerequisite_tools.py tests\ibkr_paper_30d\test_day1_launch.py
   ```

   Expected: zero failures; successor target A cannot drift to B.
8. Commit: `feat(ibkr): bind launches to explicit successor targets`.

## Task 7: Make Manifests, Bootstrap, and Start Evidence Dynamic

**Files:**
- Modify: `ibkr_paper_30d/epoch_manifest.py`
- Modify: `ibkr_paper_30d/autonomy_bootstrap.py`
- Modify: `ibkr_paper_30d/day1_launch.py`
- Modify: `ibkr_paper_30d/autonomous_service.py`
- Modify: `tests/ibkr_paper_30d/test_epoch_manifest.py`
- Modify: `tests/ibkr_paper_30d/test_autonomy_bootstrap.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_service.py`
- Modify: `tests/ibkr_paper_30d/test_day1_launch.py`

1. Add RED tests showing manifest, bootstrap, service, accepted launch,
   `EPOCH_MANIFEST_CREATED`, and `EPOCH_STARTED` all bind the same explicit
   successor epoch, definition, and clock hashes.
2. Remove the hard-coded manifest epoch ID and require it as input.
3. Ensure the service receives the transition's `ExperimentClock` instance and
   retains the `broker_server_time_utc()` constructor regression.
4. Wrap the post-clock/pre-start region. On any safe classified failure append
   `EPOCH_PRE_START_FAILED` with target, definition, clock, launch attempt,
   optional manifest hash, and deterministic reason codes only (S).
5. Reject relaunch of the failed epoch with
   `FAILED_EPOCH_REQUIRES_EXPLICIT_SUCCESSOR`; allow only a new chained
   definition/authorization/transition (T).
6. Re-run toolbox negatives: no `__getattr__`, no `_account_state` exposure,
   and timestamp-only return.
7. Run:

   ```powershell
   python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_epoch_manifest.py tests\ibkr_paper_30d\test_autonomy_bootstrap.py tests\ibkr_paper_30d\test_autonomous_service.py tests\ibkr_paper_30d\test_autonomy_toolbox.py tests\ibkr_paper_30d\test_day1_launch.py
   ```

   Expected: zero failures; failures after clock start are auditable and never
   rewrite the clock.
8. Commit: `feat(ibkr): bind runtime evidence to successor clocks`.

## Task 8: Complete the Production-Shaped Adversarial Matrix

**Files:**
- Create: `tests/ibkr_paper_30d/production_epoch_v1_fixture.py`
- Create: `tests/ibkr_paper_30d/test_successor_production_compatibility.py`
- Modify: V2 test files as coverage gaps require

1. Build the complete 535-row legacy anchor plus state sequences 536-539 and a
   V1 September 23 clock, using valid canonical hashes and production schemas.
2. Snapshot all V1 clock, authorization, state, ledger, order-registry, cycle,
   invocation, and result rows before V2 fixture operations.
3. Execute definition, authorization, clock/transition, failure, and another
   permitted successor entirely in the fixture.
4. Assert cases A-AG are each named and covered. Add any missing adversarial
   test before implementation adjustments.
5. Assert all historical raw rows/hashes remain identical, the old clock is
   queryable, epoch 1 is historical, and only the verified terminal successor
   is current.
6. Assert the broker-write tripwire remains zero (V).
7. Run:

   ```powershell
   python -m pytest -q -p no:cacheprovider tests\ibkr_paper_30d\test_successor_production_compatibility.py tests\ibkr_paper_30d\test_successor_schema_v2.py tests\ibkr_paper_30d\test_successor_clock_v2.py tests\ibkr_paper_30d\test_successor_epoch_graph.py tests\ibkr_paper_30d\test_successor_authorization_v2.py tests\ibkr_paper_30d\test_successor_transition.py
   ```

   Expected: zero failures and explicit coverage labels A-AG.
8. Commit: `test(ibkr): prove successor compatibility adversarially`.

## Task 9: Regenerate Authority Closure and Run All Verification

**Files:**
- Regenerate: `IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`
- Modify tests only if a real authority-closure defect is discovered

1. Run focused suites for experiment control, clock V2, epoch graph, Owner V2,
   Day1, service, toolbox, runtime integrity, lock, scheduler, kernel, and
   provenance.
2. Regenerate the kernel manifest:

   ```powershell
   python -m ibkr_paper_30d.kernel_manifest --repo-root . --output IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json
   ```

3. Verify the regenerated manifest independently with
   `verify_kernel_manifest()` and record the exact SHA.
4. Run the complete suite:

   ```powershell
   python -m pytest tests\ibkr_paper_30d -q -p no:cacheprovider
   ```

   Expected: zero failures.
5. Parse `FINALIZE_IBKR_PREREQUISITES.ps1`,
   `RUN_IBKR_MARKET_DATA_GATE.ps1`, and `RUN_IBKR_DAY1_SERVICE.ps1` through the
   PowerShell AST parser. Expected: zero parse errors for all three.
6. Run `git diff --check`. Expected: no output and exit 0.
7. Commit: `chore(ibkr): seal successor clock authority closure`.

## Task 10: Final Review, Canonical Integration, and Frozen Verification

**Files:**
- No production-state writes
- Canonical code fast-forward only

1. Build the whole-branch review package from canonical base
   `81fd236403632b2e2de4e9ebb86e14e02024770f` to implementation HEAD.
2. Review specifically for the Review Focus below. Fix any Critical/Important
   finding with a RED test, GREEN fix, full suite, and commit.
3. Verify the remediation worktree tracked state is clean and runtime
   provenance passes against exact HEAD.
4. Verify canonical tracked HEAD is still the base and tracked state is clean.
5. Fast-forward canonical to implementation HEAD. Do not open the production
   database through `Database.open()`.
6. Rebind only the disabled scheduler's `ApprovedHead` to final HEAD and verify
   its state remains `Disabled`.
7. Use SQLite URI `mode=ro` to prove production sequences 536-539 and hashes
   are unchanged, old `EPOCH_STARTED` count is zero, V2 tables are absent, and
   no successor state event exists.
8. Perform read-only PAPER reconciliation to a non-production output path and
   report positions, open orders, executions, and writes as zero.
9. Verify no Day1 process is running and run final kernel/provenance checks from
   canonical.
10. Return the exact `SUCCESSOR_CLOCK_V2_IMPLEMENTATION_REPORT` and stop. Do
    not install V2 or activate a successor.

## Review Focus

- Can any read/deploy/audit path install schema V2 or start a clock?
- Can target successor identity drift between preflight and transaction?
- Does every transactional prerequisite get re-read under `BEGIN IMMEDIATE`?
- Can malformed/old/future/backward broker time become start authority?
- Can independent activations, branches, missing edges, or sequence ordering
  produce a current epoch?
- Can any failure leave a clock without its supersession/activation pair?
- Can a failed pre-start epoch be retried without a new explicit successor?
- Can any V1 row, hash, unique constraint, or Owner authorization be reused or
  rewritten?
- Does any diagnostic persist raw exception text, account identity, balances,
  credentials, prompts, or tokens?
- Does any test or verification operation call an IBKR write method?

## Completion Contract

The plan is complete only when all focused and full tests pass, kernel and
runtime provenance pass at final HEAD, PowerShell AST and diff checks pass,
canonical is fast-forwarded, scheduler remains disabled, and read-only
production verification proves no V2 schema/state or broker activity exists.
