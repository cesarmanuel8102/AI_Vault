from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ibkr_paper_30d.multi_universe_models import (
    CanaryAuthorization,
    CanonicalBagLeg,
    CanonicalContractIdentity,
    CapitalSleeve,
    ContractOwnershipGroup,
    OwnerEconomicRiskAuthorization,
    ProductFamilyKey,
    SleeveAuthorityDefinition,
    TransitionPhase,
    TransitionTarget,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64
HEAD = "1" * 40
NOW = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)


def _stock(con_id: int = 101) -> CanonicalContractIdentity:
    return CanonicalContractIdentity(
        con_id=con_id,
        security_type="STK",
        currency="USD",
        exchange="SMART",
        primary_exchange="NASDAQ",
        local_symbol="TEST",
        trading_class="NMS",
    )


def _family() -> ProductFamilyKey:
    return ProductFamilyKey(
        security_type="STK",
        venue_or_routing="SMART",
        quantity_semantics="WHOLE_SHARES",
        order_representation="SINGLE_LIMIT",
        lifecycle_behavior="DELIVERABLE_EQUITY",
    )


def _risk_authorization(**changes) -> OwnerEconomicRiskAuthorization:
    values = {
        "authorization_id": "risk-auth-1",
        "owner_id": "owner-1",
        "policy_version": "AGGRESSIVE_CAPITAL_BOUNDARY_V1",
        "regular_allocation_usd": Decimal("500"),
        "extended_allocation_usd": Decimal("500"),
        "maximum_liability_ratio": Decimal("1.00"),
        "daily_loss_limit_usd": "DISABLED",
        "drawdown_limit_usd": "DISABLED",
        "successor_definition_sha256": SHA_A,
        "issued_at_utc": NOW,
        "expires_at_utc": NOW + timedelta(days=2),
    }
    values.update(changes)
    return OwnerEconomicRiskAuthorization(**values)


def test_only_two_economic_sleeves_exist() -> None:
    assert {item.value for item in CapitalSleeve} == {
        "REGULAR_SLEEVE",
        "CONTINUOUS_SLEEVE",
    }
    assert CapitalSleeve("EXTENDED_SLEEVE") is CapitalSleeve.CONTINUOUS_SLEEVE
    assert CapitalSleeve.EXTENDED_SLEEVE is CapitalSleeve.CONTINUOUS_SLEEVE

    with pytest.raises(ValueError):
        CapitalSleeve("CANARY_SLEEVE")


def test_contract_identity_hash_includes_bag_legs() -> None:
    first = CanonicalContractIdentity(
        con_id=0,
        security_type="BAG",
        currency="USD",
        exchange="SMART",
        local_symbol="TEST COMBO",
        bag_legs=(
            CanonicalBagLeg(con_id=201, ratio=1, action="BUY", exchange="SMART"),
            CanonicalBagLeg(con_id=202, ratio=1, action="SELL", exchange="SMART"),
        ),
    )
    changed = first.model_copy(
        update={
            "bag_legs": (
                CanonicalBagLeg(
                    con_id=201, ratio=1, action="BUY", exchange="SMART"
                ),
                CanonicalBagLeg(
                    con_id=203, ratio=1, action="SELL", exchange="SMART"
                ),
            )
        }
    )

    assert len(first.sha256) == 64
    assert first.sha256 != changed.sha256

    with pytest.raises(ValidationError, match="duplicate"):
        CanonicalContractIdentity(
            con_id=0,
            security_type="BAG",
            currency="USD",
            exchange="SMART",
            bag_legs=(
                CanonicalBagLeg(
                    con_id=201, ratio=1, action="BUY", exchange="SMART"
                ),
                CanonicalBagLeg(
                    con_id=201, ratio=1, action="SELL", exchange="SMART"
                ),
            ),
        )


def test_currency_is_not_an_exclusive_contract_identity() -> None:
    with pytest.raises(ValidationError, match="currency balance"):
        CanonicalContractIdentity(
            con_id=0,
            security_type="CURRENCY_BALANCE",
            currency="USD",
            exchange="ACCOUNT",
        )

    assert _stock().exclusive_ownership_eligible is True


def test_models_are_frozen_and_reject_unknown_fields() -> None:
    contract = _stock()

    with pytest.raises(ValidationError):
        CanonicalContractIdentity(
            **contract.model_dump(),
            invented_authority=True,
        )
    with pytest.raises(ValidationError):
        contract.currency = "EUR"


def test_owner_economic_authorization_binds_exact_policy_and_limits() -> None:
    authorization = _risk_authorization()
    thresholded = _risk_authorization(
        daily_loss_limit_usd=Decimal("125.00"),
        drawdown_limit_usd=Decimal("250.00"),
    )

    assert authorization.maximum_liability_ratio == Decimal("1.00")
    assert authorization.daily_loss_limit_usd == "DISABLED"
    assert authorization.sha256 != thresholded.sha256

    for changes in (
        {"policy_version": "OLD_POLICY"},
        {"regular_allocation_usd": Decimal("499.99")},
        {"maximum_liability_ratio": Decimal("1.01")},
        {"daily_loss_limit_usd": None},
        {"drawdown_limit_usd": Decimal("-0.01")},
        {"expires_at_utc": NOW},
    ):
        with pytest.raises(ValidationError):
            _risk_authorization(**changes)


def test_transition_target_hash_binds_all_authority() -> None:
    regular = SleeveAuthorityDefinition(
        sleeve=CapitalSleeve.REGULAR_SLEEVE,
        authorized_principal_usd=Decimal("500"),
        opening_equity_usd=Decimal("487.25"),
        opening_pnl_usd=Decimal("-12.75"),
        source_state_sha256=SHA_A,
    )
    extended = SleeveAuthorityDefinition(
        sleeve=CapitalSleeve.CONTINUOUS_SLEEVE,
        authorized_principal_usd=Decimal("500"),
        opening_equity_usd=Decimal("500"),
        opening_pnl_usd=Decimal("0"),
        source_state_sha256=SHA_B,
    )
    family = _family()
    group = ContractOwnershipGroup(
        group_id="group-1",
        sleeve=CapitalSleeve.REGULAR_SLEEVE,
        parent_contract=_stock(),
        member_contracts=(_stock(),),
        contingent_contracts=(_stock(102),),
        generation=1,
    )
    canary = CanaryAuthorization(
        authorization_id="canary-1",
        owner_id="owner-1",
        account_identity_sha256=SHA_A,
        successor_definition_sha256=SHA_B,
        product_family_sha256=family.sha256,
        contract_scope_sha256=(group.parent_contract.sha256,),
        maximum_debit_usd=Decimal("10"),
        maximum_loss_usd=Decimal("10"),
        fee_allowance_usd=Decimal("2"),
        maximum_order_count=2,
        issued_at_utc=NOW,
        expires_at_utc=NOW + timedelta(hours=1),
    )
    target = TransitionTarget(
        transition_id="transition-1",
        predecessor_epoch_id="epoch-1",
        successor_epoch_id="epoch-2",
        successor_definition_sha256=SHA_A,
        owner_authorization_sha256=SHA_B,
        approved_git_head=HEAD,
        account_identity_sha256=SHA_C,
        clock_authority_sha256=SHA_D,
        regular_sleeve_authority_sha256=regular.sha256,
        continuous_sleeve_authority_sha256=extended.sha256,
        economic_risk_authorization_sha256=_risk_authorization().sha256,
        certified_family_set_sha256=SHA_E,
        canary_authorization_sha256=canary.sha256,
        writer_binding_sha256=SHA_F,
    )

    assert set(TransitionPhase) == {
        TransitionPhase.PREPARED,
        TransitionPhase.PREDECESSOR_QUIESCED,
        TransitionPhase.PREDECESSOR_RETIRED,
        TransitionPhase.SUCCESSOR_COMMITTED,
        TransitionPhase.SUPERVISION_BOUND,
        TransitionPhase.CANARY_EXCLUSIVE,
        TransitionPhase.CANARY_PASS,
        TransitionPhase.RUNTIME_BOUND,
        TransitionPhase.ACTIVE,
    }
    assert len(target.sha256) == 64
    assert target.sha256 != target.model_copy(
        update={"certified_family_set_sha256": SHA_F}
    ).sha256


def test_transition_target_emits_continuous_authority_binding() -> None:
    values = {
        "transition_id": "transition-canonical",
        "predecessor_epoch_id": "epoch-1",
        "successor_epoch_id": "epoch-2",
        "successor_definition_sha256": SHA_A,
        "owner_authorization_sha256": SHA_B,
        "approved_git_head": HEAD,
        "account_identity_sha256": SHA_C,
        "clock_authority_sha256": SHA_D,
        "regular_sleeve_authority_sha256": SHA_E,
        "extended_sleeve_authority_sha256": SHA_F,
        "economic_risk_authorization_sha256": "1" * 64,
        "certified_family_set_sha256": "2" * 64,
        "canary_authorization_sha256": "3" * 64,
        "writer_binding_sha256": "4" * 64,
    }

    target = TransitionTarget.model_validate(values)
    dumped = target.model_dump(mode="json")

    assert target.continuous_sleeve_authority_sha256 == SHA_F
    assert dumped["continuous_sleeve_authority_sha256"] == SHA_F
    assert "extended_sleeve_authority_sha256" not in dumped


def test_ownership_group_rejects_duplicate_contracts() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        ContractOwnershipGroup(
            group_id="group-1",
            sleeve=CapitalSleeve.REGULAR_SLEEVE,
            parent_contract=_stock(),
            member_contracts=(_stock(), _stock()),
            generation=1,
        )
