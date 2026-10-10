from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

from ibkr_paper_30d.reporting import (
    build_multi_universe_performance_report,
    build_supervision_first_pilot_report,
)


NOW = datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc)
H1 = "1" * 64
H2 = "2" * 64
H3 = "3" * 64
H4 = "4" * 64


def _pilot_evidence() -> dict[str, object]:
    return {
        "exact_head": "a" * 40,
        "transition": {
            "phase": "ACTIVE",
            "target_sha256": H1,
            "phase_event_sha256": H2,
        },
        "account": {
            "account_identity_sha256": H3,
            "paper_only": True,
            "fresh": True,
        },
        "writer": {
            "writer_binding_sha256": H4,
            "client_id": 19761,
            "pid": 1200,
            "fresh": True,
        },
        "execution_lock": {
            "generation": 7,
            "pid": 1200,
            "state": "ACTIVE",
            "fresh": True,
        },
        "inherited_bindings": [
            {
                "contract_identity_sha256": "5" * 64,
                "binding_sha256": "6" * 64,
                "sleeve": "REGULAR_SLEEVE",
            }
        ],
        "sleeve_economics": {
            "REGULAR_SLEEVE": {
                "principal_usd": "500.00",
                "equity_usd": "510.00",
                "maximum_liability_usd": "100.00",
                "state_sha256": "7" * 64,
            },
            "CONTINUOUS_SLEEVE": {
                "principal_usd": "500.00",
                "equity_usd": "500.00",
                "maximum_liability_usd": "0.00",
                "state_sha256": "8" * 64,
            },
        },
        "family_lifecycle": [
            {
                "product_family_sha256": "9" * 64,
                "status": "CERTIFIED",
                "receipt_sha256": "a" * 64,
            }
        ],
        "canary": {
            "status": "CANARY_PASS",
            "candidate_sha256": "b" * 64,
            "lifecycle_receipt_sha256": "c" * 64,
            "flat_state_sha256": "d" * 64,
        },
        "orders": [],
        "fills": [],
        "positions": [],
        "accepted_model_cycles": [
            {"invocation_id": "cycle-1", "result_sha256": "e" * 64}
        ],
        "alert_delivery": {
            "windows_event_log": "CONFIRMED",
            "external_owner_channel": "CONFIRMED",
            "state_sha256": "f" * 64,
        },
        "broker_write_counts": {
            "canary_submit": 1,
            "canary_exit": 1,
            "ordinary": 0,
        },
        "db_receipts": {
            "fresh": True,
            "phase": "ACTIVE",
            "phase_event_sha256": H2,
            "orders_state_sha256": "1" * 64,
            "executions_state_sha256": "2" * 64,
            "positions_state_sha256": "0" * 64,
            "canary_lifecycle_receipt_sha256": "c" * 64,
            "canary_flat_state_sha256": "d" * 64,
        },
        "broker_receipts": {
            "fresh": True,
            "account_identity_sha256": H3,
            "writer_binding_sha256": H4,
            "orders_state_sha256": "1" * 64,
            "executions_state_sha256": "2" * 64,
            "positions_state_sha256": "0" * 64,
            "canary_lifecycle_receipt_sha256": "c" * 64,
            "canary_flat_state_sha256": "d" * 64,
        },
    }


def test_multi_universe_report_preserves_history_and_sleeve_separation() -> None:
    report = build_multi_universe_performance_report(
        regular_principal_usd=Decimal("500"),
        regular_opening_equity_usd=Decimal("470"),
        regular_current_equity_usd=Decimal("485"),
        extended_principal_usd=Decimal("500"),
        extended_opening_equity_usd=Decimal("500"),
        extended_current_equity_usd=Decimal("510"),
        regular_currency_balances={"USD": Decimal("210"), "EUR": Decimal("12")},
        extended_currency_balances={"USD": Decimal("300"), "EUR": Decimal("5")},
        canary_adjustment_usd=Decimal("-1.25"),
        ownership={
            "REGULAR_SLEEVE": ("regular-contract",),
            "EXTENDED_SLEEVE": ("extended-contract",),
        },
        certified_families=("family-a",),
        paper_limitations=("PAPER_FILL_SIMULATION",),
    )

    assert report["regular_historical_pnl_usd"] == "-30.00"
    assert report["regular_successor_pnl_usd"] == "15.00"
    assert report["extended_successor_pnl_usd"] == "10.00"
    assert report["combined_successor_pnl_usd"] == "25.00"
    assert report["combined_lifetime_pnl_usd"] == "-5.00"
    assert report["canary_adjustment_usd"] == "-1.25"
    assert report["currency_balances"]["REGULAR_SLEEVE"]["EUR"] == "12.00"
    assert report["currency_balances"]["EXTENDED_SLEEVE"]["EUR"] == "5.00"
    assert report["aggregate_currency_balances"]["EUR"] == "17.00"
    assert report["capital_rebased"] is False
    assert report["cross_sleeve_netting"] is False


def test_supervision_first_pilot_report_passes_only_complete_hash_bound_evidence() -> None:
    report = build_supervision_first_pilot_report(
        _pilot_evidence(), generated_at_utc=NOW
    )

    assert report["schema"] == "SUPERVISION_FIRST_PILOT_REPORT_V1"
    assert report["gate"] == "PASS"
    assert report["reason_codes"] == []
    assert report["exact_head"] == "a" * 40
    assert report["transition"]["phase"] == "ACTIVE"
    assert report["broker_write_counts"] == {
        "canary_submit": 1,
        "canary_exit": 1,
        "ordinary": 0,
        "total": 2,
    }
    assert len(report["report_sha256"]) == 64


def test_supervision_first_pilot_report_blocks_missing_stale_and_unhashed_evidence() -> None:
    evidence = _pilot_evidence()
    del evidence["writer"]["writer_binding_sha256"]
    evidence["broker_receipts"]["fresh"] = False
    evidence["family_lifecycle"][0]["receipt_sha256"] = "not-a-hash"

    report = build_supervision_first_pilot_report(evidence, generated_at_utc=NOW)

    assert report["gate"] == "BLOCK"
    assert "WRITER_BINDING_HASH_REQUIRED" in report["reason_codes"]
    assert "BROKER_EVIDENCE_STALE" in report["reason_codes"]
    assert "UNHASHED_EVIDENCE" in report["reason_codes"]


def test_active_claim_requires_matching_database_phase_event_receipt() -> None:
    evidence = _pilot_evidence()
    evidence["db_receipts"]["phase_event_sha256"] = "f" * 64

    report = build_supervision_first_pilot_report(evidence, generated_at_utc=NOW)

    assert report["gate"] == "BLOCK"
    assert "ACTIVE_PHASE_RECEIPT_MISMATCH" in report["reason_codes"]


def test_canary_pass_requires_matching_lifecycle_and_flat_receipts() -> None:
    evidence = _pilot_evidence()
    evidence["broker_receipts"]["canary_flat_state_sha256"] = "e" * 64

    report = build_supervision_first_pilot_report(evidence, generated_at_utc=NOW)

    assert report["gate"] == "BLOCK"
    assert "CANARY_PASS_RECEIPT_MISMATCH" in report["reason_codes"]


def test_zero_exposure_claim_requires_matching_db_and_broker_position_receipts() -> None:
    evidence = _pilot_evidence()
    evidence["broker_receipts"]["positions_state_sha256"] = "f" * 64

    report = build_supervision_first_pilot_report(evidence, generated_at_utc=NOW)

    assert report["gate"] == "BLOCK"
    assert "ZERO_EXPOSURE_NOT_PROVEN" in report["reason_codes"]


def test_active_report_requires_accepted_cycle_and_both_alert_channels() -> None:
    evidence = _pilot_evidence()
    evidence["accepted_model_cycles"] = []
    evidence["alert_delivery"]["external_owner_channel"] = "FAILED"

    report = build_supervision_first_pilot_report(evidence, generated_at_utc=NOW)

    assert report["gate"] == "BLOCK"
    assert "ACTIVE_ACCEPTED_CYCLE_REQUIRED" in report["reason_codes"]
    assert "ALERT_DELIVERY_NOT_CONFIRMED" in report["reason_codes"]


def test_order_and_execution_states_require_matching_db_and_broker_receipts() -> None:
    evidence = _pilot_evidence()
    evidence["broker_receipts"]["orders_state_sha256"] = "3" * 64
    evidence["broker_receipts"]["executions_state_sha256"] = "4" * 64

    report = build_supervision_first_pilot_report(evidence, generated_at_utc=NOW)

    assert report["gate"] == "BLOCK"
    assert "ORDER_STATE_RECEIPT_MISMATCH" in report["reason_codes"]
    assert "EXECUTION_STATE_RECEIPT_MISMATCH" in report["reason_codes"]


def test_report_does_not_mutate_caller_evidence() -> None:
    evidence = _pilot_evidence()
    original = deepcopy(evidence)

    build_supervision_first_pilot_report(evidence, generated_at_utc=NOW)

    assert evidence == original
