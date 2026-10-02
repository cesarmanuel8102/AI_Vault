"""Hash-verified projections over immutable continuity events."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping

from .canonical import canonical_bytes, sha256_json
from .continuity_models import (
    CodexOrderContinuityPlan,
    ContinuityEvaluation,
    ContinuityReview,
)
from .continuity_schema import verify_continuity_schema_v3
from .persistence import Database
from .repositories import EventRepository, utc_now
from .types import new_uuid7


_UNSET = object()


class ContinuityStoreError(RuntimeError):
    pass


class ContinuityStore:
    def __init__(self, db: Database):
        verify_continuity_schema_v3(db)
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

    def _verified_rows(
        self, table: str, stream_column: str, stream_id: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        rows = self.db.execute(
            f"SELECT event_type,payload_json,payload_sha256,previous_event_sha256,"
            f"event_sha256 FROM {table} WHERE {stream_column}=? ORDER BY sequence",
            (stream_id,),
        ).fetchall()
        previous = None
        result = []
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
            result.append((str(event_type), payload, str(event_sha)))
            previous = str(event_sha)
        return result

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
                len(self._verified_rows(table, stream_column, stream_id))
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
        payload = {
            "plan": plan.model_dump(mode="json"),
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
        chain: list[CodexOrderContinuityPlan] = []
        terminals: set[str] = set()
        for event_type, payload, _ in self._verified_rows(
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
                if active is not None or plan.predecessor_plan_sha256 is not None:
                    raise ContinuityStoreError("ACTIVE_PLAN_FORK")
                active = plan
                chain.append(plan)
            elif event_type == "SUPERSEDED":
                if active is None or plan.predecessor_plan_sha256 != active.sha256:
                    raise ContinuityStoreError("ACTIVE_PLAN_FORK")
                active = plan
                chain.append(plan)
            elif event_type == "TERMINAL":
                if active is None or active.sha256 != plan.sha256 or plan.sha256 in terminals:
                    raise ContinuityStoreError("DUPLICATE_OR_INVALID_TERMINAL")
                terminals.add(plan.sha256)
                active = None
        return chain

    def active_plan(self, order_ref: str) -> CodexOrderContinuityPlan | None:
        active: CodexOrderContinuityPlan | None = None
        for event_type, payload, _ in self._verified_rows(
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
                if active is not None or plan.predecessor_plan_sha256 is not None:
                    raise ContinuityStoreError("ACTIVE_PLAN_FORK")
                active = plan
            elif event_type == "SUPERSEDED":
                if active is None or plan.predecessor_plan_sha256 != active.sha256:
                    raise ContinuityStoreError("ACTIVE_PLAN_FORK")
                active = plan
            elif event_type == "TERMINAL":
                if active is None or active.sha256 != plan.sha256:
                    raise ContinuityStoreError("DUPLICATE_OR_INVALID_TERMINAL")
                active = None
        return active

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
