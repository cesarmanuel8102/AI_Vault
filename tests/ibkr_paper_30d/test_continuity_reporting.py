from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.continuity_models import (
    ContinuityAuthorityClass,
    ContinuityEvaluation,
    ContinuityReview,
)
from ibkr_paper_30d.continuity_reporting import (
    ContinuityReportBuilder,
    ContinuityReportingError,
    ContinuityReviewGate,
)
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.continuity_store import ContinuityStore
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


START = datetime(2026, 10, 1, 19, 2, tzinfo=timezone.utc)
END = START + timedelta(minutes=11)
H1 = "1" * 64
H2 = "2" * 64


def _open(path):
    db = Database.open(path)
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    return db


def test_report_is_factual_hash_bound_and_contains_recovery_evidence(
    tmp_path, continuity_plan_factory
):
    plan = continuity_plan_factory(plan_id="plan-report-1")
    evaluation = ContinuityEvaluation(
        evaluation_id="evaluation-report-1",
        evaluated_at_utc=START + timedelta(minutes=3),
        plan_id=plan.plan_id,
        plan_sha256=plan.sha256,
        fact_snapshot_sha256=H1,
        authority_active=True,
        selected_contingency_id=plan.contingencies[0].contingency_id,
        selected_action=plan.terminal_disposition,
        execution_ordinal=1,
        reason_codes=("CONDITION_MATCHED",),
    )
    observation = {
        "broker_order_state": {
            "order_ref": plan.order_binding.order_ref,
            "status": "PreSubmitted",
            "limit_price": "4.50",
        },
        "executions": [],
        "positions": [],
        "market_observations": [{"symbol": "UTHR", "last": "571.38"}],
        "unresolved_questions": ["Did the venue expose the combo during the outage?"],
    }
    with _open(tmp_path / "report.sqlite3") as db:
        store = ContinuityStore(db)
        store.append_provider_event(
            "outage-1", "IN_FLIGHT", {"broker_time_utc": START.isoformat()}
        )
        store.append_provider_event(
            "outage-1",
            "TIMEOUT_CONFIRMED",
            {
                "broker_time_utc": END.isoformat(),
                "failure_code": "PROVIDER_TIMEOUT",
            },
        )
        store.append_plan_event("ACTIVATED", plan)
        store.append_evaluation(evaluation, plan.order_binding.order_ref)
        store.append_execution_event(
            "execution-report-1",
            evaluation.evaluation_id,
            plan.plan_id,
            plan.order_binding.order_ref,
            1,
            "BLOCKED",
            {
                "evaluation_sha256": evaluation.sha256,
                "fact_snapshot_sha256": evaluation.fact_snapshot_sha256,
                "action_sha256": evaluation.action_sha256,
                "status": "BLOCKED",
                "reason_codes": ["OPEN_ORDER_STATE_CHANGED"],
            },
        )

        report = ContinuityReportBuilder(
            store, recovery_observation_reader=lambda outage_id: observation
        ).build("outage-1")

    assert report.outage_started_at_utc == START
    assert report.outage_ended_at_utc == END
    assert report.duration_seconds == Decimal("660")
    assert report.failure_codes == ("PROVIDER_TIMEOUT",)
    assert report.plans[0]["plan_sha256"] == plan.sha256
    assert report.evaluations[0]["fact_snapshot_sha256"] == H1
    assert report.evaluations[0]["action_sha256"] == evaluation.action_sha256
    assert report.executions[0]["status"] == "BLOCKED"
    assert report.broker_order_state["status"] == "PreSubmitted"
    assert report.market_observations[0]["last"] == "571.38"
    assert report.expectations == plan.contingencies[0].expectations
    assert report.arithmetic_differences == (
        {
            "field": "order_limit_price",
            "expected": str(plan.order_binding.original_limit_price),
            "observed": "4.50",
            "difference": str(
                Decimal("4.50") - plan.order_binding.original_limit_price
            ),
        },
    )
    assert report.unresolved_questions == (
        "Did the venue expose the combo during the outage?",
    )
    assert len(report.sha256) == 64


@pytest.mark.parametrize(
    "label", ["good", "bad", "aggressive", "conservative", "rational", "irrational"]
)
def test_report_rejects_observer_strategic_labels(tmp_path, label):
    with _open(tmp_path / f"{label}.sqlite3") as db:
        store = ContinuityStore(db)
        store.append_provider_event(
            "outage-1", "IN_FLIGHT", {"broker_time_utc": START.isoformat()}
        )
        store.append_provider_event(
            "outage-1",
            "TIMEOUT_CONFIRMED",
            {"broker_time_utc": END.isoformat(), "failure_code": "PROVIDER_TIMEOUT"},
        )
        builder = ContinuityReportBuilder(
            store,
            recovery_observation_reader=lambda outage_id: {
                "observer_annotations": [f"The plan was {label}."],
            },
        )
        with pytest.raises(ContinuityReportingError, match="STRATEGIC_LABEL_PROHIBITED"):
            builder.build("outage-1")


def _outcome(decision, **updates):
    value = {
        "decision": decision,
        "proposal": None,
        "position_action": None,
        "open_order_action": None,
        "reason_codes": ["PRUDENT", "DEFENSIVE"],
    }
    value.update(updates)
    return value


def _bundle():
    return {
        "open_orders_snapshot": [
            {
                "orderRef": "order-78",
                "orderId": 78,
                "permId": 225256222,
                "clientId": 19761,
                "totalQuantity": "2",
                "filled": "0",
                "limitPrice": "5.00",
                "action": "BUY",
                "tif": "DAY",
                "orderAttributes": {"goodTillDate": ""},
            }
        ],
        "reconciliation_receipt": {"status": "PASS"},
    }


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (_outcome("NO_TRADE"), ContinuityAuthorityClass.OBSERVATION),
        (_outcome("MONITOR_POSITION"), ContinuityAuthorityClass.OBSERVATION),
        (_outcome("CANCEL_ORDER"), ContinuityAuthorityClass.CANCEL_ORDER),
        (_outcome("REDUCE_POSITION"), ContinuityAuthorityClass.REDUCE_POSITION),
        (_outcome("CLOSE_POSITION"), ContinuityAuthorityClass.CLOSE_POSITION),
        (_outcome("PROPOSE_TRADE"), ContinuityAuthorityClass.NEW_EXPOSURE),
    ],
)
def test_authority_classification_is_mechanical(outcome, expected):
    assert ContinuityReviewGate.classify(outcome, _bundle()) == expected


def test_modify_classification_uses_liability_and_time_not_strategy_labels():
    base = {
        "order_ref": "order-78",
        "order_id": 78,
        "perm_id": 225256222,
        "client_id": 19761,
        "new_total_quantity": Decimal("1"),
        "new_limit_price": Decimal("4.50"),
        "new_tif": None,
        "new_good_till_date_utc": None,
    }
    nonexpanding = _outcome("MODIFY_ORDER", open_order_action=base)
    liability = _outcome(
        "MODIFY_ORDER", open_order_action={**base, "new_total_quantity": Decimal("3")}
    )
    time_extension = _outcome(
        "MODIFY_ORDER", open_order_action={**base, "new_tif": "GTC"}
    )

    assert ContinuityReviewGate.classify(
        nonexpanding, _bundle()
    ) == ContinuityAuthorityClass.NONEXPANDING_EXISTING_AUTHORITY
    assert ContinuityReviewGate.classify(
        liability, _bundle()
    ) == ContinuityAuthorityClass.INCREASED_MAXIMUM_LIABILITY
    assert ContinuityReviewGate.classify(
        time_extension, _bundle()
    ) == ContinuityAuthorityClass.EXTENDED_TEMPORAL_AUTHORITY


def test_pending_report_blocks_only_authority_expansion():
    gate = ContinuityReviewGate(None)
    pending = [{"report_id": "report-1", "sha256": H1}]

    assert gate.authorize(_outcome("CANCEL_ORDER"), pending, {"status": "BLOCK"}).authorized
    assert gate.authorize(
        _outcome(
            "MODIFY_ORDER",
            open_order_action={
                "order_ref": "order-78",
                "order_id": 78,
                "perm_id": 225256222,
                "client_id": 19761,
                "new_total_quantity": Decimal("1"),
                "new_limit_price": Decimal("4.50"),
                "new_tif": None,
                "new_good_till_date_utc": None,
            },
        ),
        pending,
        {"status": "BLOCK"},
        bundle=_bundle(),
    ).authorized
    blocked = gate.authorize(
        _outcome("PROPOSE_TRADE"), pending, {"status": "PASS"}
    )
    assert blocked.authorized is False
    assert blocked.reason_codes == ("CONTINUITY_REVIEW_REQUIRED",)


@pytest.mark.parametrize(
    "disposition",
    [
        "ACK_NO_METHOD_CHANGE",
        "REFLECTION_RECORDED",
        "POLICY_SUPERSEDED",
        "MORE_RESEARCH_REQUIRED",
    ],
)
def test_review_binds_exact_report_and_accepted_result(
    tmp_path, disposition
):
    accepted = {"invocation_id": "invocation-2", "payload_sha256": H2, "accepted": True}
    with _open(tmp_path / f"review-{disposition}.sqlite3") as db:
        store = ContinuityStore(db)
        report = {"report_id": "report-1", "outage_id": "outage-1", "facts": []}
        report_hash = store.append_report("report-1", "outage-1", report)
        gate = ContinuityReviewGate(
            store, accepted_result_reader=lambda invocation_id: accepted
        )
        review = ContinuityReview(
            review_id=f"review-{disposition}",
            report_id="report-1",
            report_sha256=report_hash,
            invocation_id="invocation-2",
            accepted_result_sha256=H2,
            disposition=disposition,
            reflection=("Model-authored reflection." if disposition == "REFLECTION_RECORDED" else None),
            replacement_plan_sha256=(H1 if disposition == "POLICY_SUPERSEDED" else None),
        )
        gate.persist_review(review, accepted_plan_sha256=H1)
        pending = store.pending_reports()

    if disposition == "MORE_RESEARCH_REQUIRED":
        assert pending == [report]
    else:
        assert pending == []


def test_review_rejects_unknown_stale_or_unaccepted_binding(tmp_path):
    with _open(tmp_path / "review-invalid.sqlite3") as db:
        store = ContinuityStore(db)
        report = {"report_id": "report-1", "outage_id": "outage-1"}
        report_hash = store.append_report("report-1", "outage-1", report)
        gate = ContinuityReviewGate(
            store,
            accepted_result_reader=lambda invocation_id: {
                "invocation_id": invocation_id,
                "payload_sha256": H2,
                "accepted": False,
            },
        )
        review = ContinuityReview(
            review_id="review-invalid",
            report_id="report-1",
            report_sha256=report_hash,
            invocation_id="invocation-2",
            accepted_result_sha256=H2,
            disposition="ACK_NO_METHOD_CHANGE",
        )
        with pytest.raises(ContinuityReportingError, match="ACCEPTED_RESULT_REQUIRED"):
            gate.persist_review(review)
        with pytest.raises(ContinuityReportingError, match="REPORT_NOT_PENDING"):
            gate.persist_review(review.model_copy(update={"report_id": "unknown"}))
