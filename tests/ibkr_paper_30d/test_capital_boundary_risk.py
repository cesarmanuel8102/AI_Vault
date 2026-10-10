from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.multi_universe_models import (
    CapitalSleeve,
    OwnerEconomicRiskAuthorization,
)
from ibkr_paper_30d.risk import (
    CapitalBoundaryInputs,
    CapitalBoundaryRiskEngine,
    RiskResult,
    SleeveCapitalBoundaryInputs,
    SleeveCapitalBoundaryRiskEngine,
)


def engine():
    return CapitalBoundaryRiskEngine.aggressive_month1()


def test_full_equity_loss_is_allowed():
    result = engine().evaluate(CapitalBoundaryInputs(
        experiment_equity=Decimal("500.00"),
        maximum_loss=Decimal("500.00"),
        liability_is_bounded=True,
    ))
    assert result.result == RiskResult.PASS
    assert result.reason_codes == ()


def test_one_cent_over_equity_is_blocked():
    result = engine().evaluate(CapitalBoundaryInputs(
        experiment_equity=Decimal("500.00"),
        maximum_loss=Decimal("500.01"),
        liability_is_bounded=True,
    ))
    assert result.result == RiskResult.BLOCK
    assert result.reason_codes == ("EXPERIMENT_CAPITAL_BOUNDARY",)


def test_unbounded_liability_is_blocked_even_if_margin_is_small():
    result = engine().evaluate(CapitalBoundaryInputs(
        experiment_equity=Decimal("500.00"),
        maximum_loss=Decimal("100.00"),
        liability_is_bounded=False,
    ))
    assert result.result == RiskResult.BLOCK
    assert "UNBOUNDED_LIABILITY" in result.reason_codes


def test_external_capital_is_never_part_of_experiment():
    result = engine().evaluate(CapitalBoundaryInputs(
        experiment_equity=Decimal("1200.00"),
        maximum_loss=Decimal("1000.00"),
        liability_is_bounded=True,
        uses_external_capital=True,
    ))
    assert result.result == RiskResult.BLOCK
    assert "EXTERNAL_CAPITAL_FORBIDDEN" in result.reason_codes


NOW = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)


def _authorization(**updates) -> OwnerEconomicRiskAuthorization:
    authority = OwnerEconomicRiskAuthorization(
        authorization_id="owner-risk-v1",
        owner_id="owner-1",
        policy_version="AGGRESSIVE_CAPITAL_BOUNDARY_V1",
        regular_allocation_usd=Decimal("500.00"),
        extended_allocation_usd=Decimal("500.00"),
        maximum_liability_ratio=Decimal("1.00"),
        daily_loss_limit_usd="DISABLED",
        drawdown_limit_usd="DISABLED",
        successor_definition_sha256="a" * 64,
        issued_at_utc=NOW - timedelta(hours=1),
        expires_at_utc=NOW + timedelta(days=31),
    )
    return authority.model_copy(update=updates)


def _sleeve_inputs(**updates) -> SleeveCapitalBoundaryInputs:
    inputs = SleeveCapitalBoundaryInputs(
        sleeve=CapitalSleeve.REGULAR_SLEEVE,
        sleeve_equity_usd=Decimal("500.00"),
        reserved_liability_usd=Decimal("100.00"),
        proposed_maximum_loss_usd=Decimal("400.00"),
        aggregate_reserved_after_usd=Decimal("500.00"),
        liability_is_bounded=True,
        uses_external_capital=False,
        uses_other_sleeve_offset=False,
        uses_non_experiment_offset=False,
        owner_id="owner-1",
        successor_definition_sha256="a" * 64,
        evaluated_at_utc=NOW,
        daily_loss_usd=Decimal("0"),
        drawdown_usd=Decimal("0"),
        action_kind="NEW_RISK",
        broker_account_buying_power_usd=Decimal("1000000"),
        other_sleeve_margin_offset_usd=Decimal("0"),
    )
    return inputs.model_copy(update=updates)


def _sleeve_engine() -> SleeveCapitalBoundaryRiskEngine:
    return SleeveCapitalBoundaryRiskEngine()


@pytest.mark.parametrize(
    ("proposed", "expected"),
    [
        ("399.99", RiskResult.PASS),
        ("400.00", RiskResult.PASS),
        ("400.01", RiskResult.BLOCK),
    ],
)
def test_proposed_liability_respects_available_equity_cent_boundary(
    proposed, expected
) -> None:
    decision = _sleeve_engine().evaluate(
        _sleeve_inputs(proposed_maximum_loss_usd=Decimal(proposed)),
        _authorization(),
    )
    assert decision.result == expected
    if expected is RiskResult.BLOCK:
        assert "PROPOSED_LIABILITY_EXCEEDS_AVAILABLE" in decision.reason_codes


@pytest.mark.parametrize(
    ("aggregate", "expected"),
    [
        ("499.99", RiskResult.PASS),
        ("500.00", RiskResult.PASS),
        ("500.01", RiskResult.BLOCK),
    ],
)
def test_aggregate_reserved_respects_sleeve_equity_cent_boundary(
    aggregate, expected
) -> None:
    decision = _sleeve_engine().evaluate(
        _sleeve_inputs(aggregate_reserved_after_usd=Decimal(aggregate)),
        _authorization(),
    )
    assert decision.result == expected
    if expected is RiskResult.BLOCK:
        assert "AGGREGATE_LIABILITY_EXCEEDS_SLEEVE_EQUITY" in decision.reason_codes


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"sleeve_equity_usd": Decimal("0")}, "INVALID_SLEEVE_EQUITY"),
        ({"sleeve_equity_usd": Decimal("-0.01")}, "INVALID_SLEEVE_EQUITY"),
        ({"liability_is_bounded": False}, "UNBOUNDED_LIABILITY"),
        ({"uses_external_capital": True}, "EXTERNAL_CAPITAL_FORBIDDEN"),
        ({"uses_other_sleeve_offset": True}, "CROSS_SLEEVE_OFFSET_FORBIDDEN"),
        ({"uses_non_experiment_offset": True}, "NON_EXPERIMENT_OFFSET_FORBIDDEN"),
        (
            {"other_sleeve_margin_offset_usd": Decimal("1")},
            "CROSS_SLEEVE_OFFSET_FORBIDDEN",
        ),
    ],
)
def test_sleeve_solvency_never_uses_external_or_cross_sleeve_offsets(
    updates, reason
) -> None:
    decision = _sleeve_engine().evaluate(_sleeve_inputs(**updates), _authorization())
    assert decision.result == RiskResult.BLOCK
    assert reason in decision.reason_codes


@pytest.mark.parametrize(
    ("authority", "inputs", "reason"),
    [
        (None, {}, "ECONOMIC_AUTHORIZATION_MISSING"),
        (_authorization(expires_at_utc=NOW), {}, "ECONOMIC_AUTHORIZATION_EXPIRED"),
        (_authorization(owner_id="owner-2"), {}, "ECONOMIC_AUTHORIZATION_OWNER_MISMATCH"),
        (
            _authorization(regular_allocation_usd=Decimal("499.99")),
            {},
            "ECONOMIC_AUTHORIZATION_ALLOCATION_MISMATCH",
        ),
        (
            _authorization(policy_version="OTHER"),
            {},
            "ECONOMIC_AUTHORIZATION_POLICY_MISMATCH",
        ),
        (
            _authorization(maximum_liability_ratio=Decimal("0.99")),
            {},
            "ECONOMIC_AUTHORIZATION_RATIO_MISMATCH",
        ),
        (
            _authorization(successor_definition_sha256="b" * 64),
            {},
            "ECONOMIC_AUTHORIZATION_SUCCESSOR_MISMATCH",
        ),
        (
            _authorization(daily_loss_limit_usd=None),
            {},
            "ECONOMIC_AUTHORIZATION_DAILY_LOSS_UNSPECIFIED",
        ),
        (
            _authorization(drawdown_limit_usd=None),
            {},
            "ECONOMIC_AUTHORIZATION_DRAWDOWN_UNSPECIFIED",
        ),
    ],
)
def test_initial_risk_authority_rejects_missing_or_mismatched_owner_economics(
    authority, inputs, reason
) -> None:
    decision = _sleeve_engine().evaluate(_sleeve_inputs(**inputs), authority)
    assert decision.result == RiskResult.BLOCK
    assert reason in decision.reason_codes


@pytest.mark.parametrize("field", ["daily_loss_limit_usd", "drawdown_limit_usd"])
def test_explicit_disabled_or_nonnegative_threshold_is_required(field) -> None:
    assert _sleeve_engine().evaluate(
        _sleeve_inputs(), _authorization(**{field: "DISABLED"})
    ).result == RiskResult.PASS
    assert _sleeve_engine().evaluate(
        _sleeve_inputs(), _authorization(**{field: Decimal("25.00")})
    ).result == RiskResult.PASS


@pytest.mark.parametrize(
    ("limit_field", "loss_field", "reason"),
    [
        ("daily_loss_limit_usd", "daily_loss_usd", "MAX_DAILY_LOSS_REACHED"),
        ("drawdown_limit_usd", "drawdown_usd", "MAX_DRAWDOWN_REACHED"),
    ],
)
def test_threshold_equality_freezes_new_risk_but_preserves_exit_and_continuity(
    limit_field, loss_field, reason
) -> None:
    authority = _authorization(**{limit_field: Decimal("25.00")})
    at_limit = _sleeve_inputs(**{loss_field: Decimal("25.00")})

    entry = _sleeve_engine().evaluate(at_limit, authority)
    exit_decision = _sleeve_engine().evaluate(
        at_limit.model_copy(update={"action_kind": "EXACT_EXIT"}), authority
    )
    continuity = _sleeve_engine().evaluate(
        at_limit.model_copy(update={"action_kind": "CONTINUITY_ACTION"}), authority
    )

    assert entry.result == RiskResult.BLOCK
    assert reason in entry.reason_codes
    assert exit_decision.result == RiskResult.PASS
    assert continuity.result == RiskResult.PASS


def test_account_buying_power_cannot_expand_sleeve_authority() -> None:
    decision = _sleeve_engine().evaluate(
        _sleeve_inputs(
            proposed_maximum_loss_usd=Decimal("400.01"),
            broker_account_buying_power_usd=Decimal("999999999"),
        ),
        _authorization(),
    )
    assert decision.result == RiskResult.BLOCK
    assert decision.available_usd == Decimal("400.00")
