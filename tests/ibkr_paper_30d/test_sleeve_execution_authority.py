from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.coordinated_model_executor import ModelExecutionOperation
from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.sleeve_execution_authority import (
    SleeveAuthorityReservationStore,
    SleeveAuthoritySnapshot,
    SleeveExecutionAuthorityValidator,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from test_model_execution_engine import _request


NOW = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)


def _v4_request():
    legacy = _request(ModelExecutionOperation.NEW_TRADE)
    family = "f" * 64
    portfolio = {
        "schema": "MULTI_SLEEVE_PORTFOLIO_V4",
        "sleeves": {"regular": {}, "extended": {}},
    }
    ownership = {"projection_sha256": "d" * 64, "contract_sleeves": {}}
    bundle = legacy.input_bundle.model_copy(
        update={
            "multi_sleeve_portfolio": portfolio,
            "contract_ownership_snapshot": ownership,
            "product_capability_snapshot": {"families": []},
        }
    )
    payload = legacy.payload.model_copy(
        update={
            "capital_sleeve": CapitalSleeve.EXTENDED_SLEEVE,
            "product_family_sha256": family,
        }
    )
    data = legacy.model_dump()
    data.update(
        {
            "payload": payload,
            "payload_sha256": sha256_json(payload),
            "input_bundle": bundle,
            "input_bundle_sha256": bundle.sha256,
            "capital_sleeve": CapitalSleeve.EXTENDED_SLEEVE,
            "sleeve_authority_sha256": sha256_json(portfolio),
            "ownership_projection_sha256": "d" * 64,
            "product_family_sha256": family,
        }
    )
    return legacy.__class__.model_validate(data)


def _snapshot(request, **changes):
    values = {
        "capital_sleeve": CapitalSleeve.EXTENDED_SLEEVE,
        "sleeve_authority_sha256": request.sleeve_authority_sha256,
        "ownership_projection_sha256": request.ownership_projection_sha256,
        "product_family_sha256": request.product_family_sha256,
        "economic_authorization_sha256": "e" * 64,
        "transition_target_sha256": "a" * 64,
        "epoch_id": request.epoch_id,
        "approved_head": request.approved_head,
        "account_identity_sha256": request.account_identity_sha256,
        "transition_phase": "ACTIVE",
        "paper_only": True,
        "family_executable": True,
        "capability_fresh": True,
        "ownership_conflict": False,
        "equity_usd": Decimal("500"),
        "reserved_liability_usd": Decimal("0"),
        "proposed_maximum_loss_usd": Decimal("1"),
        "continuity_required": False,
        "continuity_plan_sha256": None,
    }
    values.update(changes)
    return SleeveAuthoritySnapshot(**values)


def _broker(request, **changes):
    value = {
        "paper_only": True,
        "fresh": True,
        "account_identity_sha256": request.account_identity_sha256,
        "contract_identity_sha256": "c" * 64,
        "observed_at_utc": NOW,
    }
    value.update(changes)
    return value


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"family_executable": False}, "PRODUCT_FAMILY_NOT_EXECUTABLE"),
        ({"capability_fresh": False}, "PRODUCT_CAPABILITY_STALE"),
        ({"ownership_conflict": True}, "CONTRACT_OWNERSHIP_CONFLICT"),
        ({"external_capital_offset_detected": True}, "CROSS_SLEEVE_OR_EXTERNAL_OFFSET_FORBIDDEN"),
        ({"unbounded_liability": True}, "MAXIMUM_LOSS_UNBOUNDED"),
        ({"economic_authorization_valid": False}, "OWNER_ECONOMIC_RISK_AUTHORIZATION_INVALID"),
        ({"paper_only": False}, "NON_PAPER_AUTHORITY"),
        ({"approved_head": "9" * 40}, "APPROVED_HEAD_MISMATCH"),
        ({"epoch_id": "wrong"}, "EPOCH_MISMATCH"),
        ({"transition_phase": "CANARY_PASS"}, "SUCCESSOR_NOT_ACTIVE"),
        ({"proposed_maximum_loss_usd": Decimal("501")}, "SLEEVE_AVAILABLE_CAPITAL_EXCEEDED"),
        ({"reserved_liability_usd": Decimal("500")}, "SLEEVE_AVAILABLE_CAPITAL_EXCEEDED"),
    ],
)
def test_gate_matrix_blocks_each_independent_authority_failure(changes, reason):
    request = _v4_request()
    receipt = SleeveExecutionAuthorityValidator.validate(
        request, _broker(request), _snapshot(request, **changes)
    )
    assert receipt.status == "BLOCK"
    assert reason in receipt.reason_codes


def test_non_paper_or_wrong_account_broker_evidence_blocks() -> None:
    request = _v4_request()
    for evidence, reason in (
        (_broker(request, paper_only=False), "BROKER_NOT_PAPER"),
        (_broker(request, fresh=False), "BROKER_EVIDENCE_STALE"),
        (_broker(request, account_identity_sha256="d" * 64), "BROKER_ACCOUNT_MISMATCH"),
    ):
        receipt = SleeveExecutionAuthorityValidator.validate(
            request, evidence, _snapshot(request)
        )
        assert reason in receipt.reason_codes


def test_missing_continuity_plan_blocks_when_snapshot_requires_it() -> None:
    request = _v4_request()
    receipt = SleeveExecutionAuthorityValidator.validate(
        request,
        _broker(request),
        _snapshot(request, continuity_required=True),
    )
    assert "CONTINUITY_PLAN_REQUIRED" in receipt.reason_codes


def test_reservation_rereads_inside_transaction_and_is_exactly_idempotent(tmp_path) -> None:
    request = _v4_request()
    db = Database.open(tmp_path / "authority.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    store = SleeveAuthorityReservationStore(db)
    calls = []

    def reader():
        calls.append(db.connection.in_transaction)
        return _snapshot(request)

    try:
        first = store.reserve(request, _broker(request), reader)
        second = store.reserve(request, _broker(request), reader)
        assert first.status == second.status == "PASS"
        assert second.idempotent is True
        assert calls == [True, True]
        assert db.execute("SELECT COUNT(*) FROM sleeve_authority_events").fetchone()[0] == 1
    finally:
        db.close()


def test_db_state_change_after_broker_collection_blocks_without_reservation(tmp_path) -> None:
    request = _v4_request()
    db = Database.open(tmp_path / "race.sqlite3")
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    install_multi_universe_schema_v4(db)
    store = SleeveAuthorityReservationStore(db)
    try:
        receipt = store.reserve(
            request,
            _broker(request),
            lambda: _snapshot(request, ownership_projection_sha256="e" * 64),
        )
        assert receipt.status == "BLOCK"
        assert "OWNERSHIP_PROJECTION_MISMATCH" in receipt.reason_codes
        assert db.execute("SELECT COUNT(*) FROM sleeve_authority_events").fetchone()[0] == 0
    finally:
        db.close()
