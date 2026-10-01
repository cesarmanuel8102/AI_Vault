from __future__ import annotations

import json
import sqlite3
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.continuity_models import CodexOrderContinuityPlan, ContinuityReview
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.continuity_store import ContinuityStore, ContinuityStoreError
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


UTC = timezone.utc
NOW = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)
H1, H2, H3 = "a" * 64, "b" * 64, "c" * 64


def _actions(value: str = "RETAIN") -> dict[str, dict[str, str]]:
    return {
        state: {"action_type": value}
        for state in (
            "UNFILLED",
            "PARTIALLY_FILLED",
            "FILLED",
            "PENDING_CANCEL",
            "CANCELLED",
            "REJECTED",
            "ABSENT",
        )
    }


def _plan(plan_id: str = "plan-1", predecessor: str | None = None) -> CodexOrderContinuityPlan:
    return CodexOrderContinuityPlan.model_validate(
        {
            "schema": "CODEX_ORDER_CONTINUITY_PLAN_V1",
            "plan_id": plan_id,
            "plan_version": 1,
            "created_at_utc": NOW,
            "created_by_model": "gpt-5-codex",
            "model_attestation_sha256": H1,
            "decision_cycle_id": f"cycle-{plan_id}",
            "invocation_id": f"invocation-{plan_id}",
            "input_bundle_sha256": H2,
            "epoch_id": "AUTONOMY_EPOCH_2",
            "definition_sha256": H3,
            "clock_event_sha256": H1,
            "owner_authorization_sha256": H2,
            "predecessor_plan_sha256": predecessor,
            "order_binding": {
                "binding_type": "EXISTING_ORDER",
                "account_identity_sha256": H1,
                "order_ref": "order-78",
                "client_order_id": "client-order-78",
                "ibkr_order_id": 78,
                "perm_id": 225256222,
                "execution_client_id": 17,
                "contract_identity_sha256": H2,
                "action": "BUY",
                "order_type": "LMT",
                "original_total_quantity": "1",
                "original_limit_price": "4.90",
                "original_tif": "DAY",
                "original_good_till_date_utc": None,
                "original_order_state_sha256": H3,
                "original_intent_sha256": H1,
                "proposal_sha256": None,
            },
            "maximum_authorized_liability": "500",
            "valid_from_utc": NOW,
            "plan_valid_until": NOW + timedelta(hours=6),
            "session_end_utc": NOW + timedelta(hours=6),
            "epoch_authority_end_utc": NOW + timedelta(days=1),
            "authority_activation_condition": {
                "operator": "PREDICATE",
                "fact": "PROVIDER_STATE",
                "comparator": "EQ",
                "value": "TIMEOUT_CONFIRMED",
                "max_age_seconds": 15,
            },
            "expiry_authority_mode": "WHEN_CONTINUITY_ACTIVE",
            "terminal_disposition": {"action_type": "CANCEL"},
            "contingencies": [
                {
                    "contingency_id": "outage",
                    "priority": 1,
                    "valid_from_utc": NOW,
                    "valid_until_utc": NOW + timedelta(hours=6),
                    "condition": {
                        "operator": "PREDICATE",
                        "fact": "PROVIDER_STATE",
                        "comparator": "EQ",
                        "value": "TIMEOUT_CONFIRMED",
                        "max_age_seconds": 15,
                    },
                    "state_actions": _actions(),
                    "unavailable_data_action": {
                        "action_type": "REQUIRES_AGENT",
                        "interim_action": {"action_type": "RETAIN"},
                    },
                    "maximum_execution_count": 1,
                    "expectations": ["May remain unfilled"],
                    "why_i_chose_this_contingency": "Exact prior intent",
                }
            ],
        }
    )


def _open(path) -> Database:
    db = Database.open(path)
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    return db


def test_plan_chain_reconstructs_supersession_and_exact_replay(tmp_path) -> None:
    with _open(tmp_path / "state.sqlite3") as db:
        store = ContinuityStore(db)
        first = _plan()
        first_hash = store.append_plan_event("ACTIVATED", first, event_id="activate-1")
        assert store.append_plan_event("ACTIVATED", first, event_id="activate-1") == first_hash

        second = _plan("plan-2", predecessor=first.sha256)
        store.append_plan_event("SUPERSEDED", second, event_id="supersede-1")

        assert store.active_plan("order-78") == second
        assert [item.plan_id for item in store.plan_chain("order-78")] == [
            "plan-1",
            "plan-2",
        ]


def test_store_rejects_bad_predecessor_duplicate_active_and_conflicting_replay(tmp_path) -> None:
    with _open(tmp_path / "state.sqlite3") as db:
        store = ContinuityStore(db)
        first = _plan()
        store.append_plan_event("ACTIVATED", first, event_id="activate-1")

        with pytest.raises(ContinuityStoreError, match="ACTIVE_PLAN_CONFLICT"):
            store.append_plan_event("ACTIVATED", _plan("other"), event_id="activate-2")
        with pytest.raises(ContinuityStoreError, match="PREDECESSOR"):
            store.append_plan_event(
                "SUPERSEDED", _plan("bad", predecessor=H3), event_id="supersede-bad"
            )
        with pytest.raises(ContinuityStoreError, match="IDEMPOTENCY_CONFLICT"):
            store.append_plan_event("ACTIVATED", _plan("other"), event_id="activate-1")


def test_projection_rejects_corrupt_payload_and_hash(tmp_path) -> None:
    with _open(tmp_path / "state.sqlite3") as db:
        store = ContinuityStore(db)
        store.append_plan_event("ACTIVATED", _plan(), event_id="activate-1")
        db.execute("DROP TRIGGER continuity_plan_events_no_update")
        db.execute(
            "UPDATE continuity_plan_events SET payload_json=? WHERE event_id='activate-1'",
            (json.dumps({"corrupt": True}),),
        )
        with pytest.raises(ContinuityStoreError, match="HASH_MISMATCH"):
            store.active_plan("order-78")


def test_one_shot_execution_is_unique(tmp_path) -> None:
    with _open(tmp_path / "state.sqlite3") as db:
        store = ContinuityStore(db)
        payload = {"action": "CANCEL", "plan_sha256": H1}
        store.append_execution_event(
            "execution-1", "evaluation-1", "plan-1", "order-78", 1, "EXECUTED", payload
        )
        with pytest.raises(ContinuityStoreError, match="EXECUTION_ORDINAL_CONFLICT"):
            store.append_execution_event(
                "execution-2", "evaluation-2", "plan-1", "order-78", 1, "EXECUTED", payload
            )


def test_report_review_binding_and_pending_projection(tmp_path) -> None:
    with _open(tmp_path / "state.sqlite3") as db:
        store = ContinuityStore(db)
        report = {"report_id": "report-1", "outage_id": "outage-1", "facts": []}
        report_hash = store.append_report("report-1", "outage-1", report)
        assert store.pending_reports() == [report]

        bad = ContinuityReview(
            review_id="review-1",
            report_id="report-1",
            report_sha256=H1,
            invocation_id="invocation-2",
            accepted_result_sha256=H2,
            disposition="ACK_NO_METHOD_CHANGE",
        )
        with pytest.raises(ContinuityStoreError, match="REPORT_HASH_MISMATCH"):
            store.append_review(bad)

        review = bad.model_copy(update={"report_sha256": report_hash})
        store.append_review(review)
        assert store.pending_reports() == []


def test_provider_projection_validates_chain(tmp_path) -> None:
    with _open(tmp_path / "state.sqlite3") as db:
        store = ContinuityStore(db)
        store.append_provider_event("inv-1", "IN_FLIGHT", {"attempt": 1})
        store.append_provider_event("inv-1", "TIMEOUT_CONFIRMED", {"attempt": 1})
        projection = store.provider_projection("inv-1")
        assert projection["state"] == "TIMEOUT_CONFIRMED"
        assert projection["payload"] == {"attempt": 1}


def test_concurrent_contenders_allow_exactly_one_active_transition(tmp_path) -> None:
    path = tmp_path / "state.sqlite3"
    with _open(path):
        pass
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def contender(plan_id: str) -> None:
        with Database.open(path) as db:
            store = ContinuityStore(db)
            barrier.wait()
            try:
                store.append_plan_event("ACTIVATED", _plan(plan_id))
                outcomes.append("COMMITTED")
            except ContinuityStoreError as exc:
                outcomes.append(str(exc))

    threads = [threading.Thread(target=contender, args=(f"plan-{n}",)) for n in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes.count("COMMITTED") == 1
    assert sum("ACTIVE_PLAN_CONFLICT" in item for item in outcomes) == 1
