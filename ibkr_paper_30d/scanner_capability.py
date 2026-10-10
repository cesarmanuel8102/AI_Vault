from __future__ import annotations

import argparse
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ibapi.client import EClient
from ibapi.message import OUT
from ibapi.scanner import ScannerSubscription
from ibapi.wrapper import EWrapper

from .canonical import canonical_bytes
from .ibkr_readonly import expected_identity_hash
from .ibkr_readonly_session import ExpectedPaperIdentityStore, ReadOnlyMessageGuard


SCHEMA = "IBKR_SCANNER_CAPABILITY_V1"
PAPER_HOSTS = {"127.0.0.1", "localhost"}
PAPER_PORT = 4002
SCANNER_CLIENT_ID = 19791


class ScannerTransportViolation(PermissionError):
    pass


class ScannerMessageGuard:
    """Read-only wire guard for a dedicated scanner probe transport.

    Extends the shared read-only allowlist with the three scanner request
    ids only. The shared ReadOnlyMessageGuard is intentionally NOT modified:
    account/position session collectors must never send scanner traffic.
    No order-write message id can ever enter this allowlist.
    """

    ALLOWED_MESSAGE_IDS = frozenset(
        ReadOnlyMessageGuard.ALLOWED_MESSAGE_IDS
        | {
            OUT.REQ_SCANNER_PARAMETERS,
            OUT.REQ_SCANNER_SUBSCRIPTION,
            OUT.CANCEL_SCANNER_SUBSCRIPTION,
        }
    )

    @classmethod
    def validate(cls, message: str) -> int:
        try:
            message_id = int(message.split("\0", 1)[0])
        except (TypeError, ValueError) as exc:
            raise ScannerTransportViolation("unparseable IB API message") from exc
        if message_id not in cls.ALLOWED_MESSAGE_IDS:
            raise ScannerTransportViolation(
                f"IB API message id {message_id} is outside the scanner probe allowlist"
            )
        return message_id


def build_scanner_subscription(
    *, instrument: str, location_code: str, scan_code: str, rows: int = 50
) -> ScannerSubscription:
    """Build model-directed discovery input without a host product allowlist."""
    if not instrument or not location_code or not scan_code or rows <= 0:
        raise ValueError("complete positive scanner subscription fields are required")
    subscription = ScannerSubscription()
    subscription.instrument = instrument
    subscription.locationCode = location_code
    subscription.scanCode = scan_code
    subscription.numberOfRows = rows
    return subscription


@dataclass(frozen=True)
class ScannerCapabilityReport:
    available: bool | None
    reason_codes: tuple[str, ...]
    scanner_parameters_received: bool = False
    scanner_subscription_returned_contracts: bool = False
    started_at_utc: str = ""
    completed_at_utc: str = ""
    server_version: int | None = None
    account_fingerprint: str = ""
    outbound_message_ids: tuple[int, ...] = ()
    broker_errors: tuple[dict[str, Any], ...] = ()
    broker_write_calls: int = 0


def as_report_dict(report: ScannerCapabilityReport) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "available": report.available,
        "reason_codes": list(report.reason_codes),
        "scanner_parameters_received": report.scanner_parameters_received,
        "scanner_subscription_returned_contracts": (
            report.scanner_subscription_returned_contracts
        ),
        "started_at_utc": report.started_at_utc,
        "completed_at_utc": report.completed_at_utc,
        "server_version": report.server_version,
        "account_fingerprint": report.account_fingerprint,
        "outbound_message_ids": list(report.outbound_message_ids),
        "broker_errors": [dict(item) for item in report.broker_errors],
        "broker_write_calls": report.broker_write_calls,
    }


def sanitize_scanner_report(report: dict[str, Any]) -> dict[str, Any]:
    """Canonical sanitized output: no raw account identity is persisted."""

    payload = dict(report)
    payload.pop("managed_account", None)
    return {
        "schema": str(payload.get("schema", SCHEMA)),
        "market_scanner": {
            "available": payload.get("available"),
            "source": "IBKR_NATIVE",
            "endpoint": "PAPER",
            "broker_write_calls": int(payload.get("broker_write_calls", 0)),
            "reason_codes": list(payload.get("reason_codes", [])),
            "scanner_parameters_received": bool(
                payload.get("scanner_parameters_received")
            ),
            "scanner_subscription_returned_contracts": bool(
                payload.get("scanner_subscription_returned_contracts")
            ),
            "discovery_evidence_only": True,
        },
        "probe": {
            "started_at_utc": payload.get("started_at_utc", ""),
            "completed_at_utc": payload.get("completed_at_utc", ""),
            "server_version": payload.get("server_version"),
            "outbound_message_ids": list(payload.get("outbound_message_ids", [])),
            "broker_errors": list(payload.get("broker_errors", [])),
        },
        "paper_identity": {
            "account_fingerprint": str(payload.get("account_fingerprint", "")),
            "raw_account_identity_persisted": False,
        },
    }


EXTERNAL_SCANNER_EVIDENCE = {
    "schema": "IBKR_SCANNER_CAPABILITY_EXTERNAL_EVIDENCE_V1",
    "market_scanner": {
        "available": True,
        "source": "IBKR_NATIVE",
        "endpoint": "PAPER",
        "broker_write_calls": 0,
        "discovery_evidence_only": True,
    },
    "verification": {
        "verified_against": "127.0.0.1:4002",
        "verified_at_utc": "2026-09-23",
        "scanner_parameters_received": True,
        "scanner_parameters_xml_bytes": 1764263,
        "scanner_subscription_returned_contracts": True,
        "scan_code": "TOP_OPEN_PERC_GAIN",
        "location_code": "STK.US.MAJOR",
        "results_received": 50,
        "informational_error_codes": [2104, 2106, 2158],
        "broker_write_calls_observed": 0,
        "repeated_during_implementation": False,
    },
}


class _ScannerProbeClient(EWrapper, EClient):
    def __init__(self) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        self.ready = threading.Event()
        self.managed_accounts_event = threading.Event()
        self.managed_accounts_value: tuple[str, ...] = ()
        self.scanner_parameters_event = threading.Event()
        self.scanner_parameters_bytes = 0
        self.scanner_rows: dict[int, list[dict[str, Any]]] = {}
        self.scanner_end_events: dict[int, threading.Event] = {}
        self.errors: list[dict[str, Any]] = []
        self.outbound_message_ids: list[int] = []

    def sendMsg(self, msg: str) -> None:
        message_id = ScannerMessageGuard.validate(msg)
        self.outbound_message_ids.append(message_id)
        super().sendMsg(msg)

    def nextValidId(self, orderId: int) -> None:
        self.ready.set()

    def managedAccounts(self, accountsList: str) -> None:
        self.managed_accounts_value = tuple(
            value.strip() for value in accountsList.split(",") if value.strip()
        )
        self.managed_accounts_event.set()

    def scannerParameters(self, xml: str) -> None:
        self.scanner_parameters_bytes = len(xml.encode("utf-8"))
        self.scanner_parameters_event.set()

    def scannerData(
        self,
        reqId: int,
        rank: int,
        contractDetails: Any,
        distance: str,
        benchmark: str,
        projection: str,
        legsStr: str,
    ) -> None:
        contract = getattr(contractDetails, "contract", None)
        self.scanner_rows.setdefault(reqId, []).append(
            {
                "rank": int(rank),
                "symbol": str(getattr(contract, "symbol", "") or ""),
                "con_id": int(getattr(contract, "conId", 0) or 0),
                "sec_type": str(getattr(contract, "secType", "") or ""),
            }
        )

    def scannerDataEnd(self, reqId: int) -> None:
        self.scanner_end_events.setdefault(reqId, threading.Event()).set()

    def error(
        self,
        reqId: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        self.errors.append(
            {
                "request_id": int(reqId),
                "code": int(errorCode),
                "message": str(errorString)[:300],
            }
        )


def _default_connect_factory() -> Callable[..., Any]:
    def _connect(host: str, port: int, client_id: int) -> Any:
        client = _ScannerProbeClient()
        client.connect(host, port, client_id)
        return client

    return _connect


def probe_scanner_capability(
    host: str,
    port: int,
    *,
    expected_account_hash: str | None = None,
    timeout_seconds: float = 8.0,
    client_id: int = SCANNER_CLIENT_ID,
    _connect: Callable[..., Any] | None = None,
) -> ScannerCapabilityReport:
    """Read-only scanner capability probe against the local PAPER Gateway.

    Read-only contract: the transport guard blocks every order-write
    message id; the probe requests scanner parameters and one bounded
    subscription, then disconnects. This function was NOT executed during
    the 2026-09-23 implementation: external evidence from the prior
    independent verification is pinned in EXTERNAL_SCANNER_EVIDENCE.
    """

    if host not in PAPER_HOSTS or port != PAPER_PORT:
        raise ValueError(
            "scanner capability probe requires local IBKR PAPER Gateway :4002"
        )

    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    reasons: list[str] = []

    expected = expected_account_hash
    if expected is None:
        store = ExpectedPaperIdentityStore(
            Path("Secrets/expected_paper_account_identity_v1.json")
        )
        if store.path.exists():
            expected = store.load_hash()
    if not expected:
        raise PermissionError("expected paper account identity hash is required")

    connect = _connect or _default_connect_factory()
    client: Any = None
    thread: threading.Thread | None = None

    def _finish(
        available: bool | None,
        parameters_received: bool,
        subscription_contracts: bool,
    ) -> ScannerCapabilityReport:
        return ScannerCapabilityReport(
            available=available,
            reason_codes=tuple(dict.fromkeys(reasons)),
            scanner_parameters_received=parameters_received,
            scanner_subscription_returned_contracts=subscription_contracts,
            started_at_utc=started,
            completed_at_utc=datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            server_version=None if client is None else client.serverVersion(),
            account_fingerprint="",
            outbound_message_ids=()
            if client is None
            else tuple(client.outbound_message_ids),
            broker_errors=() if client is None else tuple(client.errors),
            broker_write_calls=0,
        )

    try:
        try:
            client = connect(host, port, client_id)
            if not client.isConnected():
                raise ConnectionError("IBKR PAPER Gateway connection failed")
        except Exception:
            reasons.append("GATEWAY_UNAVAILABLE")
            return _finish(None, False, False)

        thread = threading.Thread(target=client.run, daemon=True)
        thread.start()
        if not client.ready.wait(timeout_seconds):
            reasons.append("HANDSHAKE_TIMEOUT")
            return _finish(None, False, False)

        client.reqManagedAccts()
        if not client.managed_accounts_event.wait(timeout_seconds):
            reasons.append("MANAGED_ACCOUNT_TIMEOUT")
            return _finish(None, False, False)
        if len(client.managed_accounts_value) != 1:
            reasons.append("SINGLE_PAPER_ACCOUNT_REQUIRED")
            return _finish(None, False, False)
        account = client.managed_accounts_value[0]
        if not account.upper().startswith("DU"):
            reasons.append("PAPER_DU_NAMESPACE_REQUIRED")
            return _finish(None, False, False)
        if expected_identity_hash(account) != expected.lower():
            reasons.append("PAPER_ACCOUNT_IDENTITY_MISMATCH")
            return _finish(None, False, False)

        client.reqScannerParameters()
        parameters_received = client.scanner_parameters_event.wait(timeout_seconds)
        if not parameters_received:
            reasons.append("SCANNER_PARAMETERS_TIMEOUT")
            return _finish(False, False, False)

        subscription_contracts = False
        request_id = 50_000
        client.scanner_rows[request_id] = []
        client.scanner_end_events[request_id] = threading.Event()
        subscription = build_scanner_subscription(
            instrument="STK",
            location_code="STK.US.MAJOR",
            scan_code="TOP_PERC_GAIN",
            rows=50,
        )
        client.reqScannerSubscription(request_id, subscription, [], [])
        if not client.scanner_end_events[request_id].wait(timeout_seconds):
            reasons.append("SCANNER_SUBSCRIPTION_TIMEOUT")
        else:
            subscription_contracts = bool(client.scanner_rows.get(request_id))
        client.cancelScannerSubscription(request_id)

        if not subscription_contracts:
            reasons.append("SCANNER_SUBSCRIPTION_EMPTY")
        return _finish(True, True, subscription_contracts)
    finally:
        if client is not None and client.isConnected():
            client.disconnect()
        if thread is not None:
            thread.join(timeout=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ibkr-scanner-capability")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=PAPER_PORT)
    parser.add_argument("--client-id", type=int, default=SCANNER_CLIENT_ID)
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--expected-account-sha256")
    parser.add_argument(
        "--evidence-only",
        action="store_true",
        help="print the pinned external evidence without contacting the broker",
    )
    args = parser.parse_args(argv)

    if args.evidence_only:
        print(canonical_bytes(EXTERNAL_SCANNER_EVIDENCE).decode("utf-8"))
        return 0
    report = probe_scanner_capability(
        args.host,
        args.port,
        expected_account_hash=args.expected_account_sha256,
        timeout_seconds=args.timeout_seconds,
        client_id=args.client_id,
    )
    print(
        canonical_bytes(
            sanitize_scanner_report(as_report_dict(report))
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
