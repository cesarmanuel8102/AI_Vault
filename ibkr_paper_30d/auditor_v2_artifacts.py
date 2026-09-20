from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .auditor_gate_v2 import AuditorGateV2Evaluation, AuditorGateV2Receipt
from .canonical import canonical_bytes, sha256_json


class ArtifactValidationError(ValueError):
    """Raised when operational V2 evidence is unsafe to materialize."""


_ACCOUNT_RE = re.compile(rb"\bDU[0-9]{4,}\b", re.IGNORECASE)
_EXPIRATION_TRIGGERS = (
    "PAPER_ACCOUNT_IDENTITY_CHANGE",
    "PAPER_IDENTITY_RECEIPT_MATERIAL_CHANGE",
    "BROKER_ENVIRONMENT_CHANGE",
    "PAPER_ONLY_FALSE",
    "LIVE_OR_REAL_MONEY_ENABLEMENT",
    "AUDITOR_RUNTIME_OR_PRIVILEGE_BOUNDARY_MATERIAL_CHANGE",
    "MONTH1_EXPERIMENT_COMPLETION_OR_TERMINATION",
)


def _thaw(value: object) -> object:
    if isinstance(value, (dict, MappingProxyType)):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(child) for child in value]
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return value


def _receipt_projection(receipt: AuditorGateV2Receipt) -> dict[str, object]:
    return {
        "schema": receipt.schema,
        "gate_version": receipt.gate_version,
        "run_id": receipt.run_id,
        "started_at_utc": _thaw(receipt.started_at_utc),
        "completed_at_utc": _thaw(receipt.completed_at_utc),
        "effective_sid": receipt.effective_sid,
        "token_elevated": receipt.token_elevated,
        "separate_process": receipt.separate_process,
        "runtime_integrity": _thaw(receipt.runtime_integrity),
        "target_validation_matrix": _thaw(receipt.target_validation_matrix),
        "capability_outcomes": _thaw(receipt.capability_outcomes),
        "functional_auditor": _thaw(receipt.functional_auditor),
        "paper_identity": _thaw(receipt.paper_identity),
        "network_facts": _thaw(receipt.network_facts),
        "output": _thaw(receipt.output),
    }


def build_residual_risk_acceptance(
    receipt: AuditorGateV2Receipt,
    evaluation: AuditorGateV2Evaluation,
    owner_decision: Mapping[str, object],
) -> dict[str, object]:
    if evaluation.canonical_gate != "PASS" or evaluation.compatibility_gate != "PASS":
        raise ArtifactValidationError("REAL_RECEIPT_REQUIRED")
    if receipt.output.get("evidence_origin") != "REAL_RESTRICTED_TOKEN":
        raise ArtifactValidationError("REAL_RECEIPT_REQUIRED")

    identity = receipt.paper_identity
    if (
        identity.get("paper_only") is not True
        or identity.get("live_allowed") is not False
        or identity.get("real_money_allowed") is not False
    ):
        raise ArtifactValidationError("MONTH1_PAPER_SCOPE_INVALID")
    network = receipt.network_facts
    expected_network = {
        "AUDITOR_TECHNICAL_SOCKET_REACHABILITY": True,
        "AUDITOR_NETWORK_ISOLATION_REQUIRED": False,
        "AUDITOR_UNAUTHORIZED_RAW_API_PATH_POSSIBLE": True,
        "AUDITOR_COMPROMISE_CONTAINMENT_NOT_CLAIMED": True,
    }
    if any(network.get(key) is not value for key, value in expected_network.items()):
        raise ArtifactValidationError("NETWORK_RESIDUAL_RISK_INVALID")

    receipt_projection = _receipt_projection(receipt)
    body: dict[str, object] = {
        "schema": "AUDITOR_MONTH1_PAPER_RESIDUAL_RISK_ACCEPTANCE_V1",
        "scope": "MONTH1_PAPER_ONLY",
        "AUDITOR_SID": receipt.effective_sid,
        "EXPECTED_PAPER_ACCOUNT_IDENTITY_HASH": identity.get(
            "expected_account_identity_hash"
        ),
        "PAPER_IDENTITY_RECEIPT_SHA256": identity.get("identity_receipt_sha256"),
        "PAPER_ENVIRONMENT_REFERENCE": identity.get("environment_reference"),
        "BROKER_SESSION_ENVIRONMENT_REFERENCE": identity.get(
            "broker_session_environment_reference"
        ),
        "PAPER_IDENTITY_VERIFIED_AT_UTC": identity.get("verified_at_utc"),
        "PAPER_ONLY": True,
        "LIVE_ALLOWED": False,
        "REAL_MONEY_ALLOWED": False,
        **expected_network,
        "AUDITOR_ORDER_AUTHORITY_GRANTED": False,
        "AUDITOR_BROKER_CONTROL_PATH_AUTHORIZED": False,
        "APPROVED_RUNTIME_STRUCTURAL_PREDICATES": dict(
            receipt.runtime_integrity.get("predicates", {})
        ),
        "NETWORK_ENDPOINT_OBSERVATIONS": dict(network.get("endpoints", {})),
        "AUDITOR_V2_RECEIPT_CANONICAL_SHA256": sha256_json(receipt_projection),
        "RUNTIME_MANIFEST_SHA256": receipt.runtime_integrity.get(
            "runtime_manifest_sha256"
        ),
        "DEPLOYMENT_MANIFEST_SHA256": receipt.runtime_integrity.get(
            "deployment_manifest_sha256"
        ),
        "EXPIRATION_TRIGGERS": list(_EXPIRATION_TRIGGERS),
        "OWNER_DECISION": dict(owner_decision),
        "RISK_STATEMENT": (
            "The authenticated local IB Gateway may technically accept another "
            "local API client."
        ),
    }
    encoded = canonical_bytes(body)
    if _ACCOUNT_RE.search(encoded):
        raise ArtifactValidationError("CLEARTEXT_ACCOUNT_ID_REJECTED")
    return {**body, "ARTIFACT_SHA256": sha256_json(body)}


def write_immutable_json(path: Path | str, payload: Mapping[str, object]) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_bytes(dict(payload))
    if _ACCOUNT_RE.search(data):
        raise ArtifactValidationError("CLEARTEXT_ACCOUNT_ID_REJECTED")
    with destination.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(data).hexdigest()


def verify_immutable_json(path: Path | str, expected_sha256: str) -> bool:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return False
    return hashlib.sha256(data).hexdigest() == expected_sha256
