from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.auditor_gate_v2 import (
    EXPECTED_AUDITOR_SID,
    IdentityBindingError,
    PaperIdentityBinding,
    AuditorGateV2Evaluation,
    AuditorGateV2Receipt,
    ReceiptValidationError,
    evaluate_auditor_gate_v2,
    evaluate_acceptance_expiration,
    parse_auditor_gate_v2_receipt,
)
from ibkr_paper_30d.auditor_v2_artifacts import (
    ArtifactValidationError,
    build_residual_risk_acceptance,
    render_auditor_gate_v2_report,
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
    outcomes["BROKER_WRITE_PATH_ACCESS"] = "ALLOWED"
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
            "verified_at_utc": "2026-09-20T15:57:30Z",
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
        environment_reference="PAPER:gateway:4002",
        broker_session_environment_reference="PAPER:session:4002",
        runtime_manifest_sha256="a" * 64,
        deployment_manifest_sha256="b" * 64,
        probe_sha256="c" * 64,
        probe_manifest_sha256="d" * 64,
        raw_account="DU" + "1234567",
    )


@pytest.fixture
def owner_decision() -> dict[str, object]:
    return {
        "decision": "OWNER_AUTHORIZATION_IMPLEMENT_AUDITOR_GATE_V2",
        "design_commit": "322a79cb",
        "plan_commit": "7e8d4689",
        "month1_paper_only": True,
    }


@pytest.fixture
def expected_hash() -> str:
    return "1" * 64


@pytest.fixture
def readonly_receipt_bytes(expected_hash: str) -> bytes:
    return canonical_bytes(
        {
            "schema": "REAL_IBKR_READ_ONLY_RECONCILIATION_V1",
            "status": "PASS",
            "paper_account_identity_gate": "PASS",
            "real_ibkr_read_only_identity_gate": "PASS",
            "broker_reconciliation_gate": "PASS",
            "expected_account_identity_bound": True,
            "expected_account_identity_hash": expected_hash,
            "raw_account_identity_persisted": False,
            "host": "127.0.0.1",
            "port": 4002,
            "gateway_mode": "PAPER",
            "server_version": 180,
            "connection_time": "20260920 11:57:00 EST",
            "server_timestamp_utc": "2026-09-20T15:57:00Z",
        }
    )


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


def test_gate_v2_passes_only_one_complete_coherent_receipt(
    complete_receipt, expected_identity, now
) -> None:
    receipt = parse_auditor_gate_v2_receipt(canonical_bytes(complete_receipt))

    result = evaluate_auditor_gate_v2(receipt, expected_identity, now)

    assert result.canonical_gate == "PASS"
    assert result.compatibility_gate == "PASS"
    assert result.gate_version == "V2"
    assert result.reason_codes == ()


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


NEGATIVE_GATE_CASES = (
    ("v1_only", "SCHEMA_INVALID"),
    ("partial", "MISSING_FIELD"),
    ("stale", "RECEIPT_STALE"),
    ("mixed_run", "MIXED_RUN_EVIDENCE"),
    ("wrong_sid", "AUDITOR_SID_MISMATCH"),
    ("elevated", "AUDITOR_TOKEN_ELEVATED"),
    ("wrong_paper_account_hash", "PAPER_ACCOUNT_IDENTITY_MISMATCH"),
    ("wrong_paper_identity_receipt", "PAPER_IDENTITY_RECEIPT_MISMATCH"),
    ("paper_environment_change", "PAPER_ENVIRONMENT_MISMATCH"),
    ("runtime_extra_file", "RUNTIME_INTEGRITY_BLOCK"),
    ("runtime_missing_file", "RUNTIME_INTEGRITY_BLOCK"),
    ("runtime_hash_mismatch", "RUNTIME_EXPECTATION_MISMATCH"),
    ("broker_module_introduced", "RUNTIME_FORBIDDEN_CAPABILITY_PRESENT"),
    ("order_symbol_introduced", "RUNTIME_FORBIDDEN_CAPABILITY_PRESENT"),
    ("execution_lock_code_introduced", "RUNTIME_FORBIDDEN_CAPABILITY_PRESENT"),
    ("trader_ipc_introduced", "RUNTIME_FORBIDDEN_CAPABILITY_PRESENT"),
    ("missing_target_row", "TARGET_VALIDATION_COUNT_INVALID"),
    ("missing_capability_outcome", "CAPABILITY_OUTCOMES_INVALID"),
    ("broadened_runtime_bundle", "RUNTIME_INTEGRITY_BLOCK"),
    ("residual_risk_artifact_tamper", "ARTIFACT_TAMPERED"),
    ("live_allowed_true", "MONTH1_PAPER_SCOPE_INVALID"),
    ("real_money_allowed_true", "MONTH1_PAPER_SCOPE_INVALID"),
)


def _apply_negative_mutation(name: str, payload: dict[str, object]) -> None:
    if name == "v1_only":
        payload["schema"] = "CODEX_DECISION_AUDITOR_ISOLATION_V1"
    elif name == "partial":
        del payload["runtime_integrity"]
    elif name == "stale":
        payload["started_at_utc"] = "2026-09-18T15:58:00Z"
        payload["completed_at_utc"] = "2026-09-18T15:59:00Z"
    elif name == "mixed_run":
        payload["target_validation_matrix"][0]["run_id"] = "other-run"
    elif name == "wrong_sid":
        payload["effective_sid"] = "S-1-5-18"
    elif name == "elevated":
        payload["token_elevated"] = True
    elif name == "wrong_paper_account_hash":
        payload["paper_identity"]["expected_account_identity_hash"] = "9" * 64
    elif name == "wrong_paper_identity_receipt":
        payload["paper_identity"]["identity_receipt_sha256"] = "8" * 64
    elif name == "paper_environment_change":
        payload["paper_identity"]["environment_reference"] = "LIVE:gateway:4001"
    elif name in {"runtime_extra_file", "runtime_missing_file", "broadened_runtime_bundle"}:
        payload["runtime_integrity"]["exact_fileset"] = False
    elif name == "runtime_hash_mismatch":
        payload["runtime_integrity"]["runtime_manifest_sha256"] = "9" * 64
    elif name == "broker_module_introduced":
        payload["runtime_integrity"]["predicates"]["BROKER_MODULE_AVAILABLE"] = True
    elif name == "order_symbol_introduced":
        payload["runtime_integrity"]["predicates"]["ORDER_WRITE_SYMBOL_AVAILABLE"] = True
    elif name == "execution_lock_code_introduced":
        payload["runtime_integrity"]["predicates"]["EXECUTION_LOCK_CLIENT_AVAILABLE"] = True
    elif name == "trader_ipc_introduced":
        payload["runtime_integrity"]["predicates"]["TRADER_IPC_CLIENT_AVAILABLE"] = True
    elif name == "missing_target_row":
        payload["target_validation_matrix"].pop()
    elif name == "missing_capability_outcome":
        del payload["capability_outcomes"]["SECRETS_READ"]
    elif name == "live_allowed_true":
        payload["paper_identity"]["live_allowed"] = True
    elif name == "real_money_allowed_true":
        payload["paper_identity"]["real_money_allowed"] = True


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    NEGATIVE_GATE_CASES,
    ids=[case[0] for case in NEGATIVE_GATE_CASES],
)
def test_every_negative_v2_mutation_blocks(
    tmp_path,
    complete_receipt,
    expected_identity,
    now,
    pass_evaluation,
    owner_decision,
    mutation,
    reason_code,
) -> None:
    payload = deepcopy(complete_receipt)
    if mutation == "residual_risk_artifact_tamper":
        receipt = parse_auditor_gate_v2_receipt(canonical_bytes(payload))
        artifact = build_residual_risk_acceptance(
            receipt, pass_evaluation, owner_decision
        )
        path = tmp_path / "acceptance.json"
        digest = write_immutable_json(path, artifact)
        path.write_bytes(path.read_bytes() + b" ")
        assert verify_immutable_json(path, digest) is False
        return

    _apply_negative_mutation(mutation, payload)
    try:
        receipt = parse_auditor_gate_v2_receipt(canonical_bytes(payload))
    except ReceiptValidationError as exc:
        assert reason_code in str(exc)
        return

    result = evaluate_auditor_gate_v2(receipt, expected_identity, now)

    assert result.canonical_gate == "BLOCK"
    assert reason_code in result.reason_codes


def test_unsafe_target_and_configuration_only_evidence_remain_blocked(
    complete_receipt, expected_identity, now
) -> None:
    unsafe = deepcopy(complete_receipt)
    unsafe["target_validation_matrix"][0]["valid"] = False
    unsafe_receipt = parse_auditor_gate_v2_receipt(canonical_bytes(unsafe))
    assert evaluate_auditor_gate_v2(unsafe_receipt, expected_identity, now).canonical_gate == "BLOCK"

    with pytest.raises(ReceiptValidationError):
        parse_auditor_gate_v2_receipt(canonical_bytes({"gate": "PASS", "PAPER_ONLY": True}))


def test_paper_binding_uses_hashes_and_broker_derived_gate(
    readonly_receipt_bytes, expected_hash
) -> None:
    binding = PaperIdentityBinding.from_readonly_receipt(
        json.loads(readonly_receipt_bytes), readonly_receipt_bytes
    )

    assert binding.expected_account_hash == expected_hash
    assert binding.receipt_sha256 == hashlib.sha256(readonly_receipt_bytes).hexdigest()
    assert binding.paper_identity_gate == "PASS"
    assert binding.raw_account_identity_persisted is False
    assert binding.environment_reference.startswith("PAPER:")
    assert binding.broker_session_environment_reference.startswith("PAPER-SESSION:")


def test_paper_binding_rejects_configuration_only_or_failed_broker_gate(
    readonly_receipt_bytes,
) -> None:
    payload = json.loads(readonly_receipt_bytes)
    payload["paper_account_identity_gate"] = "BLOCK"
    with pytest.raises(IdentityBindingError, match="BROKER_DERIVED_PAPER_IDENTITY_BLOCK"):
        PaperIdentityBinding.from_readonly_receipt(payload, canonical_bytes(payload))

    with pytest.raises(IdentityBindingError, match="READONLY_RECEIPT_SCHEMA_INVALID"):
        PaperIdentityBinding.from_readonly_receipt(
            {"PAPER_ONLY": True}, canonical_bytes({"PAPER_ONLY": True})
        )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("expected_account_hash", "9" * 64, "PAPER_ACCOUNT_IDENTITY_CHANGED"),
        ("receipt_sha256", "8" * 64, "PAPER_IDENTITY_RECEIPT_CHANGED"),
        ("paper_environment_reference", "PAPER:changed", "PAPER_ENVIRONMENT_CHANGED"),
        (
            "broker_session_environment_reference",
            "PAPER-SESSION:changed",
            "BROKER_SESSION_ENVIRONMENT_CHANGED",
        ),
        ("runtime_manifest_sha256", "7" * 64, "AUDITOR_RUNTIME_CHANGED"),
        ("deployment_manifest_sha256", "6" * 64, "AUDITOR_RUNTIME_CHANGED"),
        ("auditor_sid", "S-1-5-18", "AUDITOR_PRIVILEGE_BOUNDARY_CHANGED"),
        ("experiment_state", "COMPLETED", "MONTH1_EXPERIMENT_ENDED"),
        ("live_allowed", True, "LIVE_OR_REAL_MONEY_REQUESTED"),
        ("real_money_allowed", True, "LIVE_OR_REAL_MONEY_REQUESTED"),
    ],
)
def test_acceptance_expiration_detects_every_material_boundary_change(
    field, value, reason
) -> None:
    acceptance = {
        "EXPECTED_PAPER_ACCOUNT_IDENTITY_HASH": "1" * 64,
        "PAPER_IDENTITY_RECEIPT_SHA256": "2" * 64,
        "PAPER_ENVIRONMENT_REFERENCE": "PAPER:env",
        "BROKER_SESSION_ENVIRONMENT_REFERENCE": "PAPER-SESSION:env",
        "RUNTIME_MANIFEST_SHA256": "a" * 64,
        "DEPLOYMENT_MANIFEST_SHA256": "b" * 64,
        "AUDITOR_SID": EXPECTED_AUDITOR_SID,
        "PAPER_ONLY": True,
        "LIVE_ALLOWED": False,
        "REAL_MONEY_ALLOWED": False,
    }
    current = {
        "expected_account_hash": "1" * 64,
        "receipt_sha256": "2" * 64,
        "paper_environment_reference": "PAPER:env",
        "broker_session_environment_reference": "PAPER-SESSION:env",
        "runtime_manifest_sha256": "a" * 64,
        "deployment_manifest_sha256": "b" * 64,
        "auditor_sid": EXPECTED_AUDITOR_SID,
        "token_elevated": False,
        "paper_only": True,
        "live_allowed": False,
        "real_money_allowed": False,
        "experiment_state": "ACTIVE",
    }
    current[field] = value

    result = evaluate_acceptance_expiration(acceptance, current)

    assert result.status == "EXPIRED"
    assert reason in result.reason_codes


def test_acceptance_expiration_keeps_exact_month1_context_active() -> None:
    acceptance = {
        "EXPECTED_PAPER_ACCOUNT_IDENTITY_HASH": "1" * 64,
        "PAPER_IDENTITY_RECEIPT_SHA256": "2" * 64,
        "PAPER_ENVIRONMENT_REFERENCE": "PAPER:env",
        "BROKER_SESSION_ENVIRONMENT_REFERENCE": "PAPER-SESSION:env",
        "RUNTIME_MANIFEST_SHA256": "a" * 64,
        "DEPLOYMENT_MANIFEST_SHA256": "b" * 64,
        "AUDITOR_SID": EXPECTED_AUDITOR_SID,
        "PAPER_ONLY": True,
        "LIVE_ALLOWED": False,
        "REAL_MONEY_ALLOWED": False,
    }
    current = {
        "expected_account_hash": "1" * 64,
        "receipt_sha256": "2" * 64,
        "paper_environment_reference": "PAPER:env",
        "broker_session_environment_reference": "PAPER-SESSION:env",
        "runtime_manifest_sha256": "a" * 64,
        "deployment_manifest_sha256": "b" * 64,
        "auditor_sid": EXPECTED_AUDITOR_SID,
        "token_elevated": False,
        "paper_only": True,
        "live_allowed": False,
        "real_money_allowed": False,
        "experiment_state": "ACTIVE",
    }

    result = evaluate_acceptance_expiration(acceptance, current)

    assert result.status == "ACTIVE"
    assert result.reason_codes == ()


def test_gate_report_renders_all_v2_evidence_without_account_identity(
    complete_receipt, expected_identity, now
) -> None:
    receipt = parse_auditor_gate_v2_receipt(canonical_bytes(complete_receipt))
    evaluation = evaluate_auditor_gate_v2(receipt, expected_identity, now)

    report = render_auditor_gate_v2_report(
        receipt,
        evaluation,
        {
            "receipt": {
                "path": r"C:\ProgramData\CodexAuditorV1\reports\v2.json",
                "sha256": "4" * 64,
            },
            "deployment_review": {
                "path": "AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1",
                "sha256": "5" * 64,
            },
        },
    )

    for value in (
        "AUDITOR_LEAST_PRIVILEGE_AND_RUNTIME_INTEGRITY_GATE_V2: PASS",
        "AUDITOR_ISOLATION_GATE_V2: PASS",
        "AUDITOR_TECHNICAL_SOCKET_REACHABILITY: true",
        "AUDITOR_NETWORK_ISOLATION_REQUIRED: false",
        "AUDITOR_UNAUTHORIZED_RAW_API_PATH_POSSIBLE: true",
        "AUDITOR_COMPROMISE_CONTAINMENT_NOT_CLAIMED: true",
        "LEGACY_FIREWALL_CONTROL: INEFFECTIVE_FOR_LOOPBACK_REQUIREMENT",
        "WFP_AUDITOR_FRONT: DEFERRED",
        "EXPECTED_PAPER_ACCOUNT_IDENTITY_HASH",
        "PAPER_ENVIRONMENT_REFERENCE",
        "BROKER_MODULE_AVAILABLE",
        "receipt",
    ):
        assert value in report
    assert expected_identity.raw_account not in report


def test_gate_report_is_blocked_when_real_receipt_is_absent() -> None:
    evaluation = AuditorGateV2Evaluation(
        "BLOCK", "BLOCK", "V2", ("NEW_ADMIN_ACTION_REQUIRED",)
    )

    report = render_auditor_gate_v2_report(
        None,
        evaluation,
        {"deployment_review": {"sha256": "5" * 64}},
    )

    assert "AUDITOR_LEAST_PRIVILEGE_AND_RUNTIME_INTEGRITY_GATE_V2: BLOCK" in report
    assert "NEW_ADMIN_ACTION_REQUIRED" in report
    assert "Accepted receipt: NONE" in report
