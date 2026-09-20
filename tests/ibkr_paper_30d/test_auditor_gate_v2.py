from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.auditor_gate_v2 import (
    EXPECTED_AUDITOR_SID,
    AuditorGateV2Evaluation,
    AuditorGateV2Receipt,
    ReceiptValidationError,
    parse_auditor_gate_v2_receipt,
)
from ibkr_paper_30d.auditor_v2_artifacts import (
    ArtifactValidationError,
    build_residual_risk_acceptance,
    verify_immutable_json,
    write_immutable_json,
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
            "paper_only": True,
            "live_allowed": False,
            "real_money_allowed": False,
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
            "evidence_origin": "REAL_RESTRICTED_TOKEN",
        },
    }


@pytest.fixture
def pass_evaluation() -> AuditorGateV2Evaluation:
    return AuditorGateV2Evaluation("PASS", "PASS", "V2", ())


@pytest.fixture
def expected_identity() -> SimpleNamespace:
    return SimpleNamespace(
        expected_account_hash="1" * 64,
        receipt_sha256="2" * 64,
        raw_account="DU1234567",
    )


@pytest.fixture
def owner_decision() -> dict[str, object]:
    return {
        "decision": "OWNER_AUTHORIZATION_IMPLEMENT_AUDITOR_GATE_V2",
        "design_commit": "322a79cb",
        "plan_commit": "7e8d4689",
        "month1_paper_only": True,
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


def test_residual_risk_binds_paper_identity_without_cleartext_account(
    complete_receipt, pass_evaluation, expected_identity, owner_decision
) -> None:
    receipt = parse_auditor_gate_v2_receipt(canonical_bytes(complete_receipt))
    artifact = build_residual_risk_acceptance(
        receipt, pass_evaluation, owner_decision
    )

    assert artifact["EXPECTED_PAPER_ACCOUNT_IDENTITY_HASH"] == (
        expected_identity.expected_account_hash
    )
    assert artifact["PAPER_IDENTITY_RECEIPT_SHA256"] == expected_identity.receipt_sha256
    assert artifact["AUDITOR_TECHNICAL_SOCKET_REACHABILITY"] is True
    assert artifact["AUDITOR_NETWORK_ISOLATION_REQUIRED"] is False
    assert artifact["AUDITOR_UNAUTHORIZED_RAW_API_PATH_POSSIBLE"] is True
    assert artifact["AUDITOR_COMPROMISE_CONTAINMENT_NOT_CLAIMED"] is True
    assert artifact["AUDITOR_ORDER_AUTHORITY_GRANTED"] is False
    assert artifact["AUDITOR_BROKER_CONTROL_PATH_AUTHORIZED"] is False
    assert expected_identity.raw_account not in canonical_bytes(artifact).decode("ascii")
    assert len(artifact["EXPIRATION_TRIGGERS"]) == 7


def test_residual_risk_is_write_once_canonical_and_tamper_evident(
    tmp_path, complete_receipt, pass_evaluation, owner_decision, expected_identity
) -> None:
    receipt = parse_auditor_gate_v2_receipt(canonical_bytes(complete_receipt))
    artifact = build_residual_risk_acceptance(
        receipt, pass_evaluation, owner_decision
    )
    path = tmp_path / "risk.json"

    digest = write_immutable_json(path, artifact)

    assert path.read_bytes() == canonical_bytes(artifact)
    assert verify_immutable_json(path, digest) is True
    assert expected_identity.raw_account.encode("ascii") not in path.read_bytes()
    assert b"IBKR_PASSWORD" not in path.read_bytes()
    with pytest.raises(FileExistsError):
        write_immutable_json(path, artifact)
    path.write_bytes(path.read_bytes() + b" ")
    assert verify_immutable_json(path, digest) is False


@pytest.mark.parametrize(
    ("field", "value"),
    [("paper_only", False), ("live_allowed", True), ("real_money_allowed", True)],
)
def test_residual_risk_rejects_non_paper_or_live_scope(
    complete_receipt, pass_evaluation, owner_decision, field, value
) -> None:
    complete_receipt["paper_identity"][field] = value
    receipt = parse_auditor_gate_v2_receipt(canonical_bytes(complete_receipt))

    with pytest.raises(ArtifactValidationError, match="MONTH1_PAPER_SCOPE_INVALID"):
        build_residual_risk_acceptance(receipt, pass_evaluation, owner_decision)


def test_residual_risk_rejects_synthetic_or_nonpassing_receipt(
    complete_receipt, owner_decision
) -> None:
    complete_receipt["output"]["evidence_origin"] = "SYNTHETIC"
    receipt = parse_auditor_gate_v2_receipt(canonical_bytes(complete_receipt))
    blocked = AuditorGateV2Evaluation("BLOCK", "BLOCK", "V2", ("TEST",))

    with pytest.raises(ArtifactValidationError, match="REAL_RECEIPT_REQUIRED"):
        build_residual_risk_acceptance(receipt, blocked, owner_decision)
