"""Durable one-shot directives for agent-selected physical PAPER canaries."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .multi_universe_models import CapitalSleeve, GIT_HEAD_PATTERN, SHA256_PATTERN
from .persistence import Database
from .repositories import EventRepository


class PhysicalCanaryError(RuntimeError):
    pass


class PhysicalCanaryState(str, Enum):
    REQUESTED = "REQUESTED"
    ENTRY_SELECTED = "ENTRY_SELECTED"
    ISSUED_PRE_SEND = "ISSUED_PRE_SEND"
    BROKER_BOUND = "BROKER_BOUND"
    ACTIVE_MANAGEMENT = "ACTIVE_MANAGEMENT"
    FLAT_RECONCILED = "FLAT_RECONCILED"
    TERMINAL_NO_FILL = "TERMINAL_NO_FILL"
    MODEL_DECLINED = "MODEL_DECLINED"
    BLOCKED = "BLOCKED"
    UNCERTAIN = "UNCERTAIN"


class _PhysicalCanaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PhysicalCanaryDirective(_PhysicalCanaryModel):
    canary_id: str = Field(min_length=1)
    capital_sleeve: CapitalSleeve
    owner_authorization_sha256: str = Field(pattern=SHA256_PATTERN)
    requested_at_utc: datetime
    approved_head: str = Field(pattern=GIT_HEAD_PATTERN)


class PhysicalCanaryProjection(_PhysicalCanaryModel):
    directive: PhysicalCanaryDirective
    state: PhysicalCanaryState


class PhysicalCanaryStore:
    _EVENT_PREFIX = "PHYSICAL_CANARY_"
    _TERMINAL = {
        PhysicalCanaryState.FLAT_RECONCILED,
        PhysicalCanaryState.TERMINAL_NO_FILL,
        PhysicalCanaryState.MODEL_DECLINED,
        PhysicalCanaryState.BLOCKED,
    }
    _ALLOWED = {
        PhysicalCanaryState.REQUESTED: {
            PhysicalCanaryState.ENTRY_SELECTED,
            PhysicalCanaryState.MODEL_DECLINED,
            PhysicalCanaryState.BLOCKED,
            PhysicalCanaryState.UNCERTAIN,
        },
        PhysicalCanaryState.ENTRY_SELECTED: {
            PhysicalCanaryState.ISSUED_PRE_SEND,
            PhysicalCanaryState.BLOCKED,
            PhysicalCanaryState.UNCERTAIN,
        },
        PhysicalCanaryState.ISSUED_PRE_SEND: {
            PhysicalCanaryState.BROKER_BOUND,
            PhysicalCanaryState.TERMINAL_NO_FILL,
            PhysicalCanaryState.BLOCKED,
            PhysicalCanaryState.UNCERTAIN,
        },
        PhysicalCanaryState.BROKER_BOUND: {
            PhysicalCanaryState.ACTIVE_MANAGEMENT,
            PhysicalCanaryState.TERMINAL_NO_FILL,
            PhysicalCanaryState.UNCERTAIN,
        },
        PhysicalCanaryState.ACTIVE_MANAGEMENT: {
            PhysicalCanaryState.ACTIVE_MANAGEMENT,
            PhysicalCanaryState.FLAT_RECONCILED,
            PhysicalCanaryState.UNCERTAIN,
        },
        PhysicalCanaryState.UNCERTAIN: {
            PhysicalCanaryState.ACTIVE_MANAGEMENT,
            PhysicalCanaryState.FLAT_RECONCILED,
            PhysicalCanaryState.TERMINAL_NO_FILL,
        },
    }

    def __init__(self, db: Database) -> None:
        self.db = db
        self.events = EventRepository(db)

    def _projections(self) -> dict[str, PhysicalCanaryProjection]:
        rows = self.db.execute(
            "SELECT event_type,payload_json FROM state_events "
            "WHERE event_type LIKE 'PHYSICAL_CANARY_%' ORDER BY sequence"
        ).fetchall()
        projections: dict[str, PhysicalCanaryProjection] = {}
        for event_type, payload_json in rows:
            payload = json.loads(str(payload_json))
            if str(event_type) == "PHYSICAL_CANARY_REQUESTED":
                directive = PhysicalCanaryDirective.model_validate(
                    payload["directive"]
                )
                if directive.canary_id in projections:
                    raise PhysicalCanaryError(
                        "PHYSICAL_CANARY_DUPLICATE_REQUEST_EVENT"
                    )
                projections[directive.canary_id] = PhysicalCanaryProjection(
                    directive=directive,
                    state=PhysicalCanaryState.REQUESTED,
                )
                continue
            canary_id = str(payload.get("canary_id") or "")
            current = projections.get(canary_id)
            if current is None:
                raise PhysicalCanaryError("PHYSICAL_CANARY_REQUEST_MISSING")
            if (
                str(payload.get("capital_sleeve") or "")
                != current.directive.capital_sleeve.value
            ):
                raise PhysicalCanaryError("PHYSICAL_CANARY_SLEEVE_MISMATCH")
            if str(payload.get("from_state") or "") != current.state.value:
                raise PhysicalCanaryError("PHYSICAL_CANARY_CHAIN_MISMATCH")
            try:
                next_state = PhysicalCanaryState(
                    str(event_type)[len(self._EVENT_PREFIX) :]
                )
            except ValueError as exc:
                raise PhysicalCanaryError(
                    "PHYSICAL_CANARY_EVENT_UNKNOWN"
                ) from exc
            if next_state not in self._ALLOWED.get(current.state, set()):
                raise PhysicalCanaryError("PHYSICAL_CANARY_TRANSITION_INVALID")
            projections[canary_id] = current.model_copy(
                update={"state": next_state}
            )
        return projections

    def projection(self, canary_id: str) -> PhysicalCanaryProjection | None:
        return self._projections().get(canary_id)

    def projections(self) -> tuple[PhysicalCanaryProjection, ...]:
        return tuple(self._projections().values())

    def latest_evidence(self, canary_id: str) -> dict[str, object]:
        rows = self.db.execute(
            "SELECT payload_json FROM state_events "
            "WHERE event_type LIKE 'PHYSICAL_CANARY_%' ORDER BY sequence DESC"
        ).fetchall()
        merged: dict[str, object] = {}
        for (payload_json,) in rows:
            payload = json.loads(str(payload_json))
            if str(payload.get("canary_id") or "") == canary_id:
                evidence = payload.get("evidence") or {}
                if not isinstance(evidence, dict):
                    raise PhysicalCanaryError(
                        "PHYSICAL_CANARY_EVIDENCE_INVALID"
                    )
                for key, value in evidence.items():
                    merged.setdefault(str(key), value)
        return merged

    def active(self) -> PhysicalCanaryProjection | None:
        active = [
            item
            for item in self._projections().values()
            if item.state not in self._TERMINAL
        ]
        if len(active) > 1:
            raise PhysicalCanaryError("PHYSICAL_CANARY_MULTIPLE_ACTIVE")
        return active[0] if active else None

    def request(
        self, directive: PhysicalCanaryDirective
    ) -> PhysicalCanaryProjection:
        existing = self.projection(directive.canary_id)
        if existing is not None:
            if existing.directive == directive:
                return existing
            raise PhysicalCanaryError("PHYSICAL_CANARY_IDENTITY_CONFLICT")
        active = self.active()
        if active is not None:
            raise PhysicalCanaryError("PHYSICAL_CANARY_ACTIVE_CONFLICT")
        self.events.append(
            "PHYSICAL_CANARY_REQUESTED",
            {"directive": directive.model_dump(mode="json")},
        )
        projection = self.projection(directive.canary_id)
        assert projection is not None
        return projection

    def append_transition(
        self,
        canary_id: str,
        state: PhysicalCanaryState,
        *,
        capital_sleeve: CapitalSleeve,
        evidence: dict[str, object] | None = None,
    ) -> PhysicalCanaryProjection:
        current = self.projection(canary_id)
        if current is None:
            raise PhysicalCanaryError("PHYSICAL_CANARY_REQUEST_MISSING")
        if current.directive.capital_sleeve is not capital_sleeve:
            raise PhysicalCanaryError("PHYSICAL_CANARY_SLEEVE_MISMATCH")
        if state not in self._ALLOWED.get(current.state, set()):
            raise PhysicalCanaryError("PHYSICAL_CANARY_TRANSITION_INVALID")
        self.events.append(
            f"{self._EVENT_PREFIX}{state.value}",
            {
                "canary_id": canary_id,
                "capital_sleeve": capital_sleeve.value,
                "from_state": current.state.value,
                "evidence": evidence or {},
            },
        )
        projection = self.projection(canary_id)
        assert projection is not None
        return projection
