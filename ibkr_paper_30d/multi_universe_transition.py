"""Recoverable append-only transition into the multi-universe successor."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Literal

from pydantic import BaseModel, ConfigDict

from .canonical import canonical_bytes, sha256_json
from .multi_universe_models import TransitionPhase, TransitionTarget
from .multi_universe_schema import verify_multi_universe_schema_v4
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7


_PHASES = tuple(TransitionPhase)


class MultiUniverseTransitionError(RuntimeError):
    pass


class TransitionRecoveryResult(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    status: Literal["READY", "BLOCK"]
    transition_id: str
    target_sha256: str
    phase: TransitionPhase
    phase_event_sha256: str
    next_phase: TransitionPhase | None
    resume_successor: bool
    predecessor_may_resume: bool
    freeze_new_order_authority: bool
    reason_codes: tuple[str, ...] = ()
    idempotent: bool = False


class MultiUniverseTransitionCoordinator:
    SCHEMA = "MULTI_UNIVERSE_TRANSITION_EVENT_V1"

    def __init__(
        self,
        db: Database,
        *,
        critical_reporter: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> None:
        verify_multi_universe_schema_v4(db)
        self.db = db
        self.critical_reporter = critical_reporter or (lambda _code, _payload: None)
        self._target: TransitionTarget | None = None

    def _rows(self, transition_id: str) -> list[tuple[Any, ...]]:
        return self.db.execute(
            "SELECT phase,payload_json,payload_sha256,previous_event_sha256,"
            "event_sha256 FROM successor_transition_events "
            "WHERE transition_id=? ORDER BY sequence",
            (transition_id,),
        ).fetchall()

    def _events(self, target: TransitionTarget) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        previous: str | None = None
        for phase, payload_json, payload_sha, stored_previous, event_sha in self._rows(
            target.transition_id
        ):
            try:
                payload = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError) as exc:
                raise MultiUniverseTransitionError("TRANSITION_PROJECTION_AMBIGUOUS") from exc
            if (
                payload.get("schema") != self.SCHEMA
                or payload.get("target_sha256") != target.sha256
                or sha256_json(payload) != str(payload_sha)
                or (None if stored_previous is None else str(stored_previous)) != previous
                or sha256_json(
                    {"previous_event_sha256": previous, "payload": payload}
                )
                != str(event_sha)
                or payload.get("phase") != str(phase)
            ):
                raise MultiUniverseTransitionError("TRANSITION_PROJECTION_AMBIGUOUS")
            events.append({**payload, "event_sha256": str(event_sha)})
            previous = str(event_sha)
        if events:
            actual = tuple(TransitionPhase(item["phase"]) for item in events)
            if actual != _PHASES[: len(actual)]:
                raise MultiUniverseTransitionError("TRANSITION_PHASE_ORDER_INVALID")
        return events

    def _append(
        self,
        target: TransitionTarget,
        phase: TransitionPhase,
        evidence: Mapping[str, Any],
    ) -> str:
        row = self.db.execute(
            "SELECT event_sha256 FROM successor_transition_events "
            "WHERE transition_id=? ORDER BY sequence DESC LIMIT 1",
            (target.transition_id,),
        ).fetchone()
        previous = None if row is None else str(row[0])
        payload = {
            "schema": self.SCHEMA,
            "transition_id": target.transition_id,
            "phase": phase.value,
            "target": target.model_dump(mode="json"),
            "target_sha256": target.sha256,
            "evidence": dict(evidence),
            "evidence_sha256": sha256_json(dict(evidence)),
        }
        event_sha = sha256_json(
            {"previous_event_sha256": previous, "payload": payload}
        )
        self.db.execute(
            "INSERT INTO successor_transition_events("
            "event_id,transition_id,phase,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                str(new_uuid7()),
                target.transition_id,
                phase.value,
                "PHASE_COMMITTED",
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                previous,
                event_sha,
                utc_now(),
            ),
        )
        return event_sha

    @staticmethod
    def _sha256_value(value: Any) -> bool:
        text = str(value or "")
        return len(text) == 64 and all(char in "0123456789abcdef" for char in text)

    @classmethod
    def _cash_classifications(
        cls, evidence: Mapping[str, Any]
    ) -> dict[str, list[dict[str, str]]]:
        result: dict[str, list[dict[str, str]]] = {}
        for name in (
            "classified_canary_currency_balances",
            "classified_non_experiment_currency_balances",
        ):
            raw_rows = evidence.get(name)
            if not isinstance(raw_rows, list):
                raise MultiUniverseTransitionError(
                    "ACTIVE_CASH_CLASSIFICATION_REQUIRED"
                )
            rows: list[dict[str, str]] = []
            for raw in raw_rows:
                if not isinstance(raw, Mapping):
                    raise MultiUniverseTransitionError(
                        "ACTIVE_CASH_CLASSIFICATION_INVALID"
                    )
                currency = str(raw.get("currency") or "").upper()
                provenance = str(raw.get("provenance_sha256") or "")
                try:
                    amount = Decimal(str(raw.get("amount")))
                except (InvalidOperation, ValueError):
                    amount = Decimal("NaN")
                if (
                    len(currency) != 3
                    or not amount.is_finite()
                    or amount < 0
                    or not cls._sha256_value(provenance)
                ):
                    raise MultiUniverseTransitionError(
                        "ACTIVE_CASH_CLASSIFICATION_INVALID"
                    )
                rows.append(
                    {
                        "currency": currency,
                        "amount": str(amount),
                        "provenance_sha256": provenance,
                    }
                )
            result[name] = rows
        expected = evidence.get("cash_classification_sha256")
        if not cls._sha256_value(expected) or expected != sha256_json(result):
            raise MultiUniverseTransitionError(
                "ACTIVE_CASH_CLASSIFICATION_REQUIRED"
            )
        return result

    def _validate_evidence(
        self,
        target: TransitionTarget,
        phase: TransitionPhase,
        evidence: Mapping[str, Any],
    ) -> None:
        if not self._sha256_value(evidence.get("phase_evidence_sha256")):
            raise MultiUniverseTransitionError("TRANSITION_PHASE_EVIDENCE_INVALID")
        if phase is TransitionPhase.CANARY_PASS and (
            evidence.get("canary_status") != "PASS"
            or evidence.get("canary_flat") is not True
            or evidence.get("continuity_exact") is not True
        ):
            raise MultiUniverseTransitionError("CANARY_EVIDENCE_INVALID")
        if phase is TransitionPhase.PREDECESSOR_RETIRED and (
            evidence.get("retirement_status") != "PASS"
            or not self._sha256_value(
                evidence.get("retirement_tombstone_sha256")
            )
        ):
            raise MultiUniverseTransitionError("RETIREMENT_EVIDENCE_INVALID")
        if phase is TransitionPhase.SUCCESSOR_COMMITTED and not self._sha256_value(
            evidence.get("successor_commit_sha256")
        ):
            raise MultiUniverseTransitionError("SUCCESSOR_COMMIT_EVIDENCE_INVALID")
        if phase is TransitionPhase.SUPERVISION_BOUND and (
            evidence.get("reconciliation_status") != "PASS"
            or not self._sha256_value(
                evidence.get("inherited_position_projection_sha256")
            )
            or not self._sha256_value(evidence.get("ownership_projection_sha256"))
            or evidence.get("writer_binding_sha256")
            != target.writer_binding_sha256
            or evidence.get("new_entry_authority") is not False
        ):
            raise MultiUniverseTransitionError(
                "SUPERVISION_BINDING_EVIDENCE_INVALID"
            )
        if phase is TransitionPhase.RUNTIME_BOUND and (
            evidence.get("writer_binding_sha256") != target.writer_binding_sha256
        ):
            raise MultiUniverseTransitionError("WRITER_BINDING_EVIDENCE_INVALID")
        if phase is TransitionPhase.ACTIVE and (
            evidence.get("reconciliation_status") != "PASS"
        ):
            raise MultiUniverseTransitionError("ACTIVE_RECONCILIATION_REQUIRED")
        if phase is TransitionPhase.ACTIVE:
            self._cash_classifications(evidence)

    def _result(
        self,
        target: TransitionTarget,
        event: Mapping[str, Any],
        *,
        idempotent: bool,
    ) -> TransitionRecoveryResult:
        phase = TransitionPhase(str(event["phase"]))
        index = _PHASES.index(phase)
        retired = index >= _PHASES.index(TransitionPhase.PREDECESSOR_RETIRED)
        evidence = dict(event.get("evidence") or {})
        rollback_proven = phase is TransitionPhase.PREPARED or (
            evidence.get("canary_flat") is True
            and evidence.get("continuity_exact") is True
        )
        return TransitionRecoveryResult(
            status="READY",
            transition_id=target.transition_id,
            target_sha256=target.sha256,
            phase=phase,
            phase_event_sha256=str(event["event_sha256"]),
            next_phase=(None if index + 1 == len(_PHASES) else _PHASES[index + 1]),
            resume_successor=retired,
            predecessor_may_resume=(not retired and rollback_proven),
            freeze_new_order_authority=phase is not TransitionPhase.ACTIVE,
            idempotent=idempotent,
        )

    def prepare(self, target: TransitionTarget) -> TransitionRecoveryResult:
        with self.db.transaction():
            other = self.db.execute(
                "SELECT transition_id,payload_json FROM successor_transition_events "
                "ORDER BY sequence LIMIT 1"
            ).fetchone()
            if other is not None and str(other[0]) != target.transition_id:
                raise MultiUniverseTransitionError("TRANSITION_TARGET_CONFLICT")
            rows = self._rows(target.transition_id)
            if rows:
                first_payload = json.loads(str(rows[0][1]))
                if first_payload.get("target_sha256") != target.sha256:
                    raise MultiUniverseTransitionError(
                        "TRANSITION_TARGET_CONFLICT"
                    )
                events = self._events(target)
                if not events:
                    raise MultiUniverseTransitionError("TRANSITION_TARGET_CONFLICT")
                result = self._result(target, events[-1], idempotent=True)
                self._target = target
                return result
            event_sha = self._append(
                target,
                TransitionPhase.PREPARED,
                {"target_sha256": target.sha256},
            )
            event = {
                "phase": TransitionPhase.PREPARED.value,
                "event_sha256": event_sha,
                "evidence": {},
            }
        self._target = target
        return self._result(target, event, idempotent=False)

    def advance(
        self, expected_phase: TransitionPhase, evidence: Mapping[str, Any]
    ) -> TransitionRecoveryResult:
        target = self._target
        if target is None:
            raise MultiUniverseTransitionError("TRANSITION_TARGET_NOT_PREPARED")
        self._validate_evidence(target, expected_phase, evidence)
        with self.db.transaction():
            events = self._events(target)
            if not events:
                raise MultiUniverseTransitionError("TRANSITION_TARGET_NOT_PREPARED")
            current = TransitionPhase(events[-1]["phase"])
            if current is expected_phase:
                if events[-1].get("evidence_sha256") != sha256_json(dict(evidence)):
                    raise MultiUniverseTransitionError("TRANSITION_RETRY_CONFLICT")
                return self._result(target, events[-1], idempotent=True)
            current_index = _PHASES.index(current)
            if current_index + 1 >= len(_PHASES) or _PHASES[current_index + 1] is not expected_phase:
                raise MultiUniverseTransitionError("TRANSITION_PHASE_ORDER_INVALID")
            event_sha = self._append(target, expected_phase, evidence)
            event = {
                "phase": expected_phase.value,
                "event_sha256": event_sha,
                "evidence": dict(evidence),
            }
        return self._result(target, event, idempotent=False)

    def recover(self, target: TransitionTarget) -> TransitionRecoveryResult:
        self._target = target
        try:
            events = self._events(target)
            if not events:
                raise MultiUniverseTransitionError("TRANSITION_NOT_FOUND")
            return self._result(target, events[-1], idempotent=True)
        except MultiUniverseTransitionError as exc:
            self.critical_reporter(
                "EXECUTION_LOCK_AMBIGUOUS",
                {"transition_id": target.transition_id, "reason": str(exc)},
            )
            raise


def active_cash_classifications(db: Database) -> dict[str, list[dict[str, str]]]:
    """Recover hash-chained cash classifications from the ACTIVE transition."""

    row = db.execute(
        "SELECT payload_json FROM successor_transition_events "
        "ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise MultiUniverseTransitionError("ACTIVE_TRANSITION_REQUIRED")
    try:
        payload = json.loads(str(row[0]))
        target = TransitionTarget.model_validate(payload.get("target"))
    except Exception as exc:
        raise MultiUniverseTransitionError(
            "TRANSITION_PROJECTION_AMBIGUOUS"
        ) from exc
    recovered = MultiUniverseTransitionCoordinator(db).recover(target)
    if recovered.phase is not TransitionPhase.ACTIVE:
        raise MultiUniverseTransitionError("ACTIVE_TRANSITION_REQUIRED")
    evidence = payload.get("evidence")
    if not isinstance(evidence, Mapping):
        raise MultiUniverseTransitionError("ACTIVE_CASH_CLASSIFICATION_REQUIRED")
    return MultiUniverseTransitionCoordinator._cash_classifications(evidence)


def require_predecessor_retired(
    db: Database, *, transition_id: str, target_sha256: str
) -> str:
    row = db.execute(
        "SELECT phase,payload_json,event_sha256 FROM successor_transition_events "
        "WHERE transition_id=? AND phase=? ORDER BY sequence DESC LIMIT 1",
        (transition_id, TransitionPhase.PREDECESSOR_RETIRED.value),
    ).fetchone()
    if row is None:
        raise MultiUniverseTransitionError("PREDECESSOR_RETIREMENT_NOT_PROVEN")
    payload = json.loads(str(row[1]))
    if (
        payload.get("target_sha256") != target_sha256
    ):
        raise MultiUniverseTransitionError("PREDECESSOR_RETIREMENT_NOT_PROVEN")
    return str(row[2])
