"""Append-only experiment epoch definitions and truthful history projection."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

from .canonical import canonical_bytes, sha256_json
from .persistence import Database
from .repositories import EventRepository, utc_now

EPOCH_DEFINITION_SCHEMA = "AUTONOMY_EXPERIMENT_EPOCH_DEFINITION_V1"
EPOCH_ACTIVATION_SCHEMA = "AUTONOMY_EXPERIMENT_EPOCH_ACTIVATION_V1"
OWNER_ACTIVATION_SCHEMA = "OWNER_EPOCH_ACTIVATION_AUTHORIZATION_V1"
_EPOCH_ID = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_HEAD = re.compile(r"^[0-9a-f]{40}$")
AUTONOMY_EPOCH_ID = "AUTONOMY_EPOCH_1"
AUTONOMY_OBJECTIVE = (
    "Maximize terminal experimental PAPER equity over the remaining experiment horizon."
)


class EpochError(RuntimeError):
    pass


def _format(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EpochError("epoch timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EpochError("epoch timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EpochError("epoch timestamp is invalid")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class EpochDefinition:
    epoch_id: str
    status: str
    start_utc: datetime
    end_utc: datetime
    duration_days: int
    initial_allocation: Decimal
    baseline_state_event_count: int
    baseline_cycle_count: int
    baseline_ledger_event_count: int
    previous_state_event_sha256: str | None
    definition_sha256: str
    activation_receipt_sha256: str | None = None


def activation_receipt(
    *,
    epoch_id: str,
    definition_sha256: str,
    owner_authorization_event_id: str,
    approved_git_head: str,
    owner_authorization_receipt_sha256: str,
    issued_at_utc: datetime | None = None,
) -> dict[str, Any]:
    unsigned = {
        "schema": OWNER_ACTIVATION_SCHEMA,
        "state": "AUTHORIZED",
        "actor": "OWNER",
        "epoch_id": epoch_id,
        "definition_sha256": definition_sha256,
        "owner_authorization_event_id": owner_authorization_event_id,
        "approved_git_head": approved_git_head,
        "owner_authorization_receipt_sha256": owner_authorization_receipt_sha256,
        "issued_at_utc": _format(issued_at_utc or datetime.now(timezone.utc)),
    }
    return {**unsigned, "receipt_sha256": sha256_json(unsigned)}


class ExperimentEpochStore:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.events = EventRepository(db)

    def _verify_chain(self) -> None:
        definition_row = self.db.execute(
            "SELECT sequence,payload_json FROM state_events "
            "WHERE event_type='EXPERIMENT_EPOCH_DEFINED' ORDER BY sequence LIMIT 1"
        ).fetchone()
        if definition_row is None:
            return
        try:
            definition = json.loads(str(definition_row[1]))
            baseline_count = int(definition["baseline_state_event_count"])
            expected_legacy_hash = str(definition["legacy_state_events_sha256"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise EpochError(
                "epoch state event chain definition anchor is invalid"
            ) from exc
        if int(definition_row[0]) != baseline_count + 1:
            raise EpochError("epoch definition sequence does not match legacy baseline")
        rows = self._state_event_rows()
        legacy_rows = rows[:baseline_count]
        if (
            len(legacy_rows) != baseline_count
            or self._rows_sha256(legacy_rows) != expected_legacy_hash
        ):
            raise EpochError("pre-epoch history commitment is invalid")

        expected_previous = None if not legacy_rows else str(legacy_rows[-1][6])
        for row in rows[baseline_count:]:
            (
                sequence,
                event_id,
                event_type,
                payload_json,
                payload_sha256,
                previous,
                digest,
                created,
            ) = row
            try:
                payload = json.loads(str(payload_json))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise EpochError(
                    f"epoch state event JSON is invalid at sequence {sequence}"
                ) from exc
            if sha256_json(payload) != str(payload_sha256):
                raise EpochError(
                    f"epoch state event payload is invalid at sequence {sequence}"
                )
            expected = EventRepository._event_hash(
                int(sequence),
                str(event_id),
                str(event_type),
                str(payload_json),
                str(payload_sha256),
                expected_previous,
                str(created),
            )
            if previous != expected_previous or str(digest) != expected:
                raise EpochError(
                    f"epoch state event chain is invalid at sequence {sequence}"
                )
            expected_previous = str(digest)

    def _state_event_rows(self) -> list[tuple[Any, ...]]:
        return [
            tuple(row)
            for row in self.db.execute(
                "SELECT sequence,event_id,event_type,payload_json,payload_sha256,"
                "previous_event_sha256,event_sha256,created_at_utc "
                "FROM state_events ORDER BY sequence"
            ).fetchall()
        ]

    @staticmethod
    def _rows_sha256(rows: list[tuple[Any, ...]]) -> str:
        keys = (
            "sequence",
            "event_id",
            "event_type",
            "payload_json",
            "payload_sha256",
            "previous_event_sha256",
            "event_sha256",
            "created_at_utc",
        )
        return sha256_json([dict(zip(keys, row, strict=True)) for row in rows])

    def _legacy_chain_status(self) -> str:
        return (
            "VERIFIED"
            if self.events.verify_chain().valid
            else "LEGACY_UNVERIFIED_ANCHORED"
        )

    def _count(self, table: str) -> int:
        return int(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def preview(
        self,
        *,
        epoch_id: str,
        start_utc: datetime,
        duration_days: int,
        initial_allocation: Decimal,
        approved_git_head: str,
        owner_authorization_event_id: str,
        owner_authorization_receipt_sha256: str,
        objective_sha256: str,
        configuration_sha256: str,
    ) -> dict[str, Any]:
        self._verify_chain()
        if not _EPOCH_ID.fullmatch(epoch_id):
            raise EpochError("epoch id is invalid")
        if duration_days <= 0 or initial_allocation <= 0:
            raise EpochError("epoch duration and allocation must be positive")
        if not _GIT_HEAD.fullmatch(approved_git_head):
            raise EpochError("approved Git head is invalid")
        if not owner_authorization_event_id.strip():
            raise EpochError("owner authorization event id is invalid")
        for name, digest in (
            ("owner authorization receipt", owner_authorization_receipt_sha256),
            ("objective", objective_sha256),
            ("configuration", configuration_sha256),
        ):
            if not _SHA256.fullmatch(digest):
                raise EpochError(f"{name} SHA-256 is invalid")
        start = _parse(_format(start_utc))
        end = start + timedelta(days=duration_days)
        last = self.db.execute(
            "SELECT event_sha256 FROM state_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        unsigned = {
            "schema": EPOCH_DEFINITION_SCHEMA,
            "epoch_id": epoch_id,
            "status": "PROPOSED",
            "start_utc": _format(start),
            "end_utc": _format(end),
            "duration_days": duration_days,
            "initial_allocation": str(initial_allocation),
            "baseline_state_event_count": self._count("state_events"),
            "baseline_cycle_count": self._count("trader_input_bundles"),
            "baseline_ledger_event_count": self._count("autonomous_ledger_events"),
            "previous_state_event_sha256": None if last is None else str(last[0]),
            "previous_history_classification": "PRE_EPOCH_HISTORY",
            "previous_history_chain_status": self._legacy_chain_status(),
            "legacy_state_events_sha256": self._rows_sha256(self._state_event_rows()),
            "approved_git_head": approved_git_head,
            "owner_authorization_event_id": owner_authorization_event_id,
            "owner_authorization_receipt_sha256": owner_authorization_receipt_sha256,
            "objective_sha256": objective_sha256,
            "configuration_sha256": configuration_sha256,
            "owner_activation_required": True,
        }
        return {**unsigned, "definition_sha256": sha256_json(unsigned)}

    def define(self, preview: dict[str, Any]) -> EpochDefinition:
        self._verify_chain()
        if not isinstance(preview, dict):
            raise EpochError("epoch preview is invalid")
        unsigned = {
            key: value for key, value in preview.items() if key != "definition_sha256"
        }
        if (
            preview.get("schema") != EPOCH_DEFINITION_SCHEMA
            or preview.get("status") != "PROPOSED"
            or preview.get("definition_sha256") != sha256_json(unsigned)
        ):
            raise EpochError("epoch definition hash is invalid")
        if self._definition_payload(str(preview.get("epoch_id"))) is not None:
            raise EpochError("epoch is already defined")
        current_preview = self.preview(
            epoch_id=str(preview["epoch_id"]),
            start_utc=_parse(str(preview["start_utc"])),
            duration_days=int(preview["duration_days"]),
            initial_allocation=Decimal(str(preview["initial_allocation"])),
            approved_git_head=str(preview["approved_git_head"]),
            owner_authorization_event_id=str(preview["owner_authorization_event_id"]),
            owner_authorization_receipt_sha256=str(
                preview["owner_authorization_receipt_sha256"]
            ),
            objective_sha256=str(preview["objective_sha256"]),
            configuration_sha256=str(preview["configuration_sha256"]),
        )
        if current_preview != preview:
            raise EpochError("epoch baseline changed after preview")
        with self.db.transaction():
            self.events.append("EXPERIMENT_EPOCH_DEFINED", preview)
        return self._from_payload(preview)

    def _epoch_rows(self) -> list[tuple[str, dict[str, Any]]]:
        rows = self.db.execute(
            "SELECT event_type,payload_json,payload_sha256 FROM state_events "
            "WHERE event_type IN ('EXPERIMENT_EPOCH_DEFINED','EXPERIMENT_EPOCH_ACTIVATED') "
            "ORDER BY sequence"
        ).fetchall()
        parsed: list[tuple[str, dict[str, Any]]] = []
        for event_type, payload_json, payload_hash in rows:
            try:
                payload = json.loads(str(payload_json))
            except json.JSONDecodeError as exc:
                raise EpochError("epoch event JSON is invalid") from exc
            if not isinstance(payload, dict) or sha256_json(payload) != str(
                payload_hash
            ):
                raise EpochError("epoch event payload hash is invalid")
            parsed.append((str(event_type), payload))
        return parsed

    def _definition_payload(self, epoch_id: str) -> dict[str, Any] | None:
        for event_type, payload in self._epoch_rows():
            if (
                event_type == "EXPERIMENT_EPOCH_DEFINED"
                and payload.get("epoch_id") == epoch_id
            ):
                return payload
        return None

    @staticmethod
    def _from_payload(payload: dict[str, Any]) -> EpochDefinition:
        return EpochDefinition(
            epoch_id=str(payload["epoch_id"]),
            status=str(payload["status"]),
            start_utc=_parse(str(payload["start_utc"])),
            end_utc=_parse(str(payload["end_utc"])),
            duration_days=int(payload["duration_days"]),
            initial_allocation=Decimal(str(payload["initial_allocation"])),
            baseline_state_event_count=int(payload["baseline_state_event_count"]),
            baseline_cycle_count=int(payload["baseline_cycle_count"]),
            baseline_ledger_event_count=int(payload["baseline_ledger_event_count"]),
            previous_state_event_sha256=payload.get("previous_state_event_sha256"),
            definition_sha256=str(payload["definition_sha256"]),
            activation_receipt_sha256=payload.get("activation_receipt_sha256"),
        )

    def activate(self, epoch_id: str, receipt: dict[str, Any]) -> EpochDefinition:
        self._verify_chain()
        definition_payload = self._definition_payload(epoch_id)
        if definition_payload is None:
            raise EpochError("epoch definition is missing")
        if self.current() is not None:
            raise EpochError("an epoch is already active")
        if not isinstance(receipt, dict):
            raise EpochError("owner activation receipt is invalid")
        unsigned = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        if receipt.get("receipt_sha256") != sha256_json(unsigned):
            raise EpochError("owner activation receipt hash is invalid")
        if receipt.get("definition_sha256") != definition_payload["definition_sha256"]:
            raise EpochError("owner activation receipt definition hash mismatch")
        if receipt.get("approved_git_head") != definition_payload.get(
            "approved_git_head"
        ):
            raise EpochError("owner activation receipt Git head mismatch")
        if receipt.get("owner_authorization_receipt_sha256") != definition_payload.get(
            "owner_authorization_receipt_sha256"
        ):
            raise EpochError("owner activation authorization receipt mismatch")
        if (
            receipt.get("schema") != OWNER_ACTIVATION_SCHEMA
            or receipt.get("state") != "AUTHORIZED"
            or receipt.get("actor") != "OWNER"
            or receipt.get("epoch_id") != epoch_id
        ):
            raise EpochError("owner activation receipt is not authorized")
        authorization_id = str(receipt.get("owner_authorization_event_id") or "")
        row = self.db.execute(
            "SELECT state,payload_json,payload_sha256 FROM experiment_authorization_events "
            "WHERE event_id=?",
            (authorization_id,),
        ).fetchone()
        if row is None or str(row[0]) != "AUTHORIZED":
            raise EpochError("owner authorization event is missing")
        try:
            authorization_payload = json.loads(str(row[1]))
        except json.JSONDecodeError as exc:
            raise EpochError("owner authorization event is invalid") from exc
        if sha256_json(authorization_payload) != str(row[2]):
            raise EpochError("owner authorization event hash is invalid")

        payload = {
            "schema": EPOCH_ACTIVATION_SCHEMA,
            "epoch_id": epoch_id,
            "status": "ACTIVE",
            "definition_sha256": definition_payload["definition_sha256"],
            "activation_receipt_sha256": receipt["receipt_sha256"],
            "owner_authorization_event_id": authorization_id,
            "approved_git_head": definition_payload["approved_git_head"],
            "owner_authorization_receipt_sha256": definition_payload[
                "owner_authorization_receipt_sha256"
            ],
            "activated_at_utc": utc_now(),
        }
        with self.db.transaction():
            self.events.append("EXPERIMENT_EPOCH_ACTIVATED", payload)
        return replace(
            self._from_payload(definition_payload),
            status="ACTIVE",
            activation_receipt_sha256=str(receipt["receipt_sha256"]),
        )

    def current(self) -> EpochDefinition | None:
        self._verify_chain()
        successor_evidence = self.db.execute(
            "SELECT 1 FROM state_events WHERE "
            "event_type='EXPERIMENT_EPOCH_SUPERSEDED' OR "
            "json_extract(payload_json,'$.schema') IN ("
            "'AUTONOMY_EXPERIMENT_SUCCESSOR_DEFINITION_V2',"
            "'AUTONOMY_EXPERIMENT_EPOCH_ACTIVATION_V2') LIMIT 1"
        ).fetchone()
        if successor_evidence is not None:
            from .successor_epoch import current_epoch_definition

            return current_epoch_definition(self.db)
        rows = self._epoch_rows()
        activations = [
            payload for kind, payload in rows if kind == "EXPERIMENT_EPOCH_ACTIVATED"
        ]
        if not activations:
            return None
        if len(activations) != 1:
            raise EpochError("multiple active epoch events are invalid")
        activation = activations[0]
        definition = self._definition_payload(str(activation.get("epoch_id")))
        if definition is None or activation.get("definition_sha256") != definition.get(
            "definition_sha256"
        ):
            raise EpochError("active epoch is not bound to its definition")
        return replace(
            self._from_payload(definition),
            status="ACTIVE",
            activation_receipt_sha256=str(activation["activation_receipt_sha256"]),
        )

    def projection(self, now_utc: datetime) -> dict[str, Any]:
        now = _parse(_format(now_utc))
        active = self.current()
        total_cycles = self._count("trader_input_bundles")
        total_ledger = self._count("autonomous_ledger_events")
        if active is None:
            return {
                "state": "PRE_EPOCH_HISTORY",
                "epoch_id": None,
                "activation_required": True,
                "historical_cycle_count": total_cycles,
                "historical_ledger_event_count": total_ledger,
                "previous_history_classification": "PRE_EPOCH_HISTORY",
                "previous_history_chain_status": self._legacy_chain_status(),
                "legacy_state_events_sha256": self._rows_sha256(
                    self._state_event_rows()
                ),
            }
        remaining = max((active.end_utc - now).total_seconds(), 0.0)
        elapsed = max((now - active.start_utc).total_seconds(), 0.0)
        return {
            "state": "ACTIVE",
            "epoch_id": active.epoch_id,
            "activation_required": False,
            "start_utc": _format(active.start_utc),
            "end_utc": _format(active.end_utc),
            "now_utc": _format(now),
            "duration_days": active.duration_days,
            "elapsed_days": elapsed / 86400.0,
            "remaining_days": remaining / 86400.0,
            "remaining_seconds": remaining,
            "not_started": now < active.start_utc,
            "expired": remaining <= 0,
            "cycle_count": max(total_cycles - active.baseline_cycle_count, 0),
            "ledger_event_count": max(
                total_ledger - active.baseline_ledger_event_count, 0
            ),
            "historical_cycle_count": active.baseline_cycle_count,
            "historical_ledger_event_count": active.baseline_ledger_event_count,
            "previous_history_classification": "PRE_EPOCH_HISTORY",
            "definition_sha256": active.definition_sha256,
            "activation_receipt_sha256": active.activation_receipt_sha256,
        }


def _assert_database_integrity(db: Database) -> None:
    try:
        result = [
            str(row[0]) for row in db.execute("PRAGMA integrity_check").fetchall()
        ]
    except Exception as exc:
        raise EpochError("DATABASE_INTEGRITY_BLOCK") from exc
    if result != ["ok"]:
        raise EpochError("DATABASE_INTEGRITY_BLOCK")


def _definition_bindings(
    *,
    epoch_id: str,
    approved_git_head: str,
    owner_authorization_event_id: str,
    owner_authorization_receipt_sha256: str,
    objective_sha256: str,
    configuration_sha256: str,
) -> dict[str, Any]:
    return {
        "epoch_id": epoch_id,
        "approved_git_head": approved_git_head,
        "previous_history_classification": "PRE_EPOCH_HISTORY",
        "owner_authorization_event_id": owner_authorization_event_id,
        "owner_authorization_receipt_sha256": owner_authorization_receipt_sha256,
        "objective_sha256": objective_sha256,
        "configuration_sha256": configuration_sha256,
        "owner_activation_required": True,
    }


def _validate_definition_bindings(
    payload: dict[str, Any], expected: dict[str, Any]
) -> None:
    if any(payload.get(key) != value for key, value in expected.items()):
        raise EpochError("CONFLICTING_EPOCH_ACTIVATION")


def activate_epoch_transition(
    db: Database,
    *,
    epoch_id: str,
    start_utc: datetime,
    duration_days: int,
    initial_allocation: Decimal,
    approved_git_head: str,
    observed_git_head: str,
    owner_authorization_receipt: dict[str, Any],
    owner_authorization_receipt_sha256: str,
    objective_sha256: str,
    configuration_sha256: str,
    kernel_status: str,
    runtime_provenance_status: str,
    activated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    """Define and activate one exact epoch before scheduler authority is granted."""

    _assert_database_integrity(db)
    if (
        not _GIT_HEAD.fullmatch(approved_git_head)
        or observed_git_head != approved_git_head
    ):
        raise EpochError("APPROVED_HEAD_MISMATCH")
    if kernel_status != "PASS":
        raise EpochError("KERNEL_BLOCK")
    if runtime_provenance_status != "PASS":
        raise EpochError("RUNTIME_PROVENANCE_BLOCK")
    if not isinstance(owner_authorization_receipt, dict):
        raise EpochError("OWNER_AUTHORIZATION_INVALID")
    authorization_event_id = str(
        owner_authorization_receipt.get("authorization_event_id") or ""
    )
    if (
        owner_authorization_receipt.get("authorization_state") != "AUTHORIZED"
        or not authorization_event_id
        or not _SHA256.fullmatch(owner_authorization_receipt_sha256)
    ):
        raise EpochError("OWNER_AUTHORIZATION_INVALID")
    authorization_row = db.execute(
        "SELECT state,payload_json,payload_sha256 FROM "
        "experiment_authorization_events WHERE event_id=?",
        (authorization_event_id,),
    ).fetchone()
    if authorization_row is None or str(authorization_row[0]) != "AUTHORIZED":
        raise EpochError("OWNER_AUTHORIZATION_EVENT_MISMATCH")
    try:
        authorization_payload = json.loads(str(authorization_row[1]))
    except (json.JSONDecodeError, TypeError) as exc:
        raise EpochError("OWNER_AUTHORIZATION_EVENT_INVALID") from exc
    if sha256_json(authorization_payload) != str(authorization_row[2]):
        raise EpochError("OWNER_AUTHORIZATION_EVENT_INVALID")

    store = ExperimentEpochStore(db)
    store._verify_chain()
    epoch_rows = store._epoch_rows()
    definitions = [
        payload for kind, payload in epoch_rows if kind == "EXPERIMENT_EPOCH_DEFINED"
    ]
    activations = [
        payload for kind, payload in epoch_rows if kind == "EXPERIMENT_EPOCH_ACTIVATED"
    ]
    expected_bindings = _definition_bindings(
        epoch_id=epoch_id,
        approved_git_head=approved_git_head,
        owner_authorization_event_id=authorization_event_id,
        owner_authorization_receipt_sha256=owner_authorization_receipt_sha256,
        objective_sha256=objective_sha256,
        configuration_sha256=configuration_sha256,
    )
    if len(definitions) > 1 or len(activations) > 1:
        raise EpochError("CONFLICTING_EPOCH_ACTIVATION")
    if definitions:
        definition_payload = definitions[0]
        _validate_definition_bindings(definition_payload, expected_bindings)
        if (
            definition_payload.get("start_utc") != _format(start_utc)
            or int(definition_payload.get("duration_days", 0)) != duration_days
            or Decimal(str(definition_payload.get("initial_allocation")))
            != initial_allocation
        ):
            raise EpochError("CONFLICTING_EPOCH_ACTIVATION")
    else:
        if activations:
            raise EpochError("CONFLICTING_EPOCH_ACTIVATION")
        projection = store.projection(activated_at_utc or datetime.now(timezone.utc))
        if projection.get("state") != "PRE_EPOCH_HISTORY":
            raise EpochError("PRE_EPOCH_HISTORY_BLOCK")
        preview = store.preview(
            epoch_id=epoch_id,
            start_utc=start_utc,
            duration_days=duration_days,
            initial_allocation=initial_allocation,
            approved_git_head=approved_git_head,
            owner_authorization_event_id=authorization_event_id,
            owner_authorization_receipt_sha256=owner_authorization_receipt_sha256,
            objective_sha256=objective_sha256,
            configuration_sha256=configuration_sha256,
        )
        definition = store.define(preview)
        definition_payload = store._definition_payload(epoch_id)
        if (
            definition_payload is None
            or definition.definition_sha256
            != definition_payload.get("definition_sha256")
        ):
            raise EpochError("EPOCH_DEFINITION_VALIDATION_BLOCK")
        _validate_definition_bindings(definition_payload, expected_bindings)

    if activations:
        activation = activations[0]
        if (
            activation.get("epoch_id") != epoch_id
            or activation.get("definition_sha256")
            != definition_payload.get("definition_sha256")
            or activation.get("approved_git_head") != approved_git_head
            or activation.get("owner_authorization_receipt_sha256")
            != owner_authorization_receipt_sha256
        ):
            raise EpochError("CONFLICTING_EPOCH_ACTIVATION")
        current = store.current()
        if current is None or current.epoch_id != epoch_id:
            raise EpochError("EPOCH_ACTIVATION_VALIDATION_BLOCK")
        status = "VALID_ALREADY_ACTIVATED"
    else:
        receipt = activation_receipt(
            epoch_id=epoch_id,
            definition_sha256=str(definition_payload["definition_sha256"]),
            owner_authorization_event_id=authorization_event_id,
            approved_git_head=approved_git_head,
            owner_authorization_receipt_sha256=owner_authorization_receipt_sha256,
            issued_at_utc=activated_at_utc,
        )
        activated = store.activate(epoch_id, receipt)
        current = store.current()
        if (
            current is None
            or current.epoch_id != epoch_id
            or current.definition_sha256 != activated.definition_sha256
        ):
            raise EpochError("EPOCH_ACTIVATION_VALIDATION_BLOCK")
        status = "PASS"

    final_rows = store._epoch_rows()
    if (
        sum(kind == "EXPERIMENT_EPOCH_DEFINED" for kind, _ in final_rows) != 1
        or sum(kind == "EXPERIMENT_EPOCH_ACTIVATED" for kind, _ in final_rows) != 1
    ):
        raise EpochError("EPOCH_EVENT_CARDINALITY_BLOCK")
    return {
        "schema": "AUTONOMY_EPOCH_ACTIVATION_RESULT_V1",
        "status": status,
        "epoch_id": epoch_id,
        "definition_sha256": str(definition_payload["definition_sha256"]),
        "approved_git_head": approved_git_head,
        "previous_history_classification": "PRE_EPOCH_HISTORY",
        "day1_started": False,
        "autonomous_service_running": False,
        "broker_write_calls": 0,
    }


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise EpochError("GIT_STATE_BLOCK")
    return completed.stdout.strip()


def _configuration_identity(repo_root: Path, objective_sha256: str) -> str:
    source_hashes = {}
    for relative in (
        "ibkr_paper_30d/autonomous_research.py",
        "ibkr_paper_30d/day1_launch.py",
    ):
        source_hashes[relative] = hashlib.sha256(
            (repo_root / relative).read_bytes()
        ).hexdigest()
    return sha256_json(
        {
            "schema": "AUTONOMY_EPOCH_EFFECTIVE_CONFIGURATION_V1",
            "epoch_id": AUTONOMY_EPOCH_ID,
            "objective_sha256": objective_sha256,
            "duration_days": 30,
            "initial_allocation": "500",
            "paper_host": "127.0.0.1",
            "paper_port": 4002,
            "model": "gpt-5.6-sol",
            "reasoning_effort": "max",
            "source_sha256": source_hashes,
        }
    )


def activate_production_epoch(
    *,
    repo_root: Path,
    db_path: Path,
    owner_receipt_path: Path,
    expected_actor_sid: str,
    approved_head: str,
) -> dict[str, Any]:
    from .kernel_manifest import verify_kernel_manifest
    from .owner_authorization import validate_owner_authorization
    from .runtime_provenance import (
        build_approved_runtime_material,
        verify_runtime_provenance,
    )

    root = repo_root.resolve()
    observed_head = _git(root, "rev-parse", "HEAD").lower()
    if _git(root, "status", "--porcelain", "--untracked-files=no"):
        raise EpochError("TRACKED_WORKTREE_DIRTY")
    try:
        stored_kernel = json.loads(
            (root / "IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise EpochError("KERNEL_BLOCK") from exc
    kernel = verify_kernel_manifest(root, stored_kernel)
    kernel_status = "PASS" if kernel.get("verified") is True else "BLOCK"
    material = build_approved_runtime_material(root, approved_head)
    provenance = verify_runtime_provenance(root, material)
    provenance_status = str(provenance.get("gate_status") or "BLOCK")
    owner_receipt = validate_owner_authorization(
        db_path=db_path,
        receipt_path=owner_receipt_path,
        expected_actor_sid=expected_actor_sid,
    )
    receipt_sha256 = hashlib.sha256(owner_receipt_path.read_bytes()).hexdigest()
    objective_sha256 = hashlib.sha256(AUTONOMY_OBJECTIVE.encode("utf-8")).hexdigest()
    configuration_sha256 = _configuration_identity(root, objective_sha256)
    with Database.open(db_path) as db:
        return activate_epoch_transition(
            db,
            epoch_id=AUTONOMY_EPOCH_ID,
            start_utc=_parse(str(owner_receipt["start_utc"])),
            duration_days=int(owner_receipt["duration_days"]),
            initial_allocation=Decimal(str(owner_receipt["initial_allocation"])),
            approved_git_head=approved_head.lower(),
            observed_git_head=observed_head,
            owner_authorization_receipt=owner_receipt,
            owner_authorization_receipt_sha256=receipt_sha256,
            objective_sha256=objective_sha256,
            configuration_sha256=configuration_sha256,
            kernel_status=kernel_status,
            runtime_provenance_status=provenance_status,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ibkr_paper_30d.experiment_epoch")
    subparsers = parser.add_subparsers(dest="command", required=True)
    activate_parser = subparsers.add_parser("activate-production")
    activate_parser.add_argument("--repo-root", type=Path, required=True)
    activate_parser.add_argument("--db", type=Path, required=True)
    activate_parser.add_argument("--owner-receipt", type=Path, required=True)
    activate_parser.add_argument("--actor-sid", required=True)
    activate_parser.add_argument("--approved-head", required=True)
    args = parser.parse_args(argv)
    try:
        result = activate_production_epoch(
            repo_root=args.repo_root,
            db_path=args.db,
            owner_receipt_path=args.owner_receipt,
            expected_actor_sid=args.actor_sid,
            approved_head=args.approved_head,
        )
    except Exception as exc:
        print(
            json.dumps(
                {"status": "BLOCK", "reason": str(exc)},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
