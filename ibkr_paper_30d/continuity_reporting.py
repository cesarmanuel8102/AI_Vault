"""Factual outage reports and mechanical continuity-review authority gating."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from .canonical import sha256_json
from .continuity_models import (
    ContinuityAuthorityClass,
    ContinuityReview,
    ContinuityReviewDisposition,
)
from .continuity_store import ContinuityStore
from .trader_invocation import TraderDecision


class ContinuityReportingError(RuntimeError):
    pass


class ContinuityReport(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    schema: str = "CONTINUITY_REPORT_V1"
    report_id: str
    outage_id: str
    outage_started_at_utc: datetime
    outage_ended_at_utc: datetime
    duration_seconds: Decimal = Field(ge=0)
    failure_codes: tuple[str, ...]
    plans: tuple[dict[str, Any], ...]
    evaluations: tuple[dict[str, Any], ...]
    executions: tuple[dict[str, Any], ...]
    broker_order_state: dict[str, Any]
    broker_executions: tuple[dict[str, Any], ...]
    broker_positions: tuple[dict[str, Any], ...]
    market_observations: tuple[dict[str, Any], ...]
    expectations: tuple[str, ...]
    arithmetic_differences: tuple[dict[str, str], ...]
    unresolved_questions: tuple[str, ...]

    @property
    def sha256(self) -> str:
        return sha256_json(self)


class AuthorityDecision(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    authorized: bool
    authority_class: ContinuityAuthorityClass
    reason_codes: tuple[str, ...] = ()


def _value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


class ContinuityReportBuilder:
    _PROHIBITED = re.compile(
        r"\b(good|bad|aggressive|conservative|rational|irrational)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        store: ContinuityStore,
        *,
        recovery_observation_reader: Callable[[str], Mapping[str, Any]],
    ) -> None:
        self.store = store
        self.recovery_observation_reader = recovery_observation_reader

    def _payloads(self, table: str, *, where: str = "", args=()) -> list[dict[str, Any]]:
        rows = self.store.db.execute(
            f"SELECT event_type,payload_json,payload_sha256 FROM {table} "
            f"{where} ORDER BY sequence",
            tuple(args),
        ).fetchall()
        result = []
        for event_type, payload_json, payload_sha256 in rows:
            try:
                payload = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ContinuityReportingError("REPORT_SOURCE_INVALID") from exc
            if not isinstance(payload, dict) or sha256_json(payload) != str(
                payload_sha256
            ):
                raise ContinuityReportingError("REPORT_SOURCE_HASH_MISMATCH")
            result.append({"event_type": str(event_type), "payload": payload})
        return result

    @staticmethod
    def _time(raw: Any) -> datetime:
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContinuityReportingError("OUTAGE_TIME_INVALID") from exc
        if value.tzinfo is None or value.utcoffset() is None:
            raise ContinuityReportingError("OUTAGE_TIME_INVALID")
        return value

    def build(self, outage_id: str) -> ContinuityReport:
        provider = self._payloads(
            "provider_invocation_events",
            where="WHERE invocation_id=?",
            args=(outage_id,),
        )
        in_flight = next(
            (item for item in provider if item["event_type"] == "IN_FLIGHT"), None
        )
        terminal = next(
            (
                item
                for item in reversed(provider)
                if item["event_type"]
                in {"TIMEOUT_CONFIRMED", "PROCESS_ERROR", "ABANDONED"}
            ),
            None,
        )
        if in_flight is None or terminal is None:
            raise ContinuityReportingError("OUTAGE_INTERVAL_INCOMPLETE")
        start_payload = in_flight["payload"].get("payload") or {}
        terminal_payload = terminal["payload"].get("payload") or {}
        start = self._time(start_payload.get("broker_time_utc"))
        end = self._time(terminal_payload.get("broker_time_utc"))
        if end < start:
            raise ContinuityReportingError("OUTAGE_TIME_BACKWARD")

        plan_rows = self._payloads("continuity_plan_events")[-64:]
        plans: list[dict[str, Any]] = []
        expectations: list[str] = []
        for item in plan_rows:
            payload = item["payload"]
            plan = payload.get("plan")
            if not isinstance(plan, dict):
                continue
            plans.append(
                {
                    "event_type": item["event_type"],
                    "plan_id": str(plan.get("plan_id") or ""),
                    "plan_version": int(plan.get("plan_version") or 0),
                    "plan_sha256": str(payload.get("plan_sha256") or ""),
                    "order_ref": str(
                        (plan.get("order_binding") or {}).get("order_ref") or ""
                    ),
                }
            )
            for contingency in plan.get("contingencies") or []:
                if not isinstance(contingency, dict):
                    continue
                for expectation in contingency.get("expectations") or []:
                    expectations.append(str(expectation))

        evaluations = []
        for item in self._payloads("continuity_evaluation_events")[-128:]:
            payload = dict(item["payload"])
            payload["action_sha256"] = (
                sha256_json(payload["selected_action"])
                if payload.get("selected_action") is not None
                else None
            )
            evaluations.append(payload)
        executions = [
            dict(item["payload"])
            for item in self._payloads("continuity_execution_events")[-128:]
        ]

        observation = dict(self.recovery_observation_reader(outage_id) or {})
        annotations = observation.get("observer_annotations") or []
        if any(self._PROHIBITED.search(str(value)) for value in annotations):
            raise ContinuityReportingError("STRATEGIC_LABEL_PROHIBITED")
        broker_order = dict(observation.get("broker_order_state") or {})
        differences: list[dict[str, str]] = []
        if plans and broker_order.get("limit_price") is not None:
            last_plan = next(
                (
                    item["payload"].get("plan")
                    for item in reversed(plan_rows)
                    if isinstance(item["payload"].get("plan"), dict)
                ),
                None,
            )
            expected = (last_plan.get("order_binding") or {}).get(
                "original_limit_price"
            ) if last_plan else None
            if expected is not None:
                expected_decimal = Decimal(str(expected))
                observed_decimal = Decimal(str(broker_order["limit_price"]))
                differences.append(
                    {
                        "field": "order_limit_price",
                        "expected": str(expected_decimal),
                        "observed": str(broker_order["limit_price"]),
                        "difference": str(observed_decimal - expected_decimal),
                    }
                )

        failure_codes = tuple(
            dict.fromkeys(
                str((item["payload"].get("payload") or {}).get("failure_code"))
                for item in provider
                if (item["payload"].get("payload") or {}).get("failure_code")
            )
        )
        return ContinuityReport(
            report_id=f"continuity-report:{outage_id}",
            outage_id=outage_id,
            outage_started_at_utc=start,
            outage_ended_at_utc=end,
            duration_seconds=Decimal(str((end - start).total_seconds())),
            failure_codes=failure_codes,
            plans=tuple(plans),
            evaluations=tuple(evaluations),
            executions=tuple(executions),
            broker_order_state=broker_order,
            broker_executions=tuple(observation.get("executions") or ()),
            broker_positions=tuple(observation.get("positions") or ()),
            market_observations=tuple(
                observation.get("market_observations") or ()
            ),
            expectations=tuple(expectations),
            arithmetic_differences=tuple(differences),
            unresolved_questions=tuple(
                str(value)
                for value in observation.get("unresolved_questions") or ()
            ),
        )


class ContinuityReviewGate:
    _NONEXPANDING = frozenset(
        {
            ContinuityAuthorityClass.RECONCILIATION,
            ContinuityAuthorityClass.OBSERVATION,
            ContinuityAuthorityClass.CANCEL_ORDER,
            ContinuityAuthorityClass.REDUCE_POSITION,
            ContinuityAuthorityClass.CLOSE_POSITION,
            ContinuityAuthorityClass.PREAUTHORIZED_CONTINUITY,
            ContinuityAuthorityClass.NONEXPANDING_EXISTING_AUTHORITY,
        }
    )

    def __init__(
        self,
        store: ContinuityStore | None,
        *,
        accepted_result_reader: Callable[[str], Mapping[str, Any] | None]
        | None = None,
    ) -> None:
        self.store = store
        self.accepted_result_reader = (
            accepted_result_reader or self._read_accepted_result
        )

    def _read_accepted_result(self, invocation_id: str) -> Mapping[str, Any] | None:
        if self.store is None:
            return None
        row = self.store.db.execute(
            "SELECT invocation_id,payload_json,accepted FROM trader_results "
            "WHERE invocation_id=?",
            (invocation_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(str(row[1]))
        except (TypeError, json.JSONDecodeError) as exc:
            raise ContinuityReportingError("ACCEPTED_RESULT_INVALID") from exc
        if not isinstance(payload, dict):
            raise ContinuityReportingError("ACCEPTED_RESULT_INVALID")
        payload["continuity_reviews"] = []
        return {
            "invocation_id": str(row[0]),
            "payload_sha256": sha256_json(payload),
            "accepted": bool(row[2]),
        }

    @staticmethod
    def _find_order(action: Any, bundle: Any) -> Mapping[str, Any] | None:
        order_ref = _value(action, "order_ref")
        order_id = _value(action, "order_id")
        perm_id = _value(action, "perm_id")
        client_id = _value(action, "client_id")
        for order in _value(bundle, "open_orders_snapshot", []) or []:
            if (
                str(order.get("orderRef")) == str(order_ref)
                and int(order.get("orderId") or 0) == int(order_id or 0)
                and int(order.get("permId") or 0) == int(perm_id or 0)
                and int(order.get("clientId") or 0) == int(client_id or 0)
            ):
                return order
        return None

    @staticmethod
    def _parse_order_expiry(value: Any) -> datetime | None:
        if value is None or str(value).strip() == "":
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            raw = str(value).strip()
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                try:
                    parsed = datetime.strptime(
                        raw, "%Y%m%d %H:%M:%S UTC"
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)

    @classmethod
    def classify(
        cls, outcome: Any, bundle: Any | None = None
    ) -> ContinuityAuthorityClass:
        explicit = _value(outcome, "authority_class")
        if explicit is not None:
            return ContinuityAuthorityClass(_enum_value(explicit))
        decision = TraderDecision(_enum_value(_value(outcome, "decision")))
        if decision in {TraderDecision.NO_TRADE, TraderDecision.MONITOR_POSITION}:
            return ContinuityAuthorityClass.OBSERVATION
        if decision == TraderDecision.CANCEL_ORDER:
            return ContinuityAuthorityClass.CANCEL_ORDER
        if decision == TraderDecision.REDUCE_POSITION:
            return ContinuityAuthorityClass.REDUCE_POSITION
        if decision == TraderDecision.CLOSE_POSITION:
            return ContinuityAuthorityClass.CLOSE_POSITION
        if decision == TraderDecision.PROPOSE_TRADE:
            return ContinuityAuthorityClass.NEW_EXPOSURE
        if decision == TraderDecision.PAUSE_FOR_REVIEW:
            return ContinuityAuthorityClass.OBSERVATION

        action = _value(outcome, "open_order_action")
        current = cls._find_order(action, bundle) if bundle is not None else None
        if current is None:
            return ContinuityAuthorityClass.INCREASED_MAXIMUM_LIABILITY
        new_tif = _value(action, "new_tif")
        current_tif = str(current.get("tif") or "")
        if new_tif is not None:
            new_tif_value = _enum_value(new_tif)
            if new_tif_value == "GTC" and current_tif != "GTC":
                return ContinuityAuthorityClass.EXTENDED_TEMPORAL_AUTHORITY
            if new_tif_value == "GTD":
                new_good_till = _value(action, "new_good_till_date_utc")
                new_expiry = cls._parse_order_expiry(new_good_till)
                current_expiry = cls._parse_order_expiry(
                    (current.get("orderAttributes") or {}).get("goodTillDate")
                )
                if current_tif == "GTC":
                    pass
                elif current_tif != "GTD":
                    return ContinuityAuthorityClass.EXTENDED_TEMPORAL_AUTHORITY
                elif (
                    new_expiry is None
                    or current_expiry is None
                    or new_expiry > current_expiry
                ):
                    return ContinuityAuthorityClass.EXTENDED_TEMPORAL_AUTHORITY

        current_quantity = Decimal(str(current.get("totalQuantity")))
        current_limit = Decimal(str(current.get("limitPrice")))
        new_quantity_raw = _value(action, "new_total_quantity")
        new_limit_raw = _value(action, "new_limit_price")
        if (
            new_quantity_raw is not None
            and Decimal(str(new_quantity_raw)) > current_quantity
        ):
            return ContinuityAuthorityClass.INCREASED_MAXIMUM_LIABILITY
        if new_limit_raw is not None:
            new_limit = Decimal(str(new_limit_raw))
            action_side = str(current.get("action") or "").upper()
            if (action_side == "BUY" and new_limit > current_limit) or (
                action_side == "SELL" and new_limit < current_limit
            ):
                return ContinuityAuthorityClass.INCREASED_MAXIMUM_LIABILITY
        return ContinuityAuthorityClass.NONEXPANDING_EXISTING_AUTHORITY

    def authorize(
        self,
        outcome: Any,
        pending_reports: list[dict[str, Any]],
        reconciliation: Mapping[str, Any],
        *,
        bundle: Any | None = None,
    ) -> AuthorityDecision:
        authority_class = self.classify(outcome, bundle)
        if pending_reports and authority_class not in self._NONEXPANDING:
            return AuthorityDecision(
                authorized=False,
                authority_class=authority_class,
                reason_codes=("CONTINUITY_REVIEW_REQUIRED",),
            )
        if (
            not pending_reports
            and authority_class not in self._NONEXPANDING
            and reconciliation.get("status") != "PASS"
        ):
            return AuthorityDecision(
                authorized=False,
                authority_class=authority_class,
                reason_codes=("BROKER_RECONCILIATION_REQUIRED",),
            )
        return AuthorityDecision(
            authorized=True, authority_class=authority_class
        )

    def persist_review(
        self,
        review: ContinuityReview,
        *,
        accepted_plan_sha256: str | None = None,
    ) -> str:
        if self.store is None:
            raise ContinuityReportingError("CONTINUITY_STORE_REQUIRED")
        pending = {
            str(item.get("report_id")): item
            for item in self.store.pending_reports()
        }
        report = pending.get(review.report_id)
        if report is None:
            raise ContinuityReportingError("REPORT_NOT_PENDING")
        if sha256_json(report) != review.report_sha256:
            raise ContinuityReportingError("REPORT_HASH_MISMATCH")
        accepted = self.accepted_result_reader(review.invocation_id)
        if (
            not accepted
            or accepted.get("accepted") is not True
            or accepted.get("invocation_id") != review.invocation_id
            or accepted.get("payload_sha256") != review.accepted_result_sha256
        ):
            raise ContinuityReportingError("ACCEPTED_RESULT_REQUIRED")

        if review.disposition == ContinuityReviewDisposition.REFLECTION_RECORDED:
            if not review.reflection:
                raise ContinuityReportingError("REFLECTION_REQUIRED")
        elif review.disposition == ContinuityReviewDisposition.POLICY_SUPERSEDED:
            if (
                review.replacement_plan_sha256 is None
                or review.replacement_plan_sha256 != accepted_plan_sha256
            ):
                raise ContinuityReportingError("ACCEPTED_REPLACEMENT_PLAN_REQUIRED")
        elif review.reflection is not None or review.replacement_plan_sha256 is not None:
            raise ContinuityReportingError("REVIEW_PAYLOAD_NOT_ALLOWED")
        return self.store.append_review(review)
