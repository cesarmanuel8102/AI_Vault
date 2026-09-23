# Day 1 Persistent PAPER Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start and preserve exactly one authorized 30-day IBKR PAPER service after every identity, auditor, market-data, database, ledger, and model gate passes, without testing a real broker write.

**Architecture:** Keep `CodexIBKRMarketDataGate` as the sole scheduler authority and make its scheduled path hand off in the foreground from market-policy collection to a fresh elevated prerequisite finalization and then to a new Python launch coordinator. The elevated Owner finalization is the only boundary that may create the clock-bound authorization; each launch attempt receives a unique ID binding its fresh reconciliation and Auditor V2 receipts. The coordinator only validates those controls, acquires the existing OS-and-database execution lock, arms its own process, and runs the existing service in the foreground while writing sanitized canonical evidence.

**Tech Stack:** Python 3.11+, pytest, Pydantic, SQLite, pywin32 named mutexes, Windows PowerShell 5.1, Windows Scheduled Tasks, IBKR Gateway PAPER on `127.0.0.1:4002`.

**Spec:** `docs/superpowers/specs/2026-09-23-day1-persistent-launch-design.md`

## Global Constraints

- The immutable scheduled start is `2026-09-23T13:30:00Z`, duration is exactly 30 days, and initial allocation is exactly USD 500.
- The clock already began at 09:30 EDT on 2026-09-23; delayed launch time is consumed experiment time and the end remains `2026-10-23T13:30:00Z`, never actual-start plus 30 days.
- PAPER endpoint is exactly `127.0.0.1:4002`; any LIVE endpoint, non-`DU` account, multiple account, or identity-hash mismatch fails closed.
- Requested model is exactly `gpt-5.6-sol` with reasoning effort `max`; actual model attestation remains mandatory before execution.
- The existing executor and stable IBKR execution client `19761` remain the only broker-write authority.
- `IBKR_AUTONOMOUS_PAPER_ARMED=true` exists only in the authoritative Python service process; no installer, finalizer, or market collector arms trading.
- A later `KILL_SWITCH_TRIGGERED` event is never cleared automatically.
- Kill-switch launch eligibility is monotonic: exactly the initial CLEAR and no TRIGGERED event anywhere in this experiment's history; a later CLEAR cannot rehabilitate a triggered experiment.
- Native autonomous discovery remains active. There is no fixed whitelist of symbols, asset classes, strategies, expirations, strikes, markets, or sessions.
- Capability-discovery and candidate-screen outputs are advisory evidence, never an authorized-universe boundary; actual IBKR account permissions, contract qualification, what-if checks, and executable-market checks are authoritative.
- Only an elevated, explicit Owner invocation containing `AUTHORIZE 30-DAY PAPER EXPERIMENT` may create authorization; the scheduled finalizer and Python launcher may only validate and consume it.
- Existing clock, authorization, market policy, receipts, and append-only ledger history are never overwritten to obtain a PASS.
- No implementation or verification step submits, modifies, cancels, reduces, or closes a real PAPER or LIVE order.
- Auditor Gate V2 semantics, auditor runtime payloads, trust anchors, IBKR identity logic, account/SID bindings, and PAPER/LIVE boundaries are unchanged.
- Preserve all pre-existing untracked Owner artifacts and unrelated worktree changes.

## Review Focus

- Missing Owner authorization must block; neither scheduled finalization nor the launcher may synthesize an `AUTHORIZED` event.
- A restart after a possibly uncertain broker write must use a new launch-attempt ID bound to newly generated reconciliation and Auditor V2 hashes.
- Every fake launch test must connect a write tripwire to the actual executor/IBKR write surface, so any `placeOrder`, `cancelOrder`, modify, reduce, or close attempt fails the test.
- Any historical `KILL_SWITCH_TRIGGERED` after initial authorization permanently blocks launch even if a later CLEAR exists.
- An empty initial candidate universe must still permit Native research and discovery, while unknown cycle statuses must never produce `AUTONOMOUS_PAPER_EXPERIMENT_RUNNING`.

---

## File Map

- Modify `ibkr_paper_30d/market_observation.py`: retain timestamp resolution in canonical market observations.
- Modify `ibkr_paper_30d/market_observation_collector.py`: propagate IBKR integer-second resolution and include it in quote-age uncertainty.
- Modify `ibkr_paper_30d/cli.py`: add sanitized observed account cardinality/namespace facts to read-only reconciliation.
- Modify `ibkr_paper_30d/prerequisite_tools.py`: create and verify per-attempt receipt bindings without changing Auditor V2 payloads.
- Create `ibkr_paper_30d/owner_authorization.py`: elevated-only immutable clock and Owner-authorization creation/validation CLI.
- Create `ibkr_paper_30d/day1_launch.py`: pure launch/control validation, execution-lock ownership, process-local arming, service construction, evidence, and CLI.
- Modify `ibkr_paper_30d/autonomous_service.py`: persist sanitized service-start, cycle-start, cycle-complete, and failure lifecycle events.
- Create `RUN_IBKR_DAY1_SERVICE.ps1`: foreground scheduled-task handoff, transcript capture, fresh finalizer invocation, and Python launcher invocation.
- Modify `RUN_IBKR_MARKET_DATA_GATE.ps1`: route both fresh-PASS and already-PASS scheduled paths to the foreground handoff and stop unregistering the scheduler authority.
- Modify `FINALIZE_IBKR_PREREQUISITES.ps1`: install the one existing task with a 31-day execution limit and bounded five-minute restarts.
- Create `tests/ibkr_paper_30d/test_day1_launch.py`: launcher unit and integration tests with injected fakes and write-count assertions.
- Create `tests/ibkr_paper_30d/test_owner_authorization.py`: explicit Owner authorization and non-synthesis regressions.
- Modify `tests/ibkr_paper_30d/test_ibkr_readonly_session.py`: sanitized cardinality and namespace evidence regressions.
- Modify `tests/ibkr_paper_30d/test_autonomous_research.py`: empty-universe Native discovery regression.
- Modify `tests/ibkr_paper_30d/test_autonomous_service.py`: lifecycle persistence and model-attestation regression tests.
- Modify `tests/ibkr_paper_30d/test_prerequisite_finalizer.py`: PowerShell AST, handoff behavior, task settings, no-arm, and no-write regressions.
- Modify the two existing market-observation tests: integer-second and out-of-bound clock-skew regressions.

### Task 0: Capture the Pre-Implementation Cryptographic Baseline

**Files:**
- Read only: `auditor_runtime/*`
- Read only: `AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json`
- Read only: `docs/contracts/runtime_hashes_20260224.json`
- Read only: `docs/superpowers/plans/2026-09-23-day1-implementation-baseline.json`

**Interfaces:**
- Consumes: current Git HEAD and protected-file bytes before any plan task is implemented.
- Produces: verified comparison values `base_head` and `protected_sha256` used by final verification; no application or runtime file is modified.

- [ ] **Step 1: Assert the reviewed base and capture every protected hash**

The reviewed pre-implementation values are:

```text
base_head=8b919b3ae0b36a7c419b6ef36ac6cf69e428cfe6
c01c8627bc584506e66cd31e01661737c67c953f8384fb45d061eb70f0d2b1ba  auditor_runtime/AUDITOR_DENIAL_PROBE_V1.ps1
9ec985aaac45df17251a755039e261a315b0ff6c4ec4d886e29eae1fa3fdde62  auditor_runtime/AUDITOR_GATE_V2_PROBE.ps1
23a60fd2f9dd62e00887a606524e361a0d1b3f672c519853eaf5b13a5efbdfa7  auditor_runtime/CODEX_DECISION_AUDITOR_V1.ps1
028423074114e9d5378f9564e73928aa76dd0aa0100defab3c230ff6db1aeb58  AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json
4b81cb7670dd8686a636e8a929821b5ffdf0d54ae96321b5ad46a0cc5553d7dd  docs/contracts/runtime_hashes_20260224.json
```

Run: `git rev-parse HEAD`

Run: `Get-ChildItem auditor_runtime -File -Recurse | Sort-Object FullName | Get-FileHash -Algorithm SHA256; Get-FileHash -Algorithm SHA256 AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json,docs/contracts/runtime_hashes_20260224.json`

Expected: exact values above. Stop before implementation on any mismatch.

- [ ] **Step 2: Validate the pre-created canonical baseline receipt**

Run: `python -c "import json,pathlib; p=pathlib.Path('docs/superpowers/plans/2026-09-23-day1-implementation-baseline.json'); x=json.loads(p.read_text()); assert x['schema']=='DAY1_IMPLEMENTATION_BASELINE_V1'; assert x['base_head']=='8b919b3ae0b36a7c419b6ef36ac6cf69e428cfe6'; assert len(x['protected_sha256'])==5"`

Expected: exit code zero. The baseline file already exists before implementation and remains read-only for Tasks 1-7.

- [ ] **Step 3: Confirm the baseline itself made no protected change**

Run the Step 1 hash command again.

Expected: exact equality. Commit the reviewed plan and baseline together before Task 1 so their provenance precedes implementation.

```powershell
git add docs/superpowers/specs/2026-09-23-day1-persistent-launch-design.md docs/superpowers/plans/2026-09-23-day1-persistent-paper-launch.md docs/superpowers/plans/2026-09-23-day1-implementation-baseline.json
git commit -m "docs: plan persistent PAPER launch"
```

### Task 1: Preserve IBKR Timestamp Resolution

**Files:**
- Modify: `ibkr_paper_30d/market_observation.py`
- Modify: `ibkr_paper_30d/market_observation_collector.py`
- Test: `tests/ibkr_paper_30d/test_market_observation.py`
- Test: `tests/ibkr_paper_30d/test_market_observation_collector.py`

**Interfaces:**
- Consumes: integer Unix-second timestamps returned by IBKR `currentTime(long)` and tick callbacks.
- Produces: `MarketObservation.timestamp_resolution_ms: int` and `validate_quote_age(..., timestamp_resolution_ms: int)` with accepted uncertainty equal to timestamp resolution plus measured half-RTT.

- [ ] **Step 1: Keep the failing regression tests that establish integer-second precision**

```python
def test_integer_second_timestamp_accepts_subsecond_rounding_uncertainty():
    result = validate_quote_age(
        observed_at_utc="2026-09-23T19:15:00.900000Z",
        broker_timestamp_utc="2026-09-23T19:15:00Z",
        max_age_ms=500,
        half_rtt_ms=25,
        timestamp_resolution_ms=1000,
    )
    assert result.accepted is True


def test_future_timestamp_beyond_resolution_and_half_rtt_is_rejected():
    result = validate_quote_age(
        observed_at_utc="2026-09-23T19:15:00Z",
        broker_timestamp_utc="2026-09-23T19:15:01.026000Z",
        max_age_ms=500,
        half_rtt_ms=25,
        timestamp_resolution_ms=1000,
    )
    assert result.reason_code == "CLOCK_SKEW_UNCERTAIN"
```

- [ ] **Step 2: Re-run the focused RED/GREEN history**

Run: `python -m pytest -q tests/ibkr_paper_30d/test_market_observation.py tests/ibkr_paper_30d/test_market_observation_collector.py`

Expected: PASS for the four newly added resolution regressions; the recorded RED state before implementation was three unit failures plus one collector integration failure.

- [ ] **Step 3: Confirm the minimal implementation remains limited to resolution propagation**

```python
class MarketObservation(BaseModel, frozen=True):
    timestamp_resolution_ms: int = Field(default=0, ge=0)


uncertainty_ms = timestamp_resolution_ms + half_rtt_ms
if broker_time_ms - observed_time_ms > uncertainty_ms:
    return QuoteAgeResult(accepted=False, reason_code="CLOCK_SKEW_UNCERTAIN")
```

The collector must set `timestamp_resolution_ms=1000` only for timestamps sourced from IBKR integer-second APIs. It must not increase stale-quote age limits or convert rejection into acceptance outside that exact uncertainty bound.

- [ ] **Step 4: Commit the isolated timestamp correction**

```powershell
git add ibkr_paper_30d/market_observation.py ibkr_paper_30d/market_observation_collector.py tests/ibkr_paper_30d/test_market_observation.py tests/ibkr_paper_30d/test_market_observation_collector.py
git commit -m "fix: account for IBKR timestamp resolution"
```

### Task 2: Materialize Explicit Owner Authorization and Fresh Attempt Binding

**Files:**
- Create: `ibkr_paper_30d/owner_authorization.py`
- Modify: `ibkr_paper_30d/cli.py`
- Modify: `ibkr_paper_30d/prerequisite_tools.py`
- Modify: `FINALIZE_IBKR_PREREQUISITES.ps1`
- Create: `tests/ibkr_paper_30d/test_owner_authorization.py`
- Modify: `tests/ibkr_paper_30d/test_ibkr_readonly_session.py`
- Modify: `tests/ibkr_paper_30d/test_prerequisite_tools.py`

**Interfaces:**
- Consumes: the exact phrase `AUTHORIZE 30-DAY PAPER EXPERIMENT`, elevated interactive Owner SID, immutable clock parameters, an expected PAPER identity binding, a UUID launch-attempt ID, and freshly generated read-only/Auditor V2 receipts.
- Produces: `python -m ibkr_paper_30d.owner_authorization create|validate`, immutable SQLite clock and `AUTHORIZED` event created only by `create`, sanitized reconciliation fields `managed_account_count` and `paper_account_namespace_ok`, and `bind_launch_attempt(...) -> dict[str, object]`.

- [ ] **Step 1: Write failing authorization-boundary tests**

```python
def test_create_requires_exact_owner_phrase_and_elevated_interactive_boundary(tmp_path):
    db_path = tmp_path / "autonomous.sqlite3"
    with pytest.raises(OwnerAuthorizationError, match="OWNER_AUTHORIZATION_PHRASE_INVALID"):
        create_owner_authorization(
            db_path=db_path,
            phrase="almost",
            actor_sid="S-1-test-owner",
            elevated=True,
            receipt_path=tmp_path / "owner_authorization_v1.json",
        )
    assert not db_path.exists()


def test_validate_never_creates_missing_authorization(tmp_path):
    db_path = tmp_path / "autonomous.sqlite3"
    with pytest.raises(OwnerAuthorizationError, match="OWNER_AUTHORIZATION_MISSING"):
        validate_owner_authorization(
            db_path=db_path,
            receipt_path=tmp_path / "owner_authorization_v1.json",
            expected_actor_sid="S-1-test-owner",
        )
    with Database.open(db_path) as db:
        count = db.execute("SELECT COUNT(*) FROM experiment_authorization_events").fetchone()[0]
    assert count == 0


def test_authorization_is_bound_to_exact_clock_and_owner_sid(tmp_path):
    db_path = tmp_path / "autonomous.sqlite3"
    receipt = create_owner_authorization(
        db_path=db_path,
        phrase="AUTHORIZE 30-DAY PAPER EXPERIMENT",
        actor_sid="S-1-test-owner",
        elevated=True,
        receipt_path=tmp_path / "owner_authorization_v1.json",
    )
    assert receipt["start_utc"] == "2026-09-23T13:30:00Z"
    assert receipt["end_utc"] == "2026-10-23T13:30:00Z"
    assert receipt["duration_days"] == 30
    assert receipt["initial_allocation"] == "500"
    assert receipt["authorization_state"] == "AUTHORIZED"
    with Database.open(db_path) as db:
        assert KillSwitchStore(db).current() == "KILL_SWITCH_CLEAR"
```

Also test non-elevated creation, `-SkipTaskRegistration` without an existing authorization, a second conflicting phrase/SID/clock, and attempts to replace the immutable event. Validation may read but never call `ExperimentClockStore.initialize_or_load` or `OwnerAuthorizationStore.set` when an event is absent.

- [ ] **Step 2: Run authorization tests and verify RED**

Run: `python -m pytest -q tests/ibkr_paper_30d/test_owner_authorization.py`

Expected: FAIL because `owner_authorization.py` does not exist.

- [ ] **Step 3: Implement the elevated-only creation and read-only validation API**

```python
OWNER_PHRASE = "AUTHORIZE 30-DAY PAPER EXPERIMENT"
START_UTC = datetime(2026, 9, 23, 13, 30, tzinfo=timezone.utc)
DURATION_DAYS = 30
INITIAL_ALLOCATION = Decimal("500")


def create_owner_authorization(
    *, db_path: Path, phrase: str, actor_sid: str, elevated: bool,
    receipt_path: Path,
) -> dict[str, object]:
    if phrase != OWNER_PHRASE:
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_PHRASE_INVALID")
    if not elevated:
        raise OwnerAuthorizationError("OWNER_AUTHORIZATION_REQUIRES_ELEVATION")
    with Database.open(db_path) as db, db.transaction():
        clock = ExperimentClockStore(db).initialize_or_load(
            requested_start_utc=START_UTC,
            duration_days=DURATION_DAYS,
            initial_allocation=INITIAL_ALLOCATION,
        )
        if _authorization_event_count(db) == 0:
            event_id = OwnerAuthorizationStore(db).set(
                "AUTHORIZED",
                clock_event_sha256=clock.event_sha256,
                reason=OWNER_PHRASE,
                actor=actor_sid,
            )
        else:
            event_id = _validate_existing_authorization(db, clock, actor_sid)
        kill_switch = KillSwitchStore(db)
        if _kill_event_count(db) == 0:
            kill_switch.set(
                "KILL_SWITCH_CLEAR",
                reason="explicit Owner authorization for initial launch",
                actor=actor_sid,
            )
        elif _kill_history(db) != ("KILL_SWITCH_CLEAR",):
            raise OwnerAuthorizationError("KILL_SWITCH_HISTORY_INVALID")
    receipt = _authorization_receipt(clock, event_id, actor_sid)
    atomic_write_canonical_json(receipt_path, receipt)
    return receipt
```

The CLI `create` requires `--phrase`, `--actor-sid`, `--receipt`, and `--elevated`; PowerShell supplies elevation after checking its current token and SID. The canonical receipt contains only SID, event/clock hashes, fixed clock parameters, authorization state, and phrase SHA-256. The `validate` command loads the existing clock/event and receipt, then compares the exact phrase hash, actor SID, start, end, duration, and allocation without creating rows.

- [ ] **Step 4: Add observable, sanitized single-DU evidence**

```python
report.update({
    "managed_account_count": len(evidence.managed_accounts),
    "paper_account_namespace_ok": (
        len(evidence.managed_accounts) == 1
        and evidence.managed_accounts[0].strip().upper().startswith("DU")
    ),
})
```

Add read-only tests for count `0`, `1`, and `2`, plus `DU` and non-`DU` namespaces. Assert the raw managed account never appears in JSON. These are evidence-only additions: the existing `paper_account_identity_gate` logic remains authoritative and unchanged.

- [ ] **Step 5: Write failing fresh-attempt binding tests**

```python
def test_attempt_binding_hashes_fresh_receipts_and_rejects_reuse(tmp_path):
    readonly = write_receipt(tmp_path / "readonly.json", {"status": "PASS"})
    auditor = write_receipt(tmp_path / "auditor.json", {"gate_status": "PASS"})
    attempt_id = str(uuid.uuid4())
    binding = bind_launch_attempt(attempt_id, readonly, auditor, tmp_path / "binding.json")
    assert binding["launch_attempt_id"] == attempt_id
    assert binding["readonly_receipt_sha256"] == sha256_file(readonly)
    assert binding["auditor_receipt_sha256"] == sha256_file(auditor)
    with pytest.raises(ValueError, match="LAUNCH_ATTEMPT_ID_MISMATCH"):
        validate_launch_attempt_binding(str(uuid.uuid4()), readonly, auditor, tmp_path / "binding.json")
```

Also test mutation of either receipt after binding, malformed/non-UUID attempt IDs, a binding timestamp before either receipt's completion, and stale reuse on restart.

- [ ] **Step 6: Implement canonical attempt binding without auditor payload changes**

`bind_launch_attempt` writes schema `DAY1_LAUNCH_ATTEMPT_BINDING_V1`, UUID, read-only SHA-256, Auditor V2 SHA-256, expected account hash, creation UTC, and `real_order_writes_attempted=0` through canonical temporary-file replace. `validate_launch_attempt_binding` recomputes both hashes and requires exact UUID equality. Do not modify anything under `auditor_runtime`, the Auditor V2 receipt schema, or either trust-anchor file.

- [ ] **Step 7: Make elevated finalization the sole creator**

Add optional `-OwnerAuthorization` and required scheduled `-LaunchAttemptId` parameters to `FINALIZE_IBKR_PREREQUISITES.ps1`. On the interactive installation path, absence of existing authorization requires the exact phrase and calls `owner_authorization create`; later invocations call only `owner_authorization validate`. On every scheduled `-SkipTaskRegistration` run, generate fresh read-only and Auditor V2 receipts first, then invoke `prerequisite_tools bind-launch-attempt` with that run's UUID. A missing authorization exits once with `OWNER_AUTHORIZATION_MISSING`.

- [ ] **Step 8: Run focused tests and commit**

Run: `python -m pytest -q tests/ibkr_paper_30d/test_owner_authorization.py tests/ibkr_paper_30d/test_ibkr_readonly_session.py tests/ibkr_paper_30d/test_prerequisite_tools.py tests/ibkr_paper_30d/test_prerequisite_finalizer.py`

Expected: PASS; protected Auditor/runtime hashes still equal Task 0.

```powershell
git add ibkr_paper_30d/owner_authorization.py ibkr_paper_30d/cli.py ibkr_paper_30d/prerequisite_tools.py FINALIZE_IBKR_PREREQUISITES.ps1 tests/ibkr_paper_30d/test_owner_authorization.py tests/ibkr_paper_30d/test_ibkr_readonly_session.py tests/ibkr_paper_30d/test_prerequisite_tools.py tests/ibkr_paper_30d/test_prerequisite_finalizer.py
git commit -m "feat: bind explicit Owner authorization and launch attempts"
```

### Task 3: Build the Fail-Closed Launch Preflight

**Files:**
- Create: `ibkr_paper_30d/day1_launch.py`
- Create: `tests/ibkr_paper_30d/test_day1_launch.py`

**Interfaces:**
- Consumes: `Day1LaunchConfig`, externally created Owner authorization, caller-supplied UUID `launch_attempt_id`, its fresh receipt binding, latest read-only reconciliation JSON, `RuntimeAuditorGate.evaluate()`, `RuntimeMarketDataGate.evaluate(DecisionClass.NEW_TRADE)`, repository HEAD and runtime hashes.
- Produces: `LaunchPreflight`, `LaunchError(code: str)`, `evaluate_launch_preflight(config, dependencies)`, and `write_launch_evidence(config, event_type, payload)`.

- [ ] **Step 1: Write failing preflight tests with zero-write spies**

```python
@dataclass
class LaunchTestContext:
    config: Day1LaunchConfig
    dependencies: LaunchDependencies
    identity_payload: dict[str, object]
    auditor_gate: Mock
    market_gate: Mock
    service_factory: Mock
    executor_tripwire: "ExecutorTripwire"
    ib_tripwire: "IBWriteTripwire"


class ExecutorTripwire:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _fail(self, name: str):
        self.calls.append(name)
        raise AssertionError(f"broker write authority reached: {name}")

    def execute(self, *args, **kwargs):
        return self._fail("execute")

    def execute_open_order_action(self, *args, **kwargs):
        return self._fail("execute_open_order_action")

    def execute_position_action(self, *args, **kwargs):
        return self._fail("execute_position_action")


class IBWriteTripwire:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _fail(self, name: str):
        self.calls.append(name)
        raise AssertionError(f"IB write reached: {name}")

    def placeOrder(self, *args, **kwargs):
        return self._fail("placeOrder")

    def cancelOrder(self, *args, **kwargs):
        return self._fail("cancelOrder")

    def reqGlobalCancel(self, *args, **kwargs):
        return self._fail("reqGlobalCancel")


def write_identity_receipt(ctx: LaunchTestContext, **updates: object) -> None:
    ctx.identity_payload.update(updates)
    ctx.config.identity_receipt_path.write_bytes(canonical_bytes(ctx.identity_payload))


def seed_explicit_owner_authorization(config: Day1LaunchConfig) -> None:
    create_owner_authorization(
        db_path=config.db_path,
        phrase="AUTHORIZE 30-DAY PAPER EXPERIMENT",
        actor_sid="S-1-test-owner",
        elevated=True,
        receipt_path=config.owner_authorization_path,
    )


def passing_context(tmp_path: Path) -> LaunchTestContext:
    reports = tmp_path / "state" / "ibkr_paper_30d" / "reports"
    reports.mkdir(parents=True)
    config = Day1LaunchConfig(
        repo_root=tmp_path,
        db_path=tmp_path / "state" / "ibkr_paper_30d" / "autonomous.sqlite3",
        launch_root=tmp_path / "state" / "ibkr_paper_30d" / "launch",
        expected_identity_path=tmp_path / "Secrets" / "expected_paper_account_identity_v1.json",
        identity_receipt_path=reports / "read_only_real_paper_reconciliation.json",
        auditor_receipt_path=reports / "auditor_gate_v2_receipt.json",
        market_policy_path=reports / "market_data_policy_v1.json",
        market_validation_path=reports / "market_data_validation.json",
        owner_authorization_path=reports / "owner_authorization_v1.json",
        launch_attempt_binding_path=reports / "launch_attempt_binding_v1.json",
        launch_attempt_id="11111111-1111-4111-8111-111111111111",
    )
    config.expected_identity_path.parent.mkdir(parents=True)
    config.expected_identity_path.write_bytes(canonical_bytes({
        "schema": "EXPECTED_PAPER_ACCOUNT_IDENTITY_V1",
        "account_sha256": "a" * 64,
        "gateway_mode": "PAPER",
        "host": "127.0.0.1",
        "port": 4002,
        "managed_account_count": 1,
    }))
    identity_payload = {
        "schema": "REAL_IBKR_READ_ONLY_RECONCILIATION_V1",
        "status": "PASS",
        "gateway_mode": "PAPER",
        "host": "127.0.0.1",
        "port": 4002,
        "paper_account_identity_gate": "PASS",
        "real_ibkr_read_only_identity_gate": "PASS",
        "broker_reconciliation_gate": "PASS",
        "expected_account_identity_bound": True,
        "expected_account_identity_hash": "a" * 64,
        "heartbeat_ok": True,
        "raw_account_identity_persisted": False,
        "real_order_writes_attempted": 0,
        "managed_account_count": 1,
        "paper_account_namespace_ok": True,
        "query_completeness": {
            "account_summary": True, "account_values": True, "current_time": True,
            "executions": True, "managed_accounts": True,
            "open_orders": True, "positions": True,
        },
    }
    config.identity_receipt_path.write_bytes(canonical_bytes(identity_payload))
    config.auditor_receipt_path.write_text("{}", encoding="utf-8")
    config.market_policy_path.write_text("{}", encoding="utf-8")
    config.market_validation_path.write_bytes(canonical_bytes({
        "schema": "REAL_MARKET_DATA_VALIDATION_V1",
        "status": "PASS", "market_data_gate": "PASS",
        "market_data_policy_frozen": True, "broker_calls_made": 0,
        "real_order_writes_attempted": 0, "reason_codes": [],
    }))
    seed_explicit_owner_authorization(config)
    bind_launch_attempt(
        config.launch_attempt_id,
        config.identity_receipt_path,
        config.auditor_receipt_path,
        config.launch_attempt_binding_path,
    )
    auditor_gate = Mock()
    auditor_gate.evaluate.return_value = {
        "gate_status": "PASS", "reason_codes": [], "receipt_sha256": "b" * 64,
    }
    market_gate = Mock()
    market_gate.evaluate.return_value = {
        "gate_status": "PASS", "reason_codes": [], "policy_version": "V1",
    }
    service_factory = Mock()
    executor_tripwire = ExecutorTripwire()
    ib_tripwire = IBWriteTripwire()
    dependencies = LaunchDependencies(
        now_utc=lambda: datetime(2026, 9, 23, 20, 0, tzinfo=timezone.utc),
        auditor_gate_factory=lambda _: auditor_gate,
        market_gate_factory=lambda _config, _hash: market_gate,
        database_factory=Database.open,
        lock_factory=ExecutionLock,
        service_factory=service_factory,
        lock_owner_factory=lambda now: LockOwner(
            owner_id="test-owner", pid=1234,
            process_start=now.isoformat(), host_fingerprint="test-host",
            boot_session_id="test-boot",
        ),
        current_sid=lambda: "S-1-test-owner",
    )
    return LaunchTestContext(
        config, dependencies, identity_payload, auditor_gate, market_gate,
        service_factory, executor_tripwire, ib_tripwire,
    )


def rewrite_identity_then_pass(ctx: LaunchTestContext) -> dict[str, object]:
    write_identity_receipt(ctx, server_timestamp_utc="2026-09-23T20:00:01Z")
    return {"gate_status": "PASS", "reason_codes": [], "receipt_sha256": "b" * 64}


def test_preflight_rejects_live_route_before_service_or_broker_write(tmp_path):
    ctx = passing_context(tmp_path)
    write_identity_receipt(ctx, port=4001)
    with pytest.raises(LaunchError, match="LIVE_ROUTE_FORBIDDEN"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)
    assert ctx.service_factory.mock_calls == []
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []


def test_identity_receipt_changed_after_auditor_receipt_blocks(tmp_path):
    ctx = passing_context(tmp_path)
    ctx.auditor_gate.evaluate.side_effect = lambda: rewrite_identity_then_pass(ctx)
    with pytest.raises(LaunchError, match="IDENTITY_RECEIPT_CHANGED_DURING_PREFLIGHT"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []


def test_restart_requires_fresh_reconciliation_pass(tmp_path):
    ctx = passing_context(tmp_path)
    write_identity_receipt(ctx, broker_reconciliation_gate="BLOCK")
    with pytest.raises(LaunchError, match="BROKER_RECONCILIATION_REQUIRED"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []
```

Also parameterize failures for pre-start time, host not `127.0.0.1`, observed `managed_account_count` other than one, `paper_account_namespace_ok=false`, heartbeat failure, incomplete positions/executions/open-orders visibility, expected-account hash mismatch, auditor BLOCK, market BLOCK, delayed/frozen market policy, missing Owner authorization, launch-attempt ID mismatch, and receipt files whose SHA-256 no longer matches their attempt binding.

- [ ] **Step 2: Run the new tests and verify RED**

Run: `python -m pytest -q tests/ibkr_paper_30d/test_day1_launch.py -k preflight`

Expected: FAIL during import because `ibkr_paper_30d.day1_launch` does not exist.

- [ ] **Step 3: Implement immutable config, dependencies, and strict validation**

```python
@dataclass(frozen=True)
class Day1LaunchConfig:
    repo_root: Path
    db_path: Path
    launch_root: Path
    expected_identity_path: Path
    identity_receipt_path: Path
    auditor_receipt_path: Path
    market_policy_path: Path
    market_validation_path: Path
    owner_authorization_path: Path
    launch_attempt_binding_path: Path
    launch_attempt_id: str
    scheduled_start_utc: datetime = datetime(2026, 9, 23, 13, 30, tzinfo=timezone.utc)
    duration_days: int = 30
    initial_allocation: Decimal = Decimal("500")
    paper_host: str = "127.0.0.1"
    paper_port: int = 4002
    model: str = "gpt-5.6-sol"
    reasoning_effort: str = "max"


@dataclass
class LaunchDependencies:
    now_utc: Callable[[], datetime]
    auditor_gate_factory: Callable[[Day1LaunchConfig], RuntimeAuditorGate]
    market_gate_factory: Callable[[Day1LaunchConfig, str], RuntimeMarketDataGate]
    database_factory: Callable[[Path], Database]
    lock_factory: Callable[[Database], ExecutionLock]
    service_factory: Callable[..., AutonomousExperimentService]
    lock_owner_factory: Callable[[datetime], LockOwner]
    current_sid: Callable[[], str]


class LaunchError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LaunchPreflight:
    launch_attempt_id: str
    authorization_event_id: str
    expected_account_hash: str
    identity_receipt_sha256: str
    auditor_receipt_sha256: str
    market_policy_sha256: str
    market_validation_sha256: str
    actual_start_utc: datetime
```

`evaluate_launch_preflight` first validates the externally created Owner authorization and current immutable clock without inserting a row. The authorization SID must equal `dependencies.current_sid()`, implemented in production from the current Windows process token, so a different principal cannot consume it. It validates `launch_attempt_binding_v1.json` against `config.launch_attempt_id` and recomputes the current read-only and Auditor receipt hashes. It then loads `Secrets/expected_paper_account_identity_v1.json` through `config.expected_identity_path` and requires its schema, PAPER host/port, one managed account, and 64-character lowercase `account_sha256`. The read-only receipt must have `schema=REAL_IBKR_READ_ONLY_RECONCILIATION_V1`, `status=PASS`, `gateway_mode=PAPER`, `host=127.0.0.1`, `port=4002`, `managed_account_count=1`, `paper_account_namespace_ok=true`, `paper_account_identity_gate=PASS`, `real_ibkr_read_only_identity_gate=PASS`, `broker_reconciliation_gate=PASS`, `expected_account_identity_bound=true`, `heartbeat_ok=true`, `raw_account_identity_persisted=false`, `real_order_writes_attempted=0`, every `query_completeness` value true, and an `expected_account_identity_hash` equal to that immutable Owner binding. It hashes the receipt before Auditor V2 evaluation, requires `RuntimeAuditorGate.evaluate()` PASS against the same path, reads and hashes the receipt again, and blocks if the bytes changed during preflight. It then evaluates `RuntimeMarketDataGate.evaluate(DecisionClass.NEW_TRADE)` and returns hashes only. It must never return or persist a raw account ID.

The persisted `market_data_validation.json` must independently have schema `REAL_MARKET_DATA_VALIDATION_V1`, `status=PASS`, `market_data_gate=PASS`, `market_data_policy_frozen=true`, `broker_calls_made=0`, and `real_order_writes_attempted=0`. Hash both that report and the verified frozen policy before running the fresh runtime market gate.

- [ ] **Step 4: Add atomic canonical evidence and sanitization tests**

```python
def test_launch_evidence_is_atomic_hashed_and_contains_no_account_id(tmp_path):
    ctx = passing_context(tmp_path)
    path = write_launch_evidence(
        ctx.config,
        "PREFLIGHT_PASS",
        {"expected_account_hash": "a" * 64, "reason_codes": []},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["event_sha256"] == sha256_json(payload["event"])
    assert "DU" not in path.read_text(encoding="utf-8")
    assert not list(path.parent.glob("*.tmp"))
```

Implement writes as `canonical_bytes` to a same-directory temporary file followed by `os.replace`; append history as one canonical JSON value per line. Reject evidence keys named `account`, `account_id`, `credential`, `token`, or `prompt`.

- [ ] **Step 5: Run focused tests and commit**

Run: `python -m pytest -q tests/ibkr_paper_30d/test_day1_launch.py -k "preflight or evidence"`

Expected: PASS and zero calls on both executor and IB write tripwires.

```powershell
git add ibkr_paper_30d/day1_launch.py tests/ibkr_paper_30d/test_day1_launch.py
git commit -m "feat: add fail-closed Day 1 preflight"
```

### Task 4: Validate Controls and Own One Service

**Files:**
- Modify: `ibkr_paper_30d/day1_launch.py`
- Modify: `ibkr_paper_30d/autonomous_state.py`
- Modify: `tests/ibkr_paper_30d/test_day1_launch.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_state.py`

**Interfaces:**
- Consumes: `LaunchPreflight`, `Database`, `ExperimentClockStore`, `OwnerAuthorizationStore`, `KillSwitchStore`, `AutonomousExperimentLedger`, `ExecutionLock`, and an injected `service_factory`.
- Produces: read-only `validate_launch_controls(db, config) -> LaunchControls`, `run_day1_launch(config, dependencies) -> None`, append-only launch-attempt consumption, and CLI `main(argv: Sequence[str] | None = None) -> int`.

- [ ] **Step 1: Write failing control-consumption and immutability tests**

```python
class StopTestService(RuntimeError):
    pass


def seed_active_lock_projection(path: Path) -> None:
    db = Database.open(path)
    payload = {
        "state": "ACTIVE", "owner_id": "stale-owner", "pid": 999999,
        "process_start": "2026-09-23T19:00:00Z", "host_fingerprint": "test-host",
        "boot_session_id": "old-boot", "generation": 1,
        "heartbeat_at_utc": "2026-09-23T19:00:00Z", "order_authority": False,
    }
    db.execute(
        "INSERT INTO experiment_state(experiment_id,version,payload_json,payload_sha256,updated_at_utc) VALUES(?,?,?,?,?)",
        ("EXECUTION_LOCK_V1", 1, canonical_bytes(payload).decode("utf-8"),
         sha256_json(payload), "2026-09-23T19:00:00Z"),
    )
    db.close()


def test_launcher_only_consumes_preexisting_clock_authorization_and_kill_clear(tmp_path):
    ctx = passing_context(tmp_path)
    before = control_event_counts(ctx.config.db_path)
    ctx.service_factory.return_value.run_forever.side_effect = StopTestService
    with pytest.raises(StopTestService):
        run_day1_launch(ctx.config, ctx.dependencies)
    db = Database.open(ctx.config.db_path)
    clock = ExperimentClockStore(db).load()
    assert clock.start_utc == datetime(2026, 9, 23, 13, 30, tzinfo=timezone.utc)
    assert clock.duration_days == 30
    assert clock.initial_allocation == Decimal("500")
    assert OwnerAuthorizationStore(db).current(clock_event_sha256=clock.event_sha256) == "AUTHORIZED"
    assert KillSwitchStore(db).current() == "KILL_SWITCH_CLEAR"
    assert control_event_counts(ctx.config.db_path) == before


def test_missing_authorization_blocks_without_creating_it(tmp_path):
    ctx = passing_context(tmp_path)
    delete_test_database_and_authorization_receipt(ctx)
    with pytest.raises(LaunchError, match="OWNER_AUTHORIZATION_MISSING"):
        run_day1_launch(ctx.config, ctx.dependencies)
    assert authorization_event_count(ctx.config.db_path) == 0
    assert ctx.service_factory.mock_calls == []


def test_existing_triggered_kill_switch_is_never_auto_cleared(tmp_path):
    ctx = passing_context(tmp_path)
    db = Database.open(ctx.config.db_path)
    KillSwitchStore(db).set("KILL_SWITCH_TRIGGERED", reason="owner stop")
    KillSwitchStore(db).set("KILL_SWITCH_CLEAR", reason="invalid later clear")
    assert KillSwitchStore(db).current() == "KILL_SWITCH_CLEAR"
    with pytest.raises(LaunchError, match="KILL_SWITCH_TRIGGERED"):
        run_day1_launch(ctx.config, ctx.dependencies)
    assert kill_switch_history(db) == (
        "KILL_SWITCH_CLEAR", "KILL_SWITCH_TRIGGERED", "KILL_SWITCH_CLEAR",
    )
    assert ctx.service_factory.mock_calls == []


def test_state_builder_cannot_clear_default_or_triggered_kill_switch(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        with pytest.raises(AutonomousStateBuildError, match="KILL_SWITCH_OVERRIDE_FORBIDDEN"):
            AutonomousStateBuilder(
                db, FakeToolbox(), experiment_start_utc=START_UTC,
                kill_switch_state="KILL_SWITCH_CLEAR",
                runtime_market_gate=FakeMarketGate(),
            )
        assert KillSwitchStore(db).current() == "KILL_SWITCH_TRIGGERED"


def test_stale_active_database_lock_requires_owner_action(tmp_path):
    ctx = passing_context(tmp_path)
    seed_active_lock_projection(ctx.config.db_path)
    with pytest.raises(LaunchError, match="EXECUTION_LOCK_OWNER_ACTION_REQUIRED"):
        run_day1_launch(ctx.config, ctx.dependencies)
    assert ctx.service_factory.mock_calls == []
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []
```

Add tests for immutable clock mismatch, revoked/mismatched authorization, corrupt `PRAGMA integrity_check`, invalid ledger projection, live named mutex, abandoned mutex, and a second direct invocation. A live named mutex must return the idempotent status `AUTONOMOUS_PAPER_EXPERIMENT_ALREADY_RUNNING` without constructing a service; an abandoned mutex or active database projection without a live mutex must return `OWNER_ACTION_REQUIRED`. Every test asserts no broker-write calls.

- [ ] **Step 2: Run the control tests and verify RED**

Run: `python -m pytest -q tests/ibkr_paper_30d/test_day1_launch.py -k "clock or authorization or kill or lock or ledger"`

Expected: FAIL because control initialization and lock ownership are not implemented.

- [ ] **Step 3: Implement read-only control validation without auto-recovery**

```python
def assert_integrity_check_ok(db: Database) -> None:
    rows = [str(row[0]) for row in db.execute("PRAGMA integrity_check").fetchall()]
    if rows != ["ok"]:
        raise LaunchError("DATABASE_INTEGRITY_CHECK_FAILED")


def latest_authorization_event_id(db: Database) -> str:
    row = db.execute(
        "SELECT event_id FROM experiment_authorization_events ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise LaunchError("OWNER_AUTHORIZATION_MISSING")
    return str(row[0])


@dataclass(frozen=True)
class LaunchControls:
    clock_event_sha256: str
    authorization_event_id: str
    kill_switch_state: str


def validate_launch_controls(db: Database, config: Day1LaunchConfig) -> LaunchControls:
    assert_integrity_check_ok(db)
    clock = ExperimentClockStore(db).load()
    if clock is None:
        raise LaunchError("EXPERIMENT_CLOCK_MISSING")
    if (
        clock.start_utc != config.scheduled_start_utc
        or clock.end_utc != datetime(2026, 10, 23, 13, 30, tzinfo=timezone.utc)
        or clock.duration_days != 30
        or clock.initial_allocation != Decimal("500")
    ):
        raise LaunchError("EXPERIMENT_CLOCK_MISMATCH")
    authorization = OwnerAuthorizationStore(db)
    if authorization.current(clock_event_sha256=clock.event_sha256) != "AUTHORIZED":
        raise LaunchError("OWNER_AUTHORIZATION_INVALID")
    authorization_event_id = latest_authorization_event_id(db)
    states = tuple(
        str(row[0]) for row in db.execute(
            "SELECT state FROM kill_switch_events ORDER BY sequence ASC"
        ).fetchall()
    )
    if states != ("KILL_SWITCH_CLEAR",):
        raise LaunchError("KILL_SWITCH_TRIGGERED")
    return LaunchControls(clock.event_sha256, authorization_event_id, states[0])
```

The validator performs no INSERT or UPDATE. Require `AutonomousExperimentLedger(db, allocation=Decimal("500")).project().valid`, then append the accepted launch-attempt ID once immediately before arming; a repeated ID fails `LAUNCH_ATTEMPT_REUSED`. Do not call `ExecutionLock.recover_stale`. Map `OS_MUTEX_HELD` to a sanitized `AUTONOMOUS_PAPER_EXPERIMENT_ALREADY_RUNNING` evidence event and successful idempotent CLI return without starting another service. Map `ABANDONED_MUTEX` and `LOCK_RECORD_ACTIVE` to explicit `OWNER_ACTION_REQUIRED` launch codes.

Remove the `AutonomousStateBuilder` behavior that turns its optional `kill_switch_state="KILL_SWITCH_CLEAR"` constructor argument into a database CLEAR event. Existing tests must seed the initial CLEAR through the Owner-authorization helper and construct the builder without an override. Passing a control state that differs from persisted state raises `KILL_SWITCH_OVERRIDE_FORBIDDEN` and performs no write.

- [ ] **Step 4: Implement process-local arming, foreground service, and lock heartbeat**

```python
@contextmanager
def paper_arm_environment(expected_account_hash: str):
    old_arm = os.environ.get("IBKR_AUTONOMOUS_PAPER_ARMED")
    old_hash = os.environ.get("IBKR_PAPER_ACCOUNT_SHA256")
    os.environ["IBKR_AUTONOMOUS_PAPER_ARMED"] = "true"
    os.environ["IBKR_PAPER_ACCOUNT_SHA256"] = expected_account_hash
    try:
        yield
    finally:
        restore_env("IBKR_AUTONOMOUS_PAPER_ARMED", old_arm)
        restore_env("IBKR_PAPER_ACCOUNT_SHA256", old_hash)


def restore_env(name: str, previous: str | None) -> None:
    if previous is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous
```

Acquire `ExecutionLock` before setting either environment variable. Start a 30-second heartbeat worker that opens its own SQLite connection and calls `ExecutionLock(heartbeat_db).heartbeat(receipt)`; any rejected heartbeat sets the service stop event and records `OWNER_ACTION_REQUIRED`. Build `AutonomousExperimentService` with `execute_paper=True`, `model="gpt-5.6-sol"`, `reasoning_effort="max"`, `scan_interval_seconds=300`, and `position_interval_seconds=60`; call `run_forever()` in the foreground. Stop the heartbeat and release the lock in `finally`.

The CLI returns `0` only for an orderly terminal service state or the idempotent `AUTONOMOUS_PAPER_EXPERIMENT_ALREADY_RUNNING` result. It returns `20` for fail-closed preflight/control failures and `30` for `OWNER_ACTION_REQUIRED`; unexpected exceptions return `1` after sanitized failure evidence. It prints one canonical JSON status line and never prints account IDs, environment values, credentials, prompts, or exception messages.

- [ ] **Step 5: Test crash-and-restart ordering**

```python
def test_restart_after_service_crash_reconciles_before_rearming(tmp_path):
    ctx = passing_context(tmp_path)
    ctx.service_factory.return_value.run_forever.side_effect = RuntimeError("crash")
    with pytest.raises(RuntimeError, match="crash"):
        run_day1_launch(ctx.config, ctx.dependencies)
    with pytest.raises(LaunchError, match="LAUNCH_ATTEMPT_REUSED"):
        run_day1_launch(ctx.config, ctx.dependencies)
    ctx.config = replace(
        ctx.config,
        launch_attempt_id="22222222-2222-4222-8222-222222222222",
    )
    write_identity_receipt(ctx, broker_reconciliation_gate="BLOCK")
    bind_launch_attempt(
        ctx.config.launch_attempt_id,
        ctx.config.identity_receipt_path,
        ctx.config.auditor_receipt_path,
        ctx.config.launch_attempt_binding_path,
    )
    with pytest.raises(LaunchError, match="BROKER_RECONCILIATION_REQUIRED"):
        run_day1_launch(ctx.config, ctx.dependencies)
    assert ctx.service_factory.call_count == 1
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []
```

Run: `python -m pytest -q tests/ibkr_paper_30d/test_day1_launch.py`

Expected: PASS, including exact call-order assertions `preflight -> lock -> controls -> arm -> service`, and no executor or IB write-tripwire calls.

- [ ] **Step 6: Commit**

```powershell
git add ibkr_paper_30d/day1_launch.py ibkr_paper_30d/autonomous_state.py tests/ibkr_paper_30d/test_day1_launch.py tests/ibkr_paper_30d/test_autonomous_state.py
git commit -m "feat: own one persistent PAPER service"
```

### Task 5: Persist Service Lifecycle and First-Cycle Evidence

**Files:**
- Modify: `ibkr_paper_30d/autonomous_service.py`
- Preserve: `ibkr_paper_30d/autonomous_state.py` Native/no-predefined-universe contract
- Modify: `tests/ibkr_paper_30d/test_autonomous_service.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_research.py`
- Modify: `tests/ibkr_paper_30d/test_day1_launch.py`

**Interfaces:**
- Consumes: existing `_append_state_event`, `_run_cycle`, and service constructor fields.
- Produces: append-only `AUTONOMOUS_SERVICE_STARTED`, `AUTONOMOUS_CYCLE_STARTED`, `AUTONOMOUS_CYCLE_COMPLETED`, `AUTONOMOUS_CYCLE_FAILED`, and first-cycle `AUTONOMOUS_PAPER_EXPERIMENT_RUNNING` events without raw prompts, credentials, or account IDs.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_run_forever_records_first_cycle_start_and_completion(service, db):
    service._run_cycle = Mock(return_value={
        "status": "PASS",
        "outcome": {"decision": "NO_TRADE"},
        "request": {"decision_cycle_id": "cycle-1"},
    })
    service.stop_event.set = Mock(side_effect=service.stop_event.set)
    service.sleep = lambda _: service.stop_event.set()
    service.run_forever()
    event_types = state_event_types(db)
    assert "AUTONOMOUS_SERVICE_STARTED" in event_types
    assert "AUTONOMOUS_CYCLE_STARTED" in event_types
    assert "AUTONOMOUS_CYCLE_COMPLETED" in event_types
    assert "AUTONOMOUS_PAPER_EXPERIMENT_RUNNING" in event_types


@pytest.mark.parametrize("status", ["UNKNOWN", "PARTIAL", "RECOVERING", "BLOCK"])
def test_unknown_or_nonoperational_status_never_declares_running(service, db, status):
    service._run_cycle = Mock(return_value={
        "status": status,
        "outcome": {"decision": "NO_TRADE"},
        "request": {"decision_cycle_id": "cycle-1"},
    })
    service.sleep = lambda _: service.stop_event.set()
    service.run_forever()
    assert "AUTONOMOUS_PAPER_EXPERIMENT_RUNNING" not in state_event_types(db)


def test_cycle_exception_records_sanitized_failure_and_reraises(service, db):
    service._run_cycle = Mock(side_effect=RuntimeError("secret-token-value"))
    with pytest.raises(RuntimeError):
        service.run_forever()
    event = latest_state_event(db, "AUTONOMOUS_CYCLE_FAILED")
    assert event["error_type"] == "RuntimeError"
    assert "secret-token-value" not in json.dumps(event)
```

- [ ] **Step 2: Run the lifecycle tests and verify RED**

Run: `python -m pytest -q tests/ibkr_paper_30d/test_autonomous_service.py -k "lifecycle or first_cycle or sanitized_failure"`

Expected: FAIL because the lifecycle events do not yet exist.

- [ ] **Step 3: Add events around the existing cycle boundary**

```python
_append_state_event(self.db, "AUTONOMOUS_CYCLE_STARTED", {"trigger": trigger})
try:
    result = self._run_cycle(trigger)
except Exception as exc:
    _append_state_event(
        self.db,
        "AUTONOMOUS_CYCLE_FAILED",
        {"trigger": trigger, "error_type": type(exc).__name__},
    )
    raise
_append_state_event(
    self.db,
    "AUTONOMOUS_CYCLE_COMPLETED",
    {
        "trigger": trigger,
        "status": str(result.get("status") or "UNKNOWN"),
        "decision_cycle_id": str((result.get("request") or {}).get("decision_cycle_id") or ""),
    },
)
```

Apply the wrapper once so scheduled scans, position events, and observation-only follow-ups all use it. Do not persist the request prompt or full model response.

Define an explicit allowlist: `status == "PASS"` and outcome decision in `NO_TRADE`, `PROPOSE_TRADE`, `CANCEL_ORDER`, `MODIFY_ORDER`, `MONITOR_POSITION`, `REDUCE_POSITION`, or `CLOSE_POSITION`. Only after such a completed cycle may the service append `AUTONOMOUS_PAPER_EXPERIMENT_RUNNING` once with the cycle identifier, requested model, reasoning effort, PID, scheduled start, actual service start, and delay seconds. Any absent/unknown/new status is non-operational by default. Never emit the running event merely because the process was constructed.

- [ ] **Step 4: Prove Native discovery does not depend on a candidate whitelist**

```python
def test_empty_initial_universe_can_discover_and_propose_new_symbol():
    value = bundle().model_copy(update={"candidate_screen_results": []})
    research = AutonomousTurn(
        mode=AutonomousTurnMode.RESEARCH,
        research_requests=[ResearchRequest(
            request_id="r1", tool=ResearchTool.MARKET_SCANNER,
            arguments={"scan_code": "TOP_PERC_GAIN"},
            purpose="Discover opportunities without a predefined universe",
        )],
        decision=None, proposal=None, confidence="0.5",
        reasoning_summary="Need broker-wide discovery", reason_codes=["NEED_DISCOVERY"],
    )
    final = AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.PROPOSE_TRADE,
        proposal=proposal(symbol="NVDA"),
        confidence="0.72",
        reasoning_summary="Discovered symbol passes broker feasibility",
        reason_codes=["AUTONOMOUS_DISCOVERY"],
    )
    outcome = AutonomousResearchLoop(
        SequenceProvider([research, final]), FakeToolbox()
    ).run(request(value), value)
    assert value.candidate_screen_results == []
    assert outcome.accepted is True
    assert outcome.proposal.symbol == "NVDA"
```

Also assert the prompt mandate retains `predefined_symbol_universe=false`, `predefined_strategy_family=false`, and `broker_and_account_permissions_are_authoritative=true`. No capability-discovery output may be loaded as a whitelist by the state builder or launcher.

- [ ] **Step 5: Preserve actual-model fail-closed behavior**

Add a regression in which the provider reports any model other than `gpt-5.6-sol`; assert the first cycle fails before the executor's broker method is called and produces a sanitized failure event.

Run: `python -m pytest -q tests/ibkr_paper_30d/test_autonomous_service.py tests/ibkr_paper_30d/test_autonomous_research.py`

Expected: PASS.

- [ ] **Step 6: Run a real-service, fake-dependency launch integration test**

```python
def test_complete_fake_launch_persists_running_event_without_broker_write(tmp_path):
    ctx = passing_context(tmp_path)
    install_real_service_factory(
        ctx,
        provider=NoTradeAttestedProvider(actual_model="gpt-5.6-sol"),
        executor=ctx.executor_tripwire,
        ib_client=ctx.ib_tripwire,
        stop_after_cycles=1,
    )
    run_day1_launch(ctx.config, ctx.dependencies)
    with Database.open(ctx.config.db_path) as db:
        running = latest_state_event(db, "AUTONOMOUS_PAPER_EXPERIMENT_RUNNING")
        assert running["decision"] == "NO_TRADE"
        assert running["launch_attempt_id"] == ctx.config.launch_attempt_id
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []
```

This test must instantiate the real `AutonomousExperimentService`, real state builder, real runtime cycle, and SQLite repositories. Only the Codex provider, read-only toolbox responses, clock, sleep, and IB transport are fake. The executor and IB fake are tripwires, not disconnected mocks.

- [ ] **Step 7: Commit**

```powershell
git add ibkr_paper_30d/autonomous_service.py tests/ibkr_paper_30d/test_autonomous_service.py tests/ibkr_paper_30d/test_autonomous_research.py tests/ibkr_paper_30d/test_day1_launch.py
git commit -m "feat: persist autonomous service lifecycle"
```

### Task 6: Chain the Scheduled Task into the Foreground Launcher

**Files:**
- Create: `RUN_IBKR_DAY1_SERVICE.ps1`
- Modify: `RUN_IBKR_MARKET_DATA_GATE.ps1`
- Modify: `FINALIZE_IBKR_PREREQUISITES.ps1`
- Modify: `tests/ibkr_paper_30d/test_prerequisite_finalizer.py`

**Interfaces:**
- Consumes: `FINALIZE_IBKR_PREREQUISITES.ps1 -SkipTaskRegistration -LaunchAttemptId <uuid>`, `python -m ibkr_paper_30d.day1_launch --launch-attempt-id <same uuid>`, and the market runner's scheduled PASS branches.
- Produces: `RUN_IBKR_DAY1_SERVICE.ps1 -RepoRoot <path> [-ValidateOnly]`, one fresh UUID per process attempt, task settings with 31-day execution and three five-minute restart attempts, weekday plus Owner-logon triggers on the same task, and a foreground process chain.

- [ ] **Step 1: Write failing PowerShell behavior tests**

```python
def test_day1_handoff_validate_only_reports_foreground_commands(tmp_path):
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-File", str(DAY1_RUNNER),
         "-RepoRoot", str(ROOT), "-ValidateOnly"],
        capture_output=True, text=True, check=False,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert result.returncode == 0
    assert "-SkipTaskRegistration" in payload["finalizer_arguments"]
    assert payload["python_arguments"][:3] == ["-m", "ibkr_paper_30d.day1_launch", "--repo-root"]
    assert payload["launch_attempt_id"] in payload["finalizer_arguments"]
    assert payload["launch_attempt_id"] in payload["python_arguments"]
    assert payload["foreground"] is True
    assert payload["broker_write_calls"] == 0
```

Add tests that all three PowerShell files parse with the Windows PowerShell 5.1 AST; no script contains `IBKR_AUTONOMOUS_PAPER_ARMED=true`, `placeOrder`, or a LIVE port argument; the already-PASS scheduled branch invokes `RUN_IBKR_DAY1_SERVICE.ps1`; neither scheduled PASS branch calls `Unregister-ScheduledTask`; and a mocked nonzero finalizer exit prevents launcher invocation. A behavioral finalizer harness must assert the call order `owner authorization validate -> fresh read-only reconciliation -> fresh Auditor V2 -> bind launch attempt`, the exact same UUID in the binding and launcher commands, and no call to `owner_authorization create` under `-SkipTaskRegistration`. The scheduled-task object test must assert both weekday and Owner-logon triggers belong to the same task definition.

- [ ] **Step 2: Run the PowerShell tests and verify RED**

Run: `python -m pytest -q tests/ibkr_paper_30d/test_prerequisite_finalizer.py`

Expected: FAIL because the foreground handoff script and persistent settings do not exist.

- [ ] **Step 3: Implement the foreground handoff script**

```powershell
param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [switch]$ValidateOnly
)
$ErrorActionPreference = "Stop"
$LaunchAttemptId = [guid]::NewGuid().ToString("D")
$FinalizerArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $RepoRoot "FINALIZE_IBKR_PREREQUISITES.ps1"), "-RepoRoot", $RepoRoot, "-SkipTaskRegistration", "-LaunchAttemptId", $LaunchAttemptId)
$LaunchArgs = @("-m", "ibkr_paper_30d.day1_launch", "--repo-root", $RepoRoot, "--launch-attempt-id", $LaunchAttemptId)
if ($ValidateOnly) {
    [ordered]@{ launch_attempt_id = $LaunchAttemptId; finalizer_arguments = $FinalizerArgs; python_arguments = $LaunchArgs; foreground = $true; broker_write_calls = 0 } | ConvertTo-Json -Compress
    exit 0
}
```

Create `state/ibkr_paper_30d/launch` if absent, start a transcript named with UTC timestamp and PID, invoke the finalizer synchronously, require exit code zero, then invoke Python synchronously and return its exact exit code. Put `Stop-Transcript` in `finally`. Never echo environment values or account identifiers.

The same `$LaunchAttemptId` must appear in the fresh binding written by the finalizer and in the launcher CLI. The finalizer's scheduled path validates the existing Owner authorization and must not accept or synthesize the authorization phrase.

- [ ] **Step 4: Replace scheduled unregister behavior with one foreground handoff**

In `RUN_IBKR_MARKET_DATA_GATE.ps1`, define `Invoke-Day1ForegroundService` once and call it only when `-Scheduled` and either the existing validation is already PASS or the newly produced validation becomes PASS. Interactive collection mode retains its current return behavior. Any handoff failure exits nonzero so Task Scheduler can apply bounded restart settings.

- [ ] **Step 5: Install durable single-task settings**

```powershell
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Days 31) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5)
$Triggers = @(
    (New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 9:35AM),
    (New-ScheduledTaskTrigger -AtLogOn -User $OwnerPrincipal)
)
```

Keep the existing task name, action, interactive Owner principal, and highest run level. Register both triggers on that same task: weekday 09:35 for initial market-policy collection and Owner logon for reboot/weekend recovery after a policy already exists. `IgnoreNew` prevents either trigger from creating a second authority. Do not register a second task or add a fixed market-session whitelist to the service.

- [ ] **Step 6: Run focused tests and commit**

Run: `python -m pytest -q tests/ibkr_paper_30d/test_prerequisite_finalizer.py tests/ibkr_paper_30d/test_day1_launch.py`

Expected: PASS; `-ValidateOnly` starts no finalizer, broker connection, service, or order API.

```powershell
git add RUN_IBKR_DAY1_SERVICE.ps1 RUN_IBKR_MARKET_DATA_GATE.ps1 FINALIZE_IBKR_PREREQUISITES.ps1 tests/ibkr_paper_30d/test_prerequisite_finalizer.py
git commit -m "feat: persist scheduled PAPER launch"
```

### Task 7: Verify the Complete Launch Without a Broker Write

**Files:**
- Modify only if a test exposes a defect in files already named above.
- Preserve: auditor runtime payloads and trust-anchor files byte-for-byte.

**Interfaces:**
- Consumes: all completed tasks.
- Produces: reproducible verification evidence and an Owner-only elevated installation instruction; it does not execute the finalizer or start Day 1 from Codex.

- [ ] **Step 1: Load the Task 0 baseline before verification**

```powershell
Get-FileHash -Algorithm SHA256 auditor_runtime\* | Sort-Object Path
Get-FileHash -Algorithm SHA256 AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json,docs\contracts\runtime_hashes_20260224.json | Sort-Object Path
```

Compare command output to `docs/superpowers/plans/2026-09-23-day1-implementation-baseline.json` and the exact Task 0 values. Any mismatch is a release blocker; do not establish a new baseline here.

- [ ] **Step 2: Run focused launch and runtime tests**

Run: `python -m pytest -q tests/ibkr_paper_30d/test_owner_authorization.py tests/ibkr_paper_30d/test_day1_launch.py tests/ibkr_paper_30d/test_autonomous_service.py tests/ibkr_paper_30d/test_autonomous_research.py tests/ibkr_paper_30d/test_ibkr_readonly_session.py tests/ibkr_paper_30d/test_prerequisite_tools.py tests/ibkr_paper_30d/test_prerequisite_finalizer.py tests/ibkr_paper_30d/test_auditor_runtime.py tests/ibkr_paper_30d/test_auditor_runtime_v2.py`

Expected: PASS with both the executor and IB transport tripwires reporting no calls.

- [ ] **Step 3: Run the full IBKR PAPER suite**

Run: `python -m pytest -q tests/ibkr_paper_30d`

Expected: all tests PASS, no skip newly introduced by this plan, and no real broker-write adapter used.

- [ ] **Step 4: Parse every changed PowerShell file with Windows PowerShell 5.1**

```powershell
$Files = @("FINALIZE_IBKR_PREREQUISITES.ps1", "RUN_IBKR_MARKET_DATA_GATE.ps1", "RUN_IBKR_DAY1_SERVICE.ps1")
foreach ($File in $Files) {
    $Tokens = $null
    $Errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile((Resolve-Path $File), [ref]$Tokens, [ref]$Errors)
    if ($Errors.Count) { throw "$File PowerShell parse failure: $($Errors.Message -join '; ')" }
}
```

Expected: no output and exit code zero.

- [ ] **Step 5: Run a fake-only launcher dry run and repository checks**

Run: `python -m pytest -q tests/ibkr_paper_30d/test_day1_launch.py::test_complete_fake_launch_persists_running_event_without_broker_write`

Expected: PASS with all fake external gates PASS, one real service cycle using fully fake dependencies, a persisted SQLite running event, zero executor/IB tripwire calls, and no modification beneath the real `state/ibkr_paper_30d` directory. The test must use `tmp_path` for its repository, receipts, launch evidence, and database.

Run: `git diff --check`

Run: `git status --short`

Expected: no whitespace errors; only planned tracked changes plus the Owner's pre-existing untracked artifacts.

- [ ] **Step 6: Recompute protected hashes and inspect the final diff**

```powershell
Get-FileHash -Algorithm SHA256 auditor_runtime\* | Sort-Object Path
Get-FileHash -Algorithm SHA256 AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json,docs\contracts\runtime_hashes_20260224.json | Sort-Object Path
$BaseHead = (Get-Content docs\superpowers\plans\2026-09-23-day1-implementation-baseline.json | ConvertFrom-Json).base_head
git diff --stat "$BaseHead..HEAD"
git diff "$BaseHead..HEAD" -- auditor_runtime AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json docs/contracts/runtime_hashes_20260224.json
```

Expected: protected hashes equal Step 1 and protected-path diff is empty.

- [ ] **Step 7: Produce the readiness report and stop for the Owner**

Report exact test count, pass/fail count, PowerShell validation, protected hashes changed `false`, trust-anchor impact `none`, real broker-write calls `0`, installed task settings pending `true`, and `SAFE_TO_RERUN_FINALIZER=true` only if every prior check passes.

The next action belongs to the Owner: run `FINALIZE_IBKR_PREREQUISITES.ps1 -OwnerAuthorization "AUTHORIZE 30-DAY PAPER EXPERIMENT"` once in elevated Windows PowerShell to create/validate the immutable authorization, refresh Auditor V2, and replace the existing task settings. Codex must not run that elevated finalizer, arm PAPER manually, submit a test order, or declare `AUTONOMOUS_PAPER_EXPERIMENT_RUNNING` before observing the persisted first-cycle evidence.
