from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .canonical import sha256_json
from .types import new_uuid7


REGRET_SCHEMA = "CODEX_REGRET_OBSERVATION_V1"
NO_CANDIDATE_SCHEMA = "CODEX_NO_IDENTIFIABLE_REJECTED_CANDIDATE_V1"

IDENTIFIABLE_CANDIDATE_FIELDS = ("symbol",)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_identifiable_candidate(candidate: dict[str, Any]) -> None:
    if not isinstance(candidate, dict) or not any(
        str(candidate.get(field) or "").strip()
        for field in IDENTIFIABLE_CANDIDATE_FIELDS
    ):
        raise ValueError(
            "a regret record requires an identifiable candidate with at "
            "least a symbol; never fabricate a candidate from a NO_TRADE"
        )


def build_regret_record(
    *,
    decision_cycle_id: str,
    candidate: dict[str, Any],
    ex_ante_evidence: dict[str, Any],
    rejection_reason_codes: tuple[str, ...] | list[str],
    rejection_mechanism: str = "",
    sample_size: int = 1,
    repeated_mechanism: bool = False,
    uncertainty: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an observational regret/counterfactual record.

    Rulings encoded here (user corrections 2026-09-23):
    - U2: sample_size and repeated_mechanism are descriptive fields only.
      No numeric threshold may ever transition policy_status; records are
      born OBSERVATION and only an explicit human/owner review can mark a
      hypothesis as under investigation.
    - U4: an identifiable candidate and real ex-ante evidence are required.
      NO_TRADE cycles without a concrete candidate must never produce a
      fabricated regret record.
    """

    _require_identifiable_candidate(candidate)
    if not ex_ante_evidence:
        raise ValueError(
            "a regret record requires real ex-ante evidence; an empty "
            "evidence snapshot cannot support a counterfactual"
        )
    reasons = [str(code) for code in rejection_reason_codes]
    if not reasons:
        raise ValueError("a regret record requires a real rejection reason")
    return {
        "schema": REGRET_SCHEMA,
        "record_id": f"regret-{new_uuid7()}",
        "decision_cycle_id": str(decision_cycle_id),
        "timestamp_utc": _utc_now(),
        "candidate": dict(candidate),
        "ex_ante_evidence": dict(ex_ante_evidence),
        "ex_ante_evidence_sha256": sha256_json(ex_ante_evidence),
        "rejection_reason_codes": reasons,
        "rejection_mechanism": str(
            rejection_mechanism or "MODEL_DECISION_OR_VALIDATION"
        ),
        "ex_post_outcome": None,
        "ex_post_observed_at_utc": None,
        "sample_size": int(sample_size),
        "repeated_mechanism": bool(repeated_mechanism),
        "uncertainty": dict(
            uncertainty
            or {
                "sample_size_note": (
                    "sample_size and repeated_mechanism are descriptive "
                    "observations; no automatic policy conclusion may be "
                    "drawn from any count"
                ),
                "ex_post_outcome_may_be_unobservable": True,
            }
        ),
        "policy_status": "OBSERVATION",
    }


def observation_without_identifiable_candidate(
    *,
    decision_cycle_id: str,
    reason_codes: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    """Observational note for a NO_TRADE with no concrete rejected candidate.

    This is deliberately NOT a regret record: no candidate is fabricated.
    """

    return {
        "schema": NO_CANDIDATE_SCHEMA,
        "observation_type": "NO_IDENTIFIABLE_REJECTED_CANDIDATE",
        "decision_cycle_id": str(decision_cycle_id),
        "timestamp_utc": _utc_now(),
        "reason_codes": [str(code) for code in reason_codes],
    }


def persist_regret_record(db: Any, record: dict[str, Any]) -> str:
    if record.get("schema") not in {REGRET_SCHEMA, NO_CANDIDATE_SCHEMA}:
        raise ValueError("unknown observation schema for persistence")
    event_id = str(new_uuid7())
    payload = {
        "decision_cycle_id": record.get("decision_cycle_id", ""),
        "invocation_id": "observation-only",
        "observation": record,
    }
    db.execute(
        "INSERT INTO autonomous_research_events("
        "event_id,decision_cycle_id,invocation_id,round_index,event_type,"
        "payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
        (
            event_id,
            str(record.get("decision_cycle_id", "")),
            "observation-only",
            0,
            "regret_observation"
            if record["schema"] == REGRET_SCHEMA
            else "no_identifiable_rejected_candidate",
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            sha256_json(payload),
            _utc_now(),
        ),
    )
    return event_id


def load_regret_records(db_path: Any) -> list[dict[str, Any]]:
    from pathlib import Path

    path = Path(db_path)
    if not path.exists():
        return []
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT payload_json FROM autonomous_research_events "
            "WHERE event_type='regret_observation' ORDER BY created_at_utc, rowid"
        ).fetchall()
    finally:
        connection.close()

    records: list[dict[str, Any]] = []
    for (raw_payload,) in rows:
        try:
            payload = json.loads(str(raw_payload))
        except json.JSONDecodeError:
            continue
        observation = (
            payload.get("observation") if isinstance(payload, dict) else None
        )
        if isinstance(observation, dict):
            records.append(observation)
    return records