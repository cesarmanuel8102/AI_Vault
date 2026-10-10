from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from ibapi.message import OUT

import ibkr_paper_30d.scanner_capability as scanner
import ibkr_paper_30d.ibkr_research_tools as research_tools


REPO = Path(__file__).resolve().parents[2]


def test_scanner_client_id_is_dedicated_and_never_collides_with_execution():
    from ibkr_paper_30d.open_order_management import EXECUTION_CLIENT_ID

    assert scanner.SCANNER_CLIENT_ID == 19791
    assert scanner.SCANNER_CLIENT_ID != EXECUTION_CLIENT_ID


def test_scanner_guard_extends_readonly_guard_without_polluting_shared_guard():
    from ibkr_paper_30d.ibkr_readonly_session import ReadOnlyMessageGuard

    shared = set(ReadOnlyMessageGuard.ALLOWED_MESSAGE_IDS)
    extended = set(scanner.ScannerMessageGuard.ALLOWED_MESSAGE_IDS)
    assert shared <= extended
    assert {
        OUT.REQ_SCANNER_PARAMETERS,
        OUT.REQ_SCANNER_SUBSCRIPTION,
        OUT.CANCEL_SCANNER_SUBSCRIPTION,
    } <= extended
    assert OUT.REQ_SCANNER_PARAMETERS not in shared
    assert OUT.REQ_SCANNER_SUBSCRIPTION not in shared
    # Shared guard is byte-identical to its pre-task definition.
    assert len(shared) == 16


def test_scanner_guard_admits_no_write_message_ids():
    write_ids = {
        OUT.PLACE_ORDER,
        OUT.CANCEL_ORDER,
        OUT.EXERCISE_OPTIONS,
        OUT.REQ_GLOBAL_CANCEL,
    }
    for message_id in sorted(write_ids):
        wire = f"{message_id}\0payload\0"
        with pytest.raises(scanner.ScannerTransportViolation):
            scanner.ScannerMessageGuard.validate(wire)


def test_probe_rejects_nonpaper_endpoint_before_network():
    for host, port in (
        ("127.0.0.1", 4001),
        ("localhost", 7497),
        ("example.com", 4002),
    ):
        with pytest.raises(ValueError, match="PAPER Gateway"):
            scanner.probe_scanner_capability(
                host, port, expected_account_hash="a" * 64
            )


def test_scanner_module_has_no_order_write_surface():
    source = inspect.getsource(scanner)
    forbidden = (
        "place" + "Order",
        "cancel" + "Order",
        "whatIf" + "Order",
        "reqGlobal" + "Cancel",
    )
    assert not any(name in source for name in forbidden)
    assert "ScannerMessageGuard.validate" in source


def test_unavailable_gateway_reports_clean_capability_status():
    def broken_connect(*args, **kwargs):
        raise ConnectionError("IBKR PAPER Gateway connection failed")

    report = scanner.probe_scanner_capability(
        "127.0.0.1",
        4002,
        expected_account_hash="a" * 64,
        _connect=broken_connect,
    )

    assert report.available is None
    assert "GATEWAY_UNAVAILABLE" in report.reason_codes
    assert report.broker_write_calls == 0


def test_sanitize_report_never_persists_raw_account_identity():
    report = {
        "schema": scanner.SCHEMA,
        "available": True,
        "managed_account": "DU12345678",
        "account_fingerprint": "0123456789abcdef",
        "reason_codes": [],
        "scanner_parameters_received": True,
        "scanner_subscription_returned_contracts": True,
        "broker_write_calls": 0,
    }

    out = scanner.sanitize_scanner_report(report)

    assert out["paper_identity"]["account_fingerprint"] == "0123456789abcdef"
    assert out["paper_identity"]["raw_account_identity_persisted"] is False
    assert "managed_account" not in out
    assert "DU" not in json.dumps(out)


def test_sanitized_capability_json_has_required_semantics():
    report = scanner.ScannerCapabilityReport(
        available=True,
        reason_codes=(),
        scanner_parameters_received=True,
        scanner_subscription_returned_contracts=True,
    )

    out = scanner.sanitize_scanner_report(scanner.as_report_dict(report))

    assert out["market_scanner"]["available"] is True
    assert out["market_scanner"]["source"] == "IBKR_NATIVE"
    assert out["market_scanner"]["endpoint"] == "PAPER"
    assert out["market_scanner"]["broker_write_calls"] == 0
    assert out["market_scanner"]["discovery_evidence_only"] is True
    assert "authorized_universe" not in json.dumps(out)


def test_market_scanner_research_tool_is_preserved_in_toolbox():
    source = inspect.getsource(research_tools)
    assert "MARKET_SCANNER" in source
    assert "def _market_scanner" in source
    # The native discovery manifest remains model-directed.
    assert "Codex chooses instrument/location/scan code" in source


def test_scanner_subscription_builder_has_no_host_product_allowlist():
    subscription = scanner.build_scanner_subscription(
        instrument="FUT.US",
        location_code="FUT.GLOBEX",
        scan_code="MOST_ACTIVE",
        rows=17,
    )
    assert subscription.instrument == "FUT.US"
    assert subscription.locationCode == "FUT.GLOBEX"
    assert subscription.scanCode == "MOST_ACTIVE"
    assert subscription.numberOfRows == 17


def test_scanner_output_is_discovery_evidence_never_a_universe():
    toolbox_source = inspect.getsource(research_tools)
    validate_source = Path(
        "ibkr_paper_30d/ibkr_research_tools.py"
    ).read_text(encoding="utf-8")

    for forbidden in ("authorized_universe", "whitelist", "frozen_universe"):
        assert forbidden not in toolbox_source.lower(), forbidden

    # validate_proposal must not consult scanner results.
    validate_section = validate_source[
        validate_source.index("def validate_proposal"):
        validate_source.index("def validate_position_action")
    ]
    assert "scanner" not in validate_section.lower()


def test_external_scanner_evidence_is_pinned():
    """Ruling U1: the live probe is not repeated; external evidence stands.

    The prior independent verification (2026-09-23) proved:
    reqScannerParameters PASS (XML ~1.76MB), reqScannerSubscription PASS,
    STK.US.MAJOR/TOP_OPEN_PERC_GAIN 50 results, broker writes 0.
    This contract pins the semantic result so the capability claim is
    auditable without reconnecting to the broker.
    """

    evidence = scanner.EXTERNAL_SCANNER_EVIDENCE
    assert evidence["market_scanner"]["available"] is True
    assert evidence["market_scanner"]["source"] == "IBKR_NATIVE"
    assert evidence["market_scanner"]["endpoint"] == "PAPER"
    assert evidence["market_scanner"]["broker_write_calls"] == 0
    assert evidence["verification"]["scanner_parameters_received"] is True
    assert evidence["verification"]["scanner_subscription_returned_contracts"] is True
    assert evidence["verification"]["results_received"] == 50
    assert evidence["verification"]["scan_code"] == "TOP_OPEN_PERC_GAIN"
    assert evidence["verification"]["verified_against"] == "127.0.0.1:4002"
    assert evidence["verification"]["repeated_during_implementation"] is False
