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
