# IBKR Paper 30-Day Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify an isolated, fail-closed IBKR paper-experiment infrastructure using a fake broker and safe read-only broker inspection, without enabling any real broker order write.

**Architecture:** A standalone Python package owns deterministic state, evidence, risk, market-data, invocation, alerting, reconciliation, and audit boundaries. `IBKRPaperExecutionAdapter` is represented by an interface and fake implementation for writes; the real IBKR implementation exposes read-only methods and raises a hard authorization error for submit, modify, and cancel.

**Tech Stack:** Python 3.11, pytest, Pydantic, stdlib `sqlite3`/`hashlib`/`json`, pywin32 (`win32event`, `win32evtlogutil`), SMTP over `smtplib`, and official `ibapi` for later read-only inspection.

**Spec:** `C:\AI_VAULT\CODEX_IBKR_PAPER_ARCHITECTURE_DESIGN_V2.md`

## Global Constraints

- `PAPER_ONLY=true`
- `LIVE_ALLOWED=false`
- `REAL_MONEY_ALLOWED=false`
- `DIRECTIONAL_TRADING_AUTHORIZED=false`
- `TEST_ORDER_AUTHORIZED=false`
- `BROKER_WRITE_AUTHORIZED=false`
- Do not modify `brain/**`, `tmp_agent/brain_v9/**`, HIVE, H2, H2-R2, existing order executors, or live-account configuration.
- Never print full account IDs, credentials, SMTP passwords, auth tokens, 2FA secrets, or session secrets.
- Every real adapter write method must fail before making an IBKR API call.
- SQLite uses WAL, `synchronous=FULL`, foreign keys, explicit transactions, and append-only evidence.
- Every component follows RED -> minimal implementation -> focused GREEN -> regression -> fault test -> scoped commit.

## Review Focus

- A process ID can be reused after a crash; Task 4 tests that PID alone cannot establish lock ownership.
- UTC may move backward while a monotonic clock remains valid; Task 9 tests negative quote age and timestamp provenance.
- An SMTP send can succeed while receipt persistence fails; Task 12 tests restart-safe deduplication and delivery reconciliation.
- IBKR order visibility may be incomplete across sessions; Tasks 10 and 16 test that incomplete evidence remains ambiguous rather than not-found.
- A valid Trader schema can still contradict frozen state; Task 8 tests semantic state and authority validation after schema parsing.

## File map

```text
ibkr_paper_30d/
  __init__.py                 public package metadata only
  config.py                   validated settings and authorization constants
  types.py                    enums and immutable shared models
  canonical.py                canonical JSON and SHA-256 helpers
  redaction.py                secret/account sanitization
  persistence.py              SQLite connection, migrations, transactions
  repositories.py             typed append-only persistence operations
  state_machine.py            system/broker/execution/kill transition guards
  execution_lock.py           Windows mutex plus SQLite ownership evidence
  risk.py                     deterministic Month-1 risk policy
  subledger.py                isolated USD 500 experiment accounting
  evidence.py                 durable freeze/read-back verification
  trader_invocation.py        provider-neutral Codex invocation contract
  market_data.py              snapshot normalization and freshness gate
  broker.py                   broker protocol and hard-disabled real writes
  fake_broker.py              deterministic broker/fault simulator
  ibkr_readonly.py            official-API read-only session inspection
  reconciliation.py           broker/local truth comparison and recovery
  alerts.py                   local outbox, SMTP, Event Log, optional toast
  orchestrator.py             scheduler/event loop without order authority
  auditor_export.py           immutable manifest/export publisher
  auditor.py                  restricted read-only artifact evaluator
  cli.py                      explicit local commands and report generation
tests/ibkr_paper_30d/          focused and fault-injection pytest suite
state/ibkr_paper_30d/          runtime database and immutable exports
logs/ibkr_paper_30d/           redacted operational logs
```

---

### Task 1: Package, configuration, shared types, canonicalization, and redaction

**Files:**
- Create: `ibkr_paper_30d/__init__.py`
- Create: `ibkr_paper_30d/config.py`
- Create: `ibkr_paper_30d/types.py`
- Create: `ibkr_paper_30d/canonical.py`
- Create: `ibkr_paper_30d/redaction.py`
- Create: `tests/ibkr_paper_30d/test_config_and_redaction.py`

**Interfaces:**
- Produces: `Settings.load(env)`, `new_uuid7()`, `canonical_bytes(value)`, `sha256_json(value)`, `redact_text(text)`, and the four persisted state enums.
- Consumes: Python stdlib and Pydantic only.

- [ ] **Step 1: Write failing configuration and redaction tests**

```python
def test_broker_writes_are_hard_disabled():
    settings = Settings.load({})
    assert settings.paper_only is True
    assert settings.broker_write_authorized is False

def test_redaction_masks_accounts_and_secrets():
    raw = "account=DU1234567 EMAIL_PASS=hunter2 token=abc123"
    clean = redact_text(raw)
    assert "DU1234567" not in clean
    assert "hunter2" not in clean
    assert "abc123" not in clean

def test_canonical_hash_is_key_order_independent():
    assert sha256_json({"b": 2, "a": 1}) == sha256_json({"a": 1, "b": 2})
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_config_and_redaction.py -q`

Expected: collection fails because `ibkr_paper_30d.config` does not exist.

- [ ] **Step 3: Implement immutable safety defaults and deterministic helpers**

```python
class Settings(BaseModel, frozen=True):
    paper_only: Literal[True] = True
    broker_write_authorized: Literal[False] = False
    experiment_allocation: Decimal = Decimal("500.00")
    state_dir: Path = Path("state/ibkr_paper_30d")

    @classmethod
    def load(cls, env: Mapping[str, str]) -> "Settings":
        if env.get("BROKER_WRITE_AUTHORIZED", "false").lower() != "false":
            raise ValueError("broker writes are outside current authority")
        return cls()

def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

def new_uuid7(now_ms: int | None = None) -> uuid.UUID:
    timestamp = int(time.time_ns() // 1_000_000 if now_ms is None else now_ms)
    if not 0 <= timestamp < 1 << 48:
        raise ValueError("UUIDv7 timestamp is outside 48-bit range")
    random_bits = secrets.randbits(74)
    value = (timestamp << 80) | (0x7 << 76)
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return uuid.UUID(int=value)
```

- [ ] **Step 4: Run GREEN plus a secret-pattern regression scan**

Run: `python -m pytest tests/ibkr_paper_30d/test_config_and_redaction.py -q`

Expected: all tests pass.

Run: `rg -n "DU[0-9]{5,}|EMAIL_PASS=.*[^*]|BROKER_WRITE_AUTHORIZED=true" ibkr_paper_30d tests/ibkr_paper_30d`

Expected: no secret values or write authorization.

- [ ] **Step 5: Commit the package safety foundation**

```powershell
git add ibkr_paper_30d tests/ibkr_paper_30d/test_config_and_redaction.py
git commit -m "feat(ibkr-paper): add isolated safety foundation"
```

### Task 2: SQLite migrations and immutable evidence repositories

**Files:**
- Create: `ibkr_paper_30d/persistence.py`
- Create: `ibkr_paper_30d/repositories.py`
- Create: `tests/ibkr_paper_30d/test_persistence.py`

**Interfaces:**
- Consumes: `canonical_bytes`, `sha256_json`, shared IDs and enums.
- Produces: `Database.open(path)`, `Database.transaction()`, `EventRepository.append(...)`, and typed repositories for every V2 table.

- [ ] **Step 1: Write RED tests for durability, rollback, foreign keys, hash chains, and immutability**

```python
def test_committed_event_survives_reopen(db_path):
    with Database.open(db_path) as db:
        EventRepository(db).append("SYSTEM_BOOTING", {"boot": 1})
    with Database.open(db_path) as db:
        assert EventRepository(db).verify_chain().valid is True

def test_incomplete_transaction_rolls_back(db_path):
    with pytest.raises(RuntimeError):
        with Database.open(db_path).transaction() as tx:
            EventRepository(tx).append("X", {"n": 1})
            raise RuntimeError("crash")
    with Database.open(db_path) as db:
        assert EventRepository(db).count() == 0

def test_immutable_event_rejects_update(db):
    event_id = EventRepository(db).append("X", {"n": 1})
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE state_events SET event_type='Y' WHERE event_id=?", (event_id,))
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_persistence.py -q`

Expected: import failure for `persistence`.

- [ ] **Step 3: Implement migrations and transaction boundaries**

```python
def configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")

IMMUTABLE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS state_events_no_update
BEFORE UPDATE ON state_events BEGIN SELECT RAISE(ABORT, 'immutable'); END;
"""
```

Create every V1/V2 table, unique order/invocation constraints, append-only triggers, schema version table, and hash-chain verification in a single idempotent migration sequence.

- [ ] **Step 4: Run GREEN and crash/reopen regression**

Run: `python -m pytest tests/ibkr_paper_30d/test_persistence.py -q`

Expected: all persistence tests pass.

- [ ] **Step 5: Commit persistence**

```powershell
git add ibkr_paper_30d/persistence.py ibkr_paper_30d/repositories.py tests/ibkr_paper_30d/test_persistence.py
git commit -m "feat(ibkr-paper): add durable immutable state store"
```

### Task 3: Complete fail-closed state machines

**Files:**
- Create: `ibkr_paper_30d/state_machine.py`
- Create: `tests/ibkr_paper_30d/test_state_machine.py`

**Interfaces:**
- Consumes: all state enums and `EventRepository`.
- Produces: `TransitionGuard.transition(machine, current, target, context) -> TransitionReceipt`.

- [ ] **Step 1: Write parameterized RED tests for every approved edge and all other pairs**

```python
@pytest.mark.parametrize("source,target", sorted(ALLOWED_SYSTEM_EDGES))
def test_allowed_system_edges(source, target, guard):
    assert guard.transition("system", source, target, valid_context()).accepted

@pytest.mark.parametrize("source,target", forbidden_pairs(SystemState, ALLOWED_SYSTEM_EDGES))
def test_unlisted_system_edges_fail_closed(source, target, guard):
    receipt = guard.transition("system", source, target, valid_context())
    assert receipt.accepted is False
    assert receipt.fail_closed is True
```

Repeat the same actual pair-generation test for broker, execution, and kill-switch enums.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_state_machine.py -q`

Expected: import failure for `TransitionGuard`.

- [ ] **Step 3: Implement explicit edge sets and guarded transition persistence**

```python
ALLOWED_KILL_EDGES = {
    (KillSwitchState.CLEAR, KillSwitchState.TRIGGERED),
    (KillSwitchState.TRIGGERED, KillSwitchState.RECOVERY_REVIEW),
    (KillSwitchState.RECOVERY_REVIEW, KillSwitchState.CLEAR),
    (KillSwitchState.RECOVERY_REVIEW, KillSwitchState.TRIGGERED),
}

def transition(self, machine, current, target, context):
    accepted = (current, target) in self.edges[machine] and self.preconditions(machine, target, context)
    self.events.append("STATE_TRANSITION", {"machine": machine, "from": current.value,
                                             "to": target.value, "accepted": accepted})
    return TransitionReceipt(accepted=accepted, fail_closed=not accepted)
```

- [ ] **Step 4: Run GREEN and assert complete pair coverage**

Run: `python -m pytest tests/ibkr_paper_30d/test_state_machine.py -q`

Expected: every enum pair is exercised and all tests pass.

- [ ] **Step 5: Commit state machines**

```powershell
git add ibkr_paper_30d/state_machine.py tests/ibkr_paper_30d/test_state_machine.py
git commit -m "feat(ibkr-paper): enforce fail-closed state machines"
```

### Task 4: EXECUTION_LOCK_V1

**Files:**
- Create: `ibkr_paper_30d/execution_lock.py`
- Create: `tests/ibkr_paper_30d/test_execution_lock.py`

**Interfaces:**
- Consumes: `Database`, lock-event repository, `win32event`.
- Produces: `ExecutionLock.acquire(owner)`, `heartbeat(receipt)`, `release(receipt)`, and `recover_stale(evidence)`.

- [ ] **Step 1: Write RED tests for dual ownership, stale owner, PID reuse, crash, and ambiguity**

```python
def test_second_writer_cannot_acquire(lock_factory):
    first = lock_factory().acquire(owner(pid=100, start="A"))
    second = lock_factory().acquire(owner(pid=200, start="B"))
    assert first.acquired is True
    assert second.acquired is False

def test_pid_reuse_does_not_prove_same_owner(lock_factory):
    stale = owner(pid=100, start="A")
    observed = owner(pid=100, start="B")
    result = lock_factory().recover_stale(stale, observed)
    assert result.state == "EXECUTION_LOCK_AMBIGUOUS"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_execution_lock.py -q`

Expected: missing `ExecutionLock`.

- [ ] **Step 3: Implement named mutex plus atomic DB owner generation**

```python
MUTEX_NAME = r"Local\CodexIbkrPaper30DExecutionLockV1"

def acquire(self, owner: LockOwner) -> LockReceipt:
    handle = win32event.CreateMutex(None, False, MUTEX_NAME)
    wait = win32event.WaitForSingleObject(handle, 0)
    if wait not in (win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED):
        return LockReceipt(acquired=False, reason="OS_MUTEX_HELD")
    return self._claim_database_generation(owner, handle, abandoned=wait == win32event.WAIT_ABANDONED)
```

An abandoned mutex always enters recovery and cannot immediately grant order authority.

- [ ] **Step 4: Run GREEN and subprocess contention tests**

Run: `python -m pytest tests/ibkr_paper_30d/test_execution_lock.py -q`

Expected: all lock tests pass.

- [ ] **Step 5: Commit execution locking**

```powershell
git add ibkr_paper_30d/execution_lock.py tests/ibkr_paper_30d/test_execution_lock.py
git commit -m "feat(ibkr-paper): add recoverable single-writer lock"
```

### Task 5: Deterministic Month-1 risk engine

**Files:**
- Create: `ibkr_paper_30d/risk.py`
- Create: `tests/ibkr_paper_30d/test_risk.py`

**Interfaces:**
- Produces: `RiskPolicy.month1()`, `RiskEngine.evaluate(inputs) -> RiskDecision`.
- Outputs only: `PASS`, `BLOCK`, or `REDUCE_SIZE` with deterministic reason codes.

- [ ] **Step 1: Write RED boundary tests for all seven limits**

```python
@pytest.mark.parametrize("field,below,at,above", [
    ("estimated_loss", "24.99", "25.00", "25.01"),
    ("position_capital", "199.99", "200.00", "200.01"),
    ("total_open_risk", "74.99", "75.00", "75.01"),
    ("daily_loss", "39.99", "40.00", "40.01"),
    ("weekly_drawdown", "59.99", "60.00", "60.01"),
    ("total_drawdown", "99.99", "100.00", "100.01"),
])
def test_money_limit_boundaries(field, below, at, above, base_inputs):
    assert evaluate_with(base_inputs, field, below).result == RiskResult.PASS
    assert evaluate_with(base_inputs, field, at).result == RiskResult.BLOCK
    assert evaluate_with(base_inputs, field, above).result == RiskResult.BLOCK

def test_fourth_concurrent_position_is_blocked(base_inputs):
    assert evaluate_with(base_inputs, "concurrent_positions", 3).result == RiskResult.BLOCK
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_risk.py -q`

Expected: missing risk module.

- [ ] **Step 3: Implement Decimal-only policy evaluation**

```python
class RiskPolicy(BaseModel, frozen=True):
    max_loss_per_trade: Decimal = Decimal("0.05")
    max_position_capital: Decimal = Decimal("0.40")
    max_total_open_risk: Decimal = Decimal("0.15")
    max_concurrent_positions: int = 3
    max_daily_loss: Decimal = Decimal("0.08")
    max_weekly_drawdown: Decimal = Decimal("0.12")
    max_total_drawdown: Decimal = Decimal("0.20")
```

Evaluate every threshold against the correct equity basis and combine failures without short-circuiting evidence.

- [ ] **Step 4: Run GREEN plus randomized determinism regression**

Run: `python -m pytest tests/ibkr_paper_30d/test_risk.py -q`

Expected: all tests pass and repeated identical inputs produce byte-identical results.

- [ ] **Step 5: Commit risk engine**

```powershell
git add ibkr_paper_30d/risk.py tests/ibkr_paper_30d/test_risk.py
git commit -m "feat(ibkr-paper): add deterministic month-one risk gate"
```

### Task 6: USD 500 experiment subledger

**Files:**
- Create: `ibkr_paper_30d/subledger.py`
- Create: `tests/ibkr_paper_30d/test_subledger.py`

**Interfaces:**
- Consumes: immutable fills, fees, broker snapshots, and `subledger_events`.
- Produces: `Subledger.project(events)`, `Subledger.reconcile(broker, projection)`.

- [ ] **Step 1: Write RED accounting and isolation tests**

```python
def test_broker_buying_power_cannot_raise_allocation():
    snapshot = broker_snapshot(cash="100000.00", buying_power="400000.00")
    ledger = Subledger.start(Decimal("500.00"))
    assert ledger.reconcile(snapshot).maximum_allocated_capital == Decimal("500.00")

def test_fill_fee_and_mark_update_equity():
    events = [buy_fill("100.00"), fee("1.00"), mark("110.00")]
    state = Subledger.project(events)
    assert state.equity == Decimal("509.00")
    assert state.high_water_mark == Decimal("509.00")
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_subledger.py -q`

Expected: missing subledger module.

- [ ] **Step 3: Implement append-only Decimal projections and reconciliation**

```python
@dataclass(frozen=True)
class SubledgerState:
    allocation: Decimal
    cash: Decimal
    settled_cash: Decimal
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    equity: Decimal
    high_water_mark: Decimal
    drawdown: Decimal
```

- [ ] **Step 4: Run GREEN and restart/reprojection regression**

Run: `python -m pytest tests/ibkr_paper_30d/test_subledger.py -q`

Expected: fills, fees, P&L, high-water, drawdown, restart, and mismatch tests pass.

- [ ] **Step 5: Commit subledger**

```powershell
git add ibkr_paper_30d/subledger.py tests/ibkr_paper_30d/test_subledger.py
git commit -m "feat(ibkr-paper): isolate five-hundred-dollar subledger"
```

### Task 7: PRETRADE_EVIDENCE_FREEZE_V1

**Files:**
- Create: `ibkr_paper_30d/evidence.py`
- Create: `tests/ibkr_paper_30d/test_evidence.py`

**Interfaces:**
- Produces: `EvidenceFreezer.freeze(record) -> EvidenceReceipt` and `verify(receipt)`.

- [ ] **Step 1: Write RED tests for canonical commit, read-back, successor-only correction, and crash windows**

```python
def test_freeze_commits_and_reads_back_same_hash(freezer):
    receipt = freezer.freeze({"decision_id": "d1", "value": "x"})
    assert receipt.durable is True
    assert freezer.verify(receipt).valid is True

def test_frozen_record_cannot_be_overwritten(freezer):
    freezer.freeze({"decision_id": "d1", "value": "x"})
    with pytest.raises(ImmutableRecordError):
        freezer.freeze({"decision_id": "d1", "value": "y"})
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_evidence.py -q`

Expected: missing evidence module.

- [ ] **Step 3: Implement transaction commit and independent read-back verification**

```python
def freeze(self, record: Mapping[str, object]) -> EvidenceReceipt:
    payload = canonical_bytes(record)
    digest = hashlib.sha256(payload).hexdigest()
    with self.db.transaction() as tx:
        self.repo.insert(tx, record["decision_id"], payload, digest)
    stored = self.repo.read(record["decision_id"])
    if hashlib.sha256(stored.payload).hexdigest() != digest:
        raise EvidenceIntegrityError("durable read-back mismatch")
    return EvidenceReceipt(record["decision_id"], digest, durable=True)
```

- [ ] **Step 4: Run GREEN with injected failures before, during, and after commit**

Run: `python -m pytest tests/ibkr_paper_30d/test_evidence.py -q`

Expected: committed evidence survives; incomplete transactions roll back; post-commit exceptions preserve immutable evidence.

- [ ] **Step 5: Commit evidence freeze**

```powershell
git add ibkr_paper_30d/evidence.py tests/ibkr_paper_30d/test_evidence.py
git commit -m "feat(ibkr-paper): freeze durable pretrade evidence"
```

### Task 8: CODEX_TRADER_INVOCATION_ADAPTER_V1

**Files:**
- Create: `ibkr_paper_30d/trader_invocation.py`
- Create: `tests/ibkr_paper_30d/test_trader_invocation.py`

**Interfaces:**
- Consumes: durable `TraderInputBundle`, model policy, provider protocol.
- Produces: `TraderInvocationAdapter.invoke(request, bundle) -> ValidatedTraderResult`.

- [ ] **Step 1: Write RED tests for all required decision and failure classes**

```python
def test_duplicate_cycle_accepts_at_most_one_result(adapter, valid_bundle):
    first = adapter.invoke(request(cycle="c1"), valid_bundle)
    second = adapter.invoke(request(cycle="c1", invocation="i2"), valid_bundle)
    assert first.accepted is True
    assert second.accepted is False
    assert second.effective_decision == "NO_TRADE"

@pytest.mark.parametrize("provider_result", [MALFORMED, TIMEOUT, WRONG_SCHEMA,
                                               STALE_HASH, AUTHORITY_EXCESS,
                                               STATE_CONTRADICTION])
def test_invalid_results_fail_to_no_trade(adapter_for, valid_bundle, provider_result):
    result = adapter_for(provider_result).invoke(request(), valid_bundle)
    assert result.validation == "INVALID"
    assert result.effective_decision == "NO_TRADE"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_trader_invocation.py -q`

Expected: missing invocation adapter.

- [ ] **Step 3: Implement strict Pydantic schemas, model policy, bounded retry, and cycle idempotency**

```python
class TraderDecision(str, Enum):
    NO_TRADE = "NO_TRADE"
    PROPOSE_TRADE = "PROPOSE_TRADE"
    MONITOR_POSITION = "MONITOR_POSITION"
    REDUCE_POSITION = "REDUCE_POSITION"
    CLOSE_POSITION = "CLOSE_POSITION"
    PAUSE_FOR_REVIEW = "PAUSE_FOR_REVIEW"

def validate_result(raw, request, bundle):
    parsed = TraderOutput.model_validate(raw)
    if parsed.input_bundle_sha256 != bundle.sha256:
        return invalid("INPUT_HASH_MISMATCH")
    if parsed.decision_cycle_id != request.decision_cycle_id:
        return invalid("CYCLE_MISMATCH")
    return semantic_validate(parsed, bundle)
```

- [ ] **Step 4: Run GREEN and confirm previous decisions are never reused**

Run: `python -m pytest tests/ibkr_paper_30d/test_trader_invocation.py -q`

Expected: valid output, `NO_TRADE`, proposal, malformed, timeout, duplicate, stale, model failure, explicit fallback, and semantic contradiction tests pass.

- [ ] **Step 5: Commit Trader invocation adapter**

```powershell
git add ibkr_paper_30d/trader_invocation.py tests/ibkr_paper_30d/test_trader_invocation.py
git commit -m "feat(ibkr-paper): add auditable trader invocation adapter"
```

### Task 9: MARKET_DATA_GATE_V1

**Files:**
- Create: `ibkr_paper_30d/market_data.py`
- Create: `tests/ibkr_paper_30d/test_market_data.py`

**Interfaces:**
- Produces: `MarketDataSnapshot.freeze(quotes)`, `MarketDataGate.evaluate(snapshot, requirements, now)`.

- [ ] **Step 1: Write RED tests for freshness, entitlement, timestamps, and quote shape**

```python
@pytest.mark.parametrize("mutation,reason", [
    ({"realtime_or_delayed": "DELAYED"}, "DELAYED_DATA"),
    ({"bid": None}, "MISSING_BID_ASK"),
    ({"bid": "101", "ask": "100"}, "CROSSED_MARKET"),
    ({"data_entitlement_status": "UNAVAILABLE"}, "ENTITLEMENT_UNAVAILABLE"),
    ({"source_health": "DEGRADED"}, "SOURCE_UNHEALTHY"),
])
def test_invalid_quotes_block(mutation, reason, fresh_quote, gate):
    result = gate.evaluate(fresh_quote.model_copy(update=mutation), NEW_TRADE)
    assert result.status == "BLOCK"
    assert reason in result.reason_codes

def test_negative_age_beyond_clock_skew_blocks(gate, fresh_quote):
    quote = fresh_quote.model_copy(update={"quote_timestamp": future_time(seconds=10)})
    assert gate.evaluate(quote, NEW_TRADE).status == "BLOCK"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_market_data.py -q`

Expected: missing market-data module.

- [ ] **Step 3: Implement versioned thresholds and exact snapshot binding**

```python
class MarketDataPolicy(BaseModel, frozen=True):
    max_new_trade_age_ms: int
    max_position_management_age_ms: int
    max_clock_skew_ms: int
    require_realtime_for_new_trade: bool = True
    require_bid_ask_for_spread: bool = True
```

Use Decimal for prices, UTC plus monotonic receipt metadata, explicit session/entitlement enums, and snapshot SHA-256 in every gate result.

- [ ] **Step 4: Run GREEN including new-trade versus management thresholds**

Run: `python -m pytest tests/ibkr_paper_30d/test_market_data.py -q`

Expected: all quote and binding tests pass.

- [ ] **Step 5: Commit market-data authority**

```powershell
git add ibkr_paper_30d/market_data.py tests/ibkr_paper_30d/test_market_data.py
git commit -m "feat(ibkr-paper): enforce market data freshness gate"
```

### Task 10: Fake broker, order identity, and adapter write contracts

**Files:**
- Create: `ibkr_paper_30d/broker.py`
- Create: `ibkr_paper_30d/fake_broker.py`
- Create: `tests/ibkr_paper_30d/test_fake_broker.py`
- Create: `tests/ibkr_paper_30d/test_order_identity.py`

**Interfaces:**
- Produces: `BrokerReadProtocol`, `BrokerWriteProtocol`, `FakeIBKRPaperBroker`, `IBKRPaperExecutionAdapter` with fake-only writes.
- Consumes: evidence/risk/lock/identity receipts and immutable order command.

- [ ] **Step 1: Write RED tests for broker behavior, idempotency, and hard real-write disablement**

```python
def test_duplicate_idempotency_key_transmits_once(fake_adapter, command):
    first = fake_adapter.submit_order(command)
    second = fake_adapter.submit_order(command)
    assert first.status == "SUCCESS"
    assert second.status == "BLOCKED"
    assert fake_adapter.broker.submit_count == 1

def test_real_adapter_write_is_unconditionally_disabled(real_adapter, command):
    with pytest.raises(BrokerWriteNotAuthorized):
        real_adapter.submit_order(command)
    assert real_adapter.api_write_calls == 0

def test_unknown_submit_is_never_retried(fake_adapter, command):
    fake_adapter.broker.inject("UNKNOWN_SUBMIT_RESULT")
    result = fake_adapter.submit_order(command)
    assert result.status == "UNKNOWN"
    assert fake_adapter.broker.submit_count == 1
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_fake_broker.py tests/ibkr_paper_30d/test_order_identity.py -q`

Expected: missing broker modules.

- [ ] **Step 3: Implement fake lifecycle and immutable identity mappings**

```python
@dataclass(frozen=True)
class OrderIdentity:
    decision_id: str
    idempotency_key: str
    client_order_id: str
    order_ref: str
    ibkr_order_id: int | None = None
    perm_id: int | None = None

class RealWriteDisabledAdapter:
    def submit_order(self, command):
        raise BrokerWriteNotAuthorized("REAL_PAPER_ORDER_WRITE_AUTHORIZED=false")
    cancel_order = submit_order
    modify_order = submit_order
```

Fake behavior includes connect, identity, account, positions, orders, executions, fills, partial fills, rejection, cancel, modify, disconnect, 2FA, delayed ACK, unknown submit, duplicates, restart, and configurable history limits.

- [ ] **Step 4: Run GREEN across all fake broker scenarios**

Run: `python -m pytest tests/ibkr_paper_30d/test_fake_broker.py tests/ibkr_paper_30d/test_order_identity.py -q`

Expected: all fake/write-contract tests pass and real API write-call count remains zero.

- [ ] **Step 5: Commit fake broker and contracts**

```powershell
git add ibkr_paper_30d/broker.py ibkr_paper_30d/fake_broker.py tests/ibkr_paper_30d/test_fake_broker.py tests/ibkr_paper_30d/test_order_identity.py
git commit -m "feat(ibkr-paper): add fake broker and order contracts"
```

### Task 11: Reconciliation and deterministic recovery

**Files:**
- Create: `ibkr_paper_30d/reconciliation.py`
- Create: `tests/ibkr_paper_30d/test_reconciliation.py`

**Interfaces:**
- Consumes: broker snapshots, local mappings, configurable `not_found_confirmation_window`.
- Produces: `Reconciler.reconcile_account()` and `reconcile_order()` with found/not-found/ambiguous outcomes.

- [ ] **Step 1: Write RED tests for every crash window and proof outcome**

```python
def test_unset_real_not_found_window_cannot_prove_absence(reconciler):
    result = reconciler.with_window(None).reconcile_order(missing_identity())
    assert result.outcome == "ORDER_STATE_AMBIGUOUS"

def test_two_complete_snapshots_prove_not_found(fake_reconciler):
    fake_reconciler.clock.advance(fake_reconciler.window)
    result = fake_reconciler.reconcile_order(missing_identity())
    assert result.outcome == "ORDER_NOT_FOUND_WITH_PROOF"

def test_multiple_matches_are_ambiguous(fake_reconciler):
    fake_reconciler.broker.seed_matching_orders(2)
    assert fake_reconciler.reconcile_order(identity()).outcome == "ORDER_STATE_AMBIGUOUS"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_reconciliation.py -q`

Expected: missing reconciler.

- [ ] **Step 3: Implement broker-authoritative diffing and crash-window recovery**

```python
class ReconcileOutcome(str, Enum):
    ORDER_FOUND = "ORDER_FOUND"
    ORDER_NOT_FOUND_WITH_PROOF = "ORDER_NOT_FOUND_WITH_PROOF"
    ORDER_STATE_AMBIGUOUS = "ORDER_STATE_AMBIGUOUS"

def reconcile_order(self, identity):
    first = self.broker.complete_snapshot(identity)
    if first.unique_match:
        return found(first)
    if self.window is None or not first.complete:
        return ambiguous("INCOMPLETE_PROOF")
    self.clock.wait(self.window)
    second = self.broker.complete_snapshot(identity)
    return prove_from_pair(first, second)
```

- [ ] **Step 4: Run GREEN for all mandated recovery scenarios**

Run: `python -m pytest tests/ibkr_paper_30d/test_reconciliation.py -q`

Expected: crash, disconnect, 2FA, auth, DB, subledger, duplicate, and market-data recovery cases pass.

- [ ] **Step 5: Commit reconciliation**

```powershell
git add ibkr_paper_30d/reconciliation.py tests/ibkr_paper_30d/test_reconciliation.py
git commit -m "feat(ibkr-paper): add deterministic broker reconciliation"
```

### Task 12: OWNER_CRITICAL_ALERT_V1

**Files:**
- Create: `ibkr_paper_30d/alerts.py`
- Create: `tests/ibkr_paper_30d/test_alerts.py`

**Interfaces:**
- Consumes: alert repository, redaction, read-only `Secrets/email_alerts.env` loader.
- Produces: `AlertService.raise_critical(event)`, durable SMTP outbox, Event Log receipts.

- [ ] **Step 1: Write RED tests for persist-first delivery, retries, degradation, and restart deduplication**

```python
def test_fail_closed_precedes_delivery(alert_service, system):
    alert_service.raise_critical(event("KILL_SWITCH_TRIGGERED"))
    assert system.new_order_authority is False
    assert alert_service.repo.persisted_count == 1
    assert alert_service.smtp.attempt_count == 1

def test_smtp_success_before_receipt_crash_is_reconciled_without_duplicate(alert_service):
    alert_service.inject("CRASH_AFTER_SMTP_BEFORE_RECEIPT")
    with pytest.raises(InjectedCrash):
        alert_service.raise_critical(event("BROKER_2FA_REAUTH_REQUIRED"))
    resumed = alert_service.restart()
    resumed.reconcile_delivery_outbox()
    assert resumed.delivery_state in {"CONFIRMED", "OWNER_REVIEW_REQUIRED"}
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_alerts.py -q`

Expected: missing alert service.

- [ ] **Step 3: Implement local persistence, Event Log, redacted SMTP, and durable retry schedule**

```python
RETRY_DELAYS_SECONDS = (0, 15, 60, 300, 900, 900, 900, 900)

def raise_critical(self, event):
    self.authority.revoke_new_orders(event.correlation_id)
    alert = self.repo.persist(event.to_alert())
    self.event_log.write(redact_payload(alert))
    self.outbox.enqueue(alert.alert_id, channel="SMTP")
    return self.dispatch_due(alert.alert_id)
```

Secret loading returns only an SMTP client object; credentials never appear in result objects or logs.

- [ ] **Step 4: Run GREEN with fake channels, then separately run authorized delivery simulations**

Run: `python -m pytest tests/ibkr_paper_30d/test_alerts.py -q`

Expected: unit and fault tests pass.

Later implementation command: `python -m ibkr_paper_30d.cli simulate-alerts --events KILL_SWITCH_TRIGGERED BROKER_2FA_REAUTH_REQUIRED BROKER_HEARTBEAT_TIMEOUT`

Expected: sanitized SMTP send receipts and queryable Windows Event Log records, with no broker calls.

- [ ] **Step 5: Commit alert system**

```powershell
git add ibkr_paper_30d/alerts.py tests/ibkr_paper_30d/test_alerts.py
git commit -m "feat(ibkr-paper): add durable dual-channel critical alerts"
```

### Task 13: Orchestrator, heartbeats, and explicit 2FA flow

**Files:**
- Create: `ibkr_paper_30d/orchestrator.py`
- Create: `tests/ibkr_paper_30d/test_orchestrator.py`

**Interfaces:**
- Consumes: gates, invocation adapter, lock, reconciliation, alerts, fake broker.
- Produces: `PaperOrchestrator.handle(event)` and heartbeat timeout evaluation. It has no broker write methods.

- [ ] **Step 1: Write RED tests for authority ordering and pause/recovery**

```python
def test_orchestrator_cannot_access_order_writes(orchestrator):
    assert not hasattr(orchestrator, "submit_order")
    assert not hasattr(orchestrator, "cancel_order")

def test_2fa_requires_owner_and_full_reconciliation(orchestrator):
    orchestrator.handle(BrokerEvent.TWO_FACTOR_REQUIRED)
    assert orchestrator.system_state == SystemState.PAUSED
    assert orchestrator.broker_state == BrokerState.TWO_FACTOR_REQUIRED
    assert orchestrator.last_alert.owner_action_required is True
    orchestrator.handle(BrokerEvent.AUTHENTICATED)
    assert orchestrator.broker_state == BrokerState.RECONCILIATION_REQUIRED
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_orchestrator.py -q`

Expected: missing orchestrator.

- [ ] **Step 3: Implement event dispatch and gate sequence without write authority**

```python
def evaluate_cycle(self, trigger):
    with self.lock.acquire(self.owner) as receipt:
        self.require_clear_kill_switch()
        self.require_paper_identity()
        reconciliation = self.require_reconciliation()
        self.require_fresh_heartbeats()
        self.require_subledger()
        market = self.require_market_data()
        bundle = self.freeze_trader_bundle(trigger, reconciliation, market)
        return self.trader.invoke(self.invocation_request(trigger, bundle), bundle)
```

The orchestration result can freeze a proposal and run risk against fakes, but cannot call a real broker write path.

- [ ] **Step 4: Run GREEN including restart and heartbeat fault tests**

Run: `python -m pytest tests/ibkr_paper_30d/test_orchestrator.py -q`

Expected: scheduling, ordering, heartbeat, 2FA, restart, and no-write tests pass.

- [ ] **Step 5: Commit orchestrator**

```powershell
git add ibkr_paper_30d/orchestrator.py tests/ibkr_paper_30d/test_orchestrator.py
git commit -m "feat(ibkr-paper): add no-write orchestrator and heartbeats"
```

### Task 14: Structurally isolated auditor

**Files:**
- Create: `ibkr_paper_30d/auditor_export.py`
- Create: `ibkr_paper_30d/auditor.py`
- Create: `tests/ibkr_paper_30d/test_auditor_isolation.py`

**Interfaces:**
- Produces: `AuditExporter.publish(bundle) -> ManifestReceipt` and `Auditor.run(export_dir, report_dir)`.
- Auditor consumes only immutable JSON plus a hash manifest.

- [ ] **Step 1: Write RED tests for immutable manifests and denied capabilities**

```python
def test_auditor_environment_has_no_secrets(auditor_process):
    result = auditor_process.probe_environment()
    assert result.can_read_secrets is False
    assert result.can_import_broker_adapter is False
    assert result.can_acquire_execution_lock is False
    assert result.can_mutate_live_database is False

def test_modified_export_is_rejected(audit_export):
    audit_export.mutate_input("decision.json")
    assert Auditor().run(audit_export.path).status == "HASH_MISMATCH"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_auditor_isolation.py -q`

Expected: missing auditor modules.

- [ ] **Step 3: Implement atomic export and restricted-process launcher**

```python
def publish(self, records):
    staging = self.root / f".{new_uuid7()}-staging"
    write_canonical_files(staging, records)
    manifest = build_sha256_manifest(staging)
    write_manifest(staging, manifest)
    final = self.root / manifest.bundle_id
    os.replace(staging, final)
    return ManifestReceipt(final, manifest.sha256)
```

Use a sanitized environment, read-only input ACLs, append-only report directory, and a restricted Windows token/dedicated account when available. If OS-level denials cannot be proven, the isolation gate remains BLOCK.

- [ ] **Step 4: Run GREEN including real ACL denial probes**

Run: `python -m pytest tests/ibkr_paper_30d/test_auditor_isolation.py -q`

Expected: manifest tests pass; environment probes report explicit denials or the gate reports BLOCK rather than PASS.

- [ ] **Step 5: Commit auditor boundary**

```powershell
git add ibkr_paper_30d/auditor_export.py ibkr_paper_30d/auditor.py tests/ibkr_paper_30d/test_auditor_isolation.py
git commit -m "feat(ibkr-paper): add isolated immutable auditor flow"
```

### Task 15: Full fault-injection suite and reports

**Files:**
- Create: `tests/ibkr_paper_30d/test_fault_injection.py`
- Create: `ibkr_paper_30d/reporting.py`
- Create at run time: `state/ibkr_paper_30d/reports/fault_injection_report.json`
- Create at run time: `state/ibkr_paper_30d/reports/security_boundary_report.json`

**Interfaces:**
- Consumes: every local component and fake broker.
- Produces: deterministic machine-readable test evidence and gate verdicts.

- [ ] **Step 1: Write the RED scenario matrix**

```python
SCENARIOS = [
    "crash_before_commit", "crash_after_commit", "crash_during_submit",
    "crash_after_ack", "partial_fill_crash", "broker_disconnect",
    "two_factor_required", "auth_failure", "duplicate_order", "db_lock",
    "db_corruption", "subledger_mismatch", "market_data_loss",
    "smtp_failure", "event_log_failure", "stale_execution_lock",
    "trader_timeout", "trader_malformed", "auditor_access_attempt",
]

@pytest.mark.parametrize("scenario", SCENARIOS)
def test_fault_scenario_fails_closed(scenario, harness):
    result = harness.run(scenario)
    assert result.new_order_authority is False
    assert result.evidence_persisted is True
```

- [ ] **Step 2: Run RED to expose unimplemented scenario hooks**

Run: `python -m pytest tests/ibkr_paper_30d/test_fault_injection.py -q`

Expected: scenario hook failures identify missing fault controls.

- [ ] **Step 3: Implement deterministic fault hooks and report generation**

```python
def build_fault_report(results):
    return {
        "schema": "CODEX_IBKR_FAULT_REPORT_V1",
        "generated_at_utc": utc_now(),
        "scenario_count": len(results),
        "pass": sum(r.passed for r in results),
        "fail": sum(not r.passed for r in results),
        "results": [r.model_dump(mode="json") for r in results],
    }
```

- [ ] **Step 4: Run the complete fake/fault/security suites and write reports**

Run: `python -m pytest tests/ibkr_paper_30d -q --junitxml=state/ibkr_paper_30d/reports/pytest.xml`

Expected: zero failures before reports can say PASS.

Run: `python -m ibkr_paper_30d.cli write-local-reports`

Expected: reports include test evidence hashes and no secrets.

- [ ] **Step 5: Commit fault harness and report schema, not mutable runtime outputs**

```powershell
git add ibkr_paper_30d/reporting.py tests/ibkr_paper_30d/test_fault_injection.py
git commit -m "test(ibkr-paper): add full fault injection matrix"
```

### Task 16: Read-only real IBKR inspection, capability matrix, and final local gate report

**Files:**
- Create: `ibkr_paper_30d/ibkr_readonly.py`
- Create: `ibkr_paper_30d/cli.py`
- Create: `tests/ibkr_paper_30d/test_ibkr_readonly.py`
- Create: `IBKR_CAPABILITY_MATRIX_V1.md`
- Create at run time: `state/ibkr_paper_30d/reports/read_only_real_paper_reconciliation.json`
- Create at run time: `state/ibkr_paper_30d/reports/updated_gate_matrix.json`

**Interfaces:**
- Consumes: official `ibapi`, exact allowed account identity from protected config, no write authorization.
- Produces: sanitized identity/account/position/order/execution/market-data evidence and final implementation status.

- [ ] **Step 1: Write RED tests proving the real adapter is read-only and identity factors fail closed**

```python
def test_readonly_adapter_exposes_no_write_methods():
    public = set(dir(IBKRReadOnlyAdapter))
    assert "submit_order" not in public
    assert "cancel_order" not in public
    assert "modify_order" not in public

def test_port_4002_wrong_account_is_blocked(readonly_adapter):
    evidence = readonly_adapter.prove_identity(fake_session(account="WRONG"))
    assert evidence.paper_identity_proven is False
    assert evidence.event_type == "POSSIBLE_LIVE_CONNECTION"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_ibkr_readonly.py -q`

Expected: missing read-only adapter.

- [ ] **Step 3: Implement official-API read callbacks without order methods**

```python
class IBKRReadOnlyAdapter(EWrapper, EClient):
    def __init__(self, expected_identity_hash: str):
        EClient.__init__(self, self)
        self.expected_identity_hash = expected_identity_hash
        self.snapshots = ReadOnlySnapshotCollector()

    def prove_identity(self, session) -> IdentityEvidence:
        factors = collect_identity_factors(session, self.snapshots)
        return IdentityEvidence.from_factors(factors, self.expected_identity_hash)
```

Do not import `Order`, call `placeOrder`, `cancelOrder`, or expose an order-write client. Add a source scan test that fails if these symbols appear in `ibkr_readonly.py`.

- [ ] **Step 4: Run all local tests before any real connection**

Run: `python -m pytest tests/ibkr_paper_30d -q`

Expected: zero failures. If any fail, use systematic-debugging before changing implementation.

- [ ] **Step 5: Perform authorized read-only inspection only when Gateway is authenticated**

Run: `python -m ibkr_paper_30d.cli inspect-ibkr-readonly --port 4002`

Expected: sanitized report for identity, account, cash, settled cash, positions, open orders, executions visibility, entitlements, timestamps, heartbeats, and connector/session consistency. If Gateway is unavailable or identity is not proven, report BLOCK without starting Gateway or making broker writes.

- [ ] **Step 6: Generate capability and gate artifacts from evidence**

Run: `python -m ibkr_paper_30d.cli write-capability-matrix`

Expected: `IBKR_CAPABILITY_MATRIX_V1.md` marks each capability AVAILABLE, UNAVAILABLE, PARTIAL, or UNKNOWN with evidence.

Run: `python -m ibkr_paper_30d.cli write-implementation-status`

Expected: reports actual counts and gate results; `AUTONOMOUS_TRADING_STATUS=BLOCKED` and every real broker write gate remains BLOCK.

- [ ] **Step 7: Run final verification and commit read-only/reporting code and stable docs**

Run: `python -m pytest tests/ibkr_paper_30d -q`

Run: `git diff --check`

Run: `rg -n "placeOrder|cancelOrder|BROKER_WRITE_AUTHORIZED=true|TEST_ORDER_AUTHORIZED=true" ibkr_paper_30d/ibkr_readonly.py ibkr_paper_30d/config.py`

Expected: tests pass, diff check is clean, and no real write symbol or authorization exists outside fake-only declarations/tests.

```powershell
git add ibkr_paper_30d tests/ibkr_paper_30d IBKR_CAPABILITY_MATRIX_V1.md CODEX_IBKR_PAPER_ARCHITECTURE_DESIGN_V2.md CODEX_IBKR_PAPER_IMPLEMENTATION_PLAN_V1.md
git commit -m "feat(ibkr-paper): complete isolated local infrastructure"
```

## Execution handoff

The Owner selected native execution through `superpowers:executing-plans`. After plan approval, execute Tasks 1-16 in order. Invoke `superpowers:test-driven-development` before Task 1, use `superpowers:systematic-debugging` for every unexpected failure, and invoke `superpowers:verification-before-completion` before each gate claim and final status report.

No execution step may place, modify, or cancel a real IBKR order. The terminal status for this authorization remains `AUTONOMOUS_TRADING_STATUS=BLOCKED` pending a separate Owner authorization for a harmless paper lifecycle test.
