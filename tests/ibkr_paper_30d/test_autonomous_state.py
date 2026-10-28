from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest
import ibkr_paper_30d.autonomous_state as state_module


def test_broker_position_uses_fresh_quote_not_average_cost():
    subject = object.__new__(AutonomousStateBuilder)
    subject._fresh_position_marks = {7884: Decimal("121.29")}
    subject._extra_mark_reasons = []
    position = subject._marked_broker_position(
        {"contract": {"conId": 7884, "multiplier": "1"},
         "position": "4", "avgCost": "118.85"}, "a" * 64,
    )
    assert position["mark"] == "121.29"
    assert position["market_value_usd"] == "485.16"
    assert position["average_cost"] == "118.85"
    assert position["mark_fresh"] is True


def test_broker_position_missing_mark_is_not_disguised_as_cost():
    subject = object.__new__(AutonomousStateBuilder)
    subject._fresh_position_marks = {}
    subject._extra_mark_reasons = []
    subject.toolbox = SimpleNamespace(execute=lambda *_args: SimpleNamespace(success=False))
    position = subject._marked_broker_position(
        {"contract": {"conId": 7884}, "position": "4", "avgCost": "118.85"},
        "a" * 64,
    )
    assert position["mark_fresh"] is False
    assert position["mark"] == "0"
    assert "MARK_QUOTE_FAILED:7884" in subject._extra_mark_reasons


def test_broker_position_quote_preserves_crypto_venue_identity():
    captured = {}

    def execute(request, _bundle):
        captured.update(request.arguments)
        return SimpleNamespace(success=True, data={"marketPrice": "103.25"})

    subject = object.__new__(AutonomousStateBuilder)
    subject._fresh_position_marks = {}
    subject._extra_mark_reasons = []
    subject.toolbox = SimpleNamespace(execute=execute)

    position = subject._marked_broker_position(
        {
            "contract": {
                "conId": 766137558,
                "symbol": "SOL",
                "localSymbol": "SOL.USD",
                "secType": "CRYPTO",
                "exchange": "PAXOS",
                "currency": "USD",
            },
            "position": "4.7",
            "avgCost": "102.22",
        },
        "b" * 64,
    )

    assert captured == {
        "conId": 766137558,
        "symbol": "SOL",
        "local_symbol": "SOL.USD",
        "sec_type": "CRYPTO",
        "exchange": "PAXOS",
        "currency": "USD",
    }
    assert position["mark_fresh"] is True
    assert position["mark"] == "103.25"


def test_broker_position_quote_uses_id_only_when_broker_omits_venue():
    captured = {}

    def execute(request, _bundle):
        captured.update(request.arguments)
        return SimpleNamespace(success=True, data={"marketPrice": "104.30"})

    subject = object.__new__(AutonomousStateBuilder)
    subject._fresh_position_marks = {}
    subject._extra_mark_reasons = []
    subject.toolbox = SimpleNamespace(execute=execute)

    position = subject._marked_broker_position(
        {
            "contract": {
                "conId": 766137558,
                "symbol": "SOL",
                "localSymbol": "SOL.USD",
                "secType": "CRYPTO",
                "exchange": "",
                "currency": "USD",
            },
            "position": "4.7",
            "avgCost": "102.59234045",
        },
        "b" * 64,
    )

    assert captured == {"conId": 766137558}
    assert position["mark_fresh"] is True
    assert position["mark"] == "104.30"


def test_ledger_crypto_position_mark_uses_authoritative_contract_id_only():
    captured = {}

    def execute(request, _bundle):
        captured.update(request.arguments)
        return SimpleNamespace(success=True, data={"marketPrice": "104.30"})

    recorded = {}
    subject = object.__new__(AutonomousStateBuilder)
    subject.toolbox = SimpleNamespace(execute=execute)
    subject.ledger = SimpleNamespace(
        project=lambda: SimpleNamespace(
            positions=(
                SimpleNamespace(
                    contract_id=766137558,
                    symbol="SOL",
                    sec_type="CRYPTO",
                ),
            )
        ),
        record_mark=lambda **kwargs: recorded.update(kwargs),
    )
    subject._minimal_placeholder_bundle = lambda: None

    reasons = subject._mark_open_positions()

    assert reasons == []
    assert captured == {"conId": 766137558}
    assert subject._fresh_position_marks == {766137558: Decimal("104.30")}
    assert recorded == {
        "contract_id": 766137558,
        "symbol": "SOL",
        "price": Decimal("104.30"),
    }


def test_derivative_broker_cost_is_per_contract_but_mark_is_per_unit():
    subject = object.__new__(AutonomousStateBuilder)
    subject._fresh_position_marks = {9001: Decimal("205")}
    subject._extra_mark_reasons = []
    position = subject._marked_broker_position(
        {"contract": {"conId": 9001, "multiplier": "5"},
         "position": "1", "avgCost": "1000"}, "a" * 64,
    )
    assert position["average_cost"] == "200"
    assert position["market_value_usd"] == "1025"


def test_unavailable_sleeve_valuation_blocks_only_its_new_entries():
    subject = object.__new__(AutonomousStateBuilder)
    common = {"initialized": True, "allocation_usd": "500", "fees_usd": "0"}
    subject.sleeve_ledger_store = SimpleNamespace(project_all=lambda: _Dumpable({
        "regular": {**common, "valuation_status": "UNAVAILABLE"},
        "continuous": {**common, "valuation_status": "FRESH"},
    }))
    subject.contract_ownership_store = SimpleNamespace(projection=lambda: _Dumpable({"active_contracts": []}))
    subject.product_certification_store = SimpleNamespace(projections=lambda: ())
    portfolio, _, _ = subject._multi_sleeve_context(
        reconciliation={"status": "PASS"}, account={}, broker_positions={},
        open_orders={}, transition_phase="ACTIVE", regular_entry_open=True,
    )
    gate = portfolio["entry_eligibility"]["REGULAR_SLEEVE"]
    assert gate["status"] == "BLOCK"
    assert gate["reason_codes"] == ["SLEEVE_FRESH_VALUATION_REQUIRED"]
    assert "SLEEVE_FRESH_VALUATION_REQUIRED" not in portfolio["entry_eligibility"]["CONTINUOUS_SLEEVE"]["reason_codes"]

from ibkr_paper_30d.autonomous_research import ResearchResult, ResearchTool
from ibkr_paper_30d.autonomous_state import (
    AutonomousStateBuildError,
    AutonomousStateBuilder,
    _commission_adjusted_cash_matches,
    _trusted_commission_from_outcome,
)
from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.continuity_store import ContinuityStore
from ibkr_paper_30d.experiment_control import KillSwitchStore
from ibkr_paper_30d.multi_universe_models import (
    ProductFamilyKey,
    REGULAR_DAY1_PRODUCT_FAMILY,
)
from ibkr_paper_30d.open_order_management import canonical_open_order
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_clock import BrokerTimeObservation, clock_for_epoch
from ibkr_paper_30d.successor_epoch import (
    BrokerTransitionEvidence,
    commit_successor_transition,
)
from successor_test_support import (
    ACCOUNT_HASH,
    OWNER_SID,
    SUCCESSOR_START,
    build_authorized_successor,
)


def test_missing_commission_recovery_requires_exact_accepted_outcome_binding():
    action = {
        "action": "SELL",
        "capital_sleeve": "REGULAR_SLEEVE",
        "contract_id": 7884,
        "expiry": None,
        "limit_price": "118.25",
        "order_type": "LMT",
        "product_family_sha256": "a" * 64,
        "quantity": "4",
        "reason": "Exit the position.",
        "right": None,
        "sec_type": "STK",
        "strike": None,
        "symbol": "HAE",
        "time_in_force": "DAY",
    }
    invocation_id = "autonomous-commission-test"
    authority = {
        "event_type": "EXECUTION_AUTHORITY_RESERVED",
        "event_sha256": "b" * 64,
        "execution_key": (
            f"model:writer-id:{invocation_id}:POSITION_ACTION:{sha256_json(action)}"
        ),
        "operation": "POSITION_ACTION",
        "order_ref": "codex-ibkr-paper-30d-p-hae",
        "capital_sleeve": "REGULAR_SLEEVE",
        "contract_identity_sha256": "c" * 64,
    }
    result = {
        "accepted": True,
        "validation": "PASS",
        "decision": "CLOSE_POSITION",
        "invocation_id": invocation_id,
        "position_action": action,
        "broker_validation": {
            "success": True,
            "whatIf": True,
            "commission": 1.0097558,
            "requested_quantity": "4",
            "contract": {"conId": 7884, "currency": "USD"},
        },
    }
    fill = {
        "execution_id_hash": "d" * 64,
        "orderRef": "codex-ibkr-paper-30d-p-hae",
        "side": "SELL",
        "quantity": "4.0",
        "contract": {"conId": 7884},
    }

    assert _trusted_commission_from_outcome(fill, authority, result) == Decimal(
        "1.0097558"
    )
    assert _trusted_commission_from_outcome(
        {**fill, "quantity": "3"}, authority, result
    ) is None
    assert _trusted_commission_from_outcome(
        fill,
        authority,
        {**result, "broker_validation": {**result["broker_validation"], "whatIf": False}},
    ) is None
    assert _trusted_commission_from_outcome(
        fill,
        {**authority, "execution_key": authority["execution_key"][:-1] + "0"},
        result,
    ) is None


def test_missing_entry_commission_recovery_requires_exact_proposal_binding():
    proposal = {
        "action": "BUY",
        "capital_sleeve": "REGULAR_SLEEVE",
        "quantity": "69",
        "symbol": "WEN",
    }
    invocation_id = "autonomous-entry-commission-test"
    authority = {
        "event_type": "EXECUTION_AUTHORITY_RESERVED",
        "event_sha256": "b" * 64,
        "execution_key": (
            f"model:writer-id:{invocation_id}:NEW_TRADE:{sha256_json(proposal)}"
        ),
        "operation": "NEW_TRADE",
        "order_ref": "codex-ibkr-paper-30d-a-wen",
        "capital_sleeve": "REGULAR_SLEEVE",
    }
    result = {
        "accepted": True,
        "validation": "PASS",
        "decision": "PROPOSE_TRADE",
        "invocation_id": invocation_id,
        "proposal": proposal,
        "broker_validation": {
            "what_if": {
                "success": True,
                "whatIf": True,
                "commission": 1.000207,
                "contract": {"conId": 90655688, "currency": "USD"},
            }
        },
    }
    fill = {
        "execution_id_hash": "d" * 64,
        "orderRef": "codex-ibkr-paper-30d-a-wen",
        "side": "BUY",
        "quantity": "69.0",
        "contract": {"conId": 90655688},
    }

    assert _trusted_commission_from_outcome(fill, authority, result) == Decimal(
        "1.000207"
    )
    assert _trusted_commission_from_outcome(
        {**fill, "quantity": "68"}, authority, result
    ) is None


def test_usd_cash_values_accepts_raw_ibkr_reconciliation_snapshot_shape():
    account = {
        "cash_balance_basis": "IBKR_LEDGER_CASH_BALANCE_USD_V1",
        "cash_reporting_quantum_usd": "0.0001",
        "broker_snapshot_sha256": "a" * 64,
        "currency_balances": [{"currency": "USD", "amount": "254845.3702"}],
        "classified_canary_currency_balances": [],
        "classified_non_experiment_currency_balances": [
            {"currency": "USD", "amount": "253880.174886"}
        ],
    }
    ledger = {
        "aggregate_currency_balances": [
            {"currency": "USD", "amount": "966.2050698"}
        ]
    }

    assert AutonomousStateBuilder._usd_cash_values(account, ledger) == (
        Decimal("254845.3702"),
        Decimal("254846.3799558"),
        Decimal("0.0001"),
    )


def test_missing_commission_cash_comparison_ignores_ambient_decimal_precision():
    with localcontext() as context:
        context.prec = 6
        assert _commission_adjusted_cash_matches(
            actual=Decimal("254375.4615"),
            expected=Decimal("254376.46174400000000000"),
            commission=Decimal("1.000207"),
            quantum=Decimal("0.01"),
        )


class _Dumpable:
    def __init__(self, payload):
        self.payload = payload

    def model_dump(self, *, mode="python"):
        return self.payload


def test_authenticated_broker_session_replaces_unknown_requested_session() -> None:
    assert state_module._resolved_market_session_state(
        "UNKNOWN", {"session": "REGULAR"}
    ) == "REGULAR"
    assert state_module._resolved_market_session_state(
        "UNKNOWN", {"session": "AFTER_HOURS"}
    ) == "AFTER_HOURS"
    assert state_module._resolved_market_session_state(
        "PREMARKET", {"session": "REGULAR"}
    ) == "PREMARKET"


def test_v4_state_context_contains_both_sleeves_ownership_and_capabilities() -> None:
    subject = object.__new__(AutonomousStateBuilder)
    subject.sleeve_ledger_store = SimpleNamespace(
        project_all=lambda: _Dumpable(
            {
                "regular": {
                    "sleeve": "REGULAR_SLEEVE",
                    "allocation_usd": "500",
                    "currency_balances": [{"currency": "USD", "amount": "450"}],
                    "positions": [{"market_value_usd": "25"}],
                    "realized_pnl_usd": "-25",
                    "unrealized_pnl_usd": "0",
                    "fees_usd": "0",
                    "initialized": True,
                },
                "continuous": {
                    "sleeve": "CONTINUOUS_SLEEVE",
                    "allocation_usd": "500",
                    "currency_balances": [{"currency": "USD", "amount": "510"}],
                    "positions": [],
                    "realized_pnl_usd": "10",
                    "unrealized_pnl_usd": "0",
                    "fees_usd": "0",
                    "initialized": True,
                },
                "aggregate_currency_balances": [{"currency": "USD", "amount": "1000"}],
            }
        )
    )
    subject.contract_ownership_store = SimpleNamespace(
        projection=lambda: _Dumpable(
            {
                "active_contracts": [
                    {
                        "contract_identity_sha256": "c" * 64,
                        "contract": {"con_id": 756733},
                        "sleeve": "REGULAR_SLEEVE",
                    }
                ],
                "projection_sha256": "o" * 64,
            }
        )
    )
    subject.product_certification_store = SimpleNamespace(
        projections=lambda: (
            _Dumpable(
                {
                    "family_sha256": "f" * 64,
                    "status": "FULL_LIFECYCLE_VERIFIED",
                    "executable": True,
                }
            ),
        )
    )

    family_sha256 = "f" * 64
    portfolio, ownership, capabilities = subject._multi_sleeve_context(
        reconciliation={"status": "BLOCK", "reason_codes": ["ACCOUNT_MISMATCH"]},
        account={"net_liquidation": "1000"},
        broker_positions={"positions": [{"contract_id": 756733}]},
        open_orders={"open_orders": []},
        transition_phase="ACTIVE",
        regular_entry_open=True,
        family_sessions={
            family_sha256: {
                "authenticated": True,
                "tradable_now": True,
                "session": "REGULAR",
                "eligible_sleeves": [
                    "REGULAR_SLEEVE",
                    "CONTINUOUS_SLEEVE",
                ],
            }
        },
    )

    assert portfolio["schema"] == "MULTI_SLEEVE_PORTFOLIO_V4"
    assert set(portfolio["sleeves"]) == {"regular", "continuous"}
    assert portfolio["sleeves"]["regular"]["equity_usd"] == "475"
    assert portfolio["sleeves"]["continuous"]["equity_usd"] == "510"
    assert portfolio["new_entries_enabled"] is False
    assert portfolio["transition_phase"] == "ACTIVE"
    assert set(portfolio["entry_eligibility"]) == {
        "REGULAR_SLEEVE",
        "CONTINUOUS_SLEEVE",
    }
    assert portfolio["entry_eligibility"]["CONTINUOUS_SLEEVE"] == {
        "status": "BLOCK",
        "reason_codes": ["BROKER_RECONCILIATION_REQUIRED"],
        "eligible_family_sha256": [family_sha256],
    }
    assert portfolio["entry_eligibility"]["REGULAR_SLEEVE"] == {
        "status": "BLOCK",
        "reason_codes": ["BROKER_RECONCILIATION_REQUIRED"],
        "eligible_family_sha256": [
            REGULAR_DAY1_PRODUCT_FAMILY.sha256,
            family_sha256,
        ],
    }
    assert portfolio["management_eligibility"]["756733"]["status"] == "PASS"
    assert portfolio["account_observation"]["position_count"] == 1
    assert ownership["contract_sleeves"] == {"756733": "REGULAR_SLEEVE"}
    assert capabilities["families"][0]["family_sha256"] == "f" * 64
    assert capabilities["authenticated_sessions"] == {
        REGULAR_DAY1_PRODUCT_FAMILY.sha256: {
            "authenticated": True,
            "tradable_now": True,
            "session": "REGULAR",
            "eligible_sleeves": ["REGULAR_SLEEVE"],
        },
        family_sha256: {
            "authenticated": True,
            "tradable_now": True,
            "session": "REGULAR",
            "eligible_sleeves": [
                "REGULAR_SLEEVE",
                "CONTINUOUS_SLEEVE",
            ],
        },
    }


def test_supervision_exposes_only_regular_entry_eligibility() -> None:
    subject = object.__new__(AutonomousStateBuilder)
    subject.sleeve_ledger_store = SimpleNamespace(
        project_all=lambda: _Dumpable(
            {
                "regular": {
                    "initialized": True,
                    "allocation_usd": "500",
                    "realized_pnl_usd": "0",
                    "unrealized_pnl_usd": "0",
                    "fees_usd": "0",
                },
                "continuous": {
                    "initialized": True,
                    "allocation_usd": "500",
                    "realized_pnl_usd": "0",
                    "unrealized_pnl_usd": "0",
                    "fees_usd": "0",
                },
                "aggregate_currency_balances": [],
            }
        )
    )
    subject.contract_ownership_store = SimpleNamespace(
        projection=lambda: _Dumpable(
            {"active_contracts": [], "projection_sha256": "o" * 64}
        )
    )
    subject.product_certification_store = SimpleNamespace(projections=lambda: ())
    family_sha256 = REGULAR_DAY1_PRODUCT_FAMILY.sha256

    portfolio, _, _ = subject._multi_sleeve_context(
        reconciliation={"status": "PASS", "reason_codes": []},
        account={},
        broker_positions={"positions": []},
        open_orders={"open_orders": []},
        transition_phase="SUPERVISION_BOUND",
        regular_entry_open=True,
        family_sessions={},
    )

    assert portfolio["entry_eligibility"]["REGULAR_SLEEVE"] == {
        "status": "PASS",
        "reason_codes": [],
        "eligible_family_sha256": [family_sha256],
    }
    assert portfolio["entry_eligibility"]["CONTINUOUS_SLEEVE"] == {
        "status": "BLOCK",
        "reason_codes": ["SUCCESSOR_NOT_ACTIVE", "FAMILY_SESSION_CLOSED"],
        "eligible_family_sha256": [],
    }
    assert portfolio["new_entries_enabled"] is True


def test_open_regular_session_reports_market_gate_block_without_disabling_management() -> None:
    subject = object.__new__(AutonomousStateBuilder)
    subject.sleeve_ledger_store = SimpleNamespace(
        project_all=lambda: _Dumpable(
            {
                "regular": {
                    "initialized": True,
                    "allocation_usd": "500",
                    "realized_pnl_usd": "0",
                    "unrealized_pnl_usd": "0",
                    "fees_usd": "0",
                },
                "continuous": {
                    "initialized": True,
                    "allocation_usd": "500",
                    "realized_pnl_usd": "0",
                    "unrealized_pnl_usd": "0",
                    "fees_usd": "0",
                },
                "aggregate_currency_balances": [],
            }
        )
    )
    subject.contract_ownership_store = SimpleNamespace(
        projection=lambda: _Dumpable(
            {
                "active_contracts": [
                    {
                        "contract_identity_sha256": "c" * 64,
                        "contract": {"con_id": 10828168},
                        "sleeve": "REGULAR_SLEEVE",
                    }
                ],
                "projection_sha256": "o" * 64,
            }
        )
    )
    subject.product_certification_store = SimpleNamespace(projections=lambda: ())

    portfolio, _, capabilities = subject._multi_sleeve_context(
        reconciliation={"status": "PASS", "reason_codes": []},
        account={},
        broker_positions={"positions": [{"contract_id": 10828168}]},
        open_orders={"open_orders": []},
        transition_phase="ACTIVE",
        regular_entry_open=False,
        regular_session_open=True,
        regular_market_gate_reason_codes=("TIMESTAMP_MISMATCH", "CLOCK_SKEW"),
    )

    regular_family = REGULAR_DAY1_PRODUCT_FAMILY.sha256
    assert portfolio["entry_eligibility"]["REGULAR_SLEEVE"] == {
        "status": "BLOCK",
        "reason_codes": [
            "MARKET_DATA_GATE_BLOCK",
            "TIMESTAMP_MISMATCH",
            "CLOCK_SKEW",
        ],
        "eligible_family_sha256": [regular_family],
    }
    assert portfolio["management_eligibility"]["10828168"]["status"] == "PASS"
    assert capabilities["authenticated_sessions"][regular_family] == {
        "authenticated": True,
        "tradable_now": True,
        "session": "REGULAR",
        "eligible_sleeves": ["REGULAR_SLEEVE"],
    }


def test_continuous_owned_position_in_current_family_is_manageable() -> None:
    subject = object.__new__(AutonomousStateBuilder)
    subject.sleeve_ledger_store = SimpleNamespace(
        project_all=lambda: _Dumpable(
            {
                "regular": {"initialized": True},
                "continuous": {"initialized": True},
                "aggregate_currency_balances": [],
            }
        )
    )
    family = ProductFamilyKey(
        security_type="CRYPTO",
        venue_or_routing="PAXOS",
        quantity_semantics="FRACTIONAL_ASSET_UNITS",
        order_representation="DIRECT",
        lifecycle_behavior="CONTINUOUS_24X7",
    )
    subject.contract_ownership_store = SimpleNamespace(
        projection=lambda: _Dumpable(
            {
                "active_contracts": [
                    {
                        "contract_identity_sha256": "c" * 64,
                        "contract": {
                            "con_id": 766137558,
                            "security_type": "CRYPTO",
                            "exchange": "PAXOS",
                        },
                        "sleeve": "CONTINUOUS_SLEEVE",
                    }
                ],
                "projection_sha256": "o" * 64,
            }
        )
    )
    subject.product_certification_store = SimpleNamespace(
        projections=lambda: (
            _Dumpable(
                {
                    "family": family.model_dump(mode="json"),
                    "family_sha256": family.sha256,
                    "status": "FULL_LIFECYCLE_VERIFIED",
                    "executable": True,
                }
            ),
        )
    )

    portfolio, _, _ = subject._multi_sleeve_context(
        reconciliation={"status": "PASS", "reason_codes": []},
        account={},
        broker_positions={
            "positions": [
                {
                    "contract": {
                        "conId": 766137558,
                        "secType": "CRYPTO",
                        "exchange": "PAXOS",
                    }
                }
            ]
        },
        open_orders={"open_orders": []},
        transition_phase="ACTIVE",
        family_sessions={
            family.sha256: {
                "authenticated": True,
                "tradable_now": True,
                "session": "REGULAR",
                "eligible_sleeves": ["CONTINUOUS_SLEEVE"],
            }
        },
    )

    assert portfolio["management_eligibility"]["766137558"] == {
        "status": "PASS",
        "reason_codes": [],
        "capital_sleeve": "CONTINUOUS_SLEEVE",
        "contract_identity_sha256": "c" * 64,
    }


def test_continuous_owned_position_does_not_borrow_another_venues_family() -> None:
    subject = object.__new__(AutonomousStateBuilder)
    subject.sleeve_ledger_store = SimpleNamespace(
        project_all=lambda: _Dumpable(
            {
                "regular": {"initialized": True},
                "continuous": {"initialized": True},
                "aggregate_currency_balances": [],
            }
        )
    )
    family = ProductFamilyKey(
        security_type="CRYPTO",
        venue_or_routing="PAXOS",
        quantity_semantics="FRACTIONAL_ASSET_UNITS",
        order_representation="DIRECT",
        lifecycle_behavior="CONTINUOUS_24X7",
    )
    subject.contract_ownership_store = SimpleNamespace(
        projection=lambda: _Dumpable(
            {
                "active_contracts": [
                    {
                        "contract_identity_sha256": "c" * 64,
                        "contract": {
                            "con_id": 766137558,
                            "security_type": "CRYPTO",
                            "exchange": "OTHER",
                        },
                        "sleeve": "CONTINUOUS_SLEEVE",
                    }
                ],
                "projection_sha256": "o" * 64,
            }
        )
    )
    subject.product_certification_store = SimpleNamespace(
        projections=lambda: (
            _Dumpable(
                {
                    "family": family.model_dump(mode="json"),
                    "family_sha256": family.sha256,
                    "status": "FULL_LIFECYCLE_VERIFIED",
                    "executable": True,
                }
            ),
        )
    )

    portfolio, _, _ = subject._multi_sleeve_context(
        reconciliation={"status": "PASS", "reason_codes": []},
        account={},
        broker_positions={"positions": [{"contract_id": 766137558}]},
        open_orders={"open_orders": []},
        transition_phase="ACTIVE",
        family_sessions={
            family.sha256: {
                "authenticated": True,
                "tradable_now": True,
                "eligible_sleeves": ["CONTINUOUS_SLEEVE"],
            }
        },
    )

    assert portfolio["management_eligibility"]["766137558"]["status"] == "BLOCK"


def test_v4_state_blocks_until_both_sleeves_are_bootstrapped() -> None:
    subject = object.__new__(AutonomousStateBuilder)
    subject.sleeve_ledger_store = SimpleNamespace(
        project_all=lambda: _Dumpable(
            {
                "regular": {"sleeve": "REGULAR_SLEEVE", "initialized": True},
                "continuous": {
                    "sleeve": "CONTINUOUS_SLEEVE",
                    "initialized": False,
                },
                "aggregate_currency_balances": [],
            }
        )
    )
    subject.contract_ownership_store = SimpleNamespace(
        projection=lambda: _Dumpable(
            {"active_contracts": [], "projection_sha256": "c" * 64}
        )
    )
    subject.product_certification_store = SimpleNamespace(projections=lambda: ())

    with pytest.raises(AutonomousStateBuildError, match="V4_SLEEVE_BOOTSTRAP_REQUIRED"):
        subject._multi_sleeve_context(
            reconciliation={"status": "PASS", "reason_codes": []},
            account={},
            broker_positions={"positions": []},
            open_orders={"open_orders": []},
        )


def test_supervision_missing_regular_mark_blocks_only_that_contract() -> None:
    subject = object.__new__(AutonomousStateBuilder)
    subject.sleeve_ledger_store = SimpleNamespace(
        project_all=lambda: _Dumpable(
            {
                "regular": {
                    "initialized": True,
                    "allocation_usd": "500",
                    "currency_balances": [{"currency": "USD", "amount": "0"}],
                    "positions": [],
                    "realized_pnl_usd": "0",
                    "unrealized_pnl_usd": "0",
                    "fees_usd": "0",
                },
                "continuous": {
                    "initialized": True,
                    "allocation_usd": "500",
                    "currency_balances": [{"currency": "USD", "amount": "500"}],
                    "positions": [],
                    "realized_pnl_usd": "0",
                    "unrealized_pnl_usd": "0",
                    "fees_usd": "0",
                },
                "aggregate_currency_balances": [{"currency": "USD", "amount": "500"}],
            }
        )
    )
    subject.contract_ownership_store = SimpleNamespace(
        projection=lambda: _Dumpable(
            {
                "active_contracts": [
                    {
                        "contract_identity_sha256": "c" * 64,
                        "contract": {"con_id": 7884},
                        "sleeve": "REGULAR_SLEEVE",
                    }
                ],
                "projection_sha256": "o" * 64,
            }
        )
    )
    subject.product_certification_store = SimpleNamespace(projections=lambda: ())

    portfolio, _, _ = subject._multi_sleeve_context(
        reconciliation={"status": "PASS", "reason_codes": []},
        account={},
        broker_positions={"positions": [{"contract_id": 7884}]},
        open_orders={"open_orders": []},
        transition_phase="SUPERVISION_BOUND",
        unmarked_contract_ids={7884},
        mark_reason_codes=("MARK_QUOTE_INVALID:7884",),
    )

    assert portfolio["new_entries_enabled"] is False
    assert portfolio["management_eligibility"]["7884"] == {
        "status": "BLOCK",
        "reason_codes": ["FRESH_MARK_REQUIRED"],
        "capital_sleeve": "REGULAR_SLEEVE",
        "contract_identity_sha256": "c" * 64,
    }
    assert portfolio["market_data_advisories"] == ["MARK_QUOTE_INVALID:7884"]


def test_v4_reconciliation_uses_independent_broker_cash_not_ledger_copy() -> None:
    class Ownership:
        active_contracts = ()

        def model_dump(self, *, mode="python"):
            return {"active_contracts": [], "projection_sha256": "a" * 64}

    ledger_payload = {
        "regular": {
            "initialized": True,
            "currency_balances": [{"currency": "USD", "amount": "500"}],
            "positions": [],
            "open_order_count": 0,
            "fees_usd": "0",
        },
        "extended": {
            "initialized": True,
            "currency_balances": [{"currency": "USD", "amount": "500"}],
            "positions": [],
            "open_order_count": 0,
            "fees_usd": "0",
        },
        "aggregate_currency_balances": [{"currency": "USD", "amount": "1000"}],
    }
    ledger_store = SimpleNamespace(
        reconcile_broker_snapshot=lambda _snapshot, _ownership: {},
        project_all=lambda: _Dumpable(ledger_payload),
    )
    subject = object.__new__(AutonomousStateBuilder)
    subject.sleeve_ledger_store = ledger_store
    subject.contract_ownership_store = SimpleNamespace(projection=lambda: Ownership())
    observed_times = []

    def account_reconciliation_snapshot(*, observed_at_utc):
        observed_times.append(observed_at_utc)
        return {
            "paper_only": True,
            "account_identity_sha256": "b" * 64,
            "currency_balances": [{"currency": "USD", "amount": "1001"}],
            "broker_snapshot_sha256": "c" * 64,
        }

    subject.toolbox = SimpleNamespace(
        account_reconciliation_snapshot=account_reconciliation_snapshot
    )
    subject._latest_executions = []
    subject._transition_cash_classifications = lambda: {
        "classified_canary_currency_balances": [],
        "classified_non_experiment_currency_balances": [],
    }

    receipt = subject._sync_and_reconcile_v4(
        account={
            "paper_account": True,
            "server_time_utc": "2026-10-16T04:28:12Z",
        },
        broker_positions={"positions": []},
        open_orders={"open_orders": []},
    )

    assert receipt["status"] == "BLOCK"
    assert "AGGREGATE_CURRENCY_MISMATCH:USD" in receipt["reason_codes"]
    assert observed_times == ["2026-10-16T04:28:12Z"]


def open_order_trade():
    return SimpleNamespace(
        contract=SimpleNamespace(
            conId=756733,
            symbol="SPY",
            localSymbol="SPY",
            secType="STK",
            exchange="SMART",
            currency="USD",
            lastTradeDateOrContractMonth="",
            strike=0,
            right="",
            multiplier="1",
        ),
        order=SimpleNamespace(
            orderRef="codex-ibkr-paper-30d-a-cycle",
            orderId=41,
            permId=9001,
            clientId=19761,
            account="DU1234567",
            action="BUY",
            orderType="LMT",
            totalQuantity=2,
            lmtPrice=10,
            auxPrice=0,
            tif="DAY",
            outsideRth=False,
        ),
        orderStatus=SimpleNamespace(status="Submitted", filled=0, remaining=2),
    )


class FakeMarketGate:
    def evaluate(self, decision_class):
        return {
            "gate_status": "PASS",
            "reason_codes": [],
            "policy_version": "MARKET_DATA_POLICY_V1",
            "snapshot_id": "fake",
            "snapshot_sha256": "a" * 64,
        }


def test_state_builder_classifies_transient_broker_read_failure():
    class TimeoutToolbox:
        def execute(self, request, bundle):
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=False,
                data={},
                error="TimeoutError:tool_failed",
            )

    subject = object.__new__(AutonomousStateBuilder)
    subject.toolbox = TimeoutToolbox()

    with pytest.raises(
        state_module.TransientBrokerStateBuildError,
        match="POSITIONS_FAILED:TimeoutError:tool_failed",
    ):
        subject._tool(ResearchTool.POSITIONS)


def test_state_builder_classifies_connection_subclass_as_transient():
    class ConnectionFailureToolbox:
        def execute(self, request, bundle):
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=False,
                data={},
                error="ConnectionRefusedError:tool_failed",
            )

    subject = object.__new__(AutonomousStateBuilder)
    subject.toolbox = ConnectionFailureToolbox()

    with pytest.raises(state_module.TransientBrokerStateBuildError):
        subject._tool(ResearchTool.POSITIONS)


def test_state_builder_keeps_identity_failure_non_transient():
    class IdentityFailureToolbox:
        def execute(self, request, bundle):
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=False,
                data={},
                error="PermissionError:tool_failed",
            )

    subject = object.__new__(AutonomousStateBuilder)
    subject.toolbox = IdentityFailureToolbox()

    with pytest.raises(AutonomousStateBuildError) as exc_info:
        subject._tool(ResearchTool.POSITIONS)

    assert not isinstance(exc_info.value, state_module.TransientBrokerStateBuildError)


class FakeToolbox:
    def __init__(
        self,
        broker_quantity="1",
        include_spoofed_fill=False,
        fill_updates=None,
    ):
        self.broker_quantity = broker_quantity
        self.include_spoofed_fill = include_spoofed_fill
        self.fill_updates = fill_updates or {}
        self.calls = []

    def execute(self, request, bundle):
        self.calls.append(request.tool)
        if request.tool == ResearchTool.EXECUTIONS:
            executions = [
                {
                    "execution_id_hash": "exec-1",
                    "orderRef": "codex-ibkr-paper-30d-autonomous",
                    "orderId": 44,
                    "permId": 55,
                    "clientId": 19761,
                    "execution_time": "2026-09-21T13:31:00Z",
                    "cumQty": "1",
                    "side": "BUY",
                    "quantity": "1",
                    "price": "2.00",
                    "commission": "1.00",
                    "contract": {
                        "conId": 101,
                        "symbol": "XYZ",
                        "secType": "OPT",
                        "multiplier": "100",
                    },
                    **self.fill_updates,
                }
            ]
            if self.include_spoofed_fill:
                executions.append(
                    {
                        **executions[0],
                        "execution_id_hash": "exec-spoofed",
                        "orderRef": "codex-ibkr-paper-30devil",
                    }
                )
            data = {"executions": executions}
        elif request.tool == ResearchTool.QUOTE:
            data = {"marketPrice": 3.0}
        elif request.tool == ResearchTool.ACCOUNT_STATE:
            data = {
                "paper_account": True,
                "declared_options_level": 4,
                "summary": {"BuyingPower": "10000", "NetLiquidation": "10000"},
                "server_time_utc": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        elif request.tool == ResearchTool.POSITIONS:
            data = {
                "positions": [
                    {
                        "contract": {"conId": 101, "symbol": "XYZ", "secType": "OPT"},
                        "position": self.broker_quantity,
                        "avgCost": 200.0,
                    }
                ]
            }
        elif request.tool == ResearchTool.OPEN_ORDERS:
            owned = canonical_open_order(open_order_trade())
            data = {
                "open_orders": [
                    {"orderRef": "unrelated", "orderId": 1},
                    {
                        "orderRef": "codex-ibkr-paper-30devil",
                        "orderId": 2,
                    },
                    owned,
                ]
            }
        else:
            raise AssertionError(f"unexpected tool {request.tool}")
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=True,
            data=data,
        )


def builder(
    db,
    toolbox,
    *,
    anchor_perm_id=55,
    payload_sha256=None,
):
    KillSwitchStore(db).set(
        "KILL_SWITCH_CLEAR",
        reason="explicit test Owner authorization boundary",
        actor="test-owner",
    )
    payload = {
        "schema": "EXPERIMENT_ORDER_REGISTRY_V2",
        "lifecycle_event": "ISSUED_PRE_SEND",
        "order_ref": "codex-ibkr-paper-30d-autonomous",
        "client_order_id": 44,
        "perm_id": anchor_perm_id,
        "ibkr_order_id": 44,
        "contract_id": 101,
        "action": "BUY",
        "quantity": "1",
        "execution_client_id": 19761,
        "account": "DU1234567",
    }
    db.execute(
        "INSERT INTO experiment_order_registry("
        "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
        "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            "registry-1",
            "codex-ibkr-paper-30d-autonomous",
            44,
            anchor_perm_id,
            44,
            101,
            "BUY",
            "1",
            canonical_bytes(payload).decode("utf-8"),
            payload_sha256 or sha256_json(payload),
            "2026-09-21T13:30:00Z",
        ),
    )
    return AutonomousStateBuilder(
        db,
        toolbox,
        allocation=Decimal("500.00"),
        experiment_start_utc=datetime.now(timezone.utc) - timedelta(days=1),
        duration_days=30,
        runtime_market_gate=FakeMarketGate(),
    )


def register_bag_binding(db):
    payload = {
        "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
        "lifecycle_event": "BROKER_BOUND",
        "order_ref": "codex-ibkr-paper-30d-a-bag-cycle",
        "client_order_id": 13,
        "perm_id": 1401602203,
        "ibkr_order_id": 13,
        "contract_id": 28812380,
        "action": "BUY",
        "quantity": "1",
        "execution_client_id": 19761,
        "account": "DU1234567",
        "contract": {
            "conId": 28812380,
            "symbol": "IOVA",
            "secType": "BAG",
            "exchange": "SMART",
            "currency": "USD",
            "comboLegs": [
                {"conId": 913925915, "ratio": 1, "action": "BUY", "exchange": "SMART"},
                {"conId": 926221865, "ratio": 1, "action": "SELL", "exchange": "SMART"},
            ],
        },
    }
    db.execute(
        "INSERT INTO experiment_order_registry("
        "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
        "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            "bag-binding",
            payload["order_ref"],
            13,
            1401602203,
            13,
            28812380,
            "BUY",
            "1",
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            "2026-09-29T17:55:57Z",
        ),
    )


def bag_fill(*, con_id, side, account="DU1234567", quantity="1", cum_qty="1"):
    return {
        "execution_id_hash": f"exec-{con_id}-{side}",
        "orderRef": "codex-ibkr-paper-30d-a-bag-cycle",
        "orderId": 13,
        "permId": 1401602203,
        "clientId": 19761,
        "account": account,
        "execution_time": "2026-09-29T18:00:00Z",
        "cumQty": cum_qty,
        "side": side,
        "quantity": quantity,
        "price": "0.50",
        "commission": "0",
        "contract": {
            "conId": con_id,
            "symbol": "IOVA",
            "secType": "OPT",
            "multiplier": "100",
        },
    }


def test_state_builder_cannot_override_default_kill_switch(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        with pytest.raises(
            AutonomousStateBuildError, match="KILL_SWITCH_OVERRIDE_FORBIDDEN"
        ):
            AutonomousStateBuilder(
                db,
                FakeToolbox(),
                experiment_start_utc=datetime.now(timezone.utc),
                kill_switch_state="KILL_SWITCH_CLEAR",
                runtime_market_gate=FakeMarketGate(),
            )
        assert KillSwitchStore(db).current() == "KILL_SWITCH_TRIGGERED"
        assert db.execute("SELECT COUNT(*) FROM kill_switch_events").fetchone()[0] == 0


def test_state_builder_refreshes_equity_and_keeps_discovery_unconstrained(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        subject = builder(db, FakeToolbox())
        value = subject.build(trigger="SCHEDULED_SCAN", market_session_state="REGULAR")

        assert value.experiment_subledger_snapshot["cash"] == "299.00"
        assert value.experiment_subledger_snapshot["market_value"] == "300.00"
        assert value.experiment_subledger_snapshot["equity"] == "599.00"
        assert value.positions_snapshot[0]["contract_id"] == 101
        assert value.positions_snapshot[0]["quantity"] == "1"
        assert value.candidate_screen_results == []
        assert value.reconciliation_receipt["status"] == "PASS"
        assert value.market_data_snapshot["gate_status"] == "PASS"
        assert value.broker_account_snapshot["declared_options_level"] == 4
        assert value.broker_account_snapshot["experiment_buying_power"] == "599.00"
        assert value.broker_account_snapshot["global_broker_balances_redacted"] is True
        assert value.experiment_clock["remaining_days"] > 28
        assert value.experiment_clock["epoch_state"] == "PRE_EPOCH_HISTORY"
        assert value.experiment_clock["epoch_id"] is None
        assert value.experiment_clock["epoch_activation_required"] is True
        assert len(value.open_orders_snapshot) == 1
        open_order = value.open_orders_snapshot[0]
        assert open_order["permId"] == 9001
        assert open_order["clientId"] == 19761
        assert open_order["contract"]["conId"] == 756733
        assert len(open_order["state_sha256"]) == 64


def test_state_builder_exposes_v3_continuity_context_without_strategy_guidance(
    tmp_path,
):
    from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
    from ibkr_paper_30d.successor_schema import install_successor_schema_v2

    with Database.open(tmp_path / "state.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        value = builder(db, FakeToolbox()).build(trigger="SCHEDULED_SCAN")

    assert value.continuity_context["status"] == "AVAILABLE"
    assert value.continuity_context["authority_contract_required"] is True
    assert value.continuity_context["active_plans"] == []
    assert value.continuity_context["provider_states"] == []
    assert value.continuity_context["pending_factual_reports"] == []
    assert value.continuity_context["prior_reflections"] == []


def _persist_completed_cycle(
    db,
    *,
    index,
    trigger,
    decision,
    accepted,
    symbols,
    tools,
    scanner_queries=0,
    option_chains=0,
    feasibility_checks=0,
):
    cycle_id = f"cycle-observation-{index}"
    invocation_id = f"invocation-observation-{index}"
    bundle_id = f"bundle-observation-{index}"
    bundle_payload = {"decision_cycle_id": cycle_id}
    invocation_payload = {
        "decision_cycle_id": cycle_id,
        "invocation_id": invocation_id,
        "invocation_trigger": trigger,
    }
    final_payload = {
        "decision_cycle_id": cycle_id,
        "invocation_id": invocation_id,
        "accepted": accepted,
        "decision": decision,
        "reason_codes": [],
    }
    telemetry = {
        "schema": "CODEX_RESEARCH_TELEMETRY_V1",
        "telemetry_source": "SYSTEM_GENERATED",
        "research_requests_executed": len(tools),
        "tools_used": tools,
        "scanner_queries": scanner_queries,
        "scanner_results_received": len(symbols) if scanner_queries else 0,
        "symbols_examined": symbols,
        "asset_classes_examined": [],
        "option_chains_queried": option_chains,
        "candidates_generated": len(symbols),
        "feasibility_checks": feasibility_checks,
        "blocked_requests": 0,
    }
    db.execute(
        "INSERT INTO trader_input_bundles(bundle_id,decision_cycle_id,payload_json,"
        "payload_sha256,created_at_utc) VALUES(?,?,?,?,?)",
        (
            bundle_id,
            cycle_id,
            canonical_bytes(bundle_payload).decode("utf-8"),
            sha256_json(bundle_payload),
            f"2026-10-09T14:{index:02d}:00Z",
        ),
    )
    db.execute(
        "INSERT INTO trader_invocations(invocation_id,decision_cycle_id,bundle_id,"
        "payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?)",
        (
            invocation_id,
            cycle_id,
            bundle_id,
            canonical_bytes(invocation_payload).decode("utf-8"),
            sha256_json(invocation_payload),
            f"2026-10-09T14:{index:02d}:01Z",
        ),
    )
    for event_type, payload, round_index in (
        (
            "research_telemetry_summary",
            {
                "decision_cycle_id": cycle_id,
                "invocation_id": invocation_id,
                "event": telemetry,
            },
            1,
        ),
        ("final_outcome", final_payload, 2),
    ):
        db.execute(
            "INSERT INTO autonomous_research_events(event_id,decision_cycle_id,"
            "invocation_id,round_index,event_type,payload_json,payload_sha256,"
            "created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
            (
                f"event-{event_type}-{index}",
                cycle_id,
                invocation_id,
                round_index,
                event_type,
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                f"2026-10-09T14:{index:02d}:02Z",
            ),
        )


def test_state_builder_projects_factual_process_observation_without_guidance(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        _persist_completed_cycle(
            db,
            index=1,
            trigger="SCHEDULED_SCAN",
            decision="NO_TRADE",
            accepted=True,
            symbols=["HAE"],
            tools=["QUOTE", "NEWS_SEARCH"],
        )
        _persist_completed_cycle(
            db,
            index=2,
            trigger="POSITION_EVENT",
            decision="MONITOR_POSITION",
            accepted=True,
            symbols=["HAE"],
            tools=["QUOTE"],
        )

        value = builder(db, FakeToolbox()).build(
            trigger="SCHEDULED_SCAN",
            benchmark_state={"owner_benchmark": "preserved"},
        )

    observation = value.benchmark_state["autonomous_process_observation"]
    assert value.benchmark_state["owner_benchmark"] == "preserved"
    assert observation["telemetry_source"] == "SYSTEM_GENERATED_DURABLE_EVENTS"
    assert observation["cycles_observed"] == 2
    assert observation["trigger_counts"] == {
        "POSITION_EVENT": 1,
        "SCHEDULED_SCAN": 1,
    }
    assert observation["decision_counts"] == {
        "MONITOR_POSITION": 1,
        "NO_TRADE": 1,
    }
    assert observation["latest_kill_switch_event"] == {
        "actor": "test-owner",
        "reason_code": None,
        "recovery_receipt_present": False,
        "state": "KILL_SWITCH_CLEAR",
    }
    assert observation["symbols_examined"] == ["HAE"]
    assert observation["symbol_cycle_counts"] == {"HAE": 2}
    assert observation["scanner_queries"] == 0
    assert observation["feasibility_checks"] == 0
    assert observation["largest_position_share_of_equity"] == "0.5008"
    serialized = json.dumps(observation, sort_keys=True)
    assert "must" not in serialized.lower()
    assert "recommend" not in serialized.lower()


def test_instrument_coverage_observes_available_but_unexamined_option_family():
    process_observation = {
        "telemetry_cycles_observed": 20,
        "scanner_queries": 3,
        "option_chains_queried": 0,
        "asset_class_cycle_counts": {"CRYPTO": 4},
    }
    product_capabilities = {
        "families": [
            {
                "status": "FULL_LIFECYCLE_VERIFIED",
                "executable": True,
                "family": REGULAR_DAY1_PRODUCT_FAMILY.model_dump(mode="json"),
            },
            {
                "status": "FULL_LIFECYCLE_VERIFIED",
                "executable": True,
                "family": {
                    "security_type": "CRYPTO",
                    "venue_or_routing": "PAXOS",
                },
            },
        ]
    }

    coverage = AutonomousStateBuilder._instrument_family_coverage(
        process_observation,
        product_capabilities,
    )

    assert coverage == {
        "schema": "INSTRUMENT_FAMILY_COVERAGE_OBSERVATION_V1",
        "telemetry_cycles_observed": 20,
        "minimum_cycles_for_gap_diagnostic": 10,
        "available_families": ["BAG", "CRYPTO", "OPT", "STK"],
        "examined_families": ["CRYPTO", "STK"],
        "unexamined_available_families": ["BAG", "OPT"],
        "diagnostic_reason_codes": [
            "AVAILABLE_INSTRUMENT_FAMILY_UNEXAMINED:BAG",
            "AVAILABLE_INSTRUMENT_FAMILY_UNEXAMINED:OPT",
        ],
        "diagnostic_only": True,
        "host_enforcement": False,
    }


def test_instrument_coverage_clears_option_gap_after_chain_research():
    coverage = AutonomousStateBuilder._instrument_family_coverage(
        {
            "telemetry_cycles_observed": 20,
            "scanner_queries": 3,
            "option_chains_queried": 1,
            "asset_class_cycle_counts": {"CRYPTO": 4},
        },
        {
            "families": [
                {
                    "status": "FULL_LIFECYCLE_VERIFIED",
                    "executable": True,
                    "family": REGULAR_DAY1_PRODUCT_FAMILY.model_dump(mode="json"),
                },
                {
                    "status": "FULL_LIFECYCLE_VERIFIED",
                    "executable": True,
                    "family": {"security_type": "CRYPTO"},
                },
            ]
        },
    )

    assert coverage["examined_families"] == ["BAG", "CRYPTO", "OPT", "STK"]
    assert coverage["unexamined_available_families"] == []
    assert coverage["diagnostic_reason_codes"] == []


def test_expired_filled_plan_is_summarized_but_not_model_active(
    tmp_path, continuity_plan_factory
):
    from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
    from ibkr_paper_30d.successor_schema import install_successor_schema_v2

    with Database.open(tmp_path / "state.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        plan = continuity_plan_factory(
            order_binding={
                "order_ref": "filled-order",
                "client_order_id": "filled-order",
            }
        )
        ContinuityStore(db).append_plan_event("ACTIVATED", plan)
        registry_payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
            "lifecycle_event": "BROKER_BOUND",
            "order_ref": "filled-order",
            "contract_id": 101,
            "contract": {"conId": 101, "symbol": "HAE", "secType": "STK"},
        }
        db.execute(
            "INSERT INTO experiment_order_registry(registry_id,order_ref,client_order_id,"
            "perm_id,ibkr_order_id,contract_id,action,quantity,payload_json,"
            "payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "filled-order-registry",
                "filled-order",
                78,
                225256222,
                78,
                101,
                "BUY",
                "1",
                canonical_bytes(registry_payload).decode("utf-8"),
                sha256_json(registry_payload),
                "2026-10-01T14:01:00Z",
            ),
        )
        subject = builder(db, FakeToolbox())
        context = subject._continuity_context(
            {"epoch_state": "PRE_EPOCH_HISTORY", "now_utc": "2026-10-02T14:00:00Z"},
            open_orders_snapshot=[],
            positions_snapshot=[{"contract_id": 101, "quantity": "1"}],
        )

    assert context["active_plans"] == []
    assert context["inactive_plan_summaries"] == [
        {
            "plan_id": plan.plan_id,
            "plan_sha256": plan.sha256,
            "order_ref": "filled-order",
            "plan_valid_until": "2026-10-01T20:00:00Z",
            "reason": "EXPIRED_NO_OPEN_ORDER_POSITION_PRESENT",
        }
    ]


def test_expired_plan_with_open_order_remains_model_active(
    tmp_path, continuity_plan_factory
):
    from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
    from ibkr_paper_30d.successor_schema import install_successor_schema_v2

    with Database.open(tmp_path / "state.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        plan = continuity_plan_factory()
        ContinuityStore(db).append_plan_event("ACTIVATED", plan)
        subject = builder(db, FakeToolbox())
        context = subject._continuity_context(
            {"epoch_state": "PRE_EPOCH_HISTORY", "now_utc": "2026-10-02T14:00:00Z"},
            open_orders_snapshot=[{"orderRef": "order-78", "orderId": 78}],
            positions_snapshot=[],
        )

    assert len(context["active_plans"]) == 1
    assert context["inactive_plan_summaries"] == []


def test_continuity_provider_history_is_bounded_and_summarized(tmp_path):
    from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
    from ibkr_paper_30d.successor_schema import install_successor_schema_v2

    with Database.open(tmp_path / "state.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        store = ContinuityStore(db)
        for index in range(7):
            store.append_provider_event(
                f"provider-{index}",
                "COMPLETED_ACCEPTED" if index % 2 else "TIMEOUT_CONFIRMED",
                {"index": index},
            )
        context = builder(db, FakeToolbox())._continuity_context(
            {"epoch_state": "PRE_EPOCH_HISTORY", "now_utc": "2026-10-09T15:00:00Z"}
        )

    assert len(context["provider_states"]) == 5
    assert [item["invocation_id"] for item in context["provider_states"]] == [
        "provider-6",
        "provider-5",
        "provider-4",
        "provider-3",
        "provider-2",
    ]
    assert context["provider_state_summary"] == {
        "total_invocations": 7,
        "state_counts": {"COMPLETED_ACCEPTED": 3, "TIMEOUT_CONFIRMED": 4},
        "recent_states_limit": 5,
    }


def _active_successor_state_builder(tmp_path):
    from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3

    db_path = tmp_path / "active-successor.sqlite3"
    receipt_path = tmp_path / "owner-successor.json"
    definition, receipt = build_authorized_successor(db_path, receipt_path)
    db = Database.open(db_path)
    evidence = BrokerTransitionEvidence(
        account_identity_sha256=ACCOUNT_HASH,
        collected_at_utc=SUCCESSOR_START + timedelta(seconds=1),
        observation=BrokerTimeObservation(
            server_time_utc=SUCCESSOR_START,
            observed_at_utc=SUCCESSOR_START + timedelta(seconds=1),
            authenticated=True,
            paper_session=True,
        ),
        positions_count=0,
        open_orders_count=0,
        broker_write_count=0,
    )
    transition = commit_successor_transition(
        db=db,
        launch_attempt_id="continuity-authority-test",
        target_successor_epoch_id=str(definition["epoch_id"]),
        target_successor_definition_sha256=str(definition["definition_sha256"]),
        expected_account_identity_sha256=ACCOUNT_HASH,
        expected_owner_sid=OWNER_SID,
        owner_authorization_receipt=receipt,
        execution_lock_verifier=lambda: True,
        broker_evidence_collector=lambda: evidence,
        now_utc=lambda: SUCCESSOR_START + timedelta(seconds=2),
    )
    install_continuity_schema_v3(db)
    clock = clock_for_epoch(db, str(definition["epoch_id"]))
    subject = AutonomousStateBuilder(
        db,
        FakeToolbox(),
        allocation=Decimal("500.00"),
        experiment_start_utc=clock.start_utc,
        experiment_clock=clock,
        duration_days=30,
        runtime_market_gate=FakeMarketGate(),
    )
    return db, subject, definition, receipt, transition


def test_continuity_context_projects_verified_successor_authority(tmp_path):
    db, subject, definition, receipt, transition = _active_successor_state_builder(
        tmp_path
    )
    try:
        clock = subject._clock(SUCCESSOR_START + timedelta(minutes=1))
        context = subject._continuity_context(clock)
    finally:
        db.close()

    assert context["epoch_id"] == definition["epoch_id"]
    assert context["definition_sha256"] == definition["definition_sha256"]
    assert context["clock_event_sha256"] == transition.clock_event_sha256
    assert context["owner_authorization_sha256"] == receipt["receipt_sha256"]


def test_continuity_context_rejects_forged_clock_authority(tmp_path):
    db, subject, _, _, _ = _active_successor_state_builder(tmp_path)
    try:
        clock = subject._clock(SUCCESSOR_START + timedelta(minutes=1))
        clock["clock_event_sha256"] = "f" * 64
        with pytest.raises(
            AutonomousStateBuildError,
            match="CONTINUITY_AUTHORITY_BINDING_MISMATCH",
        ):
            subject._continuity_context(clock)
    finally:
        db.close()


def test_state_builder_blocks_when_tracked_position_does_not_match_broker(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        subject = builder(db, FakeToolbox(broker_quantity="2"))
        value = subject.build(trigger="POSITION_EVENT")

        assert value.reconciliation_receipt["status"] == "BLOCK"
        assert any(
            reason.startswith("POSITION_QUANTITY_MISMATCH")
            for reason in value.reconciliation_receipt["reason_codes"]
        )
        assert value.market_data_snapshot["gate_status"] == "PASS"


def test_repeated_build_does_not_duplicate_same_execution(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        subject = builder(db, FakeToolbox())
        first = subject.build(trigger="SCHEDULED_SCAN")
        second = subject.build(trigger="SCHEDULED_SCAN")

        assert first.experiment_subledger_snapshot["equity"] == "599.00"
        assert second.experiment_subledger_snapshot["equity"] == "599.00"
        assert second.experiment_subledger_snapshot["fees"] == "1.00"


def test_state_builder_ignores_fill_without_namespace_boundary(tmp_path):
    with Database.open(tmp_path / "spoofed-fill.sqlite3") as db:
        subject = builder(db, FakeToolbox(include_spoofed_fill=True))
        value = subject.build(trigger="SCHEDULED_SCAN")

        assert value.reconciliation_receipt["status"] == "PASS"
        assert value.experiment_subledger_snapshot["cash"] == "299.00"
        assert value.experiment_subledger_snapshot["fees"] == "1.00"


def test_state_builder_rejects_fill_from_foreign_execution_client(tmp_path):
    with Database.open(tmp_path / "foreign-client-fill.sqlite3") as db:
        subject = builder(db, FakeToolbox(fill_updates={"clientId": 7}))
        value = subject.build(trigger="SCHEDULED_SCAN")

        assert value.reconciliation_receipt["status"] == "BLOCK"
        assert "UNREGISTERED_EXPERIMENT_FILL:44" in (
            value.reconciliation_receipt["reason_codes"]
        )


def test_state_builder_rejects_fill_without_hash_valid_v2_anchor(tmp_path):
    with Database.open(tmp_path / "invalid-anchor-fill.sqlite3") as db:
        subject = builder(db, FakeToolbox(), payload_sha256="0" * 64)
        value = subject.build(trigger="SCHEDULED_SCAN")

        assert value.reconciliation_receipt["status"] == "BLOCK"
        assert "UNREGISTERED_EXPERIMENT_FILL:44" in (
            value.reconciliation_receipt["reason_codes"]
        )


def test_state_builder_accepts_late_perm_id_when_v2_anchor_has_zero(tmp_path):
    with Database.open(tmp_path / "late-perm-fill.sqlite3") as db:
        subject = builder(db, FakeToolbox(), anchor_perm_id=0)
        value = subject.build(trigger="SCHEDULED_SCAN")

        bound = db.execute(
            "SELECT perm_id,payload_json FROM experiment_order_registry "
            "WHERE order_ref='codex-ibkr-paper-30d-autonomous' "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()

        assert value.reconciliation_receipt["status"] == "PASS"
        assert value.experiment_subledger_snapshot["equity"] == "599.00"
        assert int(bound[0]) == 55
        assert json.loads(str(bound[1]))["lifecycle_event"] == "BROKER_BOUND"


@pytest.mark.parametrize(
    "fill_updates",
    [
        {"quantity": "2", "cumQty": "2"},
        {"quantity": "1", "cumQty": "2"},
    ],
)
def test_state_builder_rejects_fill_quantity_exceeding_issuance(tmp_path, fill_updates):
    with Database.open(tmp_path / "oversized-fill.sqlite3") as db:
        subject = builder(db, FakeToolbox(fill_updates=fill_updates))
        value = subject.build(trigger="SCHEDULED_SCAN")

        assert value.reconciliation_receipt["status"] == "BLOCK"
        assert "UNREGISTERED_EXPERIMENT_FILL:44" in (
            value.reconciliation_receipt["reason_codes"]
        )


@pytest.mark.parametrize(
    ("con_id", "side"),
    [(913925915, "BUY"), (926221865, "SELL")],
)
def test_state_builder_accepts_only_authorized_bag_leg_side(tmp_path, con_id, side):
    with Database.open(tmp_path / f"bag-{con_id}.sqlite3") as db:
        subject = builder(db, FakeToolbox())
        register_bag_binding(db)

        assert subject._registered_fill(bag_fill(con_id=con_id, side=side)) is True


@pytest.mark.parametrize(
    "updates",
    [
        {"con_id": 999999999, "side": "BUY"},
        {"con_id": 913925915, "side": "SELL"},
        {"con_id": 926221865, "side": "BUY"},
        {"con_id": 913925915, "side": "BUY", "account": "DU7654321"},
        {"con_id": 913925915, "side": "BUY", "quantity": "2", "cum_qty": "2"},
        {"con_id": 913925915, "side": "BUY", "quantity": "1", "cum_qty": "2"},
    ],
)
def test_state_builder_blocks_unowned_or_oversized_bag_leg_fill(tmp_path, updates):
    with Database.open(tmp_path / "bag-invalid.sqlite3") as db:
        subject = builder(db, FakeToolbox())
        register_bag_binding(db)

        assert subject._registered_fill(bag_fill(**updates)) is False


def test_authorized_bag_leg_fill_remains_deduplicated_in_ledger(tmp_path):
    with Database.open(tmp_path / "bag-dedupe.sqlite3") as db:
        subject = builder(db, FakeToolbox())
        register_bag_binding(db)
        fill = bag_fill(con_id=913925915, side="BUY")

        assert subject._registered_fill(fill) is True
        first = subject.ledger.record_fill(fill)
        second = subject.ledger.record_fill(fill)

        assert not first.startswith("duplicate:")
        assert second.startswith("duplicate:")
        assert subject.ledger.project().event_count == 1


def test_durable_registered_model_fill_is_recovered_into_its_sleeve_once(tmp_path):
    from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
    from ibkr_paper_30d.contract_ownership import (
        ContractOwnershipStore,
        canonical_contract_identity,
    )
    from ibkr_paper_30d.experiment_ledger import AutonomousExperimentLedger
    from ibkr_paper_30d.multi_universe_models import CapitalSleeve
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
    from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore
    from ibkr_paper_30d.successor_schema import install_successor_schema_v2

    with Database.open(tmp_path / "durable-fill-recovery.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        sleeve = CapitalSleeve.CONTINUOUS_SLEEVE
        ledger = SleeveLedgerStore(db)
        ledger.bootstrap_continuous()
        execution_key = "model:sol-entry"
        with db.transaction():
            ledger.reserve_liability_in_transaction(
                sleeve,
                amount_usd=Decimal("482.60"),
                reservation_key=execution_key,
            )
        contract = canonical_contract_identity(
            {
                "conId": 766137558,
                "secType": "CRYPTO",
                "currency": "USD",
                "exchange": "PAXOS",
                "localSymbol": "SOL.USD",
                "tradingClass": "SOL",
            }
        )
        ownership = ContractOwnershipStore(db)
        ownership.claim(
            sleeve,
            contract,
            side="BUY",
            group_id="order:codex-ibkr-paper-30d-a-sol",
        )
        order_ref = "codex-ibkr-paper-30d-a-sol"
        registry_payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
            "lifecycle_event": "BROKER_BOUND",
            "order_ref": order_ref,
            "client_order_id": 736,
            "perm_id": 1017434661,
            "ibkr_order_id": 736,
            "contract_id": contract.con_id,
            "action": "BUY",
            "quantity": "4.7",
            "execution_client_id": 19761,
            "account": "DUM891854",
            "contract": {"conId": contract.con_id},
        }
        db.execute(
            "INSERT INTO experiment_order_registry("
            "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
            "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "sol-registry",
                order_ref,
                736,
                1017434661,
                736,
                contract.con_id,
                "BUY",
                "4.7",
                canonical_bytes(registry_payload).decode("utf-8"),
                sha256_json(registry_payload),
                "2026-10-18T17:14:37Z",
            ),
        )
        authority_payload = {
            "schema": "SLEEVE_EXECUTION_RESERVATION_V1",
            "execution_key": execution_key,
            "operation": "NEW_TRADE",
            "order_ref": order_ref,
            "capital_sleeve": sleeve.value,
            "reserved_liability_usd": "482.60",
            "contract_identity_sha256": contract.sha256,
        }
        authority_sha = sha256_json(
            {"previous_event_sha256": None, "payload": authority_payload}
        )
        db.execute(
            "INSERT INTO sleeve_authority_events("
            "event_id,sleeve,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                "sol-authority",
                sleeve.value,
                "EXECUTION_AUTHORITY_RESERVED",
                canonical_bytes(authority_payload).decode("utf-8"),
                sha256_json(authority_payload),
                None,
                authority_sha,
                "2026-10-18T17:14:33Z",
            ),
        )
        legacy = AutonomousExperimentLedger(db)
        legacy.record_fill(
            {
                "execution_id_hash": "e" * 64,
                "execution_fingerprint": "d" * 64,
                "orderRef": order_ref,
                "orderId": 736,
                "permId": 1017434661,
                "clientId": 19761,
                "side": "BUY",
                "quantity": "4.7",
                "cumQty": "4.7",
                "price": "102.22",
                "commission": "1.75",
                "contract": {
                    "conId": contract.con_id,
                    "symbol": "SOL",
                    "secType": "CRYPTO",
                    "multiplier": "1",
                },
            }
        )
        subject = object.__new__(AutonomousStateBuilder)
        subject.db = db
        subject.ledger = legacy
        subject.sleeve_ledger_store = ledger
        subject.contract_ownership_store = ownership

        assert subject._import_durable_sleeve_fills() == []
        event_count = ledger.project(sleeve).event_count
        assert subject._import_durable_sleeve_fills() == []
        state = ledger.project(sleeve)

        assert state.balance("USD") == Decimal("17.816")
        assert state.fees_usd == Decimal("1.75")
        assert state.reserved_liability_usd == Decimal("482.60")
        assert state.event_count == event_count
