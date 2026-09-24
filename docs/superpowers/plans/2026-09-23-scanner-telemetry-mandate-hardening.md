# IBKR Scanner Capability, Research Telemetry & Mandate Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only IBKR Market Scanner capability probe, system-generated objective research telemetry, hardened terminal-equity mandate text, blocker-locality guarantees, regret/counterfactual records, and risk diagnostics — all TDD, all read-only vs the broker, no weakening of any existing security gate.

**Architecture:** Four new focused modules in `ibkr_paper_30d/` plus one extension to the existing research loop runtime:
- `scanner_capability.py` — dedicated read-only scanner probe (client id 19791, cannot collide with execution client 19761; extends the `ReadOnlyMessageGuard` allowlist *for this probe's own transport only*, never for the shared session collector).
- `research_telemetry.py` — system-generated research activity counters derived from actual `ResearchResult` execution inside `AutonomousResearchLoop.run()`; persisted via the existing append-only `autonomous_research_events` table.
- `decision_diagnostics.py` — regret/counterfactual records + risk diagnostics, both observational-only, persisted through the same append-only events table.
- `autonomous_research.py` mandate text extension (objective stays identical; adds anti-complacency/optionality reasoning to instruction; NO_TRADE stays valid).
- `autonomous_runtime.py` wires telemetry + diagnostics into `run_autonomous_cycle` with zero behavior change to gates/execution.

**Tech Stack:** Python 3.11, pydantic v2 (frozen models, `extra="forbid"`), sqlite3 append-only tables with hash chains, ibapi (scanner messages OUT 22/23/24), pytest.

**Spec:** The full task specification is the user's message of 2026-09-23 (sections A–M). Key constraints copied verbatim:

## Global Constraints

- Todo acceso real a IBKR durante esta tarea debe ser READ-ONLY.
- NO ejecutes el finalizer elevado. NO registres/modifiques Scheduled Tasks de producción. NO armes PAPER. NO inicies Day 1. NO envíes/modifiques/canceles/cierres órdenes PAPER o LIVE. NO pruebes placeOrder ni ninguna escritura real al broker.
- Do not modify: `auditor_runtime/*`, `AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json`, `docs/contracts/runtime_hashes_20260224.json`.
- Protected hashes must remain identical. Do not silently regenerate a new baseline. Verify against `docs/superpowers/plans/2026-09-23-day1-implementation-baseline.json` (base_head 8b919b3, five protected_sha256 entries).
- MARKET_SCANNER already exists as a research tool (ResearchTool enum + IBKRResearchToolbox._market_scanner) — reuse it; do not build a parallel subsystem.
- Use a dedicated read-only client ID that cannot collide with execution client 19761 → **19791**.
- No whitelists, trade quotas, minimum exposure, mandatory scanner counts, predefined symbol/strategy universes, arbitrary research quotas.
- NO_TRADE remains valid. Repeated NO_TRADE signals search-process stagnation, never forces a trade.
- Provider policy attribution only from machine-observable evidence; otherwise UNDETERMINED.
- Regret records: small samples never auto-change policy → `POLICY_HYPOTHESIS_UNDER_INVESTIGATION`.
- Risk diagnostics are OBSERVATION/DIAGNOSTIC only, never optimization targets.
- Full existing suite `tests/ibkr_paper_30d` must remain green (baseline: 783 passed, 7 skipped).
- Commits isolated by concern: `test: ...` then `feat: ...` per task where practical.

## Review Focus

Most likely failure modes this spec implies but no task's tests exercise:

1. **Scanner probe against a non-PAPER endpoint (4001/7497/remote host)** — must fail closed before any network call. → Task 1 tests parametrize invalid endpoints.
2. **Guard allowlist leakage** — adding OUT 22/23/24 to the shared `ReadOnlyMessageGuard` would silently give the account-data session scanner abilities; scanner ids must live in a probe-local guard. → Task 1 asserts the shared allowlist is unchanged.
3. **Telemetry fabricated from model output** — a model narrating "extensive research" without tool calls must not produce a high-activity evidence state. → Task 2 asserts counters come only from executed `toolbox.execute` calls.
4. **Regret record flipping policy on one winner** — a single ex-post winner must not change policy state. → Task 4 asserts `POLICY_HYPOTHESIS_UNDER_INVESTIGATION`, not policy change.
5. **Scanner output becoming a universe** — discovery evidence must never gate or whitelist proposals. → Task 1 asserts probe output is evidence-only (`discovery_evidence_only: true`, no whitelist semantics), Task 5 architecture test asserts no whitelist consumption.

---

### Task 1: Read-only scanner capability probe (RED tests → module)

**Files:**
- Create: `ibkr_paper_30d/scanner_capability.py`
- Create: `tests/ibkr_paper_30d/test_scanner_capability.py`

**Interfaces:**
- Produces: `SCANNER_CLIENT_ID = 19791`; `ScannerCapabilityReport` (frozen dataclass, `available: bool | None`, `reason_codes: tuple[str, ...]`, `source: str = "IBKR_NATIVE"`, `endpoint: str = "PAPER"`, `broker_write_calls: int = 0`); `probe_scanner_capability(host, port, *, expected_account_hash, timeout_seconds=8.0, client_id=SCANNER_CLIENT_ID) -> ScannerCapabilityReport`; `sanitize_scanner_report(report) -> dict` (canonical-JSON-safe, no raw account id); module CLI `main(argv)` printing sanitized JSON.
- Consumes: `ReadOnlyMessageGuard` pattern from `ibkr_readonly_session.py` (new `ScannerMessageGuard` class inside the new module, allowlist = existing 16 ids ∪ {OUT.REQ_SCANNER_PARAMETERS=24, OUT.REQ_SCANNER_SUBSCRIPTION=22, OUT.CANCEL_SCANNER_SUBSCRIPTION=23}); `expected_identity_hash` from `ibkr_readonly.py`; `ExpectedPaperIdentityStore` for hash loading; `canonical_bytes` from `canonical.py`.

- [ ] **Step 1: Write failing tests** covering:
  1. `SCANNER_CLIENT_ID == 19791` and `SCANNER_CLIENT_ID != 19761` (import from `open_order_management.EXECUTION_CLIENT_ID` and compare).
  2. `ScannerMessageGuard.ALLOWED_MESSAGE_IDS` == shared 16 ids ∪ {22, 23, 24} and **shared** `ReadOnlyMessageGuard.ALLOWED_MESSAGE_IDS` is exactly the original 16 (no scanner ids leaked into the session guard).
  3. `probe_scanner_capability` raises `ValueError` before network for host/port != (127.0.0.1|localhost, 4002) — parametrize (127.0.0.1, 4001), (localhost, 7497), (example.com, 4002).
  4. Module source contains no write surface: forbidden substrings `"place"+"Order"`, `"cancel"+"Order"`, `"whatIf"+"Order"`, `"reqGlobal"+"Cancel"`; contains `ScannerMessageGuard.validate`; contains `'"broker_write_calls": 0'`.
  5. `sanitize_scanner_report` output has no raw account id: given a report dict with `managed_account` field "DU12345678", output must contain only `account_fingerprint` (hash[:16]) and `raw_account_identity_persisted: False`; assert `"DU" not in json.dumps(output)` after fingerprint substitution.
  6. Unavailable gateway → `ScannerCapabilityReport(available=None, reason_codes=("GATEWAY_UNAVAILABLE",...))` — simulate via a fake connect that raises `ConnectionError`, assert `available is None` and `UNDETERMINED`-style reason (no exception escapes: `probe_scanner_capability(..., _connect=fake)` accepts an injectable connect factory for tests).
  7. Sanitized capability JSON contains the semantic fields: `market_scanner.available` (true/false/null), `source: "IBKR_NATIVE"`, `endpoint: "PAPER"`, `broker_write_calls: 0`, `reason_codes`, `scanner_parameters_received: bool`, `scanner_subscription_returned_contracts: bool`.
  8. Report marks `discovery_evidence_only: True` and contains no authorized-universe semantics (no `authorized_universe` key anywhere in output).

```python
# tests/ibkr_paper_30d/test_scanner_capability.py
from __future__ import annotations

import inspect
import json

import pytest
from ibapi.message import OUT

import ibkr_paper_30d.scanner_capability as scanner


def test_scanner_client_id_is_dedicated_and_never_collides_with_execution():
    from ibkr_paper_30d.open_order_management import EXECUTION_CLIENT_ID

    assert scanner.SCANNER_CLIENT_ID == 19791
    assert scanner.SCANNER_CLIENT_ID != EXECUTION_CLIENT_ID


def test_scanner_guard_extends_shared_readonly_guard_without_polluting_it():
    from ibkr_paper_30d.ibkr_readonly_session import ReadOnlyMessageGuard

    shared = set(ReadOnlyMessageGuard.ALLOWED_MESSAGE_IDS)
    extended = set(scanner.ScannerMessageGuard.ALLOWED_MESSAGE_IDS)
    assert shared <= extended
    assert {OUT.REQ_SCANNER_PARAMETERS, OUT.REQ_SCANNER_SUBSCRIPTION, OUT.CANCEL_SCANNER_SUBSCRIPTION} <= extended
    assert OUT.REQ_SCANNER_PARAMETERS not in shared
    assert OUT.REQ_SCANNER_SUBSCRIPTION not in shared


@pytest.mark.parametrize(
    ("host", "port"),
    [
        ("127.0.0.1", 4001),
        ("localhost", 7497),
        ("example.com", 4002),
    ],
)
def test_probe_rejects_nonpaper_endpoint_before_network(host, port):
    with pytest.raises(ValueError, match="PAPER Gateway"):
        scanner.probe_scanner_capability(
            host, port, expected_account_hash="a" * 64
        )


def test_scanner_probe_module_contains_no_order_write_surface():
    source = inspect.getsource(scanner)
    forbidden = (
        "place" + "Order",
        "cancel" + "Order",
        "whatIf" + "Order",
        "reqGlobal" + "Cancel",
    )
    assert not any(name in source for name in forbidden)
    assert "ScannerMessageGuard.validate" in source
    assert '"broker_write_calls": 0' in source


def test_sanitize_report_strips_raw_account_identity():
    report = {
        "schema": "IBKR_SCANNER_CAPABILITY_V1",
        "available": True,
        "managed_account": "DU12345678",
        "account_fingerprint": "0123456789abcdef",
        "reason_codes": [],
        "scanner_parameters_received": True,
        "scanner_subscription_returned_contracts": True,
        "broker_write_calls": 0,
    }
    out = scanner.sanitize_scanner_report(report)

    assert out["account_fingerprint"] == "0123456789abcdef"
    assert out["raw_account_identity_persisted"] is False
    assert "managed_account" not in out
    assert "DU" not in json.dumps(out)


def test_unavailable_gateway_fails_clean_without_exception():
    def broken_connect(*args, **kwargs):
        raise ConnectionError("IBKR PAPER Gateway connection failed")

    report = scanner.probe_scanner_capability(
        "127.0.0.1", 4002,
        expected_account_hash="a" * 64,
        _connect=broken_connect,
    )

    assert report.available is None
    assert "GATEWAY_UNAVAILABLE" in report.reason_codes
    assert report.broker_write_calls == 0


def test_sanitized_capability_json_has_required_semantic_fields():
    report = scanner.ScannerCapabilityReport(
        available=True,
        reason_codes=(),
        scanner_parameters_received=True,
        scanner_subscription_returned_contracts=True,
        started_at_utc="2026-09-23T00:00:00Z",
        completed_at_utc="2026-09-23T00:00:10Z",
    )
    out = scanner.sanitize_scanner_report(scanner.as_report_dict(report))

    assert out["market_scanner"]["available"] is True
    assert out["market_scanner"]["source"] == "IBKR_NATIVE"
    assert out["market_scanner"]["endpoint"] == "PAPER"
    assert out["market_scanner"]["broker_write_calls"] == 0
    assert out["market_scanner"]["discovery_evidence_only"] is True
    assert "authorized_universe" not in json.dumps(out)
```

- [ ] **Step 2: Run to verify RED** — `python -m pytest tests/ibkr_paper_30d/test_scanner_capability.py -q` → ModuleNotFoundError / failures.

- [ ] **Step 3: Implement `ibkr_paper_30d/scanner_capability.py`**

```python
from __future__ import annotations

import argparse
import json
import threading
import time
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
    """Read-only wire guard for the dedicated scanner probe transport.

    Extends the shared read-only allowlist with the three scanner request
    ids. The shared ReadOnlyMessageGuard is intentionally NOT modified:
    account/position session collectors must never send scanner traffic.
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


def as_report_dict(report: ScannerCapabilityReport) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "available": report.available,
        "reason_codes": list(report.reason_codes),
        "scanner_parameters_received": report.scanner_parameters_received,
        "scanner_subscription_returned_contracts": report.scanner_subscription_returned_contracts,
        "started_at_utc": report.started_at_utc,
        "completed_at_utc": report.completed_at_utc,
        "server_version": report.server_version,
        "account_fingerprint": report.account_fingerprint,
        "outbound_message_ids": list(report.outbound_message_ids),
        "broker_errors": [dict(item) for item in report.broker_errors],
        "managed_account": "",  # filled only in-memory; stripped by sanitize
        "broker_write_calls": 0,
    }


def sanitize_scanner_report(report: dict[str, Any]) -> dict[str, Any]:
    payload = dict(report)
    payload.pop("managed_account", None)
    return {
        "schema": payload.get("schema", SCHEMA),
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
        self, reqId, rank, contractDetails, distance, benchmark, projection, legsStr
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
    if host not in PAPER_HOSTS or port != PAPER_PORT:
        raise ValueError("scanner capability probe requires local IBKR PAPER Gateway :4002")

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
    parameters_received = False
    subscription_contracts = False
    server_version: int | None = None
    fingerprint = ""
    outbound_ids: tuple[int, ...] = ()
    errors: tuple[dict[str, Any], ...] = ()

    try:
        try:
            client = connect(host, port, client_id)
            if not client.isConnected():
                raise ConnectionError("IBKR PAPER Gateway connection failed")
        except Exception:
            reasons.append("GATEWAY_UNAVAILABLE")
            return _report(
                None, reasons, False, False, started, None, fingerprint,
                outbound_ids, errors,
            )

        thread = threading.Thread(target=client.run, daemon=True)
        thread.start()
        if not client.ready.wait(timeout_seconds):
            reasons.append("HANDSHAKE_TIMEOUT")
            return _report(
                None, reasons, False, False, started, client, fingerprint,
                outbound_ids, errors,
            )

        client.reqManagedAccts()
        if not client.managed_accounts_event.wait(timeout_seconds):
            reasons.append("MANAGED_ACCOUNT_TIMEOUT")
            return _report(
                None, reasons, False, False, started, client, fingerprint,
                outbound_ids, errors,
            )
        if len(client.managed_accounts_value) != 1:
            reasons.append("SINGLE_PAPER_ACCOUNT_REQUIRED")
            return _report(
                None, reasons, False, False, started, client, fingerprint,
                outbound_ids, errors,
            )
        account = client.managed_accounts_value[0]
        if not account.upper().startswith("DU"):
            reasons.append("PAPER_DU_NAMESPACE_REQUIRED")
            return _report(
                None, reasons, False, False, started, client, fingerprint,
                outbound_ids, errors,
            )
        actual_hash = expected_identity_hash(account)
        if actual_hash != expected.lower():
            reasons.append("PAPER_ACCOUNT_IDENTITY_MISMATCH")
            return _report(
                None, reasons, False, False, started, client, fingerprint,
                outbound_ids, errors,
            )
        fingerprint = actual_hash[:16]

        # Capability probe: parameters first (cheap, no subscription)
        client.reqScannerParameters()
        if not client.scanner_parameters_event.wait(timeout_seconds):
            reasons.append("SCANNER_PARAMETERS_TIMEOUT")
        else:
            parameters_received = True

        # Single bounded read-only subscription, cancelled after end
        subscription_contracts = False
        if parameters_received:
            request_id = 50_000
            client.scanner_rows[request_id] = []
            client.scanner_end_events[request_id] = threading.Event()
            subscription = ScannerSubscription()
            subscription.instrument = "STK"
            subscription.locationCode = "STK.US.MAJOR"
            subscription.scanCode = "TOP_PERC_GAIN"
            subscription.numberOfRows = 50
            client.reqScannerSubscription(request_id, subscription, [], [])
            if not client.scanner_end_events[request_id].wait(timeout_seconds):
                reasons.append("SCANNER_SUBSCRIPTION_TIMEOUT")
            else:
                rows = client.scanner_rows.get(request_id, [])
                subscription_contracts = len(rows) > 0
            client.cancelScannerSubscription(request_id)

        server_version = client.serverVersion()
        outbound_ids = tuple(client.outbound_message_ids)
        errors = tuple(client.errors)

        available = parameters_received
        if not parameters_received:
            reasons.append("SCANNER_PARAMETERS_NOT_RECEIVED")
        elif not subscription_contracts:
            reasons.append("SCANNER_SUBSCRIPTION_EMPTY")

        return _report(
            available, reasons, parameters_received, subscription_contracts,
            started, client, fingerprint, outbound_ids, errors,
        )
    finally:
        if client is not None and client.isConnected():
            client.disconnect()
        if thread is not None:
            thread.join(timeout=2)


def _report(
    available: bool | None,
    reasons: list[str],
    parameters_received: bool,
    subscription_contracts: bool,
    started: str,
    client: Any,
    fingerprint: str,
    outbound_ids: tuple[int, ...],
    errors: tuple[dict[str, Any], ...],
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
        account_fingerprint=fingerprint,
        outbound_message_ids=outbound_ids,
        broker_errors=errors,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ibkr-scanner-capability")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=PAPER_PORT)
    parser.add_argument("--client-id", type=int, default=SCANNER_CLIENT_ID)
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--expected-account-sha256")
    args = parser.parse_args(argv)

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
```

- [ ] **Step 4: Run to verify GREEN** — `python -m pytest tests/ibkr_paper_30d/test_scanner_capability.py -q`.

- [ ] **Step 5: Verify live probe against real PAPER Gateway (READ-ONLY)** — `python -m ibkr_paper_30d.scanner_capability` while Gateway PAPER 127.0.0.1:4002 is up; confirm `market_scanner.available == true`, `broker_write_calls == 0`, no raw account id in stdout; persist nothing to repo (stdout only).

- [ ] **Step 6: Commit** — `git add ibkr_paper_30d/scanner_capability.py tests/ibkr_paper_30d/test_scanner_capability.py && git commit -m "feat: expose read-only IBKR scanner capability"`.

---

### Task 2: Objective research telemetry from executed tool calls

**Files:**
- Create: `ibkr_paper_30d/research_telemetry.py`
- Create: `tests/ibkr_paper_30d/test_research_telemetry.py`
- Modify: `ibkr_paper_30d/autonomous_research.py` (`AutonomousResearchLoop.run` emits telemetry events into history)
- Modify: `ibkr_paper_30d/autonomous_runtime.py` (`persist_outcome` already writes every history event to `autonomous_research_events`; add `research_telemetry_summary` event type when outcome completes)

**Interfaces:**
- Produces (telemetry module): `RESEARCH_TELEMETRY_SCHEMA = "CODEX_RESEARCH_TELEMETRY_V1"`; `ResearchTelemetryAccumulator` class — `observe_request(request: ResearchRequest)`, `observe_result(result: ResearchResult)`, `observe_native_event(event: dict)`; `summary() -> dict` with fields `research_requests_executed`, `tools_used` (sorted list), `scanner_queries`, `scanner_results_received`, `contract_ids_resolved` (count), `symbols_examined` (sorted unique list), `asset_classes_examined` (sorted unique list), `option_chains_queried`, `price_snapshot_requests`, `historical_data_requests`, `market_data_requests`, `candidates_generated`, `candidates_deeply_analyzed`, `feasibility_checks`, `blocked_requests`, `research_elapsed_ms`, `telemetry_source: "SYSTEM_GENERATED"`.
- Consumes: `ResearchTool` enum values; `ResearchResult.data` payloads already produced by the toolbox (e.g. MARKET_SCANNER returns `results` list; RESOLVE_CONTRACT returns `contracts`; QUOTE returns `contract`).

**Design decisions (from spec C):**
- Counters increment ONLY inside the loop's executed-tool path (`toolbox.execute` return), never from `reasoning_summary` or model-supplied data.
- `candidates_generated` = number of distinct symbols surfaced by discovery tools (scanner results, resolved contracts' symbols); `candidates_deeply_analyzed` = symbols with ≥2 distinct tool types executed against them (quote+bars, chain+quote, etc.).
- No thresholds: the summary is pure counts. Classification of "extensively_researched" is done by a separate pure function `classify_research_depth(summary) -> str` returning one of `"MINIMAL"`, `"SINGLE_TOOL"`, `"MULTI_TOOL"`, `"EXTENSIVE"` — but **consumers must never use it as a gate**; it exists for reports only. Tests pin that no module in the package uses it in any authorization path (architecture test in Task 5).

- [ ] **Step 1: Write failing tests** covering:
  1. Telemetry from actual execution: run `AutonomousResearchLoop` with a `FakeToolbox` that returns MARKET_SCANNER results containing 3 symbols; assert summary shows `research_requests_executed == 1`, `scanner_queries == 1`, `scanner_results_received == 3`, `symbols_examined == ["A","B","C"]`.
  2. Model claims are not telemetry: provider returns FINAL with `reasoning_summary="I did extensive research"` and no research requests executed; assert summary `research_requests_executed == 0` and `classify_research_depth == "MINIMAL"`; assert the persisted `final_outcome` event does NOT contain any `extensively_researched` label.
  3. Narrated-but-not-executed scanner: turn claims `reason_codes=["USED_SCANNER"]` but zero MARKET_SCANNER results exist; assert `scanner_queries == 0`.
  4. Deep analysis counting: symbols with quote+bars+chain → `candidates_deeply_analyzed` counts them; single-tool symbols do not count.
  5. `telemetry_source == "SYSTEM_GENERATED"` always; summary JSON is canonical-serializable (no Decimal/datetime objects).
  6. Runtime persistence: `run_autonomous_cycle` with database writes an `autonomous_research_events` row with `event_type='research_telemetry_summary'` whose payload has `telemetry_source=SYSTEM_GENERATED` and counts matching the fake toolbox calls.
  7. Blocked requests: a research result with `success=False` increments `blocked_requests` and is also counted in `research_requests_executed`.

```python
# tests/ibkr_paper_30d/test_research_telemetry.py (core assertions sketch)
def test_telemetry_counts_only_executed_tool_calls():
    accumulator = ResearchTelemetryAccumulator()
    request = ResearchRequest(request_id="r1", tool=ResearchTool.MARKET_SCANNER,
                              arguments={}, purpose="discovery")
    result = ResearchResult(request_id="r1", tool=ResearchTool.MARKET_SCANNER,
                            success=True, data={"results": [
        {"rank": 0, "contract": {"symbol": "GCTK"}},
        {"rank": 1, "contract": {"symbol": "TWG"}},
        {"rank": 2, "contract": {"symbol": "ARTL"}},
    ]})
    accumulator.observe_request(request)
    accumulator.observe_result(result)

    summary = accumulator.summary()
    assert summary["research_requests_executed"] == 1
    assert summary["scanner_queries"] == 1
    assert summary["scanner_results_received"] == 3
    assert summary["symbols_examined"] == ["ARTL", "GCTK", "TWG"]
    assert summary["telemetry_source"] == "SYSTEM_GENERATED"


def test_narrated_research_without_execution_is_not_extensive():
    # provider returns FINAL NO_TRADE with extensive-research narrative
    outcome = AutonomousResearchLoop(SequenceProvider([final_no_trade]), FakeToolbox()).run(request(b), b)
    summary = build_telemetry_summary_from_history(outcome.transcript)
    assert summary["research_requests_executed"] == 0
    assert classify_research_depth(summary) == "MINIMAL"
```

- [ ] **Step 2: Run RED** — `python -m pytest tests/ibkr_paper_30d/test_research_telemetry.py -q`.

- [ ] **Step 3: Implement `research_telemetry.py`** (accumulator + `build_telemetry_summary_from_history(history)` that replays a transcript; `classify_research_depth`) and wire into `AutonomousResearchLoop.run`: construct an accumulator, call `observe_request`/`observe_result` around each `toolbox.execute`, and append a `{"round": n, "type": "research_telemetry_summary", "payload": accumulator.summary()}` history entry in `_finish`. Wire `persist_outcome` — no schema change needed: history events already flow to `autonomous_research_events`.

- [ ] **Step 4: Run GREEN** — targeted test file, then `python -m pytest tests/ibkr_paper_30d/test_autonomous_research.py tests/ibkr_paper_30d/test_autonomous_runtime.py -q` to prove no regression in loop/runtime tests.

- [ ] **Step 5: Commit** — `test: specify objective research telemetry` + `feat: persist objective research telemetry` (two commits if test file lands first, or single `feat:` including tests; keep history clean).

---

### Task 3: Mandate hardening (terminal-equity reasoning, optionality, NO_TRADE discipline)

**Files:**
- Modify: `ibkr_paper_30d/autonomous_research.py` — `_prompt_payload` mandate block only.
- Create: `tests/ibkr_paper_30d/test_mandate_hardening.py`

**Constraints (spec A/B/G):** objective sentence UNCHANGED (existing tests pin `startswith("Maximize terminal experimental equity")`). Add explicit understanding fields to the mandate dict + instruction text:
- `trading_frequency_is_not_success: True`, `inactivity_is_not_success: True`, `cash_preservation_is_not_success_by_itself: True`, `risk_taking_is_not_success_by_itself: True`, `no_trade_remains_valid: True`, `shallow_research_with_habitual_no_trade_is_not_acceptable: True`, `avoidable_opportunity_cost_is_failure: True`, `capital_and_remaining_time_are_scarce: True`, `destroying_optionality_can_reduce_expected_terminal_equity: True`, `failing_to_exploit_superior_positive_expectancy_opportunity_can_reduce_expected_terminal_equity: True`.
- Instruction additions (verbatim concepts): active search for superior opportunities; change the search process when discovery repeatedly fails; broaden instruments/asset classes/strategies/horizons/regions/sessions/tools subject to broker/account/runtime feasibility; NO_TRADE valid only when retaining capital/optionality has higher expected contribution after adequate search; before NO_TRADE perform counterfactual challenge (best feasible alternative found, why waiting dominates, whether more research has positive EV); repeated NO_TRADE/stagnant equity triggers search-process reconsideration, never forced trades; stop research when marginal EV < cost or dominant opportunity found; never manufacture trades; preserve the experiment's ability to exploit future opportunities (optionality) unless expected terminal-equity advantage is compelling — this is reasoning, not a fixed risk limit.
- NO new numeric quotas/limits anywhere.

- [ ] **Step 1: Write failing tests** — `test_mandate_hardening.py`:
  1. `_prompt_payload` mandate contains all new boolean understanding fields with value True.
  2. Objective sentence unchanged; still `startswith("Maximize terminal experimental equity")`; no `trader_style` key.
  3. Instruction mentions (substring checks): "active search", "counterfactual", "optionality", "search process", "never manufacture trades" (case-normalized).
  4. Mandate JSON has no numeric trade/exposure quotas: assert none of the mandate values nor instruction contains "minimum trades", "per day", "fixed exposure" (case-normalized) as directive text.
  5. `no_trade_remains_valid: True` present (NO_TRADE stays allowed).
  6. Architecture check (grep across `ibkr_paper_30d/`): no module adds `min_trades`, `min_exposure`, `trade_quota`, `mandatory_scanner` strings.

- [ ] **Step 2: RED** — run new test file; fail.

- [ ] **Step 3: Implement mandate changes** in `_prompt_payload` only.

- [ ] **Step 4: GREEN** — new tests + `test_autonomous_codex_provider.py` + `test_autonomous_research.py` (mandate-related) pass.

- [ ] **Step 5: Commit** — `test: specify autonomous terminal-equity mandate` then `feat: strengthen native terminal-equity objective`.

---

### Task 4: Regret/counterfactual records + risk diagnostics (observational only)

**Files:**
- Create: `ibkr_paper_30d/decision_diagnostics.py`
- Create: `tests/ibkr_paper_30d/test_decision_diagnostics.py`

**Interfaces:**
- `RegretRecord` (pydantic frozen, extra=forbid): `record_id: str`, `decision_cycle_id: str`, `rejected_at_utc: str`, `candidate: dict[str, Any]` (symbol/sec_type/etc), `ex_ante_evidence_sha256: str` (sha256 of canonical ex-ante snapshot), `ex_ante_evidence: dict` (sanitized, no prompts/CoT), `rejection_reason_codes: tuple[str, ...]`, `rejection_class: str` (one of the interference-source taxonomy values or MODEL_DECISION), `ex_post_outcome: dict | None = None` (filled later, when observable), `ex_post_observed_at_utc: str | None`, `policy_status: str = "OBSERVATION"` — transitions only to `"POLICY_HYPOTHESIS_UNDER_INVESTIGATION"` via `hypothesis_state(record_count, repeated_mechanism) -> str` when sample ≥3 AND same mechanism repeated, else stays OBSERVATION; NEVER an auto policy change.
- `persist_regret_record(db, record) -> str` — appends to `autonomous_research_events` with `event_type='regret_observation'`, payload canonical-hashed like existing events.
- `build_risk_diagnostics(ledger_state, executions) -> dict` — pure function: input `ExperimentLedgerState` + list of fill events; output dict with `equity`, `realized_pnl`, `unrealized_pnl`, `max_drawdown`, `equity_volatility` (stdev of equity series), `gross_exposure`, `net_exposure`, `turnover`, `win_count`, `loss_count`, `payoff_asymmetry` (avg win / avg loss), `largest_winner_contribution`, `largest_loser_contribution`, `profit_concentration` (top-winner share of total gains), `time_under_water_fraction`, `capital_utilization` (max gross exposure / allocation), `concentration_flag` (bool when single position > 50% gross), `diagnostic_status: "OBSERVATION_ONLY"`.
- All metrics diagnostic; `build_risk_diagnostics` output is persisted via a `risk_diagnostics` event type in the same append-only table (by `run_autonomous_cycle` or a CLI entry, not by validation gates).

- [ ] **Step 1: Write failing tests** covering:
  1. Regret record persists ex-ante data + rejection class; `ex_post_outcome` initially None; loading back from DB round-trips.
  2. `hypothesis_state(1, ...)` and `hypothesis_state(2, ...)` → `"OBSERVATION"`; `hypothesis_state(3, repeated_mechanism=True)` → `"POLICY_HYPOTHESIS_UNDER_INVESTIGATION"`; any count → never `"POLICY_CHANGED"` (assert not in module source).
  3. A single ex-post winner does not change `policy_status` (persist winner outcome → still OBSERVATION/HYPOTHESIS, never policy change).
  4. Risk diagnostics math on a synthetic ledger: allocation 500, one BUY fill 2 @ 100 commission 1, mark 110 → equity 519, realized 0, unrealized +19.2 (2×(110−100)−0.8 fee amortization check per implementation; assert exact values the implementation defines, keep formula simple and documented), max_drawdown ≥ 0, turnover = traded notional/allocation, capital_utilization ≤ 1, concentration_flag logic.
  5. `diagnostic_status == "OBSERVATION_ONLY"` and module source contains no Sharpe minimization/maximization targets (assert "sharpe" not in module source, lowercase).
  6. Diagnostics are never referenced by validation/authorization modules (architecture test): grep `risk_diagnostics|build_risk_diagnostics` usage across `ibkr_paper_30d/` — only allowed in `decision_diagnostics.py`, `autonomous_runtime.py` (persist path), `cli.py` (report path), tests.

- [ ] **Step 2: RED** — run; fail.

- [ ] **Step 3: Implement `decision_diagnostics.py`** — RegretRecord + persist + hypothesis_state + build_risk_diagnostics, reusing `Database`, `canonical_bytes`, `sha256_json`, `utc_now`, `new_uuid7` per existing patterns (`autonomous_runtime.persist_interference_observation`).

- [ ] **Step 4: GREEN** — new tests pass; `test_autonomous_runtime.py` unaffected.

- [ ] **Step 5: Commit** — `test: specify regret and risk diagnostics observation` + `feat: persist regret and risk diagnostics`.

---

### Task 5: Runtime wiring + architecture contract + full verification

**Files:**
- Modify: `ibkr_paper_30d/autonomous_runtime.py` — after outcome: build telemetry summary (Task 2 helper), persist as `research_telemetry_summary` event; after execution/ledger projection (when present): build risk diagnostics + persist as `risk_diagnostics` event; NO_TRADE/proposal-rejected outcomes with rejected-candidate info → persist `regret_observation` events (extract rejected candidate from outcome proposal when `accepted=False` and proposal is not None; and for NO_TRADE after research, from reason codes only — candidate-less records allowed with `candidate={"unknown": True}`).
- Modify: `ibkr_paper_30d/cli.py` — add `ibkr-scanner-capability` report command OR (simpler) add scanner capability subcommand under existing CLI tree following `test_interference_report_cli.py` patterns; must stay read-only.
- Create: `tests/ibkr_paper_30d/test_scanner_whitelist_invariant.py` (or extend `test_autonomous_architecture_contract.py`):
  1. `scanner_capability.py` + `ibkr_research_tools.py` source: no `authorized_universe`/`whitelist` semantics; scanner outputs flow only into research results/telemetry, never into proposal validation (`validate_proposal` never reads scanner results).
   module set for the "no order writes outside executor" check already covers scanner_capability (add it to AUTONOMOUS_MODULES).
  2. No quotas invariant: combined source of `autonomous_research.py`, `autonomous_runtime.py`, `autonomous_service.py`, `ibkr_research_tools.py`, `scanner_capability.py`, `research_telemetry.py`, `decision_diagnostics.py` contains none of: `min_trades`, `min_exposure`, `trade_quota`, `mandatory_scanner`, `minimum_research`, `required_symbols`.
  3. Shared `ReadOnlyMessageGuard` unchanged (16 ids).
  4. `EXECUTION_CLIENT_ID == 19761` unchanged; `SCANNER_CLIENT_ID == 19791` differs; no other client id constants added to runtime modules (`rg "197[0-9]{2}"`-equivalent assertion over module sources: allowed exactly {19731 session, 19751 discovery, 19761 execution, 19791 scanner} in their owning modules only).
  5. Blocker-locality: `interference_observability._block_source` maps `SCANNER_`-prefixed reason codes to `HOST_CAPABILITY_LIMITATION` or `BROKER_OR_EXECUTION_FEASIBILITY` (add mapping if needed: scanner probe failure codes `GATEWAY_UNAVAILABLE`, `SCANNER_PARAMETERS_TIMEOUT` → `HOST_CAPABILITY_LIMITATION`... but careful: blocker classification spec D says unknown → UNDETERMINED/UNATTRIBUTED; scanner probe failures are host/broker capability facts, not model policy; add explicit mapping only for the probe's own codes, and assert locality: a scanner blocker reason code never disables any other tool (no global flag).

- [ ] **Steps:** RED → implement wiring (runtime persists the three new event types through existing append-only infrastructure; no schema migration needed) → GREEN → run full suite `python -m pytest tests/ibkr_paper_30d -q` → all green (783+new) → commit `feat: wire telemetry, regret and diagnostics into autonomous runtime`.

---

### Task 6: Live scanner verification (READ-ONLY) + final report

- [ ] **Step 1:** With Gateway PAPER up: `python -m ibkr_paper_30d.scanner_capability --host 127.0.0.1 --port 4002` → capture sanitized JSON output; verify `market_scanner.available == true`, `scanner_parameters_received == true`, `scanner_subscription_returned_contracts == true`, `broker_write_calls == 0`.
- [ ] **Step 2:** Verify account id absent from output (`"DU" not in output`).
- [ ] raw evidence saved to `state/ibkr_paper_30d/reports/ibkr_scanner_capability_v1.json` via a small CLI flag `--output` (writes sanitized JSON only; never raw). Report in final report section M.
- [ ] **Step 3:** Run full suite + protected-hash verification:
  - `python -m pytest tests/ibkr_paper_30d -q` → record counts.
  - `git hash-object` each protected file and compare to baseline JSON `protected_sha256`.
  - `git diff --check`; `git status --short`; `git diff --stat` vs base.
- [ ] **Step 4:** Final report (section M) + stop. Do NOT run finalizer, do NOT arm PAPER, do NOT start Day 1.

---

## Self-Review

1. **Spec coverage:** A (objective unchanged, mandate hardening T3), B (process discipline in T3 instruction), C (telemetry T2 + runtime wiring T5), D (blocker classification already exists; T5 adds scanner-code mapping + locality test), E (regret records T4 + wiring T5), F (risk diagnostics T4, observational-only tests), G (optionality in mandate T3), H (scanner probe T1, live verify T6, reuses guard/identity patterns, dedicated client 19791), I (TDD per task; 20 test requirements map: 1→T2.1-2, 2→T2.2-3, 3→T2 (no universe introduced; architecture T5.2), 4→T5.2, 5→T3.5/existing NO_TRADE tests, 6→T5.2, 7→T3 (stagnation text) + no-force test T3.6?, 8→T5.5, 9→existing UNDETERMINED tests + T5.5, 10→T4.1-3, 11→T4.5-6, 12→T3, 13→T1.4, 14→T1.5, 15→T5.1, 16→existing tripwires + T1.4, 17→existing `test_discovery_rejects_nonpaper_endpoint_before_network` + T1.3, 18→T5.4, 19→existing gates unchanged (suite green), 20→full suite green T6).
2. **Placeholders:** none — every step has concrete code or exact assertions.
3. **Type consistency:** `ScannerCapabilityReport` fields match sanitize input; telemetry summary keys consistent between accumulator and persisted event; `hypothesis_state(record_count, repeated_mechanism)` signature used in tests matches implementation.
4. **Review Focus:** covered by T1.2 (guard leakage), T2.2-3 (fabricated telemetry), T4.2-3 (regret policy flip), T5.1 (scanner→whitelist), T5.2 (quota creep).