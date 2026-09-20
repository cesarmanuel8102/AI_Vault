from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Mapping, Sequence


EXPECTED_AUDITOR_SID = "S-1-5-21-214160970-1890373857-4055601883-1012"
RECEIPT_MAX_AGE = timedelta(hours=24)
RECEIPT_SCHEMA = "AUDITOR_GATE_V2_RECEIPT_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema",
        "gate_version",
        "run_id",
        "started_at_utc",
        "completed_at_utc",
        "effective_sid",
        "token_elevated",
        "separate_process",
        "runtime_integrity",
        "target_validation_matrix",
        "capability_outcomes",
        "functional_auditor",
        "paper_identity",
        "network_facts",
        "output",
    }
)
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
APPROVED_CAPABILITY_OUTCOMES = {
    **{name: "DENIED" for name in TARGET_NAMES},
    "BROKER_WRITE_PATH_ACCESS": "ALLOWED",
    "IMMUTABLE_EXPORT_READ": "ALLOWED",
    "AUDITOR_REPORT_WRITE": "ALLOWED",
}
STRUCTURAL_PREDICATES = (
    "BROKER_MODULE_AVAILABLE",
    "ORDER_WRITE_SYMBOL_AVAILABLE",
    "EXECUTION_ADAPTER_AVAILABLE",
    "EXECUTION_LOCK_CLIENT_AVAILABLE",
    "TRADER_IPC_CLIENT_AVAILABLE",
    "BROKER_CREDENTIAL_SOURCE_AVAILABLE",
    "ORDER_WRITE_MODULE_AVAILABLE",
)


class ReceiptValidationError(ValueError):
    """Raised when Auditor V2 evidence is not structurally trustworthy."""


@dataclass(frozen=True)
class AuditorGateV2Receipt:
    schema: str
    gate_version: str
    run_id: str
    started_at_utc: datetime
    completed_at_utc: datetime
    effective_sid: str
    token_elevated: bool
    separate_process: bool
    runtime_integrity: Mapping[str, object]
    target_validation_matrix: Sequence[Mapping[str, object]]
    capability_outcomes: Mapping[str, str]
    functional_auditor: Mapping[str, object]
    paper_identity: Mapping[str, object]
    network_facts: Mapping[str, object]
    output: Mapping[str, object]


@dataclass(frozen=True)
class AuditorGateV2Evaluation:
    canonical_gate: str
    compatibility_gate: str
    gate_version: str
    reason_codes: tuple[str, ...]


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    normalized: set[str] = set()
    for key, value in pairs:
        folded = key.casefold()
        if folded in normalized:
            raise ReceiptValidationError(f"DUPLICATE_KEY:{key}")
        normalized.add(folded)
        result[key] = value
    return result


def _parse_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ReceiptValidationError(f"WRONG_TYPE:{field}")
    if not value.endswith("Z"):
        raise ReceiptValidationError(f"TIMESTAMP_NOT_UTC:{field}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ReceiptValidationError(f"TIMESTAMP_INVALID:{field}") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ReceiptValidationError(f"TIMESTAMP_NOT_UTC:{field}")
    return parsed.astimezone(timezone.utc)


def _validate_sha_fields(value: object, path: str = "receipt") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key.endswith("_sha256") or key == "expected_account_identity_hash":
                if not isinstance(child, str) or not _SHA256_RE.fullmatch(child):
                    raise ReceiptValidationError(f"INVALID_SHA256:{child_path}")
            _validate_sha_fields(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_sha_fields(child, f"{path}[{index}]")


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _require_type(payload: Mapping[str, object], field: str, expected: type) -> None:
    value = payload[field]
    if expected is bool:
        valid = type(value) is bool
    else:
        valid = isinstance(value, expected)
    if not valid:
        raise ReceiptValidationError(f"WRONG_TYPE:{field}")


def parse_auditor_gate_v2_receipt(source: bytes | str) -> AuditorGateV2Receipt:
    try:
        text = source.decode("utf-8") if isinstance(source, bytes) else source
    except UnicodeDecodeError as exc:
        raise ReceiptValidationError("INVALID_UTF8") from exc
    if not isinstance(text, str):
        raise ReceiptValidationError("WRONG_TYPE:source")
    try:
        payload = json.loads(text, object_pairs_hook=_strict_object)
    except ReceiptValidationError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise ReceiptValidationError("INVALID_JSON") from exc
    if not isinstance(payload, dict):
        raise ReceiptValidationError("WRONG_TYPE:receipt")

    missing = _TOP_LEVEL_FIELDS - payload.keys()
    if missing:
        raise ReceiptValidationError(f"MISSING_FIELD:{sorted(missing)[0]}")
    unknown = payload.keys() - _TOP_LEVEL_FIELDS
    if unknown:
        raise ReceiptValidationError(f"UNKNOWN_FIELD:{sorted(unknown)[0]}")

    for field in (
        "schema",
        "gate_version",
        "run_id",
        "effective_sid",
    ):
        _require_type(payload, field, str)
    for field in ("token_elevated", "separate_process"):
        _require_type(payload, field, bool)
    for field in (
        "runtime_integrity",
        "capability_outcomes",
        "functional_auditor",
        "paper_identity",
        "network_facts",
        "output",
    ):
        _require_type(payload, field, dict)
    _require_type(payload, "target_validation_matrix", list)

    if payload["schema"] != RECEIPT_SCHEMA:
        raise ReceiptValidationError("SCHEMA_INVALID")
    if payload["gate_version"] != "V2":
        raise ReceiptValidationError("GATE_VERSION_INVALID")
    if not payload["run_id"]:
        raise ReceiptValidationError("RUN_ID_INVALID")
    _validate_sha_fields(payload)

    started = _parse_utc(payload["started_at_utc"], "started_at_utc")
    completed = _parse_utc(payload["completed_at_utc"], "completed_at_utc")
    if completed < started:
        raise ReceiptValidationError("TIMESTAMP_ORDER_INVALID")

    return AuditorGateV2Receipt(
        schema=payload["schema"],
        gate_version=payload["gate_version"],
        run_id=payload["run_id"],
        started_at_utc=started,
        completed_at_utc=completed,
        effective_sid=payload["effective_sid"],
        token_elevated=payload["token_elevated"],
        separate_process=payload["separate_process"],
        runtime_integrity=_freeze(payload["runtime_integrity"]),
        target_validation_matrix=_freeze(payload["target_validation_matrix"]),
        capability_outcomes=_freeze(payload["capability_outcomes"]),
        functional_auditor=_freeze(payload["functional_auditor"]),
        paper_identity=_freeze(payload["paper_identity"]),
        network_facts=_freeze(payload["network_facts"]),
        output=_freeze(payload["output"]),
    )


def _identity_value(expected: object, name: str) -> object:
    if isinstance(expected, Mapping):
        return expected.get(name)
    return getattr(expected, name, None)


def _nested_utc(value: object) -> datetime | None:
    try:
        return _parse_utc(value, "nested")
    except ReceiptValidationError:
        return None


def _exact_keys(value: Mapping[str, object], expected: set[str]) -> bool:
    return set(value) == expected


def _evaluate_predicates(
    receipt: AuditorGateV2Receipt, expected_paper_identity: object, now: datetime
) -> list[str]:
    reasons: list[str] = []
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        reasons.append("NOW_NOT_UTC")
    elif receipt.completed_at_utc > now:
        reasons.append("RECEIPT_FROM_FUTURE")
    elif now - receipt.completed_at_utc > RECEIPT_MAX_AGE:
        reasons.append("RECEIPT_STALE")
    if receipt.effective_sid != EXPECTED_AUDITOR_SID:
        reasons.append("AUDITOR_SID_MISMATCH")
    if receipt.token_elevated is not False:
        reasons.append("AUDITOR_TOKEN_ELEVATED")
    if receipt.separate_process is not True:
        reasons.append("AUDITOR_SEPARATE_PROCESS_NOT_PROVEN")

    runtime = receipt.runtime_integrity
    runtime_keys = {
        "status",
        "runtime_manifest_sha256",
        "deployment_manifest_sha256",
        "probe_sha256",
        "probe_manifest_sha256",
        "exact_fileset",
        "verified_at_utc",
        "predicates",
    }
    if not _exact_keys(runtime, runtime_keys):
        reasons.append("RUNTIME_INTEGRITY_SCHEMA_INVALID")
    if runtime.get("status") != "PASS" or runtime.get("exact_fileset") is not True:
        reasons.append("RUNTIME_INTEGRITY_BLOCK")
    predicates = runtime.get("predicates")
    if not isinstance(predicates, Mapping) or set(predicates) != set(
        STRUCTURAL_PREDICATES
    ):
        reasons.append("RUNTIME_CAPABILITY_SET_INVALID")
    elif any(predicates[name] is not False for name in STRUCTURAL_PREDICATES):
        reasons.append("RUNTIME_FORBIDDEN_CAPABILITY_PRESENT")

    rows = receipt.target_validation_matrix
    row_names: list[object] = []
    if len(rows) != len(TARGET_NAMES):
        reasons.append("TARGET_VALIDATION_COUNT_INVALID")
    for row in rows:
        if not isinstance(row, Mapping) or not _exact_keys(
            row, {"run_id", "probe", "valid"}
        ):
            reasons.append("TARGET_VALIDATION_ROW_INVALID")
            continue
        row_names.append(row.get("probe"))
        if row.get("run_id") != receipt.run_id:
            reasons.append("MIXED_RUN_EVIDENCE")
        if row.get("valid") is not True:
            reasons.append("TARGET_VALIDATION_FAILED")
    if set(row_names) != set(TARGET_NAMES) or len(set(row_names)) != len(TARGET_NAMES):
        reasons.append("TARGET_VALIDATION_SET_INVALID")
    if dict(receipt.capability_outcomes) != APPROVED_CAPABILITY_OUTCOMES:
        reasons.append("CAPABILITY_OUTCOMES_INVALID")

    functional = receipt.functional_auditor
    if not _exact_keys(
        functional, {"run_id", "status", "bundle_id", "manifest_sha256"}
    ):
        reasons.append("FUNCTIONAL_AUDITOR_SCHEMA_INVALID")
    if functional.get("run_id") != receipt.run_id:
        reasons.append("MIXED_RUN_EVIDENCE")
    if functional.get("status") != "PASS":
        reasons.append("FUNCTIONAL_AUDITOR_BLOCK")
    for field in ("bundle_id", "manifest_sha256"):
        value = functional.get(field)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            reasons.append("IMMUTABLE_BUNDLE_IDENTITY_INVALID")

    identity = receipt.paper_identity
    identity_keys = {
        "run_id",
        "expected_account_identity_hash",
        "identity_receipt_sha256",
        "environment_reference",
        "broker_session_environment_reference",
        "verified_at_utc",
        "paper_identity_gate",
        "readonly_identity_gate",
        "broker_reconciliation_gate",
        "paper_only",
        "live_allowed",
        "real_money_allowed",
    }
    if not _exact_keys(identity, identity_keys):
        reasons.append("PAPER_IDENTITY_SCHEMA_INVALID")
    if identity.get("run_id") != receipt.run_id:
        reasons.append("MIXED_RUN_EVIDENCE")
    if identity.get("expected_account_identity_hash") != _identity_value(
        expected_paper_identity, "expected_account_hash"
    ):
        reasons.append("PAPER_ACCOUNT_IDENTITY_MISMATCH")
    if identity.get("identity_receipt_sha256") != _identity_value(
        expected_paper_identity, "receipt_sha256"
    ):
        reasons.append("PAPER_IDENTITY_RECEIPT_MISMATCH")
    for gate in (
        "paper_identity_gate",
        "readonly_identity_gate",
        "broker_reconciliation_gate",
    ):
        if identity.get(gate) != "PASS":
            reasons.append("BROKER_DERIVED_PAPER_IDENTITY_BLOCK")
    if (
        identity.get("paper_only") is not True
        or identity.get("live_allowed") is not False
        or identity.get("real_money_allowed") is not False
    ):
        reasons.append("MONTH1_PAPER_SCOPE_INVALID")

    paper_verified = _nested_utc(identity.get("verified_at_utc"))
    runtime_verified = _nested_utc(runtime.get("verified_at_utc"))
    if paper_verified is None or paper_verified > receipt.started_at_utc:
        reasons.append("PAPER_IDENTITY_TIME_INVALID")
    if runtime_verified is None or runtime_verified > receipt.started_at_utc:
        reasons.append("RUNTIME_VERIFICATION_TIME_INVALID")

    network = receipt.network_facts
    expected_network = {
        "AUDITOR_TECHNICAL_SOCKET_REACHABILITY": True,
        "AUDITOR_NETWORK_ISOLATION_REQUIRED": False,
        "AUDITOR_UNAUTHORIZED_RAW_API_PATH_POSSIBLE": True,
        "AUDITOR_COMPROMISE_CONTAINMENT_NOT_CLAIMED": True,
    }
    if not _exact_keys(network, set(expected_network) | {"endpoints"}):
        reasons.append("NETWORK_FACT_SCHEMA_INVALID")
    if any(network.get(key) is not value for key, value in expected_network.items()):
        reasons.append("NETWORK_FACT_MISMATCH")
    if not isinstance(network.get("endpoints"), Mapping):
        reasons.append("NETWORK_ENDPOINT_EVIDENCE_INVALID")

    output = receipt.output
    if not _exact_keys(
        output,
        {"run_id", "report_path", "created", "report_sha256", "evidence_origin"},
    ):
        reasons.append("OUTPUT_SCHEMA_INVALID")
    if output.get("run_id") != receipt.run_id:
        reasons.append("MIXED_RUN_EVIDENCE")
    if output.get("created") is not True or output.get("evidence_origin") != (
        "REAL_RESTRICTED_TOKEN"
    ):
        reasons.append("REAL_REPORT_OUTPUT_NOT_PROVEN")
    report_hash = output.get("report_sha256")
    if not isinstance(report_hash, str) or not _SHA256_RE.fullmatch(report_hash):
        reasons.append("REPORT_HASH_INVALID")
    report_path = output.get("report_path")
    if not isinstance(report_path, str) or not report_path:
        reasons.append("REPORT_PATH_INVALID")

    return list(dict.fromkeys(reasons))


def evaluate_auditor_gate_v2(
    receipt: AuditorGateV2Receipt,
    expected_paper_identity: object,
    now: datetime,
) -> AuditorGateV2Evaluation:
    reasons = tuple(_evaluate_predicates(receipt, expected_paper_identity, now))
    status = "PASS" if not reasons else "BLOCK"
    return AuditorGateV2Evaluation(
        canonical_gate=status,
        compatibility_gate=status,
        gate_version="V2",
        reason_codes=reasons,
    )
