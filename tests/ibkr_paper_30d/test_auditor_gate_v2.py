from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from ibkr_paper_30d.auditor_gate_v2 import (
    EXPECTED_AUDITOR_SID,
    AuditorGateV2Receipt,
    ReceiptValidationError,
    parse_auditor_gate_v2_receipt,
)
from ibkr_paper_30d.canonical import canonical_bytes


TARGET_NAMES = (
    "SECRETS_READ",
    "IBKR_SECRET_READ",
    "SMTP_SECRET_READ",
    "EXECUTION_LOCK_ACCESS",
    "LIVE_DATABASE_MUTATION",
    "BROKER_WRITE_PATH_ACCESS",
    "TRADER_CONTEXT_ACCESS",
    "AUDIT_INPUT_MUTATION",
    "IMMUTABLE_EXPORT_READ",
    "AUDITOR_REPORT_WRITE",
)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 9, 20, 16, 0, tzinfo=timezone.utc)


@pytest.fixture
def complete_receipt(now: datetime) -> dict[str, object]:
    run_id = "run-v2-001"
    outcomes = {name: "DENIED" for name in TARGET_NAMES}
    outcomes["IMMUTABLE_EXPORT_READ"] = "ALLOWED"
    outcomes["AUDITOR_REPORT_WRITE"] = "ALLOWED"
    return {
        "schema": "AUDITOR_GATE_V2_RECEIPT_V1",
        "gate_version": "V2",
        "run_id": run_id,
        "started_at_utc": "2026-09-20T15:58:00Z",
        "completed_at_utc": "2026-09-20T15:59:00Z",
        "effective_sid": EXPECTED_AUDITOR_SID,
        "token_elevated": False,
        "separate_process": True,
        "runtime_integrity": {
            "status": "PASS",
            "runtime_manifest_sha256": "a" * 64,
            "deployment_manifest_sha256": "b" * 64,
            "probe_sha256": "c" * 64,
            "probe_manifest_sha256": "d" * 64,
            "exact_fileset": True,
            "predicates": {
                "BROKER_MODULE_AVAILABLE": False,
                "ORDER_WRITE_SYMBOL_AVAILABLE": False,
                "EXECUTION_ADAPTER_AVAILABLE": False,
                "EXECUTION_LOCK_CLIENT_AVAILABLE": False,
                "TRADER_IPC_CLIENT_AVAILABLE": False,
                "BROKER_CREDENTIAL_SOURCE_AVAILABLE": False,
                "ORDER_WRITE_MODULE_AVAILABLE": False,
            },
        },
        "target_validation_matrix": [
            {"run_id": run_id, "probe": name, "valid": True}
            for name in TARGET_NAMES
        ],
        "capability_outcomes": outcomes,
        "functional_auditor": {
            "run_id": run_id,
            "status": "PASS",
            "bundle_id": "e" * 64,
            "manifest_sha256": "f" * 64,
        },
        "paper_identity": {
            "run_id": run_id,
            "expected_account_identity_hash": "1" * 64,
            "identity_receipt_sha256": "2" * 64,
            "environment_reference": "PAPER:gateway:4002",
            "broker_session_environment_reference": "PAPER:session:4002",
            "verified_at_utc": "2026-09-20T15:57:00Z",
            "paper_identity_gate": "PASS",
            "readonly_identity_gate": "PASS",
            "broker_reconciliation_gate": "PASS",
        },
        "network_facts": {
            "AUDITOR_TECHNICAL_SOCKET_REACHABILITY": True,
            "AUDITOR_NETWORK_ISOLATION_REQUIRED": False,
            "AUDITOR_UNAUTHORIZED_RAW_API_PATH_POSSIBLE": True,
            "AUDITOR_COMPROMISE_CONTAINMENT_NOT_CLAIMED": True,
            "endpoints": {"127.0.0.1:4002": "CONNECTED", "[::1]:4002": "NO_LISTENER"},
        },
        "output": {
            "run_id": run_id,
            "report_path": r"C:\ProgramData\CodexAuditorV1\reports\v2.json",
            "created": True,
            "report_sha256": "3" * 64,
        },
    }


def test_v2_receipt_parses_complete_canonical_document(complete_receipt) -> None:
    receipt = parse_auditor_gate_v2_receipt(canonical_bytes(complete_receipt))

    assert isinstance(receipt, AuditorGateV2Receipt)
    assert receipt.run_id == "run-v2-001"
    assert receipt.completed_at_utc.tzinfo is timezone.utc


@pytest.mark.parametrize("field", ["runtime_integrity", "paper_identity", "output"])
def test_v2_receipt_rejects_missing_required_top_level_field(
    complete_receipt, field
) -> None:
    missing = deepcopy(complete_receipt)
    del missing[field]

    with pytest.raises(ReceiptValidationError, match="MISSING_FIELD"):
        parse_auditor_gate_v2_receipt(canonical_bytes(missing))


def test_v2_receipt_rejects_unknown_duplicate_and_case_colliding_keys(
    complete_receipt,
) -> None:
    extra = deepcopy(complete_receipt)
    extra["unknown"] = True
    with pytest.raises(ReceiptValidationError, match="UNKNOWN_FIELD"):
        parse_auditor_gate_v2_receipt(canonical_bytes(extra))

    for source in (
        b'{"schema":"AUDITOR_GATE_V2_RECEIPT_V1","schema":"DUPLICATE"}',
        b'{"schema":"AUDITOR_GATE_V2_RECEIPT_V1","SCHEMA":"DUPLICATE"}',
    ):
        with pytest.raises(ReceiptValidationError, match="DUPLICATE_KEY"):
            parse_auditor_gate_v2_receipt(source)


def test_v2_receipt_rejects_wrong_types_and_non_utc_time(complete_receipt) -> None:
    wrong_type = deepcopy(complete_receipt)
    wrong_type["token_elevated"] = "false"
    with pytest.raises(ReceiptValidationError, match="WRONG_TYPE"):
        parse_auditor_gate_v2_receipt(canonical_bytes(wrong_type))

    non_utc = deepcopy(complete_receipt)
    non_utc["completed_at_utc"] = "2026-09-20T11:59:00-04:00"
    with pytest.raises(ReceiptValidationError, match="TIMESTAMP_NOT_UTC"):
        parse_auditor_gate_v2_receipt(canonical_bytes(non_utc))
