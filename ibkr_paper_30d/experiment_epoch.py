"""Append-only experiment epoch definitions and truthful history projection."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .canonical import canonical_bytes, sha256_json
from .persistence import Database
from .repositories import EventRepository, utc_now


EPOCH_DEFINITION_SCHEMA = "AUTONOMY_EXPERIMENT_EPOCH_DEFINITION_V1"
EPOCH_ACTIVATION_SCHEMA = "AUTONOMY_EXPERIMENT_EPOCH_ACTIVATION_V1"
OWNER_ACTIVATION_SCHEMA = "OWNER_EPOCH_ACTIVATION_AUTHORIZATION_V1"
_EPOCH_ID = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


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
    issued_at_utc: datetime | None = None,
) -> dict[str, Any]:
    unsigned = {
        "schema": OWNER_ACTIVATION_SCHEMA,
        "state": "AUTHORIZED",
        "actor": "OWNER",
        "epoch_id": epoch_id,
        "definition_sha256": definition_sha256,
        "owner_authorization_event_id": owner_authorization_event_id,
        "issued_at_utc": _format(issued_at_utc or datetime.now(timezone.utc)),
    }
    return {**unsigned, "receipt_sha256": sha256_json(unsigned)}


class ExperimentEpochStore:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.events = EventRepository(db)

    def _verify_chain(self) -> None:
        result = self.events.verify_chain()
        if not result.valid:
            raise EpochError(
                f"state event chain is invalid at sequence {result.first_invalid_sequence}"
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
    ) -> dict[str, Any]:
        self._verify_chain()
        if not _EPOCH_ID.fullmatch(epoch_id):
            raise EpochError("epoch id is invalid")
        if duration_days <= 0 or initial_allocation <= 0:
            raise EpochError("epoch duration and allocation must be positive")
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
            if not isinstance(payload, dict) or sha256_json(payload) != str(payload_hash):
                raise EpochError("epoch event payload hash is invalid")
            parsed.append((str(event_type), payload))
        return parsed

    def _definition_payload(self, epoch_id: str) -> dict[str, Any] | None:
        for event_type, payload in self._epoch_rows():
            if event_type == "EXPERIMENT_EPOCH_DEFINED" and payload.get("epoch_id") == epoch_id:
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
        rows = self._epoch_rows()
        activations = [payload for kind, payload in rows if kind == "EXPERIMENT_EPOCH_ACTIVATED"]
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
