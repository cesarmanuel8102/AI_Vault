from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

import ibkr_paper_30d.day1_launch as launch_module
from ibkr_paper_30d.canary_candidate import OwnerPilotAuthorization
from ibkr_paper_30d.day1_launch import LaunchError
from ibkr_paper_30d.multi_universe_models import TransitionTarget


NOW = datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc)


def _authorization(**updates) -> OwnerPilotAuthorization:
    values = {
        "authorization_id": "owner-pilot-1",
        "owner_id": "owner",
        "account_identity_sha256": "a" * 64,
        "successor_definition_sha256": "b" * 64,
        "approved_head": "c" * 40,
        "maximum_debit_usd": Decimal("20"),
        "maximum_loss_usd": Decimal("20"),
        "fee_allowance_usd": Decimal("2"),
        "maximum_order_count": 2,
        "issued_at_utc": NOW - timedelta(minutes=1),
        "expires_at_utc": NOW + timedelta(hours=1),
    }
    values.update(updates)
    return OwnerPilotAuthorization(**values)


def _target(authorization: OwnerPilotAuthorization) -> TransitionTarget:
    return TransitionTarget(
        transition_id="transition-1",
        predecessor_epoch_id="AUTONOMY_EPOCH_2",
        successor_epoch_id="AUTONOMY_EPOCH_3",
        successor_definition_sha256=authorization.successor_definition_sha256,
        owner_authorization_sha256="1" * 64,
        approved_git_head=authorization.approved_head,
        account_identity_sha256=authorization.account_identity_sha256,
        clock_authority_sha256="2" * 64,
        regular_sleeve_authority_sha256="3" * 64,
        continuous_sleeve_authority_sha256="4" * 64,
        economic_risk_authorization_sha256="5" * 64,
        certified_family_set_sha256="6" * 64,
        canary_authorization_sha256=authorization.sha256,
        writer_binding_sha256="7" * 64,
    )


@pytest.mark.parametrize("raw", [None, {}, {"unexpected": True}])
def test_canary_launch_requires_valid_owner_pilot_authorization(raw) -> None:
    authorization = _authorization()

    with pytest.raises(LaunchError, match="OWNER_PILOT_AUTHORIZATION_REQUIRED"):
        launch_module._validate_owner_pilot_authorization(raw, _target(authorization))


def test_canary_launch_rejects_authorization_hash_mismatch() -> None:
    authorization = _authorization()
    target = _target(authorization).model_copy(
        update={"canary_authorization_sha256": "f" * 64}
    )

    with pytest.raises(LaunchError, match="CANARY_AUTHORIZATION_MISMATCH"):
        launch_module._validate_owner_pilot_authorization(
            authorization.model_dump(mode="json"), target
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"account_identity_sha256": "d" * 64},
        {"successor_definition_sha256": "e" * 64},
        {"approved_head": "f" * 40},
    ],
)
def test_canary_launch_rejects_mismatched_scope_even_with_matching_hash(updates) -> None:
    expected = _authorization()
    forged = _authorization(**updates)
    target = _target(expected).model_copy(
        update={"canary_authorization_sha256": forged.sha256}
    )

    with pytest.raises(LaunchError, match="CANARY_AUTHORIZATION_BINDING_MISMATCH"):
        launch_module._validate_owner_pilot_authorization(
            forged.model_dump(mode="json"), target
        )


def test_canary_launch_accepts_exact_bound_authorization() -> None:
    authorization = _authorization()

    validated = launch_module._validate_owner_pilot_authorization(
        authorization.model_dump(mode="json"), _target(authorization)
    )

    assert validated == authorization
