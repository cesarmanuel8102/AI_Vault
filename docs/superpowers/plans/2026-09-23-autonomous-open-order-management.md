# Autonomous IBKR PAPER Open-Order Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ownership-gated, append-only, fail-closed cancellation and same-ID modification of autonomous IBKR PAPER experiment orders, then prove the complete runtime is ready for Day 1 without performing a real broker write during implementation.

**Architecture:** Extend the existing autonomous decision contract with one immutable open-order action model. Normalize every broker open order into a canonical hash-bound snapshot, reserve API client ID `19761` for all executor writes, and require frozen snapshot + append-only registry + live broker identity to agree immediately before a cancel or modify call. Lifecycle evidence remains in `experiment_order_registry`; economic ledger state continues to derive only from fills and commissions.

**Tech Stack:** Python 3.11, Pydantic v2, SQLite, ib_insync, pytest, PowerShell AST validation, Bandit/static source checks.

**Spec:** `docs/superpowers/specs/2026-09-23-autonomous-open-order-management-design.md`

## Global Constraints

- Work directly in `C:\AI_VAULT_IBKR`; preserve all pre-existing untracked capability evidence and local artifacts.
- PAPER account and port only: `127.0.0.1:4002`, account namespace `DU`; never add or use a LIVE endpoint.
- Do not alter Auditor Gate V2 semantics, auditor runtime payloads, or `AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json`.
- Do not alter the USD 500 experimental capital boundary, PAPER/LIVE boundary, universe freedom, strategy freedom, or `NO_TRADE` validity.
- Keep `model = gpt-5.6-sol` and `reasoning_effort = max`; silent substitution remains fail-closed.
- `MODIFY_ORDER` may preserve or reduce quantity and may change a positive limit price; it may not change contract, side, order type, TIF, routing, account, or increase quantity.
- Broker writes in tests are fake-only. Do not execute `FINALIZE_IBKR_PREREQUISITES.ps1`, arm PAPER, start Day 1, or call a real broker-write API while implementing.
- Every implementation step follows RED -> GREEN. Every task gets a narrow local commit. Do not push or merge.
- The existing untracked capability files match pinned commit `8d1e421ee700c194659f9c41bf4013f4fcea822f`; do not add, remove, or rewrite them as part of this plan.

## Review Focus

- A partially filled order whose requested new total equals the filled quantity must not be treated as safely modifiable; Task 5 tests that the now-zero remainder blocks modification and requires fresh reconciliation.
- Two live trades matching one identity tuple must fail as ambiguous rather than selecting the first; Task 4 adds an explicit duplicate-live-match test.
- A broker disconnect after the write but before confirmation must persist the attempt and refuse replay; Tasks 4 and 5 test post-write disconnects and duplicate-cycle retries.
- A database failure while persisting the result after a confirmed broker action must never report clean success; Task 4 tests the distinct uncertain/persistence-failure result.
- Broker-normalized numeric values such as `10`, `10.0`, and `10.00` must hash consistently; Task 3 tests canonical decimal normalization so harmless representation changes do not create false stale-state failures.

---

### Task 1: Restore the Auditor Test Baseline

**Files:**
- Modify: `tests/ibkr_paper_30d/test_auditor_runtime.py`
- Verify unchanged: `auditor_runtime/AUDITOR_DENIAL_PROBE_V1.ps1`
- Verify unchanged: `auditor_runtime/AUDITOR_GATE_V2_PROBE.ps1`
- Verify unchanged: `auditor_runtime/CODEX_DECISION_AUDITOR_V1.ps1`
- Verify unchanged: `AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json`

**Interfaces:**
- Consumes: the immutable probe's required target set, including `BROKER_NETWORK_SOCKET_ACCESS`.
- Produces: a green pre-change auditor runtime test without modifying runtime payloads or trust anchors.

- [ ] **Step 1: Re-run the existing failing test and capture the expected RED result**

Run:

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_auditor_runtime.py::test_probe_report_binds_effective_sid_and_elevation_state
```

Expected: FAIL with probe status `TARGET_SET_MISMATCH` because the fixture omits `BROKER_NETWORK_SOCKET_ACCESS`.

- [ ] **Step 2: Restore the complete real target shape in the fixture**

Insert the missing key beside `BROKER_WRITE_PATH_ACCESS`:

```python
"BROKER_WRITE_PATH_ACCESS": str(tmp_path / "missing-broker"),
"BROKER_NETWORK_SOCKET_ACCESS": str(tmp_path / "missing-broker"),
"TRADER_CONTEXT_ACCESS": str(tmp_path / "missing-context"),
```

Do not edit any PowerShell runtime file.

- [ ] **Step 3: Verify the focused test is GREEN**

Run:

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_auditor_runtime.py::test_probe_report_binds_effective_sid_and_elevation_state
```

Expected: `1 passed`.

- [ ] **Step 4: Record immutable runtime baselines for final comparison**

Run:

```powershell
Get-FileHash -Algorithm SHA256 AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json,auditor_runtime\AUDITOR_DENIAL_PROBE_V1.ps1,auditor_runtime\AUDITOR_GATE_V2_PROBE.ps1,auditor_runtime\CODEX_DECISION_AUDITOR_V1.ps1
```

Expected hashes:

```text
AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json  028423074114E9D5378F9564E73928AA76DD0AA0100DEFAB3C230FF6DB1AEB58
AUDITOR_DENIAL_PROBE_V1.ps1              C01C8627BC584506E66CD31E01661737C67C953F8384FB45D061EB70F0D2B1BA
AUDITOR_GATE_V2_PROBE.ps1                9EC985AAAC45DF17251A755039E261A315B0FF6C4EC4D886E29EAE1FA3FDDE62
CODEX_DECISION_AUDITOR_V1.ps1            23A60FD2F9DD62E00887A606524E361A0D1B3F672C519853EAF5B13A5EFBDFA7
```

- [ ] **Step 5: Commit the baseline repair**

```powershell
git add tests/ibkr_paper_30d/test_auditor_runtime.py
git commit -m "test: restore auditor socket target fixture"
```

---

### Task 2: Add the Open-Order Decision Contract

**Files:**
- Modify: `ibkr_paper_30d/trader_invocation.py`
- Modify: `ibkr_paper_30d/autonomous_research.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_research.py`
- Modify: `tests/ibkr_paper_30d/test_trader_invocation.py`

**Interfaces:**
- Consumes: `TraderDecision`, `AutonomousTurn`, `AutonomousResearchOutcome`, `TraderInputBundle.open_orders_snapshot`.
- Produces: `AutonomousOpenOrderAction`, `CANCEL_ORDER`, `MODIFY_ORDER`, and `ResearchToolbox.validate_open_order_action(action, bundle, decision)`.

- [ ] **Step 1: Add failing schema and validator tests**

Add imports and these tests to `test_autonomous_research.py`:

```python
import pytest

from pydantic import ValidationError

from ibkr_paper_30d.autonomous_research import AutonomousOpenOrderAction


def open_order_action(**updates):
    values = {
        "order_ref": "codex-ibkr-paper-30d-a-cycle",
        "order_id": 41,
        "perm_id": 9001,
        "client_id": 19761,
        "contract_id": 756733,
        "observed_state_sha256": "a" * 64,
        "new_total_quantity": None,
        "new_limit_price": None,
        "reason": "The resting order no longer has acceptable expected value.",
    }
    values.update(updates)
    return AutonomousOpenOrderAction(**values)


def test_cancel_order_requires_target_and_forbids_modification_fields():
    turn = AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=TraderDecision.CANCEL_ORDER,
        proposal=None,
        position_action=None,
        open_order_action=open_order_action(),
        confidence="0.8",
        reasoning_summary="Cancel the stale resting order.",
        reason_codes=["EDGE_DECAYED"],
    )
    assert turn.open_order_action.order_id == 41
    invalid = turn.model_dump(mode="json")
    invalid["open_order_action"]["new_limit_price"] = "9.50"
    with pytest.raises(ValidationError):
        AutonomousTurn.model_validate(invalid)


def test_modify_order_requires_an_effective_change():
    with pytest.raises(ValidationError):
        AutonomousTurn(
            mode=AutonomousTurnMode.FINAL,
            research_requests=[],
            decision=TraderDecision.MODIFY_ORDER,
            proposal=None,
            position_action=None,
            open_order_action=open_order_action(),
            confidence="0.8",
            reasoning_summary="No actual change.",
            reason_codes=[],
        )
```

Add enum coverage to `test_trader_invocation.py`:

```python
def test_open_order_decisions_are_first_class():
    assert TraderDecision.CANCEL_ORDER.value == "CANCEL_ORDER"
    assert TraderDecision.MODIFY_ORDER.value == "MODIFY_ORDER"
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_autonomous_research.py tests\ibkr_paper_30d\test_trader_invocation.py
```

Expected: collection/import failure because `AutonomousOpenOrderAction`, `CANCEL_ORDER`, and `MODIFY_ORDER` do not exist.

- [ ] **Step 3: Implement the minimal immutable contract**

Add to `TraderDecision`:

```python
CANCEL_ORDER = "CANCEL_ORDER"
MODIFY_ORDER = "MODIFY_ORDER"
```

Add to `autonomous_research.py`:

```python
class AutonomousOpenOrderAction(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    order_ref: str = Field(min_length=1)
    order_id: int = Field(gt=0)
    perm_id: int | None = Field(default=None, gt=0)
    client_id: int = Field(ge=0)
    contract_id: int = Field(gt=0)
    observed_state_sha256: str = Field(min_length=64, max_length=64)
    new_total_quantity: Decimal | None = Field(default=None, gt=0)
    new_limit_price: Decimal | None = Field(default=None, gt=0)
    reason: str = Field(min_length=1)
```

Add `open_order_action: AutonomousOpenOrderAction | None = None` to
`AutonomousTurn` and `AutonomousResearchOutcome`. Extend `mode_consistency` so
the payload matrix is exact:

```python
elif self.decision == TraderDecision.CANCEL_ORDER:
    if (
        self.open_order_action is None
        or self.open_order_action.new_total_quantity is not None
        or self.open_order_action.new_limit_price is not None
        or self.proposal is not None
        or self.position_action is not None
    ):
        raise ValueError("CANCEL_ORDER requires an unmodified open_order_action only")
elif self.decision == TraderDecision.MODIFY_ORDER:
    action = self.open_order_action
    if (
        action is None
        or (action.new_total_quantity is None and action.new_limit_price is None)
        or self.proposal is not None
        or self.position_action is not None
    ):
        raise ValueError("MODIFY_ORDER requires an effective open_order_action only")
elif self.proposal is not None or self.position_action is not None or self.open_order_action is not None:
    raise ValueError("trade payload not allowed for this decision")
```

Extend `_finish`, `_blocked`, and every caller with `open_order_action`, always
passing `None` outside the lifecycle branches. Extend the protocol with:

```python
def validate_open_order_action(
    self,
    action: AutonomousOpenOrderAction,
    bundle: TraderInputBundle,
    decision: TraderDecision,
) -> ProposalValidation: ...
```

- [ ] **Step 4: Add research-loop routing tests**

Initialize `self.open_order_validations = []` in `FakeToolbox.__init__`, extend
the fake with this call recorder, and add:

```python
def validate_open_order_action(self, action, bundle, decision):
    self.open_order_validations.append((action, decision))
    return ProposalValidation(
        passed=self.validation,
        reason_codes=() if self.validation else ("OPEN_ORDER_ACTION_BLOCKED",),
        broker_evidence={"decision": decision.value},
    )


@pytest.mark.parametrize(
    ("decision", "action"),
    [
        (TraderDecision.CANCEL_ORDER, open_order_action()),
        (
            TraderDecision.MODIFY_ORDER,
            open_order_action(new_total_quantity="1", new_limit_price="9.50"),
        ),
    ],
)
def test_research_loop_validates_open_order_actions(decision, action):
    value = bundle().model_copy(update={"open_orders_snapshot": [{
        "orderRef": action.order_ref,
        "orderId": action.order_id,
        "state_sha256": action.observed_state_sha256,
    }]})
    final = AutonomousTurn(
        mode=AutonomousTurnMode.FINAL,
        research_requests=[],
        decision=decision,
        proposal=None,
        position_action=None,
        open_order_action=action,
        confidence="0.8",
        reasoning_summary="Manage the resting experiment order.",
        reason_codes=["RESTING_ORDER_MANAGEMENT"],
    )
    toolbox = FakeToolbox()
    outcome = AutonomousResearchLoop(SequenceProvider([final]), toolbox).run(
        request(value), value
    )
    assert outcome.accepted is True
    assert outcome.open_order_action == action
    assert toolbox.open_order_validations == [(action, decision)]
```

Add the matching branch to `AutonomousResearchLoop.run`; a failed validation
returns an accepted-false `NO_TRADE` outcome with no executable payload.

- [ ] **Step 5: Run focused tests GREEN**

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_autonomous_research.py tests\ibkr_paper_30d\test_trader_invocation.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit the decision contract**

```powershell
git add ibkr_paper_30d/trader_invocation.py ibkr_paper_30d/autonomous_research.py tests/ibkr_paper_30d/test_autonomous_research.py tests/ibkr_paper_30d/test_trader_invocation.py
git commit -m "feat: add autonomous open-order decisions"
```

---

### Task 3: Canonicalize Open Orders and Reserve the Execution Client

**Files:**
- Create: `ibkr_paper_30d/open_order_management.py`
- Create: `tests/ibkr_paper_30d/test_open_order_management.py`
- Create: `tests/ibkr_paper_30d/test_ibkr_research_tools.py`
- Modify: `ibkr_paper_30d/ibkr_research_tools.py`
- Modify: `ibkr_paper_30d/autonomous_execution.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_execution.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_state.py`

**Interfaces:**
- Consumes: ib_insync-like `Trade`, `Order`, `OrderStatus`, and `Contract` objects.
- Produces: `EXECUTION_CLIENT_ID = 19761`, `canonical_open_order(trade) -> dict[str, Any]`, `open_order_state_sha256(payload) -> str`, and executor `_connect_execution()`.

- [ ] **Step 1: Write canonicalization tests**

Create `test_open_order_management.py` with a concrete trade factory and tests:

```python
from types import SimpleNamespace

from ibkr_paper_30d.open_order_management import (
    EXECUTION_CLIENT_ID,
    canonical_open_order,
)


def trade(*, limit_price=10):
    return SimpleNamespace(
        contract=SimpleNamespace(
            conId=756733,
            symbol="SPY",
            localSymbol="SPY",
            secType="STK",
            exchange="SMART",
            currency="USD",
            lastTradeDateOrContractMonth="",
            strike=0,
            right="",
            multiplier="1",
        ),
        order=SimpleNamespace(
            orderRef="codex-ibkr-paper-30d-a-cycle",
            orderId=41,
            permId=9001,
            clientId=EXECUTION_CLIENT_ID,
            account="DU1234567",
            action="BUY",
            orderType="LMT",
            totalQuantity=2,
            lmtPrice=limit_price,
            auxPrice=0,
            tif="DAY",
            outsideRth=False,
        ),
        orderStatus=SimpleNamespace(
            status="Submitted", filled=0, remaining=2, avgFillPrice=0
        ),
    )


def test_canonical_order_contains_complete_identity_and_hash():
    value = canonical_open_order(trade())
    assert value["orderRef"] == "codex-ibkr-paper-30d-a-cycle"
    assert value["orderId"] == 41
    assert value["permId"] == 9001
    assert value["clientId"] == EXECUTION_CLIENT_ID
    assert value["contract"]["conId"] == 756733
    assert len(value["state_sha256"]) == 64


def test_decimal_representation_does_not_change_state_hash():
    assert canonical_open_order(trade(limit_price=10))["state_sha256"] == canonical_open_order(
        trade(limit_price="10.00")
    )["state_sha256"]


def test_execution_client_is_outside_research_client_range():
    assert EXECUTION_CLIENT_ID == 19761
    assert not 19800 <= EXECUTION_CLIENT_ID <= 19899
```

- [ ] **Step 2: Run the new test RED**

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_open_order_management.py
```

Expected: import failure because `open_order_management.py` does not exist.

- [ ] **Step 3: Implement canonical normalization**

Create the module with exact constants and helpers:

```python
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .canonical import sha256_json

EXECUTION_CLIENT_ID = 19761
EXPERIMENT_ORDER_PREFIX = "codex-ibkr-paper-30d"
ACTIONABLE_ORDER_STATUSES = frozenset(
    {"PENDINGSUBMIT", "PRESUBMITTED", "SUBMITTED", "PENDINGCANCEL"}
)
CANCELLED_ORDER_STATUSES = frozenset({"CANCELLED", "APICANCELLED", "API CANCELLED"})


def _decimal_text(value: Any) -> str:
    parsed = Decimal(str(value or 0))
    if not parsed.is_finite():
        raise ValueError("open-order numeric field must be finite")
    normalized = parsed.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def canonical_open_order(trade: Any) -> dict[str, Any]:
    order = trade.order
    status = trade.orderStatus
    contract = trade.contract
    payload = {
        "orderRef": str(getattr(order, "orderRef", "") or ""),
        "orderId": int(getattr(order, "orderId", 0) or 0),
        "permId": int(getattr(order, "permId", 0) or 0),
        "clientId": int(getattr(order, "clientId", 0) or 0),
        "account": str(getattr(order, "account", "") or ""),
        "action": str(getattr(order, "action", "") or "").upper(),
        "orderType": str(getattr(order, "orderType", "") or "").upper(),
        "totalQuantity": _decimal_text(getattr(order, "totalQuantity", 0)),
        "limitPrice": _decimal_text(getattr(order, "lmtPrice", 0)),
        "auxPrice": _decimal_text(getattr(order, "auxPrice", 0)),
        "tif": str(getattr(order, "tif", "") or "").upper(),
        "outsideRth": bool(getattr(order, "outsideRth", False)),
        "status": str(getattr(status, "status", "") or ""),
        "filled": _decimal_text(getattr(status, "filled", 0)),
        "remaining": _decimal_text(getattr(status, "remaining", 0)),
        "contract": {
            "conId": int(getattr(contract, "conId", 0) or 0),
            "symbol": str(getattr(contract, "symbol", "") or ""),
            "localSymbol": str(getattr(contract, "localSymbol", "") or ""),
            "secType": str(getattr(contract, "secType", "") or "").upper(),
            "exchange": str(getattr(contract, "exchange", "") or ""),
            "currency": str(getattr(contract, "currency", "") or ""),
            "expiry": str(getattr(contract, "lastTradeDateOrContractMonth", "") or ""),
            "strike": _decimal_text(getattr(contract, "strike", 0)),
            "right": str(getattr(contract, "right", "") or "").upper(),
            "multiplier": _decimal_text(getattr(contract, "multiplier", 1) or 1),
        },
    }
    return {**payload, "state_sha256": sha256_json(payload)}
```

- [ ] **Step 4: Make observation and execution connections explicit**

Change the toolbox connector to:

```python
def _connect(self, *, client_id: int | None = None):
    from ib_insync import IB

    ib = IB()
    selected_client_id = (
        random.randint(self.client_id_min, self.client_id_max)
        if client_id is None
        else int(client_id)
    )
    ib.connect(self.host, self.port, clientId=selected_client_id, timeout=self.timeout_seconds)
    if not ib.isConnected():
        raise RuntimeError("IBKR_CONNECTION_FAILED")
    return ib
```

Make `_open_orders` call `ib.reqAllOpenOrders()` and serialize each returned
trade through `canonical_open_order`.

Add to `AutonomousPaperExecutor`:

```python
execution_client_id: int = EXECUTION_CLIENT_ID

def _connect_execution(self):
    return self.toolbox._connect(client_id=self.execution_client_id)
```

Replace the two existing write-path `self.toolbox._connect()` calls with
`self._connect_execution()`. Add `execution_client_id` and
`lifecycle_event="ISSUED_PRE_SEND"` to pre-send registry payloads, and
`lifecycle_event="BROKER_BOUND"` to post-send payloads.

Update every executor test toolbox `_connect` fake to accept the keyword-only
`client_id=None` argument and record or ignore it explicitly. Do not add a
production fallback that silently retries without the stable client ID.

- [ ] **Step 5: Add state and executor tests for enriched snapshots and stable client use**

In `test_autonomous_execution.py`, change `_PassUntilOperatorControlToolbox` to
accept `client_id=None`, record it, and assert both new-trade and
position-management execution use `19761`:

```python
def _connect(self, *, client_id=None):
    self.requested_client_ids.append(client_id)
    return self.ib


assert toolbox.requested_client_ids == [19761]
```

Create `test_ibkr_research_tools.py` with a fake whose `reqAllOpenOrders`
returns one canonicalizable trade and assert `_open_orders({})` returns the
complete canonical payload and disconnects. In `test_autonomous_state.py`,
replace the minimal owned order fixture with that canonical dictionary and
assert `permId`, `clientId`, `contract.conId`, and `state_sha256` survive into
`bundle.open_orders_snapshot` while an unrelated order remains filtered out.

- [ ] **Step 6: Run focused tests GREEN**

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_open_order_management.py tests\ibkr_paper_30d\test_autonomous_execution.py tests\ibkr_paper_30d\test_autonomous_state.py tests\ibkr_paper_30d\test_ibkr_research_tools.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit canonical order state and stable execution identity**

```powershell
git add ibkr_paper_30d/open_order_management.py ibkr_paper_30d/ibkr_research_tools.py ibkr_paper_30d/autonomous_execution.py tests/ibkr_paper_30d/test_open_order_management.py tests/ibkr_paper_30d/test_ibkr_research_tools.py tests/ibkr_paper_30d/test_autonomous_execution.py tests/ibkr_paper_30d/test_autonomous_state.py
git commit -m "feat: bind paper orders to stable execution identity"
```

---

### Task 4: Implement Ownership-Gated Cancellation

**Files:**
- Modify: `ibkr_paper_30d/open_order_management.py`
- Modify: `ibkr_paper_30d/autonomous_execution.py`
- Modify: `tests/ibkr_paper_30d/test_open_order_management.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_execution.py`

**Interfaces:**
- Consumes: `AutonomousOpenOrderAction`, canonical open-order snapshots, hash-valid V2 ownership rows from `experiment_order_registry`, executor fresh safety and operator callbacks. V1 rows remain history only and cannot independently authorize lifecycle writes.
- Produces: `resolve_owned_open_trade(...)`, append-only lifecycle evidence, and `AutonomousPaperExecutor.execute_open_order_action(...)` for `CANCEL_ORDER`.

- [ ] **Step 1: Write failing pure ownership tests**

Add a database registry helper in the test and these cases:

```python
def test_registry_and_live_identity_must_resolve_exactly_one_trade(tmp_path):
    action = open_order_action_from_trade(trade())
    with Database.open(tmp_path / "orders.sqlite3") as db:
        register_issuance(db, trade())
        resolved, snapshot = resolve_owned_open_trade(
            db, [trade()], action, execution_client_id=EXECUTION_CLIENT_ID
        )
    assert resolved.order.orderId == 41
    assert snapshot["state_sha256"] == action.observed_state_sha256


def test_prefix_spoof_without_registry_anchor_is_blocked(tmp_path):
    action = open_order_action_from_trade(trade())
    with Database.open(tmp_path / "orders.sqlite3") as db:
        with pytest.raises(OpenOrderOwnershipError, match="ORDER_REGISTRY_OWNERSHIP_REQUIRED"):
            resolve_owned_open_trade(
                db, [trade()], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_duplicate_live_identity_is_ambiguous(tmp_path):
    action = open_order_action_from_trade(trade())
    with Database.open(tmp_path / "orders.sqlite3") as db:
        register_issuance(db, trade())
        with pytest.raises(OpenOrderOwnershipError, match="OPEN_ORDER_IDENTITY_AMBIGUOUS"):
            resolve_owned_open_trade(
                db, [trade(), trade()], action, execution_client_id=EXECUTION_CLIENT_ID
            )
```

Define the two test helpers in the same file before these tests:

```python
def open_order_action_from_trade(value):
    snapshot = canonical_open_order(value)
    return AutonomousOpenOrderAction(
        order_ref=snapshot["orderRef"],
        order_id=snapshot["orderId"],
        perm_id=snapshot["permId"],
        client_id=snapshot["clientId"],
        contract_id=snapshot["contract"]["conId"],
        observed_state_sha256=snapshot["state_sha256"],
        new_total_quantity=None,
        new_limit_price=None,
        reason="Cancel the selected resting experiment order.",
    )


def register_issuance(db, value):
    snapshot = canonical_open_order(value)
    payload = {
        "schema": "EXPERIMENT_ORDER_REGISTRY_V2",
        "lifecycle_event": "ISSUED_PRE_SEND",
        "order_ref": snapshot["orderRef"],
        "execution_client_id": snapshot["clientId"],
        "account": snapshot["account"],
    }
    db.execute(
        "INSERT INTO experiment_order_registry("
        "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
        "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            "registry-test-anchor",
            snapshot["orderRef"],
            snapshot["orderId"],
            snapshot["permId"],
            snapshot["orderId"],
            snapshot["contract"]["conId"],
            snapshot["action"],
            snapshot["totalQuantity"],
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            "2026-09-23T12:00:00Z",
        ),
    )
```

Parameterize mismatch tests for order ref, order ID, positive perm ID, client ID,
contract ID, account, side, and state hash. Each mismatch must raise its own
stable reason code and never return a trade.

- [ ] **Step 2: Run ownership tests RED**

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_open_order_management.py
```

Expected: import/name failures for `resolve_owned_open_trade` and
`OpenOrderOwnershipError`.

- [ ] **Step 3: Implement ownership proof and replay detection**

Add:

```python
class OpenOrderOwnershipError(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def resolve_owned_open_trade(
    db: Database,
    trades: list[Any],
    action: Any,
    *,
    execution_client_id: int,
) -> tuple[Any, dict[str, Any]]:
    if not action.order_ref.startswith(EXPERIMENT_ORDER_PREFIX):
        raise OpenOrderOwnershipError("ORDER_REF_NAMESPACE_MISMATCH")
    rows = db.execute(
        "SELECT client_order_id,perm_id,contract_id,action,payload_json "
        "FROM experiment_order_registry WHERE order_ref=? ORDER BY sequence",
        (action.order_ref,),
    ).fetchall()
    anchors = [row for row in rows if json.loads(row[4] or "{}").get(
        "lifecycle_event", "ISSUED_PRE_SEND"
    ) in {"ISSUED_PRE_SEND", "BROKER_BOUND"}]
    if not anchors:
        raise OpenOrderOwnershipError("ORDER_REGISTRY_OWNERSHIP_REQUIRED")
    matches = []
    for candidate in trades:
        snapshot = canonical_open_order(candidate)
        if (
            snapshot["orderRef"] == action.order_ref
            and snapshot["orderId"] == action.order_id
            and snapshot["clientId"] == execution_client_id
            and snapshot["contract"]["conId"] == action.contract_id
        ):
            matches.append((candidate, snapshot))
    if len(matches) != 1:
        raise OpenOrderOwnershipError(
            "OPEN_ORDER_IDENTITY_AMBIGUOUS" if len(matches) > 1 else "OPEN_ORDER_NOT_FOUND"
        )
    candidate, snapshot = matches[0]
    if action.perm_id is not None and snapshot["permId"] != action.perm_id:
        raise OpenOrderOwnershipError("OPEN_ORDER_PERM_ID_MISMATCH")
    if snapshot["state_sha256"] != action.observed_state_sha256:
        raise OpenOrderOwnershipError("OPEN_ORDER_STATE_CHANGED")
    if snapshot["status"].upper() not in ACTIONABLE_ORDER_STATUSES:
        raise OpenOrderOwnershipError("OPEN_ORDER_NOT_ACTIONABLE")
    return candidate, snapshot
```

Complete the function by requiring an anchor whose order ID, positive perm ID,
contract ID, side, account, and V2 execution client evidence agree with the live
snapshot. Add a helper that scans lifecycle payloads and raises
`DUPLICATE_ORDER_ACTION_REQUEST` when an attempt already exists for the decision
cycle.

- [ ] **Step 4: Write failing cancel execution tests**

Add fake IB methods `reqOpenOrders`, `openTrades`, and `cancelOrder`. Cover:

```python
def test_cancel_calls_only_selected_owned_order_and_persists_attempt_and_result(tmp_path):
    with armed_cancel_fixture(tmp_path) as (executor, db, fake_ib, action, value):
        result = executor.execute_open_order_action(
            action, value, TraderDecision.CANCEL_ORDER
        )
        assert result.success is True
        assert fake_ib.cancelled_order_ids == [action.order_id]
        assert fake_ib.global_cancel_calls == 0
        events = lifecycle_events(db, action.order_ref)
        assert [item["lifecycle_event"] for item in events] == [
            "ISSUED_PRE_SEND", "CANCEL_ATTEMPT", "CANCEL_RESULT"
        ]
        assert result.order["post_action_reconciliation"]["target_actionable"] is False


def test_cancel_post_write_disconnect_persists_attempt_and_blocks_replay(tmp_path):
    with armed_cancel_fixture(tmp_path, disconnect_after_cancel=True) as fixture:
        executor, db, fake_ib, action, value = fixture
        first = executor.execute_open_order_action(action, value, TraderDecision.CANCEL_ORDER)
        second = executor.execute_open_order_action(action, value, TraderDecision.CANCEL_ORDER)
        assert first.success is False
        assert "BROKER_CONFIRMATION_UNAVAILABLE" in first.reason_codes
        assert second.reason_codes == ("DUPLICATE_ORDER_ACTION_REQUEST",)
        assert fake_ib.cancel_calls == 1
```

Implement `armed_cancel_fixture` in `test_autonomous_execution.py` with the
exact return contract below; `FakeLifecycleIB` must mutate the target status to
`Cancelled` and remove it from `openTrades()` when `cancelOrder` succeeds:

```python
def lifecycle_trade(*, total=2, filled=0, limit_price=10):
    return SimpleNamespace(
        contract=SimpleNamespace(
            conId=756733,
            symbol="SPY",
            localSymbol="SPY",
            secType="STK",
            exchange="SMART",
            currency="USD",
            lastTradeDateOrContractMonth="",
            strike=0,
            right="",
            multiplier="1",
        ),
        order=SimpleNamespace(
            orderRef="codex-ibkr-paper-30d-a-cycle",
            orderId=41,
            permId=9001,
            clientId=EXECUTION_CLIENT_ID,
            account="DU1234567",
            action="BUY",
            orderType="LMT",
            totalQuantity=total,
            lmtPrice=limit_price,
            auxPrice=0,
            tif="DAY",
            outsideRth=False,
        ),
        orderStatus=SimpleNamespace(
            status="Submitted",
            filled=filled,
            remaining=Decimal(str(total)) - Decimal(str(filled)),
            avgFillPrice=0,
        ),
        fills=[],
    )


class FakeLifecycleIB:
    def __init__(self, target, *, disconnect_after_cancel=False):
        self.target = target
        self.disconnect_after_cancel = disconnect_after_cancel
        self.cancel_calls = 0
        self.cancelled_order_ids = []
        self.global_cancel_calls = 0
        self.place_calls = []
        self.client = SimpleNamespace(getReqId=lambda: 4242)

    def reqOpenOrders(self):
        return self.openTrades()

    def openTrades(self):
        return [] if self.target.orderStatus.status == "Cancelled" else [self.target]

    def cancelOrder(self, order):
        self.cancel_calls += 1
        self.cancelled_order_ids.append(order.orderId)
        self.target.orderStatus.status = "Cancelled"
        if self.disconnect_after_cancel:
            raise ConnectionError("disconnected after cancel")
        return self.target

    def sleep(self, seconds):
        return True

    def disconnect(self):
        return None


class LifecycleToolbox:
    def __init__(self, broker):
        self.broker = broker

    def _connect(self, *, client_id=None):
        assert client_id == EXECUTION_CLIENT_ID
        return self.broker


@contextmanager
def armed_cancel_fixture(tmp_path, *, disconnect_after_cancel=False):
    with Database.open(tmp_path / "cancel.sqlite3") as db:
        target = lifecycle_trade()
        action = open_order_action_from_trade(target)
        register_issuance(db, target)
        broker = FakeLifecycleIB(
            target, disconnect_after_cancel=disconnect_after_cancel
        )
        toolbox = LifecycleToolbox(broker)
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: (),
        )
        value = bundle().model_copy(
            update={"open_orders_snapshot": [canonical_open_order(target)]}
        )
        yield executor, db, broker, action, value


def lifecycle_events(db, order_ref):
    rows = db.execute(
        "SELECT payload_json FROM experiment_order_registry "
        "WHERE order_ref=? ORDER BY sequence",
        (order_ref,),
    ).fetchall()
    return [json.loads(row[0]) for row in rows]
```

Import `contextmanager` from `contextlib`. The production implementation must
not depend on these test helpers.

Also test stale state, missing registry, wrong client ID, kill-switch failure from
the fresh callback, revoked authorization from the immediate callback, broker
rejection, confirmation timeout, initial disconnect followed by safe retry,
and result-persistence failure returning an explicit uncertain status.

- [ ] **Step 5: Run cancel tests RED**

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_open_order_management.py tests\ibkr_paper_30d\test_autonomous_execution.py -k "ownership or cancel or lifecycle"
```

Expected: failures because the executor lifecycle method and persistence helpers do not exist.

- [ ] **Step 6: Implement cancel execution**

Add to `AutonomousPaperExecutor`:

```python
def execute_open_order_action(
    self,
    action: AutonomousOpenOrderAction,
    bundle: TraderInputBundle,
    decision: TraderDecision,
) -> PaperExecutionResult:
    if decision == TraderDecision.CANCEL_ORDER:
        return self._cancel_open_order(action, bundle)
    if decision == TraderDecision.MODIFY_ORDER:
        return self._modify_open_order(action, bundle)
    raise ValueError("unsupported open-order decision")
```

Implement `_cancel_open_order` in the exact order specified by the design:
armed/frozen gates, persistent DB, fresh `OPEN_ORDER_MANAGEMENT` controls,
stable execution connection, `reqOpenOrders`, ownership resolution, replay
check, final operator check, durable `CANCEL_ATTEMPT`, one `cancelOrder`, bounded
confirmation, refreshed open-order proof, and durable `CANCEL_RESULT`.

The lifecycle persistence helper must use schema
`EXPERIMENT_ORDER_REGISTRY_LIFECYCLE_V1`, canonical JSON/hashes, the decision
cycle as request identity, and the existing registry columns without a schema
migration.

- [ ] **Step 7: Run cancel and existing execution tests GREEN**

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_open_order_management.py tests\ibkr_paper_30d\test_autonomous_execution.py
```

Expected: all tests pass and fake broker counters prove no unrelated/global cancel.

- [ ] **Step 8: Commit cancellation**

```powershell
git add ibkr_paper_30d/open_order_management.py ibkr_paper_30d/autonomous_execution.py tests/ibkr_paper_30d/test_open_order_management.py tests/ibkr_paper_30d/test_autonomous_execution.py
git commit -m "feat: cancel owned experiment orders"
```

---

### Task 5: Implement Same-ID Modification with Fresh Feasibility

**Files:**
- Modify: `ibkr_paper_30d/ibkr_research_tools.py`
- Modify: `ibkr_paper_30d/open_order_management.py`
- Modify: `ibkr_paper_30d/autonomous_execution.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_research.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_execution.py`
- Modify: `tests/ibkr_paper_30d/test_open_order_management.py`

**Interfaces:**
- Consumes: `AutonomousOpenOrderAction`, owned live trade, exact-contract quote, IBKR what-if, experimental equity.
- Produces: `IBKRResearchToolbox.validate_open_order_action(...)` and executor `_modify_open_order(...)` with preserved identity.

- [ ] **Step 1: Write failing toolbox validation tests**

Add these tests and helpers to `test_autonomous_execution.py`, where
`FakeLifecycleIB`, `lifecycle_trade`, `open_order_action_from_trade`, and
`bundle` were defined in Task 4:

```python
class ModificationValidationIB(FakeLifecycleIB):
    def __init__(self, target):
        super().__init__(target)
        self.quote_contract_ids = []
        self.what_if_calls = 0

    def reqAllOpenOrders(self):
        return self.openTrades()

    def whatIfOrder(self, contract, order):
        self.what_if_calls += 1
        return SimpleNamespace(
            commission="1.00",
            minCommission="1.00",
            maxCommission="1.00",
            initMarginChange="100.00",
            maintMarginChange="100.00",
            warningText="",
        )


def modification_validation_fixture(*, total="2", filled="0", new_total="1"):
    target = lifecycle_trade(total=total, filled=filled)
    snapshot = canonical_open_order(target)
    action = open_order_action_from_trade(target).model_copy(update={
        "new_total_quantity": Decimal(new_total),
        "new_limit_price": Decimal("9.50"),
        "reason": "Reduce and reprice the resting order.",
    })
    value = bundle().model_copy(update={"open_orders_snapshot": [snapshot]})
    fake_ib = ModificationValidationIB(target)
    toolbox = IBKRResearchToolbox()
    toolbox.live_contract_quote_evidence = lambda ib, contract: (
        fake_ib.quote_contract_ids.append(contract.conId)
        or {"success": True, "bid": 9.45, "ask": 9.50, "market_data_type": 1}
    )
    return toolbox, fake_ib, value, action


def test_modify_validation_requires_fresh_quote_and_what_if():
    toolbox, fake_ib, value, action = modification_validation_fixture()
    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )
    assert result.passed is True
    assert fake_ib.quote_contract_ids == [action.contract_id]
    assert fake_ib.what_if_calls == 1
    assert result.broker_evidence["whatIf"] is True


@pytest.mark.parametrize(
    ("quantity", "reason"),
    [("3", "OPEN_ORDER_QUANTITY_INCREASE_FORBIDDEN"), ("0.5", "OPEN_ORDER_TOTAL_BELOW_FILLED")],
)
def test_modify_validation_rejects_unsafe_quantity(quantity, reason):
    toolbox, fake_ib, value, action = modification_validation_fixture(
        total="2", filled="1", new_total=quantity
    )
    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )
    assert result.passed is False
    assert result.reason_codes == (reason,)
    assert fake_ib.what_if_calls == 0


def test_modify_to_filled_quantity_requires_reconciliation_not_zero_remainder():
    toolbox, fake_ib, value, action = modification_validation_fixture(
        total="2", filled="1", new_total="1"
    )
    result = toolbox.validate_open_order_action(
        action, value, TraderDecision.MODIFY_ORDER, ib=fake_ib
    )
    assert result.passed is False
    assert result.reason_codes == ("OPEN_ORDER_WOULD_HAVE_NO_REMAINING_QUANTITY",)
```

Also test no effective change, limit-price change on a non-LMT order, unusable
quote, what-if rejection, unacceptable warning, margin above experimental
equity, and broker state absent.

- [ ] **Step 2: Run modification validation tests RED**

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_autonomous_execution.py -k "modify_validation or unsafe_quantity or zero_remainder"
```

Expected: failures because toolbox lifecycle validation is not implemented.

- [ ] **Step 3: Implement toolbox lifecycle validation**

Implement the protocol method with optional shared connection:

```python
def validate_open_order_action(
    self,
    action: AutonomousOpenOrderAction,
    bundle: TraderInputBundle,
    decision: TraderDecision,
    *,
    ib: Any | None = None,
) -> ProposalValidation:
```

For both decisions, require an exact frozen snapshot match. For cancel, return
PASS after identity/state validation without quote or what-if. For modify,
resolve the live trade, enforce quantity and immutable-shape rules, obtain
`live_contract_quote_evidence`, clone an untransmitted what-if order, and call
`whatIfOrder`. Reuse `_feasibility_common` with only the isolated experimental
equity from the bundle. Return old state, requested change, quote, commission,
margin, warnings, and what-if evidence.

- [ ] **Step 4: Write failing executor modification tests**

Add:

```python
class FakeModifyIB(FakeLifecycleIB):
    def __init__(
        self,
        target,
        *,
        change_state_after_what_if=False,
        disconnect_after_place=False,
    ):
        super().__init__(target)
        self.change_state_after_what_if = change_state_after_what_if
        self.disconnect_after_place = disconnect_after_place
        self.what_if_calls = 0

    def reqAllOpenOrders(self):
        return self.openTrades()

    def whatIfOrder(self, contract, order):
        self.what_if_calls += 1
        if self.change_state_after_what_if:
            self.target.order.lmtPrice = 10.25
        return SimpleNamespace(
            commission="1.00",
            minCommission="1.00",
            maxCommission="1.00",
            initMarginChange="100.00",
            maintMarginChange="100.00",
            warningText="",
        )

    def placeOrder(self, contract, order):
        self.place_calls.append((contract, order))
        self.target.order = order
        self.target.orderStatus.status = "Submitted"
        self.target.orderStatus.remaining = (
            Decimal(str(order.totalQuantity))
            - Decimal(str(self.target.orderStatus.filled))
        )
        if self.disconnect_after_place:
            raise ConnectionError("disconnected after modify")
        return self.target


@contextmanager
def armed_modify_fixture(
    tmp_path,
    *,
    change_state_after_what_if=False,
    disconnect_after_place=False,
):
    with Database.open(tmp_path / "modify.sqlite3") as db:
        target = lifecycle_trade()
        action = open_order_action_from_trade(target).model_copy(update={
            "new_total_quantity": Decimal("1"),
            "new_limit_price": Decimal("9.50"),
            "reason": "Reduce and reprice the resting order.",
        })
        register_issuance(db, target)
        broker = FakeModifyIB(
            target,
            change_state_after_what_if=change_state_after_what_if,
            disconnect_after_place=disconnect_after_place,
        )
        toolbox = IBKRResearchToolbox()
        toolbox._connect = lambda *, client_id=None: broker
        toolbox.live_contract_quote_evidence = lambda ib, contract: {
            "success": True,
            "bid": 9.45,
            "ask": 9.50,
            "market_data_type": 1,
        }
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: (),
        )
        value = bundle().model_copy(
            update={"open_orders_snapshot": [canonical_open_order(target)]}
        )
        yield executor, db, broker, action, value


def test_modify_preserves_identity_and_submits_same_order_id(tmp_path):
    with armed_modify_fixture(tmp_path) as fixture:
        executor, db, fake_ib, action, value = fixture
        result = executor.execute_open_order_action(
            action, value, TraderDecision.MODIFY_ORDER
        )
        assert result.success is True
        contract, submitted = fake_ib.place_calls[0]
        assert submitted.orderId == action.order_id
        assert submitted.permId == action.perm_id
        assert submitted.clientId == action.client_id
        assert submitted.orderRef == action.order_ref
        assert submitted.action == "BUY"
        assert submitted.orderType == "LMT"
        assert submitted.tif == "DAY"
        assert submitted.totalQuantity == 1
        assert submitted.lmtPrice == 9.50
        assert contract.conId == action.contract_id


def test_state_change_after_what_if_blocks_modify_before_place_order(tmp_path):
    with armed_modify_fixture(tmp_path, change_state_after_what_if=True) as fixture:
        executor, db, fake_ib, action, value = fixture
        result = executor.execute_open_order_action(
            action, value, TraderDecision.MODIFY_ORDER
        )
        assert result.success is False
        assert result.reason_codes == ("OPEN_ORDER_STATE_CHANGED_AFTER_WHAT_IF",)
        assert fake_ib.place_calls == []


def test_modify_post_write_disconnect_is_not_replayed(tmp_path):
    with armed_modify_fixture(tmp_path, disconnect_after_place=True) as fixture:
        executor, db, fake_ib, action, value = fixture
        first = executor.execute_open_order_action(action, value, TraderDecision.MODIFY_ORDER)
        second = executor.execute_open_order_action(action, value, TraderDecision.MODIFY_ORDER)
        assert first.success is False
        assert "BROKER_CONFIRMATION_UNAVAILABLE" in first.reason_codes
        assert second.reason_codes == ("DUPLICATE_ORDER_ACTION_REQUEST",)
        assert len(fake_ib.place_calls) == 1
```

Also test broker `Inactive`, confirmation timeout, immediate kill switch or
authorization change, changed filled quantity, and preserved bounded structure.

- [ ] **Step 5: Run executor modification tests RED**

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_autonomous_execution.py -k "modify"
```

Expected: failures because `_modify_open_order` is not implemented.

- [ ] **Step 6: Implement same-ID modification**

Implement `_modify_open_order` with this immutable-field copy:

```python
modified = copy.deepcopy(trade.order)
modified.orderId = snapshot["orderId"]
modified.permId = snapshot["permId"]
modified.clientId = snapshot["clientId"]
modified.orderRef = snapshot["orderRef"]
modified.account = snapshot["account"]
modified.action = snapshot["action"]
modified.orderType = snapshot["orderType"]
modified.tif = snapshot["tif"]
modified.outsideRth = snapshot["outsideRth"]
modified.totalQuantity = float(requested_total)
modified.lmtPrice = float(requested_limit)
modified.whatIf = False
modified.transmit = True
```

Run fresh safety, live ownership, toolbox quote/what-if, a second live-state
resolution after what-if, immediate controls, durable `MODIFY_ATTEMPT`, one
same-ID `placeOrder`, bounded acknowledgement, refreshed exact-state
confirmation, and durable `MODIFY_RESULT`. Any exception after the attempt is
uncertain/fail-closed and non-replayable.

- [ ] **Step 7: Run all open-order tests GREEN**

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_autonomous_research.py tests\ibkr_paper_30d\test_open_order_management.py tests\ibkr_paper_30d\test_autonomous_execution.py
```

Expected: all tests pass.

- [ ] **Step 8: Commit modification support**

```powershell
git add ibkr_paper_30d/ibkr_research_tools.py ibkr_paper_30d/open_order_management.py ibkr_paper_30d/autonomous_execution.py tests/ibkr_paper_30d/test_autonomous_research.py tests/ibkr_paper_30d/test_autonomous_execution.py tests/ibkr_paper_30d/test_open_order_management.py
git commit -m "feat: modify owned experiment orders"
```

---

### Task 6: Integrate Runtime Routing, Immediate Refresh, and Final Audit

**Files:**
- Modify: `ibkr_paper_30d/autonomous_runtime.py`
- Modify: `ibkr_paper_30d/autonomous_service.py`
- Modify: `ibkr_paper_30d/interference_observability.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_runtime.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_service.py`
- Modify: `tests/ibkr_paper_30d/test_interference_observability.py`
- Modify: `tests/ibkr_paper_30d/test_autonomous_architecture_contract.py`

**Interfaces:**
- Consumes: accepted lifecycle outcomes and `AutonomousPaperExecutor.execute_open_order_action`.
- Produces: persisted action payloads, runtime dispatch, reporting, and one immediate observation-only post-action refresh.

- [ ] **Step 1: Write failing runtime routing tests**

Add a provider returning `CANCEL_ORDER`, a recording executor, and:

```python
class OpenOrderToolbox(PassiveToolbox):
    def validate_open_order_action(self, action, bundle, decision):
        return ProposalValidation(
            passed=True,
            reason_codes=(),
            broker_evidence={"decision": decision.value},
        )


class CancelProvider:
    last_native_tool_events = []

    def __init__(self, snapshot):
        self.snapshot = snapshot

    def next_turn(self, request, bundle, history, toolbox_manifest):
        return AutonomousTurn(
            mode=AutonomousTurnMode.FINAL,
            research_requests=[],
            decision=TraderDecision.CANCEL_ORDER,
            proposal=None,
            position_action=None,
            open_order_action=AutonomousOpenOrderAction(
                order_ref=self.snapshot["orderRef"],
                order_id=self.snapshot["orderId"],
                perm_id=self.snapshot["permId"],
                client_id=self.snapshot["clientId"],
                contract_id=self.snapshot["contract"]["conId"],
                observed_state_sha256=self.snapshot["state_sha256"],
                reason="Cancel the selected resting experiment order.",
            ),
            confidence="0.9",
            reasoning_summary="The resting order no longer has sufficient edge.",
            reason_codes=["EDGE_DECAYED"],
        )


class RecordingExecutor:
    def __init__(self):
        self.open_order_calls = []

    def execute_open_order_action(self, action, bundle, decision):
        self.open_order_calls.append((action, decision))
        return PaperExecutionResult(
            success=True,
            status="Cancelled",
            reason_codes=(),
            order={"order_management": decision.value, "fills": []},
            broker_validation={},
        )


def bundle_with_owned_open_order():
    snapshot = {
        "orderRef": "codex-ibkr-paper-30d-a-cycle",
        "orderId": 41,
        "permId": 9001,
        "clientId": 19761,
        "contract": {"conId": 756733},
        "state_sha256": "a" * 64,
    }
    return bundle().model_copy(
        update={"open_orders_snapshot": [snapshot]}
    )


def test_runtime_dispatches_accepted_cancel_to_open_order_executor(tmp_path):
    value = bundle_with_owned_open_order()
    executor = RecordingExecutor()
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        result = run_autonomous_cycle(
            value,
            execute_paper=True,
            database=db,
            provider=CancelProvider(value.open_orders_snapshot[0]),
            toolbox=OpenOrderToolbox(),
            executor=executor,
        )
        final_payload = db.execute(
            "SELECT payload_json FROM autonomous_research_events "
            "WHERE event_type='final_outcome'"
        ).fetchone()[0]
    assert executor.open_order_calls[0][1] == TraderDecision.CANCEL_ORDER
    assert result["execution"]["order"]["order_management"] == "CANCEL_ORDER"
    assert '"open_order_action"' in final_payload
```

Add a duplicate/replayed accepted cycle test proving the persistent unique
decision-cycle contract blocks a second dispatch.

- [ ] **Step 2: Write failing service refresh and reporting tests**

Add:

```python
def test_successful_order_management_triggers_one_observation_only_refresh(
    tmp_path, monkeypatch
):
    FakeLedger.positions = ()
    monkeypatch.setattr(service_module, "AutonomousExperimentLedger", FakeLedger)
    clock = Clock()
    results = [{
            "status": "PASS",
            "outcome": {"decision": "CANCEL_ORDER"},
            "execution": {
                "success": True,
                "order": {"order_management": "CANCEL_ORDER", "fills": []},
            },
        }, {"status": "PASS", "outcome": {"decision": "NO_TRADE"}}]
    with Database.open(tmp_path / "service.sqlite3") as db:
        service = make_service(db, clock, stop_after=2, results=results)
        service.run_forever()
    assert service.triggers == [
        ("SCHEDULED_SCAN", None),
        ("POSITION_EVENT", False),
    ]
```

Extend interference tests so `CANCEL_ORDER` and `MODIFY_ORDER` are classified
as model trade-management decisions without being counted as new entries or
position fills.

- [ ] **Step 3: Run integration tests RED**

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_autonomous_runtime.py tests\ibkr_paper_30d\test_autonomous_service.py tests\ibkr_paper_30d\test_interference_observability.py
```

Expected: lifecycle payload/routing/refresh assertions fail.

- [ ] **Step 4: Implement runtime and service integration**

Persist `open_order_action` beside proposal and position action:

```python
"open_order_action": (
    None
    if outcome.open_order_action is None
    else outcome.open_order_action.model_dump(mode="json")
),
```

Dispatch accepted lifecycle decisions:

```python
elif (
    outcome.decision in {TraderDecision.CANCEL_ORDER, TraderDecision.MODIFY_ORDER}
    and outcome.open_order_action is not None
):
    execution = executor.execute_open_order_action(
        outcome.open_order_action, bundle, outcome.decision
    )
```

In `run_forever`, set the observation-only follow-up condition to true when an
execution has fills or when a successful execution order contains
`order_management` equal to `CANCEL_ORDER` or `MODIFY_ORDER`. Preserve
`allow_execution=False` for the follow-up.

Update interference reporting decision sets to include both lifecycle
decisions while keeping entry, reduction, close, cancel, and modify counts
semantically distinct.

- [ ] **Step 5: Add static architecture assertions**

Extend `test_autonomous_architecture_contract.py`:

```python
def test_open_order_writes_exist_only_in_authoritative_executor():
    executor = Path("ibkr_paper_30d/autonomous_execution.py").read_text(encoding="utf-8")
    assert ".cancelOrder(" in executor
    assert ".placeOrder(" in executor
    for path in AUTONOMOUS_MODULES:
        if path == Path("ibkr_paper_30d/autonomous_execution.py"):
            continue
        source = path.read_text(encoding="utf-8")
        assert ".cancelOrder(" not in source


def test_open_order_management_retains_paper_arm_and_live_route_guards():
    source = Path("ibkr_paper_30d/autonomous_execution.py").read_text(encoding="utf-8")
    assert "IBKR_AUTONOMOUS_PAPER_ARMED" in source
    assert "EXECUTION_CLIENT_ID" in source
    assert "7497" not in source
    assert "7496" not in source
```

- [ ] **Step 6: Run focused integration tests GREEN**

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_autonomous_runtime.py tests\ibkr_paper_30d\test_autonomous_service.py tests\ibkr_paper_30d\test_interference_observability.py tests\ibkr_paper_30d\test_autonomous_architecture_contract.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit runtime integration**

```powershell
git add ibkr_paper_30d/autonomous_runtime.py ibkr_paper_30d/autonomous_service.py ibkr_paper_30d/interference_observability.py tests/ibkr_paper_30d/test_autonomous_runtime.py tests/ibkr_paper_30d/test_autonomous_service.py tests/ibkr_paper_30d/test_interference_observability.py tests/ibkr_paper_30d/test_autonomous_architecture_contract.py
git commit -m "feat: integrate autonomous order lifecycle"
```

- [ ] **Step 8: Run the owner-required focused suites**

```powershell
python -m pytest -q tests\ibkr_paper_30d\test_prerequisite_finalizer.py tests\ibkr_paper_30d\test_auditor_runtime.py
```

Expected: all tests pass.

- [ ] **Step 9: Run the complete IBKR PAPER suite**

```powershell
python -m pytest -q tests\ibkr_paper_30d
```

Expected: every collected test passes, zero failures.

- [ ] **Step 10: Run PowerShell AST and diff validation**

Run an AST parse over every repository PowerShell file touched since
`534dc86888d7b85e2d1f22ad204b37edc11c6c0d`, plus the prerequisite and auditor
entrypoints:

```powershell
$files = @(
  'FINALIZE_IBKR_PREREQUISITES.ps1',
  'RUN_IBKR_MARKET_DATA_GATE.ps1',
  'SYNC_LOCAL_CODEX_IBKR.ps1',
  'AUDITOR_WINDOWS_PROVISIONING_V1.ps1',
  'AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1',
  'auditor_runtime\AUDITOR_DENIAL_PROBE_V1.ps1',
  'auditor_runtime\AUDITOR_GATE_V2_PROBE.ps1',
  'auditor_runtime\CODEX_DECISION_AUDITOR_V1.ps1'
)
foreach ($file in $files) {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $file), [ref]$tokens, [ref]$errors
  ) | Out-Null
  if ($errors.Count -ne 0) { throw "POWERSHELL_PARSE_FAILED:$file" }
}
git diff --check 69d5d97..HEAD
```

Expected: no parser errors and `git diff --check` exits 0.

- [ ] **Step 11: Run security/static checks and prove no real broker write**

```powershell
python -m bandit -q -r ibkr_paper_30d
rg -n "7496|7497|LIVE_TRADING|reqGlobalCancel" ibkr_paper_30d tests\ibkr_paper_30d
git diff --name-only 69d5d97..HEAD | rg "^auditor_runtime/|^AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json$"
```

Expected: Bandit exits 0; no new LIVE port or global-cancel authority; no
auditor runtime or trust-anchor file appears in the implementation diff. Test
fake counters must show exactly the expected fake `cancelOrder`/`placeOrder`
calls and zero real broker writes.

- [ ] **Step 12: Recompute immutable hashes and compare to Task 1**

```powershell
Get-FileHash -Algorithm SHA256 AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json,auditor_runtime\AUDITOR_DENIAL_PROBE_V1.ps1,auditor_runtime\AUDITOR_GATE_V2_PROBE.ps1,auditor_runtime\CODEX_DECISION_AUDITOR_V1.ps1
```

Expected: all four hashes exactly match Task 1.

- [ ] **Step 13: Perform an independent read-only final review against the spec**

Build a review package from the approved spec, this plan, and
`git diff 69d5d97..HEAD`, then send it to a fresh Codex CLI context in read-only
mode:

```powershell
$reviewPrompt = @"
Act as an independent senior security and trading-runtime reviewer. Review the
approved design, implementation plan, and complete implementation diff below.
Report findings first, ordered Critical, Important, Minor, with exact file and
line references. Focus on order ownership ambiguity, stale-state races,
write-before-persist ordering, replay behavior, client-ID consistency,
PAPER-only routing, bounded liability, post-write uncertainty, and misleading
success states. State PASS only when there are no Critical or Important
findings.

DESIGN:
$(Get-Content -Raw docs\superpowers\specs\2026-09-23-autonomous-open-order-management-design.md)

PLAN:
$(Get-Content -Raw docs\superpowers\plans\2026-09-23-autonomous-open-order-management.md)

DIFF:
$(git diff --no-ext-diff 69d5d97..HEAD)
"@
$reviewPrompt | codex exec --ephemeral --ignore-user-config --skip-git-repo-check --sandbox read-only --model gpt-6-astra -c 'model_reasoning_effort="max"' -
```

Independently re-check the diff locally after reading the reviewer output. Any
Critical or Important finding must receive a new failing regression test, a
minimal fix, and a fresh full-suite run before launch preflight. Record Minor
findings explicitly for owner review; do not silently convert them to PASS.

- [ ] **Step 14: Produce the prelaunch evidence report without arming**

Report:

- `Repository`: the exact value from `git rev-parse HEAD`.
- `Tests`: the exact passed, failed, and skipped counts from the fresh full run.
- `External/final audit`: `PASS` only if Step 13 has no unresolved Critical or Important finding; otherwise `BLOCK` with every finding.
- `Capability evidence`: `96edf30873072150c0063da65228d660f5af397d5a3b80cc1cab5b451bd944fc`.
- `Cancel order`: `PASS` only when every Task 4 test passes.
- `Modify/replace`: `PASS` only when every Task 5 test passes.
- `Auditor runtime hashes changed`: `false` only when all Task 12 hashes match Task 1.
- `Trust-anchor impact`: `NONE` only when the trust-anchor hash and diff are unchanged; otherwise the exact changed path and hash.
- `Real broker write calls`: `0`.
- `Paper execution armed`: `false`.
- `Final status`: `READY_FOR_PREFLIGHT` only when every preceding item passes; otherwise `BLOCKED` followed by the exact failed item and reason code.

Do not initialize the experiment clock, record authorization, clear the kill
switch, set the armed environment variable, or start the service in this task.
Those are launch operations performed only after implementation review and a
separate fresh control-plane preflight.
