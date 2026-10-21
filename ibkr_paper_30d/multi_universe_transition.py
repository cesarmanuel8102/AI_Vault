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
    RUNTIME_RELEASE_SCHEMA = "MULTI_UNIVERSE_RUNTIME_RELEASE_V1"

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
            "SELECT phase,event_type,payload_json,payload_sha256,previous_event_sha256,"
            "event_sha256 FROM successor_transition_events "
            "WHERE transition_id=? ORDER BY sequence",
            (transition_id,),
        ).fetchall()

    def _events(self, target: TransitionTarget) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        previous: str | None = None
        effective_approved_git_head = target.approved_git_head
        for (
            phase,
            event_type,
            payload_json,
            payload_sha,
            stored_previous,
            event_sha,
        ) in self._rows(target.transition_id):
            try:
                payload = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError) as exc:
                raise MultiUniverseTransitionError(
                    "TRANSITION_PROJECTION_AMBIGUOUS"
                ) from exc
            if (
                payload.get("target_sha256") != target.sha256
                or sha256_json(payload) != str(payload_sha)
                or (None if stored_previous is None else str(stored_previous))
                != previous
                or sha256_json({"previous_event_sha256": previous, "payload": payload})
                != str(event_sha)
                or payload.get("phase") != str(phase)
            ):
                raise MultiUniverseTransitionError("TRANSITION_PROJECTION_AMBIGUOUS")
            if event_type == "PHASE_COMMITTED":
                if payload.get("schema") != self.SCHEMA:
                    raise MultiUniverseTransitionError(
                        "TRANSITION_PROJECTION_AMBIGUOUS"
                    )
                events.append({**payload, "event_sha256": str(event_sha)})
            elif event_type == "RUNTIME_RELEASE_AUTHORIZED":
                if (
                    payload.get("schema") != self.RUNTIME_RELEASE_SCHEMA
                    or payload.get("target") != target.model_dump(mode="json")
                    or payload.get("previous_approved_git_head")
                    != effective_approved_git_head
                    or not self._git_head_value(payload.get("approved_git_head"))
                    or payload.get("evidence_sha256")
                    != sha256_json(payload.get("evidence") or {})
                ):
                    raise MultiUniverseTransitionError(
                        "TRANSITION_PROJECTION_AMBIGUOUS"
                    )
                effective_approved_git_head = str(payload["approved_git_head"])
            else:
                raise MultiUniverseTransitionError("TRANSITION_PROJECTION_AMBIGUOUS")
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
        event_sha = sha256_json({"previous_event_sha256": previous, "payload": payload})
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

    @staticmethod
    def _git_head_value(value: Any) -> bool:
        text = str(value or "")
        return len(text) == 40 and all(char in "0123456789abcdef" for char in text)

    @classmethod
    def _open_order_continuation_valid(cls, evidence: Mapping[str, Any]) -> bool:
        orders = evidence.get("continuity_open_orders")
        count = evidence.get("open_order_count")
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            return False
        if not isinstance(orders, list) or len(orders) != count:
            return False
        if sha256_json(orders) != evidence.get("continuity_open_orders_sha256"):
            return False
        order_refs: set[str] = set()
        order_ids: set[int] = set()
        perm_ids: set[int] = set()
        for order in orders:
            if not isinstance(order, Mapping):
                return False
            order_ref = str(order.get("order_ref") or "")
            order_id = order.get("ibkr_order_id")
            perm_id = order.get("perm_id")
            contract_id = order.get("contract_id")
            try:
                quantity = Decimal(str(order.get("quantity")))
            except (InvalidOperation, ValueError):
                return False
            if (
                not order_ref.startswith("codex-ibkr-paper-30d-")
                or not isinstance(order_id, int)
                or isinstance(order_id, bool)
                or order_id <= 0
                or not isinstance(perm_id, int)
                or isinstance(perm_id, bool)
                or perm_id <= 0
                or not isinstance(contract_id, int)
                or isinstance(contract_id, bool)
                or contract_id <= 0
                or str(order.get("action") or "") not in {"BUY", "SELL"}
                or not quantity.is_finite()
                or quantity <= 0
                or not cls._sha256_value(order.get("registry_payload_sha256"))
                or order_ref in order_refs
                or order_id in order_ids
                or perm_id in perm_ids
            ):
                return False
            order_refs.add(order_ref)
            order_ids.add(order_id)
            perm_ids.add(perm_id)
        return True

    @staticmethod
    def _validate_runtime_release_evidence(
        target: TransitionTarget,
        approved_git_head: str,
        evidence: Mapping[str, Any],
    ) -> None:
        open_order_count = evidence.get("open_order_count")
        if open_order_count != 0:
            if evidence.get("continuity_open_orders_verified") is not True:
                raise MultiUniverseTransitionError("RUNTIME_RELEASE_BROKER_NOT_FLAT")
            if not MultiUniverseTransitionCoordinator._open_order_continuation_valid(
                evidence
            ):
                raise MultiUniverseTransitionError(
                    "RUNTIME_RELEASE_OPEN_ORDER_CONTINUITY_INVALID"
                )
        checks = (
            (evidence.get("owner_authorized") is True, "OWNER_AUTHORIZATION_REQUIRED"),
            (
                bool(str(evidence.get("owner_sid") or "").strip()),
                "OWNER_AUTHORIZATION_REQUIRED",
            ),
            (
                evidence.get("account_identity_sha256")
                == target.account_identity_sha256,
                "PAPER_ACCOUNT_MISMATCH",
            ),
            (
                evidence.get("current_head") == approved_git_head,
                "RUNTIME_RELEASE_HEAD_MISMATCH",
            ),
            (
                evidence.get("live_port_4001_listening") is False,
                "POSSIBLE_LIVE_CONNECTION",
            ),
            (
                evidence.get("paper_port_4002_listening") is True
                and evidence.get("authenticated_paper") is True,
                "PAPER_PORT_UNAVAILABLE",
            ),
            (
                evidence.get("broker_reconciliation_status") == "PASS"
                and evidence.get("broker_state_certain") is True,
                "BROKER_STATE_UNCERTAIN",
            ),
            (evidence.get("tracked_tree_clean") is True, "TRACKED_TREE_DIRTY"),
            (evidence.get("writer_count") == 0, "RUNTIME_RELEASE_WRITER_ACTIVE"),
            (
                evidence.get("new_execution_count") == 0
                and evidence.get("broker_write_count") == 0,
                "RUNTIME_RELEASE_BROKER_NOT_FLAT",
            ),
            (
                MultiUniverseTransitionCoordinator._sha256_value(
                    evidence.get("release_artifact_sha256")
                ),
                "RUNTIME_RELEASE_EVIDENCE_INVALID",
            ),
        )
        for valid, reason in checks:
            if not valid:
                raise MultiUniverseTransitionError(reason)

    def _runtime_release_rows(self, target: TransitionTarget) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT payload_json,event_sha256 FROM successor_transition_events "
            "WHERE transition_id=? AND event_type='RUNTIME_RELEASE_AUTHORIZED' "
            "ORDER BY sequence",
            (target.transition_id,),
        ).fetchall()
        releases: list[dict[str, Any]] = []
        for payload_json, event_sha256 in rows:
            try:
                payload = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError) as exc:
                raise MultiUniverseTransitionError(
                    "TRANSITION_PROJECTION_AMBIGUOUS"
                ) from exc
            releases.append({**payload, "event_sha256": str(event_sha256)})
        return releases

    def effective_approved_git_head(self, target: TransitionTarget) -> str:
        self._events(target)
        releases = self._runtime_release_rows(target)
        return (
            target.approved_git_head
            if not releases
            else str(releases[-1]["approved_git_head"])
        )

    def authorize_runtime_release(
        self,
        target: TransitionTarget,
        *,
        approved_git_head: str,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not self._git_head_value(approved_git_head):
            raise MultiUniverseTransitionError("RUNTIME_RELEASE_HEAD_INVALID")
        self._validate_runtime_release_evidence(target, approved_git_head, evidence)
        with self.db.transaction():
            events = self._events(target)
            if not events:
                raise MultiUniverseTransitionError("RUNTIME_RELEASE_PHASE_INVALID")
            current_phase = TransitionPhase(events[-1]["phase"])
            if current_phase not in {
                TransitionPhase.SUCCESSOR_COMMITTED,
                TransitionPhase.SUPERVISION_BOUND,
                TransitionPhase.CANARY_EXCLUSIVE,
                TransitionPhase.DUAL_SLEEVE_ACTIVE,
                TransitionPhase.ACTIVE,
            }:
                raise MultiUniverseTransitionError("RUNTIME_RELEASE_PHASE_INVALID")
            if current_phase is TransitionPhase.ACTIVE:
                if (
                    evidence.get("transition_phase") != "ACTIVE"
                    or evidence.get("phase_event_sha256") != events[-1]["event_sha256"]
                    or evidence.get("recertification_required") is not True
                    or not self._sha256_value(evidence.get("current_adapter_sha256"))
                ):
                    raise MultiUniverseTransitionError(
                        "ACTIVE_RELEASE_RECERTIFICATION_BINDING_REQUIRED"
                    )
                self._cash_classifications(evidence)
            if current_phase is TransitionPhase.SUPERVISION_BOUND and (
                evidence.get("transition_phase") != current_phase.value
                or evidence.get("supervision_phase_event_sha256")
                != events[-1]["event_sha256"]
            ):
                raise MultiUniverseTransitionError(
                    "RUNTIME_RELEASE_SUPERVISION_BINDING_REQUIRED"
                )
            if current_phase is TransitionPhase.SUPERVISION_BOUND:
                try:
                    self._cash_classifications(evidence)
                except MultiUniverseTransitionError as exc:
                    raise MultiUniverseTransitionError(
                        "SUPERVISION_CASH_CLASSIFICATION_REQUIRED"
                    ) from exc
            if current_phase is TransitionPhase.CANARY_EXCLUSIVE and (
                evidence.get("transition_phase") != current_phase.value
                or evidence.get("phase_event_sha256") != events[-1]["event_sha256"]
            ):
                raise MultiUniverseTransitionError(
                    "RUNTIME_RELEASE_PHASE_BINDING_REQUIRED"
                )
            releases = self._runtime_release_rows(target)
            previous_approved_git_head = (
                target.approved_git_head
                if not releases
                else str(releases[-1]["approved_git_head"])
            )
            active_evidence_refresh = False
            if releases:
                existing = releases[-1]
                if existing.get("approved_git_head") == approved_git_head:
                    if existing.get("evidence_sha256") == sha256_json(dict(evidence)):
                        return {
                            "status": "PASS",
                            "previous_approved_git_head": existing[
                                "previous_approved_git_head"
                            ],
                            "approved_git_head": approved_git_head,
                            "event_sha256": existing["event_sha256"],
                            "idempotent": True,
                        }
                    if current_phase is not TransitionPhase.ACTIVE:
                        raise MultiUniverseTransitionError("RUNTIME_RELEASE_CONFLICT")
                    active_evidence_refresh = True
            if (
                approved_git_head == previous_approved_git_head
                and not active_evidence_refresh
            ):
                raise MultiUniverseTransitionError("RUNTIME_RELEASE_HEAD_UNCHANGED")
            row = self.db.execute(
                "SELECT event_sha256 FROM successor_transition_events "
                "WHERE transition_id=? ORDER BY sequence DESC LIMIT 1",
                (target.transition_id,),
            ).fetchone()
            previous = None if row is None else str(row[0])
            payload = {
                "schema": self.RUNTIME_RELEASE_SCHEMA,
                "transition_id": target.transition_id,
                "phase": current_phase.value,
                "target": target.model_dump(mode="json"),
                "target_sha256": target.sha256,
                "previous_approved_git_head": previous_approved_git_head,
                "approved_git_head": approved_git_head,
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
                    current_phase.value,
                    "RUNTIME_RELEASE_AUTHORIZED",
                    canonical_bytes(payload).decode("utf-8"),
                    sha256_json(payload),
                    previous,
                    event_sha,
                    utc_now(),
                ),
            )
        return {
            "status": "PASS",
            "previous_approved_git_head": previous_approved_git_head,
            "approved_git_head": approved_git_head,
            "event_sha256": event_sha,
            "idempotent": False,
        }

    def active_recertification_release_sha256(
        self, account_sha256: str, approved_head: str, adapter_sha256: str
    ) -> str | None:
        row = self.db.execute(
            "SELECT payload_json FROM successor_transition_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        target = TransitionTarget.model_validate(json.loads(str(row[0]))["target"])
        recovered = self.recover(target)
        releases = self._runtime_release_rows(target)
        if recovered.phase is not TransitionPhase.ACTIVE or not releases:
            return None
        release = releases[-1]
        evidence = release.get("evidence") or {}
        if (
            target.account_identity_sha256 != account_sha256
            or release.get("approved_git_head") != approved_head
            or release.get("phase") != "ACTIVE"
            or evidence.get("recertification_required") is not True
            or evidence.get("current_adapter_sha256") != adapter_sha256
            or evidence.get("phase_event_sha256") != recovered.phase_event_sha256
        ):
            return None
        self._validate_runtime_release_evidence(target, approved_head, evidence)
        self._cash_classifications(evidence)
        return str(release["event_sha256"])

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
            raise MultiUniverseTransitionError("ACTIVE_CASH_CLASSIFICATION_REQUIRED")
        if "cash_rounding_quantum_usd" in evidence:
            quantum = Decimal(str(evidence["cash_rounding_quantum_usd"]))
            reference = evidence.get("raw_usd_cash_snapshot_sha256")
            if (
                not quantum.is_finite()
                or not 0 < quantum <= Decimal("0.01")
                or not cls._sha256_value(reference)
            ):
                raise MultiUniverseTransitionError("CASH_ROUNDING_REFERENCE_INVALID")
            result["cash_rounding_reference"] = {
                "quantum_usd": str(quantum),
                "provenance_sha256": reference,
            }
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
        if phase in {
            TransitionPhase.CANARY_PASS,
            TransitionPhase.RUNTIME_BOUND,
        } and not self._sha256_value(evidence.get("certified_family_set_sha256")):
            raise MultiUniverseTransitionError("CERTIFIED_FAMILY_SET_EVIDENCE_INVALID")
        if phase is TransitionPhase.PREDECESSOR_RETIRED and (
            evidence.get("retirement_status") != "PASS"
            or not self._sha256_value(evidence.get("retirement_tombstone_sha256"))
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
            or evidence.get("writer_binding_sha256") != target.writer_binding_sha256
            or evidence.get("new_entry_authority") is not False
        ):
            raise MultiUniverseTransitionError("SUPERVISION_BINDING_EVIDENCE_INVALID")
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
                first_payload = json.loads(str(rows[0][2]))
                if first_payload.get("target_sha256") != target.sha256:
                    raise MultiUniverseTransitionError("TRANSITION_TARGET_CONFLICT")
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
        with self.db.transaction():
            return self.advance_in_transaction(target, expected_phase, evidence)

    def advance_in_transaction(
        self,
        target: TransitionTarget,
        expected_phase: TransitionPhase,
        evidence: Mapping[str, Any],
    ) -> TransitionRecoveryResult:
        if not self.db.connection.in_transaction:
            raise MultiUniverseTransitionError("ATOMIC_TRANSITION_TRANSACTION_REQUIRED")
        self._target = target
        self._validate_evidence(target, expected_phase, evidence)
        events = self._events(target)
        if not events:
            raise MultiUniverseTransitionError("TRANSITION_TARGET_NOT_PREPARED")
        current = TransitionPhase(events[-1]["phase"])
        if current is expected_phase:
            if events[-1].get("evidence_sha256") != sha256_json(dict(evidence)):
                raise MultiUniverseTransitionError("TRANSITION_RETRY_CONFLICT")
            return self._result(target, events[-1], idempotent=True)
        current_index = _PHASES.index(current)
        if (
            current_index + 1 >= len(_PHASES)
            or _PHASES[current_index + 1] is not expected_phase
        ):
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
        raise MultiUniverseTransitionError("TRANSITION_PROJECTION_AMBIGUOUS") from exc
    recovered = MultiUniverseTransitionCoordinator(db).recover(target)
    if recovered.phase is not TransitionPhase.ACTIVE:
        raise MultiUniverseTransitionError("ACTIVE_TRANSITION_REQUIRED")
    evidence = payload.get("evidence")
    if not isinstance(evidence, Mapping):
        raise MultiUniverseTransitionError("ACTIVE_CASH_CLASSIFICATION_REQUIRED")
    return MultiUniverseTransitionCoordinator._cash_classifications(evidence)


def current_cash_classifications(db: Database) -> dict[str, list[dict[str, str]]]:
    """Recover classifications authorized for the current transition phase."""

    row = db.execute(
        "SELECT event_type,payload_json FROM successor_transition_events "
        "ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise MultiUniverseTransitionError("ACTIVE_TRANSITION_REQUIRED")
    try:
        payload = json.loads(str(row[1]))
        target = TransitionTarget.model_validate(payload.get("target"))
    except Exception as exc:
        raise MultiUniverseTransitionError("TRANSITION_PROJECTION_AMBIGUOUS") from exc
    recovered = MultiUniverseTransitionCoordinator(db).recover(target)
    if recovered.phase is TransitionPhase.ACTIVE:
        return active_cash_classifications(db)
    if recovered.phase not in {
        TransitionPhase.SUPERVISION_BOUND,
        TransitionPhase.CANARY_EXCLUSIVE,
        TransitionPhase.CANARY_PASS,
        TransitionPhase.RUNTIME_BOUND,
        TransitionPhase.DUAL_SLEEVE_ACTIVE,
    }:
        raise MultiUniverseTransitionError("SUPERVISION_CASH_CLASSIFICATION_REQUIRED")
    # A later phase-bound release may supersede the supervision cash evidence.
    release_row = db.execute(
        "SELECT payload_json FROM successor_transition_events "
        "WHERE transition_id=? AND phase=? "
        "AND event_type='RUNTIME_RELEASE_AUTHORIZED' ORDER BY sequence DESC LIMIT 1",
        (target.transition_id, recovered.phase.value),
    ).fetchone()
    if (
        release_row is not None
        and recovered.phase is not TransitionPhase.SUPERVISION_BOUND
    ):
        release = json.loads(str(release_row[0]))
        evidence = release.get("evidence") or {}
        cash_keys = {
            "classified_canary_currency_balances",
            "classified_non_experiment_currency_balances",
            "cash_classification_sha256",
        }
        if cash_keys.intersection(evidence):
            if (
                release.get("phase") != recovered.phase.value
                or evidence.get("transition_phase") != recovered.phase.value
                or evidence.get("phase_event_sha256") != recovered.phase_event_sha256
            ):
                raise MultiUniverseTransitionError(
                    "RUNTIME_RELEASE_PHASE_BINDING_REQUIRED"
                )
            MultiUniverseTransitionCoordinator._validate_runtime_release_evidence(
                target, str(release.get("approved_git_head") or ""), evidence
            )
            return MultiUniverseTransitionCoordinator._cash_classifications(evidence)
    supervision_row = db.execute(
        "SELECT event_sha256 FROM successor_transition_events "
        "WHERE transition_id=? AND phase=? AND event_type='PHASE_COMMITTED'",
        (target.transition_id, TransitionPhase.SUPERVISION_BOUND.value),
    ).fetchall()
    release_rows = db.execute(
        "SELECT payload_json FROM successor_transition_events "
        "WHERE transition_id=? AND phase=? "
        "AND event_type='RUNTIME_RELEASE_AUTHORIZED' ORDER BY sequence DESC",
        (target.transition_id, TransitionPhase.SUPERVISION_BOUND.value),
    ).fetchall()
    if len(supervision_row) != 1 or not release_rows:
        raise MultiUniverseTransitionError("SUPERVISION_CASH_CLASSIFICATION_REQUIRED")
    try:
        release = json.loads(str(release_rows[0][0]))
    except (TypeError, json.JSONDecodeError) as exc:
        raise MultiUniverseTransitionError("TRANSITION_PROJECTION_AMBIGUOUS") from exc
    evidence = release.get("evidence")
    if (
        not isinstance(evidence, Mapping)
        or release.get("phase") != TransitionPhase.SUPERVISION_BOUND.value
        or evidence.get("transition_phase") != TransitionPhase.SUPERVISION_BOUND.value
        or evidence.get("supervision_phase_event_sha256") != str(supervision_row[0][0])
    ):
        raise MultiUniverseTransitionError("SUPERVISION_CASH_CLASSIFICATION_REQUIRED")
    try:
        return MultiUniverseTransitionCoordinator._cash_classifications(evidence)
    except MultiUniverseTransitionError as exc:
        raise MultiUniverseTransitionError(
            "SUPERVISION_CASH_CLASSIFICATION_REQUIRED"
        ) from exc


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
    if payload.get("target_sha256") != target_sha256:
        raise MultiUniverseTransitionError("PREDECESSOR_RETIREMENT_NOT_PROVEN")
    return str(row[2])
