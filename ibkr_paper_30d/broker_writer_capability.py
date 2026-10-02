"""Disabled-by-default harness for validating same-client PAPER write ownership."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .canonical import canonical_bytes, sha256_json
from .ibkr_readonly import expected_identity_hash


class PaperProbeError(RuntimeError):
    pass


class IBKRPaperProbeBackend:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        ib_factory: Callable[[], Any] | None = None,
        contract_factory: Callable[[str, str, str], Any] | None = None,
        order_factory: Callable[[str, int, float], Any] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if ib_factory is None or contract_factory is None or order_factory is None:
            from ib_insync import IB, LimitOrder, Stock

            ib_factory = ib_factory or IB
            contract_factory = contract_factory or Stock
            order_factory = order_factory or LimitOrder
        self.config = config
        self.ib_factory = ib_factory
        self.contract_factory = contract_factory
        self.order_factory = order_factory
        self.monotonic = monotonic
        self.writer = None
        self.observer = None
        self.duplicate = None
        self.account = ""
        self.contract = None
        self.trade = None
        self._observer_errors: list[tuple[int, str]] = []

    def _connect(self, client: Any, client_id: int) -> None:
        client.connect(
            self.config["host"],
            int(self.config["port"]),
            clientId=client_id,
            readonly=False,
            timeout=8,
        )

    @staticmethod
    def _error_collector(target: list[tuple[int, str]]):
        def collect(_request_id: int, code: int, message: str, _contract: Any) -> None:
            target.append((int(code), str(message)))

        return collect

    def _wait(self, predicate: Callable[[], bool], reason: str, seconds: float = 10) -> None:
        deadline = self.monotonic() + seconds
        while not predicate():
            if self.monotonic() >= deadline:
                raise PaperProbeError(reason)
            self.writer.sleep(0.1)

    def _matching_trades(self, client: Any, identity: dict[str, Any]) -> list[Any]:
        return [
            trade
            for trade in list(client.reqAllOpenOrders())
            if str(getattr(trade.order, "orderRef", "") or "")
            == identity["order_ref"]
            and int(getattr(trade.order, "orderId", 0) or 0)
            == identity["order_id"]
            and int(getattr(trade.order, "permId", 0) or 0)
            == identity["perm_id"]
        ]

    def preflight(self, _config: dict[str, Any]) -> dict[str, Any]:
        self.writer = self.ib_factory()
        self._connect(self.writer, int(self.config["writer_client_id"]))
        accounts = list(self.writer.managedAccounts())
        if len(accounts) != 1 or not str(accounts[0]).upper().startswith("DU"):
            raise PaperProbeError("PAPER_ACCOUNT_REQUIRED")
        self.account = str(accounts[0])
        server_time = self.writer.reqCurrentTime()
        if server_time is None or not hasattr(server_time, "astimezone"):
            raise PaperProbeError("BROKER_TIME_REQUIRED")
        return {
            "environment": "PAPER" if int(self.config["port"]) == 4002 else "UNKNOWN",
            "account_identity_sha256": expected_identity_hash(self.account),
            "open_order_count": len(list(self.writer.reqAllOpenOrders())),
            "position_count": len(list(self.writer.positions())),
            "execution_count": len(list(self.writer.reqExecutions())),
        }

    def duplicate_connection_rejected(self) -> bool:
        self.duplicate = self.ib_factory()
        errors: list[tuple[int, str]] = []
        self.duplicate.errorEvent += self._error_collector(errors)
        try:
            self._connect(self.duplicate, int(self.config["writer_client_id"]))
        except Exception:
            pass
        return any(code == 326 for code, _message in errors)

    def place_probe_order(self) -> dict[str, Any]:
        self.contract = self.contract_factory(
            str(self.config["symbol"]), "SMART", "USD"
        )
        qualified = list(self.writer.qualifyContracts(self.contract))
        if len(qualified) != 1 or int(getattr(qualified[0], "conId", 0) or 0) <= 0:
            raise PaperProbeError("PROBE_CONTRACT_QUALIFICATION_FAILED")
        self.contract = qualified[0]
        order = self.order_factory(
            "BUY",
            int(self.config["quantity"]),
            float(self.config["initial_limit_price"]),
        )
        order.account = self.account
        order.orderRef = f"codex-capability:{self.config['authorization_id']}"
        order.tif = "DAY"
        order.outsideRth = False
        order.overridePercentageConstraints = True
        self.trade = self.writer.placeOrder(self.contract, order)
        self._wait(
            lambda: int(getattr(self.trade.order, "orderId", 0) or 0) > 0
            and int(getattr(self.trade.order, "permId", 0) or 0) > 0,
            "PROBE_ORDER_IDENTITY_UNCONFIRMED",
        )
        return {
            "order_id": int(self.trade.order.orderId),
            "perm_id": int(self.trade.order.permId),
            "order_ref": str(self.trade.order.orderRef),
        }

    def modify_probe_order(self, identity: dict[str, Any]) -> dict[str, Any]:
        modified = deepcopy(self.trade.order)
        modified.lmtPrice = float(self.config["modified_limit_price"])
        self.trade = self.writer.placeOrder(self.contract, modified)
        self._wait(
            lambda: float(getattr(self.trade.order, "lmtPrice", 0) or 0)
            == float(self.config["modified_limit_price"]),
            "PROBE_MODIFICATION_UNCONFIRMED",
        )
        return {
            "order_id": int(self.trade.order.orderId),
            "perm_id": int(self.trade.order.permId),
            "order_ref": str(self.trade.order.orderRef),
        }

    def cross_client_cancel_rejected(self, identity: dict[str, Any]) -> bool:
        self.observer = self.ib_factory()
        self.observer.errorEvent += self._error_collector(self._observer_errors)
        self._connect(self.observer, int(self.config["observer_client_id"]))
        matches = self._matching_trades(self.observer, identity)
        if len(matches) != 1:
            raise PaperProbeError("CROSS_CLIENT_ORDER_VISIBILITY_FAILED")
        self.observer.cancelOrder(matches[0].order)
        self.observer.sleep(1.0)
        remains = len(self._matching_trades(self.writer, identity)) == 1
        return remains and bool(self._observer_errors)

    def cancel_probe_order(self, identity: dict[str, Any]) -> None:
        matches = self._matching_trades(self.writer, identity)
        target = matches[0] if len(matches) == 1 else self.trade
        self.writer.cancelOrder(target.order)
        self._wait(
            lambda: len(self._matching_trades(self.writer, identity)) == 0,
            "PROBE_CANCELLATION_UNCONFIRMED",
        )

    def reconcile(self, identity: dict[str, Any]) -> dict[str, Any]:
        open_orders = list(self.writer.reqAllOpenOrders())
        return {
            "open_order_count": len(open_orders),
            "position_count": len(list(self.writer.positions())),
            "execution_count": len(list(self.writer.reqExecutions())),
            "probe_order_terminal": not self._matching_trades(self.writer, identity),
        }

    def disconnect_all(self) -> None:
        for client in (self.observer, self.duplicate, self.writer):
            if client is not None:
                try:
                    client.disconnect()
                except Exception:
                    pass


def run_paper_probe(
    receipt_path: Path,
    runtime_state_path: Path,
    report_path: Path,
    *,
    backend: Any,
    expected_head: str,
    now_utc: Callable[[], datetime],
) -> dict[str, Any]:
    now = now_utc().astimezone(timezone.utc)
    claim_path = receipt_path.with_name(f"{receipt_path.name}.claim")
    try:
        claim_fd = os.open(
            claim_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
        )
    except FileExistsError as exc:
        raise PaperProbeError("AUTHORIZATION_CLAIMED_BY_ANOTHER_PROCESS") from exc
    try:
        os.write(claim_fd, str(os.getpid()).encode("ascii"))
        receipt = _read_verified_artifact(
            receipt_path, "BROKER_WRITER_PAPER_PROBE_AUTHORIZATION_V1"
        )
        runtime = _read_verified_artifact(
            runtime_state_path, "BROKER_WRITER_PAPER_PROBE_RUNTIME_STATE_V1"
        )
        _validate_authority(receipt, runtime, expected_head=expected_head, now=now)

        receipt_hash = str(receipt["artifact_sha256"])
        runtime_hash = str(runtime["artifact_sha256"])
        consumed = dict(receipt)
        consumed.pop("artifact_sha256", None)
        consumed["consumed"] = True
        consumed["consumed_at_utc"] = now.isoformat()
        consumed["authorization_sha256_before_consumption"] = receipt_hash
        _write_artifact(receipt_path, consumed)
    finally:
        os.close(claim_fd)
        claim_path.unlink(missing_ok=True)

    identity: dict[str, Any] | None = None
    cancel_attempted = False
    write_calls = 0
    failure: str | None = None
    reconciliation: dict[str, Any] = {}
    try:
        preflight = backend.preflight(receipt)
        if (
            preflight.get("environment") != "PAPER"
            or preflight.get("account_identity_sha256")
            != receipt["expected_account_identity_sha256"]
        ):
            raise PaperProbeError("PAPER_IDENTITY_MISMATCH")
        if any(
            int(preflight.get(key, -1)) != 0
            for key in ("open_order_count", "position_count", "execution_count")
        ):
            raise PaperProbeError("BROKER_STATE_NOT_CLEAN")
        if backend.duplicate_connection_rejected() is not True:
            raise PaperProbeError("DUPLICATE_CLIENT_ID_NOT_REJECTED")
        write_calls += 1
        identity = dict(backend.place_probe_order())
        write_calls += 1
        modified = dict(backend.modify_probe_order(identity))
        if modified != identity:
            raise PaperProbeError("MODIFY_ORDER_IDENTITY_CHANGED")
        write_calls += 1
        if backend.cross_client_cancel_rejected(identity) is not True:
            raise PaperProbeError("CROSS_CLIENT_CANCEL_NOT_REJECTED")
        write_calls += 1
        backend.cancel_probe_order(identity)
        cancel_attempted = True
        reconciliation = dict(backend.reconcile(identity))
        if (
            any(
                int(reconciliation.get(key, -1)) != 0
                for key in ("open_order_count", "position_count", "execution_count")
            )
            or reconciliation.get("probe_order_terminal") is not True
        ):
            raise PaperProbeError("FINAL_RECONCILIATION_FAILED")
    except PaperProbeError as exc:
        failure = str(exc)
    except Exception:
        failure = "PROBE_EXECUTION_FAILED"
    finally:
        if identity is not None and not cancel_attempted:
            try:
                write_calls += 1
                backend.cancel_probe_order(identity)
            except Exception:
                failure = failure or "PROBE_CLEANUP_FAILED"
        try:
            backend.disconnect_all()
        except Exception:
            failure = failure or "PROBE_DISCONNECT_FAILED"

    report_body = {
        "schema": "BROKER_WRITER_PAPER_PROBE_REPORT_V1",
        "status": "PASS" if failure is None else "BLOCK",
        "reason_codes": [] if failure is None else [failure],
        "completed_at_utc": now.isoformat(),
        "authorization_sha256": receipt_hash,
        "runtime_state_sha256": runtime_hash,
        "approved_head": expected_head,
        "account_identity_sha256": receipt["expected_account_identity_sha256"],
        "writer_client_id": receipt["writer_client_id"],
        "observer_client_id": receipt["observer_client_id"],
        "order_identity": identity or {},
        "final_reconciliation": reconciliation,
        "real_broker_write_calls": write_calls,
        "global_cancel_calls": 0,
    }
    report = _write_artifact(report_path, report_body)
    if failure is not None:
        raise PaperProbeError(failure)
    return report


def _read_verified_artifact(path: Path, schema: str) -> dict[str, Any]:
    if not path.is_file():
        raise PaperProbeError("REQUIRED_ARTIFACT_MISSING")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaperProbeError("ARTIFACT_INVALID") from exc
    if not isinstance(payload, dict) or payload.get("schema") != schema:
        raise PaperProbeError("ARTIFACT_INVALID")
    body = dict(payload)
    claimed = body.pop("artifact_sha256", None)
    if claimed != sha256_json(body):
        raise PaperProbeError("ARTIFACT_HASH_MISMATCH")
    return payload


def _parse_utc(value: Any, reason: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PaperProbeError(reason) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperProbeError(reason)
    return parsed.astimezone(timezone.utc)


def _validate_authority(
    receipt: dict[str, Any],
    runtime: dict[str, Any],
    *,
    expected_head: str,
    now: datetime,
) -> None:
    if receipt.get("one_use") is not True:
        raise PaperProbeError("ONE_USE_AUTHORIZATION_REQUIRED")
    if receipt.get("consumed") is True:
        raise PaperProbeError("AUTHORIZATION_ALREADY_CONSUMED")
    if _parse_utc(receipt.get("expires_at_utc"), "AUTHORIZATION_EXPIRY_INVALID") <= now:
        raise PaperProbeError("AUTHORIZATION_EXPIRED")
    if receipt.get("approved_head") != expected_head:
        raise PaperProbeError("AUTHORIZATION_HEAD_MISMATCH")
    if runtime.get("approved_head") != expected_head:
        raise PaperProbeError("RUNTIME_HEAD_MISMATCH")
    if runtime.get("expected_account_identity_sha256") != receipt.get(
        "expected_account_identity_sha256"
    ):
        raise PaperProbeError("RUNTIME_ACCOUNT_MISMATCH")
    if runtime.get("scheduler_disabled") is not True:
        raise PaperProbeError("SCHEDULER_NOT_DISABLED")
    if runtime.get("runtime_active") is True or any(
        int(runtime.get(key, -1)) != 0
        for key in ("open_order_count", "position_count", "execution_count")
    ):
        raise PaperProbeError("ACTIVE_EXPERIMENT_OR_ORDER_SET")
    captured = _parse_utc(runtime.get("captured_at_utc"), "RUNTIME_STATE_INVALID")
    if now - captured > timedelta(minutes=5) or captured > now + timedelta(seconds=5):
        raise PaperProbeError("RUNTIME_STATE_STALE")
    if (
        receipt.get("host") != "127.0.0.1"
        or int(receipt.get("port", 0)) != 4002
        or int(receipt.get("writer_client_id", 0)) <= 0
        or int(receipt.get("observer_client_id", 0)) <= 0
        or receipt.get("writer_client_id") == receipt.get("observer_client_id")
        or int(receipt.get("quantity", 0)) != 1
        or str(receipt.get("maximum_notional")) != "0.02"
    ):
        raise PaperProbeError("AUTHORIZATION_SCOPE_INVALID")


def _write_artifact(path: Path, body: dict[str, Any]) -> dict[str, Any]:
    payload = dict(body)
    payload["artifact_sha256"] = sha256_json(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(canonical_bytes(payload))
    os.replace(temporary, path)
    return payload


DESCRIPTION = {
    "schema": "BROKER_WRITER_CAPABILITY_V1",
    "default_mode": "DESCRIBE_ONLY",
    "connections_performed": 0,
    "writes_performed": 0,
    "required_checks": [
        "single authoritative execution client ID",
        "duplicate connection rejected with IBKR error 326",
        "cross-client reqAllOpenOrders visibility is not write authority",
        "same-client cancel and modify ownership",
        "exact order identity and post-write reconciliation",
    ],
}


def describe() -> dict:
    return dict(DESCRIPTION)


def _current_head() -> str:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    head = completed.stdout.strip().lower()
    if completed.returncode != 0 or len(head) != 40:
        raise PaperProbeError("PROBE_HEAD_UNAVAILABLE")
    return head


def _paper_probe(
    receipt_path: Path, runtime_state_path: Path, report_path: Path
) -> dict[str, Any]:
    receipt = _read_verified_artifact(
        receipt_path, "BROKER_WRITER_PAPER_PROBE_AUTHORIZATION_V1"
    )
    backend = IBKRPaperProbeBackend(receipt)
    return run_paper_probe(
        receipt_path,
        runtime_state_path,
        report_path,
        backend=backend,
        expected_head=_current_head(),
        now_utc=lambda: datetime.now(timezone.utc),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--describe", action="store_true")
    modes.add_argument("--paper-probe", action="store_true")
    parser.add_argument("--authorization-receipt", type=Path)
    parser.add_argument("--runtime-state", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if args.describe:
        print(json.dumps(describe(), sort_keys=True))
        return 0
    if (
        args.authorization_receipt is None
        or args.runtime_state is None
        or args.report is None
    ):
        parser.error(
            "--paper-probe requires --authorization-receipt, --runtime-state, and --report"
        )
    try:
        report = _paper_probe(
            args.authorization_receipt, args.runtime_state, args.report
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    except (PaperProbeError, PermissionError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
