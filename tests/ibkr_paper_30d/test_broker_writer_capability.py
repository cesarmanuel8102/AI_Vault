from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.broker_writer_capability import (
    IBKRPaperProbeBackend,
    PaperProbeError,
    run_paper_probe,
)
from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.ibkr_readonly import expected_identity_hash


NOW = datetime(2026, 10, 2, 3, 15, tzinfo=timezone.utc)
HEAD = "3" * 40
ACCOUNT = "a" * 64


def _artifact(payload):
    body = dict(payload)
    body["artifact_sha256"] = sha256_json(body)
    return body


def _write(path, payload):
    path.write_bytes(canonical_bytes(payload))


def _receipt(path, **updates):
    payload = {
        "schema": "BROKER_WRITER_PAPER_PROBE_AUTHORIZATION_V1",
        "authorization_id": "probe-auth-1",
        "one_use": True,
        "consumed": False,
        "expires_at_utc": (NOW + timedelta(minutes=10)).isoformat(),
        "approved_head": HEAD,
        "expected_account_identity_sha256": ACCOUNT,
        "host": "127.0.0.1",
        "port": 4002,
        "writer_client_id": 19761,
        "observer_client_id": 19762,
        "symbol": "SPY",
        "quantity": 1,
        "initial_limit_price": "0.01",
        "modified_limit_price": "0.02",
        "maximum_notional": "0.02",
    }
    payload.update(updates)
    _write(path, _artifact(payload))


def _runtime(path, **updates):
    payload = {
        "schema": "BROKER_WRITER_PAPER_PROBE_RUNTIME_STATE_V1",
        "captured_at_utc": NOW.isoformat(),
        "runtime_active": False,
        "scheduler_disabled": True,
        "open_order_count": 0,
        "position_count": 0,
        "execution_count": 0,
        "approved_head": HEAD,
        "expected_account_identity_sha256": ACCOUNT,
    }
    payload.update(updates)
    _write(path, _artifact(payload))


class FakeBackend:
    def __init__(self, *, final=None, fail_at=None):
        self.events = []
        self.fail_at = fail_at
        self.final = final or {
            "open_order_count": 0,
            "position_count": 0,
            "execution_count": 0,
            "probe_order_terminal": True,
        }

    def _event(self, name):
        self.events.append(name)
        if self.fail_at == name:
            raise RuntimeError(f"failure at {name}")

    def preflight(self, config):
        self._event("preflight")
        return {
            "environment": "PAPER",
            "account_identity_sha256": ACCOUNT,
            "open_order_count": 0,
            "position_count": 0,
            "execution_count": 0,
        }

    def duplicate_connection_rejected(self):
        self._event("duplicate")
        return True

    def place_probe_order(self):
        self._event("place")
        return {"order_id": 41, "perm_id": 9001, "order_ref": "probe:auth-1"}

    def modify_probe_order(self, identity):
        self._event("modify")
        return identity

    def cross_client_cancel_rejected(self, identity):
        self._event("cross_cancel")
        return True

    def cancel_probe_order(self, identity):
        self._event("same_cancel")

    def reconcile(self, identity):
        self._event("reconcile")
        return dict(self.final)

    def disconnect_all(self):
        self._event("disconnect")

    def evidence(self):
        return {
            "duplicate_connection_error_codes": [326],
            "cross_client_cancel_error_codes": [10147],
            "broker_confirmed_modified_limit_price": "0.02",
        }


def test_probe_consumes_receipt_and_executes_exact_ownership_sequence(tmp_path):
    receipt = tmp_path / "authorization.json"
    runtime = tmp_path / "runtime.json"
    report = tmp_path / "report.json"
    _receipt(receipt)
    _runtime(runtime)
    backend = FakeBackend()

    result = run_paper_probe(
        receipt,
        runtime,
        report,
        backend=backend,
        expected_head=HEAD,
        now_utc=lambda: NOW,
    )

    assert result["status"] == "PASS"
    assert result["real_broker_write_calls"] == 4
    assert backend.events == [
        "preflight",
        "duplicate",
        "place",
        "modify",
        "cross_cancel",
        "same_cancel",
        "reconcile",
        "disconnect",
    ]
    assert json.loads(receipt.read_text())["consumed"] is True
    assert json.loads(report.read_text())["artifact_sha256"] == result["artifact_sha256"]
    assert result["capability_evidence"] == {
        "duplicate_connection_error_codes": [326],
        "cross_client_cancel_error_codes": [10147],
        "broker_confirmed_modified_limit_price": "0.02",
    }


@pytest.mark.parametrize(
    ("receipt_updates", "runtime_updates", "reason"),
    [
        ({"consumed": True}, {}, "AUTHORIZATION_ALREADY_CONSUMED"),
        ({"expires_at_utc": (NOW - timedelta(seconds=1)).isoformat()}, {}, "AUTHORIZATION_EXPIRED"),
        ({"approved_head": "4" * 40}, {}, "AUTHORIZATION_HEAD_MISMATCH"),
        ({}, {"runtime_active": True}, "ACTIVE_EXPERIMENT_OR_ORDER_SET"),
        ({}, {"open_order_count": 1}, "ACTIVE_EXPERIMENT_OR_ORDER_SET"),
        ({}, {"scheduler_disabled": False}, "SCHEDULER_NOT_DISABLED"),
        ({}, {"captured_at_utc": (NOW - timedelta(minutes=6)).isoformat()}, "RUNTIME_STATE_STALE"),
    ],
)
def test_probe_blocks_before_connection_when_authority_or_runtime_is_invalid(
    tmp_path, receipt_updates, runtime_updates, reason
):
    receipt = tmp_path / "authorization.json"
    runtime = tmp_path / "runtime.json"
    report = tmp_path / "report.json"
    _receipt(receipt, **receipt_updates)
    _runtime(runtime, **runtime_updates)
    backend = FakeBackend()

    with pytest.raises(PaperProbeError, match=reason):
        run_paper_probe(
            receipt,
            runtime,
            report,
            backend=backend,
            expected_head=HEAD,
            now_utc=lambda: NOW,
        )

    assert backend.events == []


def test_probe_failure_consumes_authorization_and_attempts_exact_cleanup(tmp_path):
    receipt = tmp_path / "authorization.json"
    runtime = tmp_path / "runtime.json"
    report = tmp_path / "report.json"
    _receipt(receipt)
    _runtime(runtime)
    backend = FakeBackend(fail_at="cross_cancel")

    with pytest.raises(PaperProbeError, match="PROBE_EXECUTION_FAILED"):
        run_paper_probe(
            receipt,
            runtime,
            report,
            backend=backend,
            expected_head=HEAD,
            now_utc=lambda: NOW,
        )

    assert json.loads(receipt.read_text())["consumed"] is True
    assert "same_cancel" in backend.events
    assert backend.events[-1] == "disconnect"
    assert json.loads(report.read_text())["status"] == "BLOCK"


def test_probe_blocks_when_final_reconciliation_has_any_exposure(tmp_path):
    receipt = tmp_path / "authorization.json"
    runtime = tmp_path / "runtime.json"
    report = tmp_path / "report.json"
    _receipt(receipt)
    _runtime(runtime)
    backend = FakeBackend(
        final={
            "open_order_count": 1,
            "position_count": 0,
            "execution_count": 0,
            "probe_order_terminal": False,
        }
    )

    with pytest.raises(PaperProbeError, match="FINAL_RECONCILIATION_FAILED"):
        run_paper_probe(
            receipt,
            runtime,
            report,
            backend=backend,
            expected_head=HEAD,
            now_utc=lambda: NOW,
        )

    assert json.loads(report.read_text())["status"] == "BLOCK"


class FakeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def emit(self, *args):
        for handler in self.handlers:
            handler(*args)


class FakeIB:
    def __init__(self, role, shared):
        self.role = role
        self.shared = shared
        self.errorEvent = FakeEvent()
        self.connected = False

    def connect(self, host, port, *, clientId, readonly, timeout):
        self.shared["connects"].append((self.role, host, port, clientId, readonly))
        if self.role == "duplicate":
            self.errorEvent.emit(-1, 326, "client id already in use", None)
            raise ConnectionError("duplicate client")
        self.connected = True
        self.client_id = clientId
        return self

    def disconnect(self):
        self.connected = False

    def managedAccounts(self):
        return ["DU123456"]

    def reqCurrentTime(self):
        return NOW

    def reqExecutions(self):
        return []

    def positions(self):
        return []

    def qualifyContracts(self, contract):
        contract.conId = 756733
        return [contract]

    def reqAllOpenOrders(self):
        trade = self.shared.get("trade")
        self.shared["read_events"].append(
            (
                self.role,
                None if trade is None else float(trade.order.lmtPrice),
            )
        )
        if trade is None or trade.orderStatus.status == "Cancelled":
            return []
        return [trade]

    def placeOrder(self, contract, order):
        self.shared["place_calls"].append((self.role, order.lmtPrice))
        trade = self.shared.get("trade")
        if trade is None:
            order.orderId = 41
            order.permId = 9001
            order.clientId = 19761
            trade = SimpleNamespace(
                contract=contract,
                order=order,
                orderStatus=SimpleNamespace(status="PreSubmitted"),
            )
            self.shared["trade"] = trade
        else:
            trade.order.lmtPrice = order.lmtPrice
        return trade

    def cancelOrder(self, order):
        self.shared["cancel_calls"].append(self.role)
        if self.role == "observer":
            self.errorEvent.emit(order.orderId, 10147, "order id not found", None)
            return
        self.shared["trade"].orderStatus.status = "Cancelled"

    def sleep(self, _seconds):
        return None


def test_real_backend_proves_same_client_ownership_without_global_cancel():
    shared = {
        "connects": [],
        "place_calls": [],
        "cancel_calls": [],
        "read_events": [],
    }
    roles = iter(("writer", "duplicate", "observer"))

    def ib_factory():
        return FakeIB(next(roles), shared)

    config = {
        "authorization_id": "probe-auth-1",
        "host": "127.0.0.1",
        "port": 4002,
        "writer_client_id": 19761,
        "observer_client_id": 19762,
        "expected_account_identity_sha256": expected_identity_hash("DU123456"),
        "symbol": "SPY",
        "quantity": 1,
        "initial_limit_price": "0.01",
        "modified_limit_price": "0.02",
    }
    backend = IBKRPaperProbeBackend(
        config,
        ib_factory=ib_factory,
        contract_factory=lambda symbol, exchange, currency: SimpleNamespace(
            symbol=symbol, exchange=exchange, currency=currency, conId=0
        ),
        order_factory=lambda action, quantity, price: SimpleNamespace(
            action=action,
            totalQuantity=quantity,
            lmtPrice=price,
            orderId=0,
            permId=0,
            clientId=0,
            orderRef="",
            account="",
            tif="DAY",
            outsideRth=False,
            overridePercentageConstraints=False,
        ),
    )

    assert backend.preflight(config)["environment"] == "PAPER"
    assert backend.duplicate_connection_rejected() is True
    identity = backend.place_probe_order()
    assert backend.modify_probe_order(identity) == identity
    assert backend.cross_client_cancel_rejected(identity) is True
    backend.cancel_probe_order(identity)
    assert backend.reconcile(identity) == {
        "open_order_count": 0,
        "position_count": 0,
        "execution_count": 0,
        "probe_order_terminal": True,
    }
    backend.disconnect_all()

    assert shared["place_calls"] == [("writer", 0.01), ("writer", 0.02)]
    assert shared["cancel_calls"] == ["observer", "writer"]
    assert all(item[-1] is False for item in shared["connects"])
    modified_read = shared["read_events"].index(("writer", 0.02))
    observer_read = shared["read_events"].index(("observer", 0.02))
    assert modified_read < observer_read
    assert backend.evidence() == {
        "duplicate_connection_error_codes": [326],
        "cross_client_cancel_error_codes": [10147],
        "broker_confirmed_modified_limit_price": "0.02",
    }
