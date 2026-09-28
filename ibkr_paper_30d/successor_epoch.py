"""Append-only successor definitions and verified epoch-graph projection."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from .canonical import sha256_json
from .experiment_epoch import EpochDefinition, EpochError
from .persistence import Database
from .repositories import EventRepository
from .successor_clock import SuccessorClockError, clock_for_epoch
from .successor_clock import BrokerTimeObservation, SuccessorClockStore
from .successor_schema import verify_successor_schema_v2

SUCCESSOR_DEFINITION_SCHEMA = "AUTONOMY_EXPERIMENT_SUCCESSOR_DEFINITION_V2"
SUCCESSOR_ACTIVATION_SCHEMA = "AUTONOMY_EXPERIMENT_EPOCH_ACTIVATION_V2"
SUCCESSOR_SUPERSESSION_SCHEMA = "AUTONOMY_EXPERIMENT_EPOCH_SUPERSESSION_V2"
SUCCESSOR_REASON = "PRE_START_RUNTIME_FAILURE"
CLOCK_START_POLICY = "BROKER_SERVER_TIME_AT_AUTHORIZED_LAUNCH"

_EPOCH_ID = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_HEAD = re.compile(r"^[0-9a-f]{40}$")
_OPEN_ORDER_STATUSES = {"PENDINGSUBMIT", "PRESUBMITTED", "SUBMITTED", "PENDINGCANCEL"}


class SuccessorEpochError(EpochError):
    pass


@dataclass(frozen=True)
class SuccessorDefinition:
    epoch_id: str
    predecessor_epoch_id: str
    duration_days: int
    initial_allocation: Decimal
    approved_git_head: str
    definition_sha256: str
    status: str = "PROPOSED"


@dataclass(frozen=True)
class BrokerTransitionEvidence:
    account_identity_sha256: str
    collected_at_utc: datetime
    observation: BrokerTimeObservation
    positions_count: int
    open_orders_count: int
    broker_write_count: int


@dataclass(frozen=True)
class SuccessorTransitionResult:
    epoch_id: str
    definition_sha256: str
    clock_event_sha256: str
    supersession_event_sha256: str
    activation_event_sha256: str
    broker_evidence_sha256: str
    transition_sha256: str
    idempotent: bool


@dataclass(frozen=True)
class _StateRecord:
    event_type: str
    payload: dict[str, Any]
    event_sha256: str
    sequence: int


def _state_records(db: Database) -> list[_StateRecord]:
    records: list[_StateRecord] = []
    for sequence, event_type, payload_json, payload_sha, event_sha in db.execute(
        "SELECT sequence,event_type,payload_json,payload_sha256,event_sha256 "
        "FROM state_events ORDER BY sequence"
    ):
        try:
            payload = json.loads(str(payload_json))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID") from exc
        if not isinstance(payload, dict) or sha256_json(payload) != str(payload_sha):
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        records.append(
            _StateRecord(
                event_type=str(event_type),
                payload=payload,
                event_sha256=str(event_sha),
                sequence=int(sequence),
            )
        )
    return records


def _history_commitment(records: list[_StateRecord]) -> str:
    return sha256_json(
        [
            {
                "sequence": record.sequence,
                "event_type": record.event_type,
                "payload": record.payload,
                "event_sha256": record.event_sha256,
            }
            for record in records
        ]
    )


def _one_record(
    records: list[_StateRecord], event_type: str, epoch_id: str
) -> _StateRecord | None:
    matches = [
        record
        for record in records
        if record.event_type == event_type
        and record.payload.get("epoch_id") == epoch_id
    ]
    if len(matches) > 1:
        raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
    return matches[0] if matches else None


def _definition_records(records: list[_StateRecord]) -> dict[str, _StateRecord]:
    definitions: dict[str, _StateRecord] = {}
    for record in records:
        if record.event_type != "EXPERIMENT_EPOCH_DEFINED":
            continue
        epoch_id = str(record.payload.get("epoch_id") or "")
        if not epoch_id or epoch_id in definitions:
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        unsigned = {
            key: value
            for key, value in record.payload.items()
            if key != "definition_sha256"
        }
        if record.payload.get("definition_sha256") != sha256_json(unsigned):
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        definitions[epoch_id] = record
    return definitions


def _activation_records(records: list[_StateRecord]) -> dict[str, _StateRecord]:
    activations: dict[str, _StateRecord] = {}
    for record in records:
        if record.event_type != "EXPERIMENT_EPOCH_ACTIVATED":
            continue
        epoch_id = str(record.payload.get("epoch_id") or "")
        if not epoch_id or epoch_id in activations:
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        activations[epoch_id] = record
    return activations


def _as_epoch_definition(
    definition: dict[str, Any], activation: dict[str, Any], db: Database
) -> EpochDefinition:
    epoch_id = str(definition["epoch_id"])
    try:
        clock = clock_for_epoch(db, epoch_id)
    except SuccessorClockError as exc:
        raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID") from exc
    if definition.get("schema") == SUCCESSOR_DEFINITION_SCHEMA:
        baseline_state = int(definition["history_event_count"])
    else:
        baseline_state = int(definition["baseline_state_event_count"])
    return EpochDefinition(
        epoch_id=epoch_id,
        status="ACTIVE",
        start_utc=clock.start_utc,
        end_utc=clock.end_utc,
        duration_days=int(definition["duration_days"]),
        initial_allocation=Decimal(str(definition["initial_allocation"])),
        baseline_state_event_count=baseline_state,
        baseline_cycle_count=int(definition["baseline_cycle_count"]),
        baseline_ledger_event_count=int(definition["baseline_ledger_event_count"]),
        previous_state_event_sha256=definition.get("history_terminal_event_sha256")
        or definition.get("previous_state_event_sha256"),
        definition_sha256=str(definition["definition_sha256"]),
        activation_receipt_sha256=str(
            activation.get("activation_receipt_sha256") or ""
        ),
    )


def _validate_successor_definition_record(
    db: Database,
    record: _StateRecord,
    records: list[_StateRecord],
    definitions: dict[str, _StateRecord],
    activations: dict[str, _StateRecord],
) -> None:
    payload = record.payload
    predecessor_id = str(payload.get("predecessor_epoch_id") or "")
    predecessor_definition = definitions.get(predecessor_id)
    predecessor_activation = activations.get(predecessor_id)
    if predecessor_definition is None or predecessor_activation is None:
        raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
    try:
        predecessor_clock = clock_for_epoch(db, predecessor_id)
    except SuccessorClockError as exc:
        raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID") from exc
    prior_records = [item for item in records if item.sequence < record.sequence]
    manifest = _one_record(prior_records, "EPOCH_MANIFEST_CREATED", predecessor_id)
    expected = {
        "predecessor_definition_sha256": predecessor_definition.payload.get(
            "definition_sha256"
        ),
        "predecessor_activation_receipt_sha256": predecessor_activation.payload.get(
            "activation_receipt_sha256"
        ),
        "predecessor_activation_event_sha256": predecessor_activation.event_sha256,
        "predecessor_clock_event_sha256": predecessor_clock.event_sha256,
        "predecessor_manifest_present": manifest is not None,
        "predecessor_manifest_sha256": (
            None if manifest is None else manifest.payload.get("manifest_sha256")
        ),
        "predecessor_manifest_event_sha256": (
            None if manifest is None else manifest.event_sha256
        ),
        "history_event_count": len(prior_records),
        "history_terminal_event_sha256": (
            None if not prior_records else prior_records[-1].event_sha256
        ),
        "history_commitment_sha256": _history_commitment(prior_records),
        "supersession_reason": SUCCESSOR_REASON,
        "clock_start_policy": CLOCK_START_POLICY,
        "owner_activation_required": True,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise SuccessorEpochError("SUCCESSOR_PREDECESSOR_HASH_MISMATCH")


def current_epoch_definition(db: Database) -> EpochDefinition | None:
    """Return the only terminal epoch reached through the verified graph."""

    if not EventRepository(db).verify_chain().valid:
        raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
    records = _state_records(db)
    definitions = _definition_records(records)
    activations = _activation_records(records)
    if not activations:
        return None
    if any(epoch_id not in definitions for epoch_id in activations):
        raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
    for record in definitions.values():
        if record.payload.get("schema") == SUCCESSOR_DEFINITION_SCHEMA:
            _validate_successor_definition_record(
                db, record, records, definitions, activations
            )

    supersessions = [
        record
        for record in records
        if record.event_type == "EXPERIMENT_EPOCH_SUPERSEDED"
    ]
    successor_ids: set[str] = set()
    edges: dict[str, str] = {}
    for edge in supersessions:
        payload = edge.payload
        if payload.get("schema") != SUCCESSOR_SUPERSESSION_SCHEMA:
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        predecessor_id = str(payload.get("predecessor_epoch_id") or "")
        successor_id = str(payload.get("successor_epoch_id") or "")
        if (
            not predecessor_id
            or not successor_id
            or predecessor_id in edges
            or successor_id in successor_ids
        ):
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        predecessor_definition = definitions.get(predecessor_id)
        successor_definition = definitions.get(successor_id)
        predecessor_activation = activations.get(predecessor_id)
        successor_activation = activations.get(successor_id)
        if not all(
            (
                predecessor_definition,
                successor_definition,
                predecessor_activation,
                successor_activation,
            )
        ):
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        successor_payload = successor_definition.payload
        if successor_payload.get("schema") != SUCCESSOR_DEFINITION_SCHEMA:
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        predecessor_clock = clock_for_epoch(db, predecessor_id)
        successor_clock = clock_for_epoch(db, successor_id)
        predecessor_receipt = predecessor_activation.payload.get(
            "activation_receipt_sha256"
        )
        predecessor_bindings = {
            "predecessor_epoch_id": predecessor_id,
            "predecessor_definition_sha256": predecessor_definition.payload.get(
                "definition_sha256"
            ),
            "predecessor_activation_event_sha256": predecessor_activation.event_sha256,
            "predecessor_activation_receipt_sha256": predecessor_receipt,
            "predecessor_clock_event_sha256": predecessor_clock.event_sha256,
        }
        if any(
            payload.get(key) != value or successor_payload.get(key) != value
            for key, value in predecessor_bindings.items()
        ):
            raise SuccessorEpochError("SUCCESSOR_PREDECESSOR_HASH_MISMATCH")
        if (
            payload.get("successor_definition_sha256")
            != successor_payload.get("definition_sha256")
            or payload.get("successor_clock_event_sha256")
            != successor_clock.event_sha256
            or payload.get("reason") != SUCCESSOR_REASON
        ):
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        activation = successor_activation.payload
        if (
            activation.get("schema") != SUCCESSOR_ACTIVATION_SCHEMA
            or activation.get("definition_sha256")
            != successor_payload.get("definition_sha256")
            or activation.get("clock_event_sha256") != successor_clock.event_sha256
            or activation.get("predecessor_epoch_id") != predecessor_id
            or activation.get("supersession_event_sha256") != edge.event_sha256
            or activation.get("approved_git_head")
            != successor_payload.get("approved_git_head")
            or activation.get("owner_authorization_event_id")
            != payload.get("owner_authorization_event_id")
            or activation.get("owner_authorization_receipt_sha256")
            != payload.get("owner_authorization_receipt_sha256")
        ):
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        edges[predecessor_id] = successor_id
        successor_ids.add(successor_id)

    v2_activations = {
        epoch_id
        for epoch_id, record in activations.items()
        if record.payload.get("schema") == SUCCESSOR_ACTIVATION_SCHEMA
    }
    if v2_activations != successor_ids:
        raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
    roots = set(activations) - successor_ids
    if len(roots) != 1:
        raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
    current = next(iter(roots))
    visited: set[str] = set()
    while current in edges:
        if current in visited:
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        visited.add(current)
        current = edges[current]
    visited.add(current)
    if visited != set(activations):
        raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
    return _as_epoch_definition(
        definitions[current].payload, activations[current].payload, db
    )


def _latest_positions_present(db: Database) -> bool:
    row = db.execute(
        "SELECT payload_json,payload_sha256 FROM positions_snapshots "
        "ORDER BY created_at_utc DESC,rowid DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return False
    try:
        payload = json.loads(str(row[0]))
    except json.JSONDecodeError as exc:
        raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID") from exc
    if sha256_json(payload) != str(row[1]):
        raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
    positions = payload.get("positions", []) if isinstance(payload, dict) else []
    if not isinstance(positions, list):
        raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
    for position in positions:
        if not isinstance(position, dict):
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        value = position.get("position", position.get("quantity", "0"))
        try:
            if Decimal(str(value)) != 0:
                return True
        except Exception as exc:
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID") from exc
    return False


def _open_orders_present(db: Database) -> bool:
    return any(
        str(row[0]).upper() in _OPEN_ORDER_STATUSES
        for row in db.execute("SELECT status FROM orders")
    )


class SuccessorEpochStore:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.events = EventRepository(db)

    def preview(
        self,
        *,
        epoch_id: str,
        predecessor_epoch_id: str,
        duration_days: int,
        initial_allocation: Decimal,
        approved_git_head: str,
        objective_sha256: str,
        configuration_sha256: str,
        reason: str,
    ) -> dict[str, Any]:
        verify_successor_schema_v2(self.db)
        if not self.events.verify_chain().valid:
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        if not _EPOCH_ID.fullmatch(epoch_id) or epoch_id == predecessor_epoch_id:
            raise SuccessorEpochError("SUCCESSOR_EPOCH_ID_INVALID")
        if duration_days != 30 or initial_allocation <= 0:
            raise SuccessorEpochError("SUCCESSOR_POLICY_INVALID")
        if reason != SUCCESSOR_REASON:
            raise SuccessorEpochError("SUCCESSOR_REASON_INVALID")
        if not _GIT_HEAD.fullmatch(approved_git_head) or any(
            not _SHA256.fullmatch(value)
            for value in (objective_sha256, configuration_sha256)
        ):
            raise SuccessorEpochError("SUCCESSOR_BINDING_INVALID")
        records = _state_records(self.db)
        definitions = _definition_records(records)
        if epoch_id in definitions:
            raise SuccessorEpochError("SUCCESSOR_ALREADY_DEFINED")
        current = current_epoch_definition(self.db)
        if current is None or current.epoch_id != predecessor_epoch_id:
            raise SuccessorEpochError("SUCCESSOR_PREDECESSOR_NOT_CURRENT")
        predecessor_definition = definitions.get(predecessor_epoch_id)
        predecessor_activation = _one_record(
            records, "EXPERIMENT_EPOCH_ACTIVATED", predecessor_epoch_id
        )
        if predecessor_definition is None or predecessor_activation is None:
            raise SuccessorEpochError("SUCCESSOR_CHAIN_INVALID")
        if any(
            record.event_type == "EPOCH_STARTED"
            and record.payload.get("epoch_id") == predecessor_epoch_id
            for record in records
        ):
            raise SuccessorEpochError("SUCCESSOR_NOT_ALLOWED_AFTER_EPOCH_STARTED")

        predecessor_payload = predecessor_definition.payload
        baseline_cycles = int(predecessor_payload.get("baseline_cycle_count", 0))
        baseline_ledger = int(predecessor_payload.get("baseline_ledger_event_count", 0))
        baseline_orders = int(
            predecessor_payload.get("baseline_order_registry_count", 0)
        )
        order_count = int(
            self.db.execute(
                "SELECT COUNT(*) FROM experiment_order_registry"
            ).fetchone()[0]
        )
        if order_count > baseline_orders:
            raise SuccessorEpochError("SUCCESSOR_BROKER_WRITES_PRESENT")
        if _latest_positions_present(self.db):
            raise SuccessorEpochError("SUCCESSOR_OPEN_POSITION_PRESENT")
        if _open_orders_present(self.db):
            raise SuccessorEpochError("SUCCESSOR_OPEN_ORDER_PRESENT")
        cycle_count = int(
            self.db.execute("SELECT COUNT(*) FROM trader_input_bundles").fetchone()[0]
        )
        ledger_count = int(
            self.db.execute("SELECT COUNT(*) FROM autonomous_ledger_events").fetchone()[
                0
            ]
        )
        if cycle_count > baseline_cycles or ledger_count > baseline_ledger:
            raise SuccessorEpochError("SUCCESSOR_RUNTIME_ACTIVITY_PRESENT")

        clock = clock_for_epoch(self.db, predecessor_epoch_id)
        manifest = _one_record(records, "EPOCH_MANIFEST_CREATED", predecessor_epoch_id)
        history_terminal = records[-1].event_sha256 if records else None
        unsigned = {
            "schema": SUCCESSOR_DEFINITION_SCHEMA,
            "epoch_id": epoch_id,
            "status": "PROPOSED",
            "predecessor_epoch_id": predecessor_epoch_id,
            "predecessor_definition_sha256": predecessor_payload["definition_sha256"],
            "predecessor_activation_receipt_sha256": predecessor_activation.payload.get(
                "activation_receipt_sha256"
            ),
            "predecessor_activation_event_sha256": predecessor_activation.event_sha256,
            "predecessor_clock_event_sha256": clock.event_sha256,
            "predecessor_manifest_present": manifest is not None,
            "predecessor_manifest_sha256": (
                None if manifest is None else manifest.payload.get("manifest_sha256")
            ),
            "predecessor_manifest_event_sha256": (
                None if manifest is None else manifest.event_sha256
            ),
            "supersession_reason": reason,
            "duration_days": duration_days,
            "initial_allocation": str(initial_allocation),
            "approved_git_head": approved_git_head,
            "objective_sha256": objective_sha256,
            "configuration_sha256": configuration_sha256,
            "history_event_count": len(records),
            "history_terminal_event_sha256": history_terminal,
            "history_commitment_sha256": _history_commitment(records),
            "baseline_cycle_count": cycle_count,
            "baseline_ledger_event_count": ledger_count,
            "baseline_order_registry_count": order_count,
            "owner_activation_required": True,
            "clock_start_policy": CLOCK_START_POLICY,
        }
        return {**unsigned, "definition_sha256": sha256_json(unsigned)}

    def define(self, preview: dict[str, Any]) -> SuccessorDefinition:
        if not isinstance(preview, dict):
            raise SuccessorEpochError("SUCCESSOR_DEFINITION_INVALID")
        unsigned = {
            key: value for key, value in preview.items() if key != "definition_sha256"
        }
        if preview.get("schema") != SUCCESSOR_DEFINITION_SCHEMA or preview.get(
            "definition_sha256"
        ) != sha256_json(unsigned):
            raise SuccessorEpochError("SUCCESSOR_DEFINITION_INVALID")
        current = self.preview(
            epoch_id=str(preview["epoch_id"]),
            predecessor_epoch_id=str(preview["predecessor_epoch_id"]),
            duration_days=int(preview["duration_days"]),
            initial_allocation=Decimal(str(preview["initial_allocation"])),
            approved_git_head=str(preview["approved_git_head"]),
            objective_sha256=str(preview["objective_sha256"]),
            configuration_sha256=str(preview["configuration_sha256"]),
            reason=str(preview["supersession_reason"]),
        )
        if current != preview:
            raise SuccessorEpochError("SUCCESSOR_BASELINE_CHANGED")
        with self.db.transaction():
            self.events.append("EXPERIMENT_EPOCH_DEFINED", preview)
        return SuccessorDefinition(
            epoch_id=str(preview["epoch_id"]),
            predecessor_epoch_id=str(preview["predecessor_epoch_id"]),
            duration_days=int(preview["duration_days"]),
            initial_allocation=Decimal(str(preview["initial_allocation"])),
            approved_git_head=str(preview["approved_git_head"]),
            definition_sha256=str(preview["definition_sha256"]),
        )

    def definition(self, epoch_id: str) -> dict[str, Any]:
        records = _state_records(self.db)
        record = _definition_records(records).get(epoch_id)
        if (
            record is None
            or record.payload.get("schema") != SUCCESSOR_DEFINITION_SCHEMA
        ):
            raise SuccessorEpochError("SUCCESSOR_DEFINITION_MISSING")
        return dict(record.payload)

    def validate_transition_eligibility(
        self, epoch_id: str, definition_sha256: str
    ) -> dict[str, Any]:
        definition = self.definition(epoch_id)
        if definition.get("definition_sha256") != definition_sha256:
            raise SuccessorEpochError("SUCCESSOR_DEFINITION_HASH_MISMATCH")
        current = current_epoch_definition(self.db)
        if current is None or current.epoch_id != definition.get(
            "predecessor_epoch_id"
        ):
            raise SuccessorEpochError("SUCCESSOR_PREDECESSOR_NOT_CURRENT")
        records = _state_records(self.db)
        if any(
            record.event_type == "EPOCH_STARTED"
            and record.payload.get("epoch_id") == current.epoch_id
            for record in records
        ):
            raise SuccessorEpochError("SUCCESSOR_NOT_ALLOWED_AFTER_EPOCH_STARTED")
        cycle_count = int(
            self.db.execute("SELECT COUNT(*) FROM trader_input_bundles").fetchone()[0]
        )
        ledger_count = int(
            self.db.execute("SELECT COUNT(*) FROM autonomous_ledger_events").fetchone()[
                0
            ]
        )
        order_count = int(
            self.db.execute(
                "SELECT COUNT(*) FROM experiment_order_registry"
            ).fetchone()[0]
        )
        if order_count != int(definition["baseline_order_registry_count"]):
            raise SuccessorEpochError("SUCCESSOR_BROKER_WRITES_PRESENT")
        if cycle_count != int(
            definition["baseline_cycle_count"]
        ) or ledger_count != int(definition["baseline_ledger_event_count"]):
            raise SuccessorEpochError("SUCCESSOR_RUNTIME_ACTIVITY_PRESENT")
        if _latest_positions_present(self.db):
            raise SuccessorEpochError("SUCCESSOR_OPEN_POSITION_PRESENT")
        if _open_orders_present(self.db):
            raise SuccessorEpochError("SUCCESSOR_OPEN_ORDER_PRESENT")
        return definition


def _parse_transition_time(value: datetime | str) -> datetime:
    try:
        parsed = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        )
    except (TypeError, ValueError) as exc:
        raise SuccessorEpochError("BROKER_EVIDENCE_TIME_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SuccessorEpochError("BROKER_EVIDENCE_TIME_INVALID")
    return parsed.astimezone(timezone.utc)


def _format_transition_time(value: datetime | str) -> str:
    return _parse_transition_time(value).isoformat().replace("+00:00", "Z")


def _canonical_broker_evidence(
    evidence: BrokerTransitionEvidence,
    *,
    launch_attempt_id: str,
    target_epoch_id: str,
    target_definition_sha256: str,
) -> tuple[dict[str, Any], str]:
    if not launch_attempt_id.strip():
        raise SuccessorEpochError("LAUNCH_ATTEMPT_ID_INVALID")
    if not _SHA256.fullmatch(evidence.account_identity_sha256):
        raise SuccessorEpochError("BROKER_ACCOUNT_IDENTITY_HASH_INVALID")
    if (
        min(
            evidence.positions_count,
            evidence.open_orders_count,
            evidence.broker_write_count,
        )
        < 0
    ):
        raise SuccessorEpochError("BROKER_EVIDENCE_INVALID")
    payload = {
        "schema": "SUCCESSOR_TRANSITION_BROKER_EVIDENCE_V1",
        "launch_attempt_id": launch_attempt_id,
        "target_successor_epoch_id": target_epoch_id,
        "target_successor_definition_sha256": target_definition_sha256,
        "account_identity_sha256": evidence.account_identity_sha256,
        "collected_at_utc": _format_transition_time(evidence.collected_at_utc),
        "server_time_utc": _format_transition_time(
            evidence.observation.server_time_utc
        ),
        "observed_at_utc": _format_transition_time(
            evidence.observation.observed_at_utc
        ),
        "authenticated": evidence.observation.authenticated,
        "paper_session": evidence.observation.paper_session,
        "positions_count": evidence.positions_count,
        "open_orders_count": evidence.open_orders_count,
        "broker_write_count": evidence.broker_write_count,
    }
    if payload["collected_at_utc"] != payload["observed_at_utc"]:
        raise SuccessorEpochError("BROKER_EVIDENCE_TIME_INVALID")
    return payload, sha256_json(payload)


def _verify_broker_evidence_freshness(
    payload: dict[str, Any], now_utc: datetime, *, max_age_seconds: float = 30.0
) -> None:
    age = (
        _parse_transition_time(now_utc)
        - _parse_transition_time(str(payload["collected_at_utc"]))
    ).total_seconds()
    if age < -5.0:
        raise SuccessorEpochError("BROKER_EVIDENCE_FUTURE_SKEW")
    if age > max_age_seconds:
        raise SuccessorEpochError("BROKER_EVIDENCE_STALE")


def _transition_hash(clock_sha: str, supersession_sha: str, activation_sha: str) -> str:
    return sha256_json(
        {
            "clock_event_sha256": clock_sha,
            "supersession_event_sha256": supersession_sha,
            "activation_event_sha256": activation_sha,
        }
    )


def _existing_transition(
    db: Database,
    *,
    epoch_id: str,
    definition_sha256: str,
    launch_attempt_id: str,
    owner_receipt: dict[str, Any],
    broker_evidence_sha256: str,
) -> SuccessorTransitionResult | None:
    clock_row = db.execute(
        "SELECT payload_json,event_sha256 FROM experiment_epoch_clock_events_v2 "
        "WHERE experiment_id='ibkr-paper-30d' AND epoch_id=? AND event_type='START'",
        (epoch_id,),
    ).fetchone()
    supersessions: list[_StateRecord] = []
    activations: list[_StateRecord] = []
    for record in _state_records(db):
        if (
            record.event_type == "EXPERIMENT_EPOCH_SUPERSEDED"
            and record.payload.get("successor_epoch_id") == epoch_id
        ):
            supersessions.append(record)
        if (
            record.event_type == "EXPERIMENT_EPOCH_ACTIVATED"
            and record.payload.get("schema") == SUCCESSOR_ACTIVATION_SCHEMA
            and record.payload.get("epoch_id") == epoch_id
        ):
            activations.append(record)
    if not (clock_row or supersessions or activations):
        return None
    if clock_row is None or len(supersessions) != 1 or len(activations) != 1:
        raise SuccessorEpochError("SUCCESSOR_TRANSITION_PARTIAL")
    try:
        clock_payload = json.loads(str(clock_row[0]))
    except json.JSONDecodeError as exc:
        raise SuccessorEpochError("SUCCESSOR_TRANSITION_INVALID") from exc
    supersession = supersessions[0]
    activation = activations[0]
    definition = SuccessorEpochStore(db).definition(epoch_id)
    current = current_epoch_definition(db)
    receipt_sha = owner_receipt.get("receipt_sha256")
    if (
        current is None
        or current.epoch_id != epoch_id
        or definition.get("definition_sha256") != definition_sha256
        or clock_payload.get("definition_sha256") != definition_sha256
        or clock_payload.get("approved_git_head") != definition.get("approved_git_head")
        or clock_payload.get("launch_attempt_id") != launch_attempt_id
        or clock_payload.get("broker_evidence_sha256") != broker_evidence_sha256
        or clock_payload.get("owner_authorization_event_id")
        != owner_receipt.get("authorization_event_id")
        or clock_payload.get("owner_authorization_receipt_sha256") != receipt_sha
        or supersession.payload.get("predecessor_epoch_id")
        != definition.get("predecessor_epoch_id")
        or supersession.payload.get("predecessor_definition_sha256")
        != definition.get("predecessor_definition_sha256")
        or supersession.payload.get("successor_definition_sha256") != definition_sha256
        or supersession.payload.get("successor_clock_event_sha256") != str(clock_row[1])
        or supersession.payload.get("owner_authorization_event_id")
        != owner_receipt.get("authorization_event_id")
        or supersession.payload.get("owner_authorization_receipt_sha256") != receipt_sha
        or activation.payload.get("supersession_event_sha256")
        != supersession.event_sha256
        or activation.payload.get("clock_event_sha256") != str(clock_row[1])
        or activation.payload.get("definition_sha256") != definition_sha256
    ):
        raise SuccessorEpochError("SUCCESSOR_TRANSITION_CONFLICT")
    clock_sha = str(clock_row[1])
    return SuccessorTransitionResult(
        epoch_id=epoch_id,
        definition_sha256=definition_sha256,
        clock_event_sha256=clock_sha,
        supersession_event_sha256=supersession.event_sha256,
        activation_event_sha256=activation.event_sha256,
        broker_evidence_sha256=broker_evidence_sha256,
        transition_sha256=_transition_hash(
            clock_sha, supersession.event_sha256, activation.event_sha256
        ),
        idempotent=True,
    )


def commit_successor_transition(
    *,
    db: Database,
    launch_attempt_id: str,
    target_successor_epoch_id: str,
    target_successor_definition_sha256: str,
    expected_account_identity_sha256: str,
    expected_owner_sid: str,
    owner_authorization_receipt: dict[str, Any],
    execution_lock_verifier: Callable[[], bool],
    broker_evidence_collector: Callable[[], BrokerTransitionEvidence],
    now_utc: Callable[[], datetime],
    after_evidence_collected: Callable[[BrokerTransitionEvidence], None] | None = None,
) -> SuccessorTransitionResult:
    """Collect broker evidence outside SQLite, then commit one atomic edge."""

    if db.connection.in_transaction:
        raise SuccessorEpochError("BROKER_EVIDENCE_COLLECTION_TRANSACTION_ACTIVE")
    if execution_lock_verifier() is not True:
        raise SuccessorEpochError("EXECUTION_LOCK_NOT_VERIFIED")
    evidence = broker_evidence_collector()
    if db.connection.in_transaction:
        raise SuccessorEpochError("BROKER_NETWORK_IO_INSIDE_WRITE_TRANSACTION")
    evidence_payload, evidence_sha = _canonical_broker_evidence(
        evidence,
        launch_attempt_id=launch_attempt_id,
        target_epoch_id=target_successor_epoch_id,
        target_definition_sha256=target_successor_definition_sha256,
    )
    if evidence.account_identity_sha256 != expected_account_identity_sha256:
        raise SuccessorEpochError("BROKER_ACCOUNT_IDENTITY_MISMATCH")
    if evidence.positions_count:
        raise SuccessorEpochError("SUCCESSOR_OPEN_POSITION_PRESENT")
    if evidence.open_orders_count:
        raise SuccessorEpochError("SUCCESSOR_OPEN_ORDER_PRESENT")
    if evidence.broker_write_count:
        raise SuccessorEpochError("SUCCESSOR_BROKER_WRITES_PRESENT")
    _verify_broker_evidence_freshness(evidence_payload, now_utc())
    if after_evidence_collected is not None:
        after_evidence_collected(evidence)

    from .successor_authorization import (
        SuccessorAuthorizationError,
        validate_successor_authorization_record,
    )

    try:
        with db.transaction():
            verify_successor_schema_v2(db)
            if execution_lock_verifier() is not True:
                raise SuccessorEpochError("EXECUTION_LOCK_NOT_VERIFIED")
            rebuilt_payload, rebuilt_sha = _canonical_broker_evidence(
                evidence,
                launch_attempt_id=launch_attempt_id,
                target_epoch_id=target_successor_epoch_id,
                target_definition_sha256=target_successor_definition_sha256,
            )
            if rebuilt_payload != evidence_payload or rebuilt_sha != evidence_sha:
                raise SuccessorEpochError("BROKER_EVIDENCE_HASH_MISMATCH")
            _verify_broker_evidence_freshness(evidence_payload, now_utc())
            existing = _existing_transition(
                db,
                epoch_id=target_successor_epoch_id,
                definition_sha256=target_successor_definition_sha256,
                launch_attempt_id=launch_attempt_id,
                owner_receipt=owner_authorization_receipt,
                broker_evidence_sha256=evidence_sha,
            )
            if existing is not None:
                validate_successor_authorization_record(
                    db=db,
                    epoch_id=target_successor_epoch_id,
                    definition_sha256=target_successor_definition_sha256,
                    expected_actor_sid=expected_owner_sid,
                    receipt=owner_authorization_receipt,
                )
                return existing
            definition = SuccessorEpochStore(db).validate_transition_eligibility(
                target_successor_epoch_id,
                target_successor_definition_sha256,
            )
            authorization = validate_successor_authorization_record(
                db=db,
                epoch_id=target_successor_epoch_id,
                definition_sha256=target_successor_definition_sha256,
                expected_actor_sid=expected_owner_sid,
                receipt=owner_authorization_receipt,
            )
            clock = SuccessorClockStore(db).start(
                epoch_id=target_successor_epoch_id,
                definition_sha256=target_successor_definition_sha256,
                predecessor_epoch_id=str(definition["predecessor_epoch_id"]),
                predecessor_clock_event_sha256=str(
                    definition["predecessor_clock_event_sha256"]
                ),
                observation=evidence.observation,
                duration_days=int(definition["duration_days"]),
                initial_allocation=Decimal(str(definition["initial_allocation"])),
                approved_git_head=str(definition["approved_git_head"]),
                owner_authorization_event_id=str(
                    authorization["authorization_event_id"]
                ),
                owner_authorization_receipt_sha256=str(authorization["receipt_sha256"]),
                launch_attempt_id=launch_attempt_id,
                account_identity_sha256=expected_account_identity_sha256,
                broker_evidence_sha256=evidence_sha,
                broker_evidence_collected_at_utc=str(
                    evidence_payload["collected_at_utc"]
                ),
            )
            supersession_payload = {
                "schema": SUCCESSOR_SUPERSESSION_SCHEMA,
                "predecessor_epoch_id": definition["predecessor_epoch_id"],
                "predecessor_definition_sha256": definition[
                    "predecessor_definition_sha256"
                ],
                "predecessor_activation_event_sha256": definition[
                    "predecessor_activation_event_sha256"
                ],
                "predecessor_activation_receipt_sha256": definition[
                    "predecessor_activation_receipt_sha256"
                ],
                "predecessor_clock_event_sha256": definition[
                    "predecessor_clock_event_sha256"
                ],
                "successor_epoch_id": target_successor_epoch_id,
                "successor_definition_sha256": target_successor_definition_sha256,
                "successor_clock_event_sha256": clock.event_sha256,
                "reason": definition["supersession_reason"],
                "approved_git_head": definition["approved_git_head"],
                "owner_authorization_event_id": authorization["authorization_event_id"],
                "owner_authorization_receipt_sha256": authorization["receipt_sha256"],
                "launch_attempt_id": launch_attempt_id,
                "broker_evidence_sha256": evidence_sha,
            }
            supersession_id = EventRepository(db).append(
                "EXPERIMENT_EPOCH_SUPERSEDED", supersession_payload
            )
            supersession_sha = str(
                db.execute(
                    "SELECT event_sha256 FROM state_events WHERE event_id=?",
                    (supersession_id,),
                ).fetchone()[0]
            )
            activation_receipt_sha = sha256_json(
                {
                    "definition_sha256": target_successor_definition_sha256,
                    "clock_event_sha256": clock.event_sha256,
                    "supersession_event_sha256": supersession_sha,
                    "owner_authorization_receipt_sha256": authorization[
                        "receipt_sha256"
                    ],
                }
            )
            activation_payload = {
                "schema": SUCCESSOR_ACTIVATION_SCHEMA,
                "epoch_id": target_successor_epoch_id,
                "status": "ACTIVE",
                "definition_sha256": target_successor_definition_sha256,
                "clock_event_sha256": clock.event_sha256,
                "predecessor_epoch_id": definition["predecessor_epoch_id"],
                "supersession_event_sha256": supersession_sha,
                "approved_git_head": definition["approved_git_head"],
                "owner_authorization_event_id": authorization["authorization_event_id"],
                "owner_authorization_receipt_sha256": authorization["receipt_sha256"],
                "activation_receipt_sha256": activation_receipt_sha,
                "launch_attempt_id": launch_attempt_id,
                "broker_evidence_sha256": evidence_sha,
                "activated_at_utc": _format_transition_time(now_utc()),
            }
            activation_id = EventRepository(db).append(
                "EXPERIMENT_EPOCH_ACTIVATED", activation_payload
            )
            activation_sha = str(
                db.execute(
                    "SELECT event_sha256 FROM state_events WHERE event_id=?",
                    (activation_id,),
                ).fetchone()[0]
            )
            verified_current = current_epoch_definition(db)
            if (
                verified_current is None
                or verified_current.epoch_id != target_successor_epoch_id
                or verified_current.definition_sha256
                != target_successor_definition_sha256
            ):
                raise SuccessorEpochError("SUCCESSOR_TRANSITION_VERIFICATION_FAILED")
            if execution_lock_verifier() is not True:
                raise SuccessorEpochError("EXECUTION_LOCK_NOT_VERIFIED")
            _verify_broker_evidence_freshness(evidence_payload, now_utc())
            rebuilt_payload, rebuilt_sha = _canonical_broker_evidence(
                evidence,
                launch_attempt_id=launch_attempt_id,
                target_epoch_id=target_successor_epoch_id,
                target_definition_sha256=target_successor_definition_sha256,
            )
            if rebuilt_payload != evidence_payload or rebuilt_sha != evidence_sha:
                raise SuccessorEpochError("BROKER_EVIDENCE_HASH_MISMATCH")
            return SuccessorTransitionResult(
                epoch_id=target_successor_epoch_id,
                definition_sha256=target_successor_definition_sha256,
                clock_event_sha256=clock.event_sha256,
                supersession_event_sha256=supersession_sha,
                activation_event_sha256=activation_sha,
                broker_evidence_sha256=evidence_sha,
                transition_sha256=_transition_hash(
                    clock.event_sha256, supersession_sha, activation_sha
                ),
                idempotent=False,
            )
    except (SuccessorAuthorizationError, SuccessorClockError) as exc:
        raise SuccessorEpochError(str(exc)) from exc
