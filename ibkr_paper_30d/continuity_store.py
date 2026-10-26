"""Hash-verified projections over immutable continuity events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from decimal import Decimal
from typing import Any, Iterator, Mapping

from .canonical import canonical_bytes, sha256_json
from .continuity_models import (
    CodexOrderContinuityPlan,
    ContinuityEvaluation,
    ContinuityReview,
)
from .continuity_schema import verify_continuity_schema_v3, verify_continuity_schema_v4
from .persistence import Database
from .repositories import EventRepository, utc_now
from .types import new_uuid7


_UNSET = object()


class ContinuityStoreError(RuntimeError):
    pass


class ContinuityStore:
    def __init__(self, db: Database):
        try:
            verify_continuity_schema_v3(db)
        except Exception:
            try:
                verify_continuity_schema_v4(db)
            except Exception as exc:
                raise ContinuityStoreError("CONTINUITY_SCHEMA_V3_OR_V4_REQUIRED") from exc
        self.db = db

    @staticmethod
    def _event_hash(previous: str | None, payload: Mapping[str, Any]) -> str:
        return sha256_json({"previous_event_sha256": previous, "payload": payload})

    def _append(
        self,
        *,
        table: str,
        event_id: str,
        stream_column: str,
        stream_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        identity_columns: Mapping[str, object],
        expected_previous_event_sha256: str | None | object = _UNSET,
    ) -> str:
        payload_json = canonical_bytes(payload).decode("utf-8")
        payload_sha = sha256_json(payload)
        existing = self.db.execute(
            f"SELECT payload_json,event_sha256 FROM {table} WHERE event_id=?",
            (event_id,),
        ).fetchone()
        if existing is not None:
            if str(existing[0]) != payload_json:
                raise ContinuityStoreError("IDEMPOTENCY_CONFLICT")
            return str(existing[1])
        latest = self.db.execute(
            f"SELECT event_sha256 FROM {table} WHERE {stream_column}=? "
            "ORDER BY sequence DESC LIMIT 1",
            (stream_id,),
        ).fetchone()
        previous = str(latest[0]) if latest else None
        if (
            expected_previous_event_sha256 is not _UNSET
            and expected_previous_event_sha256 != previous
        ):
            raise ContinuityStoreError("PREDECESSOR_EVENT_MISMATCH")
        event_sha = self._event_hash(previous, payload)
        columns = ["event_id", *identity_columns, "event_type", "payload_json",
                   "payload_sha256", "previous_event_sha256", "event_sha256",
                   "created_at_utc"]
        values = [event_id, *identity_columns.values(), event_type, payload_json,
                  payload_sha, previous, event_sha, utc_now()]
        placeholders = ",".join("?" for _ in values)
        self.db.execute(
            f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})",
            tuple(values),
        )
        return event_sha

    def _iter_verified_rows(
        self, table: str, stream_column: str, stream_id: str
    ) -> Iterator[tuple[str, dict[str, Any], str]]:
        rows = self.db.execute(
            f"SELECT event_type,payload_json,payload_sha256,previous_event_sha256,"
            f"event_sha256 FROM {table} WHERE {stream_column}=? ORDER BY sequence",
            (stream_id,),
        )
        previous = None
        for event_type, payload_json, payload_sha, claimed_previous, event_sha in rows:
            try:
                payload = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ContinuityStoreError("PAYLOAD_INVALID") from exc
            if (
                claimed_previous != previous
                or sha256_json(payload) != str(payload_sha)
                or self._event_hash(previous, payload) != str(event_sha)
            ):
                raise ContinuityStoreError("HASH_MISMATCH")
            yield str(event_type), payload, str(event_sha)
            previous = str(event_sha)

    def _verified_rows(
        self, table: str, stream_column: str, stream_id: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        return list(self._iter_verified_rows(table, stream_column, stream_id))

    def _iter_verified_hash_rows(
        self, table: str, stream_column: str, stream_id: str
    ) -> Iterator[str]:
        rows = self.db.execute(
            f"SELECT event_type,payload_json,payload_sha256,previous_event_sha256,"
            f"event_sha256 FROM {table} WHERE {stream_column}=? ORDER BY sequence",
            (stream_id,),
        )
        previous = None
        for event_type, payload_json, payload_sha, claimed_previous, event_sha in rows:
            if not isinstance(payload_json, str):
                raise ContinuityStoreError("PAYLOAD_INVALID")
            payload_bytes = payload_json.encode("utf-8")
            event_bytes = (
                b'{"payload":'
                + payload_bytes
                + b',"previous_event_sha256":'
                + canonical_bytes(previous)
                + b"}"
            )
            if (
                claimed_previous != previous
                or hashlib.sha256(payload_bytes).hexdigest() != str(payload_sha)
                or hashlib.sha256(event_bytes).hexdigest() != str(event_sha)
            ):
                raise ContinuityStoreError("HASH_MISMATCH")
            yield str(event_type)
            previous = str(event_sha)

    def verify_all_chains(self) -> dict[str, int]:
        streams = {
            "continuity_plan_events": "order_ref",
            "provider_invocation_events": "invocation_id",
            "continuity_watchdog_events": "order_ref",
            "continuity_evaluation_events": "order_ref",
            "continuity_execution_events": "order_ref",
            "continuity_report_events": "outage_id",
            "continuity_review_events": "report_id",
            "continuity_reflection_events": "review_id",
        }
        counts: dict[str, int] = {}
        for table, stream_column in streams.items():
            stream_ids = [
                str(row[0])
                for row in self.db.execute(
                    f"SELECT DISTINCT {stream_column} FROM {table}"
                ).fetchall()
            ]
            counts[table] = sum(
                sum(
                    1
                    for _ in self._iter_verified_hash_rows(
                        table, stream_column, stream_id
                    )
                )
                for stream_id in stream_ids
            )
        return counts

    def append_plan_event(
        self,
        event_type: str,
        plan: CodexOrderContinuityPlan,
        *,
        event_id: str | None = None,
        expected_previous_event_sha256: str | None | object = _UNSET,
        bindings: Mapping[str, Any] | None = None,
    ) -> str:
        order_ref = plan.order_binding.order_ref
        event_id = event_id or str(new_uuid7())
        plan_payload = plan.model_dump(mode="json", exclude_unset=True)
        payload = {
            "plan": plan_payload,
            "plan_sha256": plan.sha256,
            "bindings": dict(bindings or {}),
        }
        with self.db.transaction():
            existing = self.db.execute(
                "SELECT payload_json,event_sha256 FROM continuity_plan_events "
                "WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != canonical_bytes(payload).decode("utf-8"):
                    raise ContinuityStoreError("IDEMPOTENCY_CONFLICT")
                return str(existing[1])
            active = self.active_plan(order_ref)
            if event_type == "ACTIVATED":
                if active is not None:
                    raise ContinuityStoreError("ACTIVE_PLAN_CONFLICT")
                if plan.predecessor_plan_sha256 is not None:
                    raise ContinuityStoreError("PREDECESSOR_PLAN_MISMATCH")
            elif event_type == "SUPERSEDED":
                if active is None or plan.predecessor_plan_sha256 != active.sha256:
                    raise ContinuityStoreError("PREDECESSOR_PLAN_MISMATCH")
            elif event_type == "TERMINAL":
                if active is None or active.sha256 != plan.sha256:
                    raise ContinuityStoreError("TERMINAL_PLAN_MISMATCH")
            elif event_type not in {
                "DRAFTED", "VALIDATED", "BIND_PENDING", "BIND_TERMINAL"
            }:
                raise ContinuityStoreError("PLAN_EVENT_TYPE_INVALID")
            return self._append(
                table="continuity_plan_events",
                event_id=event_id,
                stream_column="order_ref",
                stream_id=order_ref,
                event_type=event_type,
                payload=payload,
                identity_columns={"plan_id": plan.plan_id, "order_ref": order_ref},
                expected_previous_event_sha256=expected_previous_event_sha256,
            )

    def plan_chain(self, order_ref: str) -> list[CodexOrderContinuityPlan]:
        active: CodexOrderContinuityPlan | None = None
        invalid_activation_sha256: str | None = None
        chain: list[CodexOrderContinuityPlan] = []
        terminals: set[str] = set()
        for event_type, payload, event_sha256 in self._verified_rows(
            "continuity_plan_events", "order_ref", order_ref
        ):
            try:
                plan = CodexOrderContinuityPlan.model_validate(payload["plan"])
            except Exception as exc:
                raise ContinuityStoreError("PAYLOAD_INVALID") from exc
            if payload.get("plan_sha256") != plan.sha256:
                raise ContinuityStoreError("HASH_MISMATCH")
            if event_type in {
                "DRAFTED", "VALIDATED", "BIND_PENDING", "BIND_TERMINAL"
            }:
                continue
            if event_type == "ACTIVATED":
                if active is not None or invalid_activation_sha256 is not None:
                    raise ContinuityStoreError("ACTIVE_PLAN_FORK")
                if plan.predecessor_plan_sha256 is not None:
                    invalid_activation_sha256 = event_sha256
                else:
                    active = plan
                chain.append(plan)
            elif event_type == "SUPERSEDED":
                if active is None or plan.predecessor_plan_sha256 != active.sha256:
                    raise ContinuityStoreError("ACTIVE_PLAN_FORK")
                active = plan
                chain.append(plan)
            elif event_type == "TERMINAL":
                bindings = payload.get("bindings") or {}
                if invalid_activation_sha256 is not None:
                    if (
                        active is not None
                        or plan.sha256 in terminals
                        or bindings.get("invalid_activation_event_sha256")
                        != invalid_activation_sha256
                    ):
                        raise ContinuityStoreError("INVALID_RECOVERY_TERMINAL")
                    invalid_activation_sha256 = None
                elif active is None or active.sha256 != plan.sha256 or plan.sha256 in terminals:
                    raise ContinuityStoreError("DUPLICATE_OR_INVALID_TERMINAL")
                terminals.add(plan.sha256)
                active = None
        if invalid_activation_sha256 is not None:
            raise ContinuityStoreError("ACTIVE_PLAN_FORK")
        return chain

    def active_plan(self, order_ref: str) -> CodexOrderContinuityPlan | None:
        active: CodexOrderContinuityPlan | None = None
        invalid_activation_sha256: str | None = None
        terminals: set[str] = set()
        for event_type, payload, event_sha256 in self._verified_rows(
            "continuity_plan_events", "order_ref", order_ref
        ):
            try:
                plan = CodexOrderContinuityPlan.model_validate(payload["plan"])
            except Exception as exc:
                raise ContinuityStoreError("PAYLOAD_INVALID") from exc
            if payload.get("plan_sha256") != plan.sha256:
                raise ContinuityStoreError("HASH_MISMATCH")
            if event_type in {
                "DRAFTED", "VALIDATED", "BIND_PENDING", "BIND_TERMINAL"
            }:
                continue
            if event_type == "ACTIVATED":
                if active is not None or invalid_activation_sha256 is not None:
                    raise ContinuityStoreError("ACTIVE_PLAN_FORK")
                if plan.predecessor_plan_sha256 is not None:
                    invalid_activation_sha256 = event_sha256
                else:
                    active = plan
            elif event_type == "SUPERSEDED":
                if active is None or plan.predecessor_plan_sha256 != active.sha256:
                    raise ContinuityStoreError("ACTIVE_PLAN_FORK")
                active = plan
            elif event_type == "TERMINAL":
                bindings = payload.get("bindings") or {}
                if invalid_activation_sha256 is not None:
                    if (
                        active is not None
                        or plan.sha256 in terminals
                        or bindings.get("invalid_activation_event_sha256")
                        != invalid_activation_sha256
                    ):
                        raise ContinuityStoreError("INVALID_RECOVERY_TERMINAL")
                    invalid_activation_sha256 = None
                elif active is None or active.sha256 != plan.sha256:
                    raise ContinuityStoreError("DUPLICATE_OR_INVALID_TERMINAL")
                terminals.add(plan.sha256)
                active = None
        if invalid_activation_sha256 is not None:
            raise ContinuityStoreError("ACTIVE_PLAN_FORK")
        return active

    def append_recovery_terminal(
        self,
        plan: CodexOrderContinuityPlan,
        *,
        invalid_activation_event_sha256: str,
        broker_evidence_sha256: str,
        reason_code: str,
    ) -> str:
        """Close one historical activation that bypassed predecessor validation."""
        order_ref = plan.order_binding.order_ref
        rows = self._verified_rows("continuity_plan_events", "order_ref", order_ref)
        matches = [
            (payload, event_sha256)
            for event_type, payload, event_sha256 in rows
            if event_type == "ACTIVATED"
            and payload.get("plan_sha256") == plan.sha256
            and event_sha256 == invalid_activation_event_sha256
        ]
        if (
            len(matches) != 1
            or plan.predecessor_plan_sha256 is None
            or not rows
            or rows[-1][2] != invalid_activation_event_sha256
        ):
            raise ContinuityStoreError("RECOVERY_ACTIVATION_MISMATCH")
        payload = {
            "plan": plan.model_dump(mode="json", exclude_unset=True),
            "plan_sha256": plan.sha256,
            "bindings": {
                "reason_code": reason_code,
                "invalid_activation_event_sha256": invalid_activation_event_sha256,
                "broker_evidence_sha256": broker_evidence_sha256,
            },
        }
        with self.db.transaction():
            return self._append(
                table="continuity_plan_events",
                event_id=f"continuity-recovery-terminal:{plan.plan_id}:{plan.sha256}",
                stream_column="order_ref",
                stream_id=order_ref,
                event_type="TERMINAL",
                payload=payload,
                identity_columns={"plan_id": plan.plan_id, "order_ref": order_ref},
                expected_previous_event_sha256=invalid_activation_event_sha256,
            )

    def terminalize_active_plan_in_transaction(
        self,
        order_ref: str,
        *,
        broker_evidence_sha256: str,
        reason_code: str,
        expected_contract_sha256: str | None = None,
    ) -> str | None:
        """Close a broker-flat active plan in the caller's release transaction."""
        if not self.db.connection.in_transaction:
            raise ContinuityStoreError("ATOMIC_PLAN_TERMINAL_TRANSACTION_REQUIRED")
        plan = self.active_plan(order_ref)
        if plan is None:
            return None
        if (
            expected_contract_sha256 is not None
            and plan.canonical_contract_sha256 is not None
            and plan.canonical_contract_sha256 != expected_contract_sha256
        ):
            raise ContinuityStoreError("TERMINAL_PLAN_CONTRACT_MISMATCH")
        payload = {
            "plan": plan.model_dump(mode="json", exclude_unset=True),
            "plan_sha256": plan.sha256,
            "bindings": {
                "reason_code": reason_code,
                "broker_evidence_sha256": broker_evidence_sha256,
            },
        }
        return self._append(
            table="continuity_plan_events",
            event_id=(
                f"continuity-terminal-reservation-released:"
                f"{plan.plan_id}:{plan.sha256}"
            ),
            stream_column="order_ref",
            stream_id=order_ref,
            event_type="TERMINAL",
            payload=payload,
            identity_columns={"plan_id": plan.plan_id, "order_ref": order_ref},
        )

    def active_plans(self) -> tuple[CodexOrderContinuityPlan, ...]:
        order_refs = tuple(
            str(row[0])
            for row in self.db.execute(
                "SELECT DISTINCT order_ref FROM continuity_plan_events "
                "ORDER BY order_ref"
            ).fetchall()
        )
        return tuple(
            plan
            for order_ref in order_refs
            if (plan := self.active_plan(order_ref)) is not None
        )

    def append_provider_event(
        self, invocation_id: str, state: str, payload: Mapping[str, Any], *, event_id: str | None = None
    ) -> str:
        body = {"state": state, "payload": dict(payload)}
        with self.db.transaction():
            return self._append(
                table="provider_invocation_events", event_id=event_id or str(new_uuid7()),
                stream_column="invocation_id", stream_id=invocation_id, event_type=state,
                payload=body, identity_columns={"invocation_id": invocation_id},
            )

    def provider_projection(self, invocation_id: str) -> dict[str, Any]:
        rows = self._verified_rows("provider_invocation_events", "invocation_id", invocation_id)
        if not rows:
            return {"invocation_id": invocation_id, "state": "IDLE", "payload": {}}
        _, body, event_hash = rows[-1]
        return {"invocation_id": invocation_id, **body, "event_sha256": event_hash}

    def latest_provider_projection(self) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT invocation_id FROM provider_invocation_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return {"invocation_id": None, "state": "IDLE", "payload": {}}
        return self.provider_projection(str(row[0]))

    def append_watchdog_event(
        self, order_ref: str, event_type: str, payload: Mapping[str, Any]
    ) -> str:
        with self.db.transaction():
            return self._append(
                table="continuity_watchdog_events", event_id=str(new_uuid7()),
                stream_column="order_ref", stream_id=order_ref, event_type=event_type,
                payload=payload, identity_columns={"order_ref": order_ref},
            )

    def append_evaluation(self, evaluation: ContinuityEvaluation, order_ref: str) -> str:
        payload = evaluation.model_dump(mode="json")
        with self.db.transaction():
            existing = self.db.execute(
                "SELECT payload_json, plan_id, order_ref, event_sha256 "
                "FROM continuity_evaluation_events WHERE evaluation_id=?",
                (evaluation.evaluation_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != canonical_bytes(payload).decode("utf-8"):
                    raise ContinuityStoreError("EVALUATION_IDENTITY_COLLISION")
                if str(existing[1]) != evaluation.plan_id:
                    raise ContinuityStoreError("EVALUATION_PLAN_ID_MISMATCH")
                if str(existing[2]) != order_ref:
                    raise ContinuityStoreError("EVALUATION_ORDER_REF_MISMATCH")
                return str(existing[3])
            return self._append(
                table="continuity_evaluation_events", event_id=str(new_uuid7()),
                stream_column="order_ref", stream_id=order_ref, event_type="EVALUATED",
                payload=payload, identity_columns={
                    "evaluation_id": evaluation.evaluation_id,
                    "plan_id": evaluation.plan_id,
                    "order_ref": order_ref,
                },
            )

    def append_execution_event(
        self, execution_id: str, evaluation_id: str, plan_id: str, order_ref: str,
        execution_ordinal: int, event_type: str, payload: Mapping[str, Any],
    ) -> str:
        try:
            with self.db.transaction():
                return self._append(
                    table="continuity_execution_events", event_id=str(new_uuid7()),
                    stream_column="order_ref", stream_id=order_ref, event_type=event_type,
                    payload=payload, identity_columns={
                        "execution_id": execution_id, "evaluation_id": evaluation_id,
                        "plan_id": plan_id, "order_ref": order_ref,
                        "execution_ordinal": execution_ordinal,
                    },
                )
        except sqlite3.IntegrityError as exc:
            raise ContinuityStoreError("EXECUTION_ORDINAL_CONFLICT") from exc

    @staticmethod
    def _require_sha256(name: str, value: str | None, *, optional: bool = False) -> None:
        if optional and value is None:
            return
        if value is None or len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ContinuityStoreError(f"{name.upper()}_INVALID")

    def append_production_write_attempt(
        self,
        *,
        request_id: str,
        request_sha256: str,
        execution_key: str,
        authority_snapshot_sha256: str,
        broker_evidence_sha256: str,
        liability_evidence_sha256: str | None,
    ) -> str:
        """Append the pre-send authority receipt in its own short transaction."""

        for name, value in (
            ("request_sha256", request_sha256),
            ("authority_snapshot_sha256", authority_snapshot_sha256),
            ("broker_evidence_sha256", broker_evidence_sha256),
        ):
            self._require_sha256(name, value)
        self._require_sha256(
            "liability_evidence_sha256",
            liability_evidence_sha256,
            optional=True,
        )
        payload = {
            "schema": "BROKER_WRITE_ATTEMPT_V1",
            "request_id": request_id,
            "request_sha256": request_sha256,
            "execution_key": execution_key,
            "authority_snapshot_sha256": authority_snapshot_sha256,
            "broker_evidence_sha256": broker_evidence_sha256,
            "liability_evidence_sha256": liability_evidence_sha256,
        }
        with self.db.transaction():
            return EventRepository(self.db).append("BROKER_WRITE_ATTEMPT_V1", payload)

    def append_production_write_result(
        self,
        *,
        request_id: str,
        request_sha256: str,
        execution_key: str,
        result_sha256: str,
        status: str,
        success: bool,
    ) -> str:
        """Append the post-reconciliation receipt in a new short transaction."""

        self._require_sha256("request_sha256", request_sha256)
        self._require_sha256("result_sha256", result_sha256)
        payload = {
            "schema": "BROKER_WRITE_RESULT_V1",
            "request_id": request_id,
            "request_sha256": request_sha256,
            "execution_key": execution_key,
            "result_sha256": result_sha256,
            "status": status,
            "success": success,
        }
        with self.db.transaction():
            return EventRepository(self.db).append("BROKER_WRITE_RESULT_V1", payload)

    def append_report(self, report_id: str, outage_id: str, payload: Mapping[str, Any]) -> str:
        with self.db.transaction():
            self._append(
                table="continuity_report_events", event_id=str(new_uuid7()),
                stream_column="outage_id", stream_id=outage_id, event_type="CREATED",
                payload=payload, identity_columns={"report_id": report_id, "outage_id": outage_id},
            )
        return sha256_json(payload)

    def pending_reports(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT report_id,payload_json,payload_sha256 FROM continuity_report_events "
            "ORDER BY sequence"
        ).fetchall()
        reviewed = set()
        for report_id, payload_json in self.db.execute(
            "SELECT report_id,payload_json FROM continuity_review_events"
        ).fetchall():
            try:
                review = ContinuityReview.model_validate_json(str(payload_json))
            except Exception as exc:
                raise ContinuityStoreError("PAYLOAD_INVALID") from exc
            if review.disposition != "MORE_RESEARCH_REQUIRED":
                reviewed.add(str(report_id))
        result = []
        for report_id, payload_json, payload_sha in rows:
            payload = json.loads(str(payload_json))
            if sha256_json(payload) != str(payload_sha):
                raise ContinuityStoreError("HASH_MISMATCH")
            if str(report_id) not in reviewed:
                result.append(payload)
        return result

    def append_review(self, review: ContinuityReview) -> str:
        report = self.db.execute(
            "SELECT payload_sha256 FROM continuity_report_events WHERE report_id=?",
            (review.report_id,),
        ).fetchone()
        if report is None:
            raise ContinuityStoreError("REPORT_NOT_FOUND")
        if str(report[0]) != review.report_sha256:
            raise ContinuityStoreError("REPORT_HASH_MISMATCH")
        with self.db.transaction():
            return self._append(
                table="continuity_review_events", event_id=str(new_uuid7()),
                stream_column="report_id", stream_id=review.report_id, event_type="REVIEWED",
                payload=review.model_dump(mode="json"), identity_columns={
                    "review_id": review.review_id, "report_id": review.report_id,
                    "report_sha256": review.report_sha256,
                    "invocation_id": review.invocation_id,
                },
            )

    def append_reflection(
        self, reflection_id: str, review_id: str, payload: Mapping[str, Any]
    ) -> str:
        if self.db.execute(
            "SELECT 1 FROM continuity_review_events WHERE review_id=?", (review_id,)
        ).fetchone() is None:
            raise ContinuityStoreError("REVIEW_NOT_FOUND")
        with self.db.transaction():
            return self._append(
                table="continuity_reflection_events", event_id=str(new_uuid7()),
                stream_column="review_id", stream_id=review_id, event_type="RECORDED",
                payload=payload, identity_columns={
                    "reflection_id": reflection_id, "review_id": review_id
                },
            )

    _TERMINAL_INTENT_STATES = frozenset({"BROKER_CONFIRMED"})

    _INTENT_TRANSITIONS: dict[str, frozenset[str]] = {
        "INTENT_RECORDED": frozenset({"SUBMISSION_ATTEMPTED"}),
        "SUBMISSION_ATTEMPTED": frozenset({"BROKER_CONFIRMED", "RESULT_UNKNOWN"}),
        "RESULT_UNKNOWN": frozenset(),
    }

    def _latest_intent_row(self, intent_id: str) -> tuple | None:
        return self.db.execute(
            "SELECT intent_id, plan_id, order_ref, evaluation_id, execution_key, "
            "command_type, command_sha256, intent_state, payload_json "
            "FROM continuity_execution_intents "
            "WHERE intent_id=? "
            "ORDER BY sequence DESC LIMIT 1",
            (intent_id,),
        ).fetchone()

    def reserve_execution_intent(
        self,
        *,
        plan_id: str,
        order_ref: str,
        evaluation_id: str | None,
        execution_key: str | None,
        command_type: str | None,
        command_sha256: str | None,
        payload: Mapping[str, Any],
    ) -> str:
        """Atomically reserve a new intent if no active intent exists.

        Returns the stable intent_id. Raises ContinuityStoreError if an active
        intent already blocks this operational scope.
        """
        verify_continuity_schema_v4(self.db)
        body = dict(payload)
        body["intent_state"] = "INTENT_RECORDED"
        with self.db.transaction():
            # Any unresolved writer outcome can affect aggregate account
            # exposure, so it blocks every new execution intent.
            row = self.db.execute(
                "SELECT plan_id,order_ref,intent_state "
                "FROM continuity_execution_intents current "
                "WHERE sequence=("
                "SELECT MAX(sequence) FROM continuity_execution_intents "
                "WHERE intent_id=current.intent_id"
                ") AND intent_state NOT IN ('BROKER_CONFIRMED') "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            if row is not None:
                reason = (
                    "ACTIVE_INTENT_BARRIER"
                    if str(row[0]) == plan_id and str(row[1]) == order_ref
                    else "GLOBAL_ACTIVE_INTENT_BARRIER"
                )
                raise ContinuityStoreError(reason)
            intent_id = str(new_uuid7())
            return self._append(
                table="continuity_execution_intents",
                event_id=str(new_uuid7()),
                stream_column="order_ref",
                stream_id=order_ref,
                event_type="INTENT_RECORDED",
                payload=body,
                identity_columns={
                    "intent_id": intent_id,
                    "plan_id": plan_id,
                    "order_ref": order_ref,
                    "evaluation_id": evaluation_id or "",
                    "execution_key": execution_key or "",
                    "intent_state": "INTENT_RECORDED",
                    "command_type": command_type or "",
                    "command_sha256": command_sha256 or "",
                },
            ), intent_id

    def transition_execution_intent(
        self,
        *,
        intent_id: str,
        plan_id: str,
        order_ref: str,
        evaluation_id: str | None,
        execution_key: str | None,
        intent_state: str,
        command_type: str | None,
        command_sha256: str | None,
        payload: Mapping[str, Any],
    ) -> str:
        """Append a state transition for an existing intent.

        Validates intent identity, state machine, and reconciliation evidence.
        All transitions for the same logical intent share the same intent_id.
        """
        verify_continuity_schema_v4(self.db)

        body = dict(payload)
        body["intent_state"] = intent_state

        with self.db.transaction():
            latest = self._latest_intent_row(intent_id)
            if latest is None:
                raise ContinuityStoreError("INTENT_NOT_FOUND")

            # A. Identity immutability validation
            # Column indices: 0=intent_id, 1=plan_id, 2=order_ref, 3=evaluation_id,
            # 4=execution_key, 5=command_type, 6=command_sha256, 7=intent_state
            identity_checks = [
                (1, plan_id, "plan_id"),
                (2, order_ref, "order_ref"),
                (3, evaluation_id or "", "evaluation_id"),
                (4, execution_key or "", "execution_key"),
                (5, command_type or "", "command_type"),
                (6, command_sha256 or "", "command_sha256"),
            ]
            for idx, expected, name in identity_checks:
                actual = str(latest[idx])
                if actual != expected:
                    raise ContinuityStoreError(
                        f"INTENT_IDENTITY_MISMATCH:{name}"
                    )

            current_state = str(latest[7])

            # B. State machine enforcement
            if current_state in self._TERMINAL_INTENT_STATES:
                raise ContinuityStoreError("INTENT_ALREADY_TERMINAL")
            allowed = self._INTENT_TRANSITIONS.get(current_state, frozenset())
            if intent_state not in allowed:
                raise ContinuityStoreError(
                    f"INTENT_TRANSITION_INVALID:{current_state}->{intent_state}"
                )

            return self._append(
                table="continuity_execution_intents",
                event_id=str(new_uuid7()),
                stream_column="order_ref",
                stream_id=order_ref,
                event_type=intent_state,
                payload=body,
                identity_columns={
                    "intent_id": intent_id,
                    "plan_id": plan_id,
                    "order_ref": order_ref,
                    "evaluation_id": evaluation_id or "",
                    "execution_key": execution_key or "",
                    "intent_state": intent_state,
                    "command_type": command_type or "",
                    "command_sha256": command_sha256 or "",
                },
            )

    def reconcile_execution_intent(
        self,
        *,
        intent_id: str,
        broker_evidence: Mapping[str, Any],
    ) -> str:
        """Attempt to reconcile an intent using verifiable broker evidence.

        Authentic reconciliation requires evidence from a controlled broker
        read path bound to the original intent identity. Since no authenticated
        reconciliation path is implementable with current components,
        RESULT_UNKNOWN remains permanently blocked.
        """
        verify_continuity_schema_v4(self.db)
        raise ContinuityStoreError("RECONCILIATION_NOT_AUTHENTICATED")

    def latest_execution_intent(
        self, plan_id: str, order_ref: str
    ) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT intent_id, intent_state, execution_key, command_sha256, event_sha256 "
            "FROM continuity_execution_intents "
            "WHERE plan_id=? AND order_ref=? "
            "ORDER BY sequence DESC LIMIT 1",
            (plan_id, order_ref),
        ).fetchone()
        if row is None:
            return None
        return {
            "intent_id": str(row[0]),
            "intent_state": str(row[1]),
            "execution_key": str(row[2]),
            "command_sha256": str(row[3]),
            "event_sha256": str(row[4]),
        }

    def has_active_execution_intent(self, plan_id: str, order_ref: str) -> bool:
        latest = self.latest_execution_intent(plan_id, order_ref)
        return latest is not None and latest["intent_state"] not in self._TERMINAL_INTENT_STATES

    def active_execution_intent(self) -> dict[str, str] | None:
        row = self.db.execute(
            "SELECT intent_id,plan_id,order_ref,intent_state "
            "FROM continuity_execution_intents current "
            "WHERE sequence=("
            "SELECT MAX(sequence) FROM continuity_execution_intents "
            "WHERE intent_id=current.intent_id"
            ") AND intent_state NOT IN ('BROKER_CONFIRMED') "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return {
            "intent_id": str(row[0]),
            "plan_id": str(row[1]),
            "order_ref": str(row[2]),
            "intent_state": str(row[3]),
        }
