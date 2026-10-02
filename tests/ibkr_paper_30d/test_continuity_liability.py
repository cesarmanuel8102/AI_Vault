from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ibkr_paper_30d.continuity_liability import (
    MaximumLiabilityEvidence,
    MaximumLiabilityRequirement,
    validate_resolved_liability_authority,
)


NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)
HASHES = tuple(character * 64 for character in "abcdef123456")


def _requirement(**overrides: object) -> MaximumLiabilityRequirement:
    payload: dict[str, object] = {
        "plan_id": "plan-1",
        "plan_sha256": HASHES[0],
        "maximum_authorized_liability": "500",
        "account_identity_sha256": HASHES[1],
        "contract_identity_sha256": HASHES[2],
        "proposed_order_sha256": HASHES[3],
        "required_leg_identity_sha256": (HASHES[4], HASHES[5]),
        "maximum_evidence_age_seconds": "30",
    }
    payload.update(overrides)
    return MaximumLiabilityRequirement.model_validate(payload)


def _evidence(**overrides: object) -> MaximumLiabilityEvidence:
    payload: dict[str, object] = {
        "evidence_id": "liability-evidence-1",
        "source": "PAPER_WHAT_IF",
        "collected_at_utc": NOW,
        "fresh_until_utc": NOW + timedelta(seconds=30),
        "account_identity_sha256": HASHES[1],
        "contract_identity_sha256": HASHES[2],
        "proposed_order_sha256": HASHES[3],
        "command_sha256": HASHES[6],
        "bounded": True,
        "maximum_loss": "353.82",
        "currency": "USD",
        "covered_leg_identity_sha256": (HASHES[4], HASHES[5]),
        "broker_evidence_sha256": HASHES[7],
    }
    payload.update(overrides)
    return MaximumLiabilityEvidence.model_validate(payload)


def test_accepts_fresh_bounded_bag_evidence_within_both_bounds() -> None:
    result = validate_resolved_liability_authority(
        requirement=_requirement(),
        evidence=_evidence(),
        command_sha256=HASHES[6],
        experiment_capital_boundary=Decimal("400"),
        now_utc=NOW + timedelta(seconds=5),
    )

    assert result.allowed is True
    assert result.reason_codes == ()
    assert result.maximum_loss == Decimal("353.82")


@pytest.mark.parametrize(
    ("evidence_updates", "reason"),
    [
        ({"covered_leg_identity_sha256": (HASHES[4],)}, "LIABILITY_LEG_COVERAGE_INCOMPLETE"),
        (
            {
                "collected_at_utc": NOW - timedelta(seconds=60),
                "fresh_until_utc": NOW - timedelta(seconds=30),
            },
            "LIABILITY_EVIDENCE_STALE",
        ),
        ({"account_identity_sha256": HASHES[8]}, "LIABILITY_ACCOUNT_MISMATCH"),
        ({"contract_identity_sha256": HASHES[8]}, "LIABILITY_CONTRACT_MISMATCH"),
        ({"proposed_order_sha256": HASHES[8]}, "LIABILITY_ORDER_MISMATCH"),
        ({"command_sha256": HASHES[8]}, "LIABILITY_COMMAND_MISMATCH"),
        ({"bounded": False, "maximum_loss": None}, "LIABILITY_UNBOUNDED"),
        ({"maximum_loss": "500.01"}, "PLAN_LIABILITY_BOUND_EXCEEDED"),
    ],
)
def test_blocks_invalid_or_excess_broker_evidence(
    evidence_updates: dict[str, object], reason: str
) -> None:
    result = validate_resolved_liability_authority(
        requirement=_requirement(),
        evidence=_evidence(**evidence_updates),
        command_sha256=HASHES[6],
        experiment_capital_boundary=Decimal("1000"),
        now_utc=NOW,
    )

    assert result.allowed is False
    assert reason in result.reason_codes


def test_blocks_missing_evidence_and_experiment_capital_excess() -> None:
    missing = validate_resolved_liability_authority(
        requirement=_requirement(),
        evidence=None,
        command_sha256=HASHES[6],
        experiment_capital_boundary=Decimal("500"),
        now_utc=NOW,
    )
    capital = validate_resolved_liability_authority(
        requirement=_requirement(),
        evidence=_evidence(maximum_loss="353.82"),
        command_sha256=HASHES[6],
        experiment_capital_boundary=Decimal("300"),
        now_utc=NOW,
    )

    assert missing.reason_codes == ("LIABILITY_EVIDENCE_MISSING",)
    assert "EXPERIMENT_CAPITAL_BOUNDARY_EXCEEDED" in capital.reason_codes


def test_rejects_partial_or_internally_inconsistent_evidence() -> None:
    with pytest.raises(ValidationError, match="bounded evidence"):
        _evidence(maximum_loss=None)
    with pytest.raises(ValidationError, match="unbounded evidence"):
        _evidence(bounded=False, maximum_loss="1")
    with pytest.raises(ValidationError, match="fresh_until"):
        _evidence(fresh_until_utc=NOW - timedelta(seconds=1))


def test_rejects_unsupported_liability_source() -> None:
    with pytest.raises(ValidationError):
        _evidence(source="MODEL_ESTIMATE")
