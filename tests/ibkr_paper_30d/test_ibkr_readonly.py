from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from ibkr_paper_30d.cli import (
    _market_behavior,
    _required_summary_complete,
    _settled_cash,
    build_capability_matrix,
    build_implementation_status,
    inspect_readonly,
)
from ibkr_paper_30d.auditor_gate_v2 import (
    AuditorGateV2Evaluation,
    load_and_evaluate_auditor_gate_v2,
)
from ibkr_paper_30d.canonical import canonical_bytes
from ibkr_paper_30d.ibkr_readonly_session import QuoteObservation
from ibkr_paper_30d.ibkr_readonly import (
    IBKRReadOnlyAdapter,
    ReadOnlySessionSnapshot,
    expected_identity_hash,
)


NOW = datetime(2026, 9, 20, 16, 30, tzinfo=timezone.utc)
ACCOUNT = "DU123456"


def session(**updates) -> ReadOnlySessionSnapshot:
    values = {
        "port": 4002,
        "connected": True,
        "authenticated": True,
        "paper_trading_mode": True,
        "managed_accounts": (ACCOUNT,),
        "connector_account_hash": expected_identity_hash(ACCOUNT),
        "cash": "512.70",
        "settled_cash": "512.70",
        "position_count": 0,
        "open_order_count": 0,
        "execution_visibility": "AVAILABLE",
        "market_data_entitlements": "UNKNOWN",
        "server_timestamp_utc": NOW,
        "heartbeat_ok": True,
    }
    values.update(updates)
    return ReadOnlySessionSnapshot(**values)


def adapter() -> IBKRReadOnlyAdapter:
    return IBKRReadOnlyAdapter(expected_identity_hash(ACCOUNT))


def test_readonly_adapter_exposes_no_write_methods() -> None:
    public = set(dir(IBKRReadOnlyAdapter))

    assert "submit_order" not in public
    assert "cancel_order" not in public
    assert "modify_order" not in public
    assert "client" not in public


def test_readonly_source_contains_no_write_symbols_or_order_import() -> None:
    source = (
        Path(__file__).parents[2] / "ibkr_paper_30d" / "ibkr_readonly.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "place" + "Order",
        "cancel" + "Order",
        "reqGlobal" + "Cancel",
        "from ibapi.order import " + "Order",
    )

    assert all(symbol not in source for symbol in forbidden)


def test_port_4002_wrong_account_is_blocked() -> None:
    evidence = adapter().prove_identity(
        session(
            managed_accounts=("DU999999",),
            connector_account_hash=expected_identity_hash("DU999999"),
        )
    )

    assert evidence.paper_identity_proven is False
    assert evidence.event_type == "POSSIBLE_LIVE_CONNECTION"
    assert "ACCOUNT_IDENTITY_MISMATCH" in evidence.reason_codes


def test_identity_requires_all_independent_factors() -> None:
    good = adapter().prove_identity(session())

    assert good.paper_identity_proven is True
    assert good.event_type == "PAPER_IDENTITY_PROVEN"
    assert good.account_fingerprint != ACCOUNT
    assert len(good.account_fingerprint) == 16


def test_wrong_port_or_nonpaper_signal_blocks() -> None:
    wrong_port = adapter().prove_identity(session(port=7497))
    nonpaper = adapter().prove_identity(session(paper_trading_mode=False))

    assert "PAPER_PORT_MISMATCH" in wrong_port.reason_codes
    assert "PAPER_MODE_NOT_PROVEN" in nonpaper.reason_codes


def test_multiple_accounts_or_connector_mismatch_blocks() -> None:
    multiple = adapter().prove_identity(
        session(managed_accounts=(ACCOUNT, "DU654321"))
    )
    connector = adapter().prove_identity(
        session(connector_account_hash=expected_identity_hash("DU654321"))
    )

    assert "MANAGED_ACCOUNT_COUNT_INVALID" in multiple.reason_codes
    assert "CONNECTOR_IDENTITY_MISMATCH" in connector.reason_codes


def test_unavailable_connector_does_not_override_local_multifactor_proof() -> None:
    evidence = adapter().prove_identity(session(connector_account_hash=None))

    assert evidence.paper_identity_proven is True
    assert "CONNECTOR_IDENTITY_MISMATCH" not in evidence.reason_codes


def test_sanitized_inspection_contains_capabilities_but_no_account_id() -> None:
    report = adapter().inspect(session())
    serialized = str(report)

    assert report.status == "PASS"
    assert report.position_count == 0
    assert report.cash == "512.70"
    assert ACCOUNT not in serialized
    assert report.identity.account_fingerprint in serialized


def test_identity_hash_is_normalized_and_one_way() -> None:
    digest = expected_identity_hash(" du123456 ")

    assert digest == hashlib.sha256(ACCOUNT.encode("ascii")).hexdigest()
    assert ACCOUNT not in digest


def test_unavailable_gateway_writes_block_report_without_starting(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("ibkr_paper_30d.cli._port_is_open", lambda host, port: False)
    output = tmp_path / "readonly.json"

    report = inspect_readonly(
        host="127.0.0.1",
        port=4002,
        expected_account_hash=expected_identity_hash(ACCOUNT),
        output_path=output,
    )

    assert report["status"] == "BLOCK"
    assert report["reason_codes"] == ["GATEWAY_UNAVAILABLE"]
    assert output.exists()


def test_capability_matrix_and_status_never_enable_trading() -> None:
    readonly_report = {"status": "BLOCK", "reason_codes": ["GATEWAY_UNAVAILABLE"]}

    matrix = build_capability_matrix(readonly_report)
    status = build_implementation_status(test_count=173, test_failures=0)

    assert "| Real IBKR read-only identity | UNAVAILABLE |" in matrix
    assert status["AUTONOMOUS_TRADING_STATUS"] == "BLOCKED"
    assert status["REAL_PAPER_ORDER_WRITE_AUTHORIZED"] is False
    assert status["TEST_ORDER_AUTHORIZED"] is False
    assert status["DIRECTIONAL_TRADING_AUTHORIZED"] is False


def test_implementation_status_uses_real_gate_receipts() -> None:
    readonly = {
        "status": "PASS",
        "paper_account_identity_gate": "PASS",
        "real_ibkr_read_only_identity_gate": "PASS",
        "broker_reconciliation_gate": "PASS",
        "market_data_policy_frozen": False,
    }
    codex = {"gate": "PASS"}
    auditor = {"gate": "BLOCK"}
    alerts = {
        "gate": "PASS",
        "results": [
            {"event_type": "BROKER_2FA_REAUTH_REQUIRED"},
            {"event_type": "KILL_SWITCH_TRIGGERED"},
            {"event_type": "BROKER_HEARTBEAT_TIMEOUT"},
        ],
    }

    status = build_implementation_status(
        test_count=200,
        test_failures=0,
        readonly_report=readonly,
        alert_report=alerts,
        real_codex_report=codex,
        auditor_report=auditor,
    )

    assert status["PAPER_ACCOUNT_IDENTITY_GATE"] == "PASS"
    assert status["REAL_IBKR_READ_ONLY_IDENTITY_GATE"] == "PASS"
    assert status["BROKER_RECONCILIATION_GATE"] == "PASS"
    assert status["MARKET_DATA_POLICY_FROZEN"] is False
    assert status["MARKET_DATA_GATE"] == "BLOCK"
    assert status["TRADER_INVOCATION_REAL_CODEX_GATE"] == "PASS"
    assert status["AUDITOR_ISOLATION_GATE"] == "BLOCK"
    assert status["OWNER_ALERT_GATE"] == "PASS"
    assert status["READY_FOR_HARMLESS_PAPER_LIFECYCLE_TEST"] is False
    assert "AUDITOR_ISOLATION_GATE" in status["UNRESOLVED_BLOCKERS"]
    assert "MARKET_DATA_POLICY_FROZEN" in status["UNRESOLVED_BLOCKERS"]
    assert status["AUTONOMOUS_TRADING_STATUS"] == "BLOCKED"


def test_local_tests_cannot_promote_real_broker_reconciliation() -> None:
    status = build_implementation_status(test_count=200, test_failures=0)

    assert status["BROKER_RECONCILIATION_GATE"] == "BLOCK"
    assert status["REAL_IBKR_READ_ONLY_IDENTITY_GATE"] == "BLOCK"


def test_auditor_status_ignores_bare_or_v1_pass() -> None:
    evaluation = load_and_evaluate_auditor_gate_v2(
        canonical_bytes({"gate": "PASS"}), object(), NOW
    )

    status = build_implementation_status(
        test_count=200,
        test_failures=0,
        auditor_report={"gate": "PASS"},
        auditor_v2_evaluation=evaluation,
    )

    assert status["AUDITOR_LEAST_PRIVILEGE_AND_RUNTIME_INTEGRITY_GATE_V2"] == "BLOCK"
    assert status["AUDITOR_ISOLATION_GATE_V2"] == "BLOCK"
    assert status["AUDITOR_ISOLATION_GATE"] == "BLOCK"
    assert status["AUDITOR_GATE_VERSION"] == "V2"


def test_auditor_status_uses_v2_evaluation_but_never_authorizes_orders() -> None:
    evaluation = AuditorGateV2Evaluation("PASS", "PASS", "V2", ())

    status = build_implementation_status(
        test_count=200,
        test_failures=0,
        auditor_v2_evaluation=evaluation,
    )

    assert status["AUDITOR_LEAST_PRIVILEGE_AND_RUNTIME_INTEGRITY_GATE_V2"] == "PASS"
    assert status["AUDITOR_ISOLATION_GATE_V2"] == "PASS"
    assert status["AUDITOR_ISOLATION_GATE"] == "PASS"
    assert status["READY_FOR_HARMLESS_PAPER_LIFECYCLE_TEST"] is False
    assert status["REAL_PAPER_ORDER_WRITE_AUTHORIZED"] is False
    assert status["AUDITOR_TECHNICAL_SOCKET_REACHABILITY"] is False
    assert status["AUDITOR_NETWORK_ISOLATION_REQUIRED"] is True
    assert status["AUDITOR_UNAUTHORIZED_RAW_API_PATH_POSSIBLE"] is False


def test_market_behavior_requires_an_actual_quote_value() -> None:
    quotes = (
        QuoteObservation("SPY", 1, None, None, None, None, True),
        QuoteObservation("QQQ", 1, None, None, None, None, True),
    )

    assert _market_behavior(quotes) == "UNAVAILABLE"


def test_reconciliation_requires_all_authorized_account_summary_fields() -> None:
    complete = {
        "TotalCashValue": "500.00",
        "SettledCash": "500.00",
        "BuyingPower": "500.00",
        "NetLiquidation": "500.00",
    }

    assert _required_summary_complete(complete) is True
    del complete["SettledCash"]
    assert _required_summary_complete(complete) is False

    complete["SettledCashByDate"] = "20260920:500.00"
    assert _required_summary_complete(complete) is True
    assert _settled_cash(complete) == "500.00"
