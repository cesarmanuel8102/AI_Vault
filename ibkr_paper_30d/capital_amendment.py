"""Atomic, append-only owner capital amendments for both autonomous sleeves."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .canonical import sha256_json
from .measurement_segment import latest_segment, record_measurement_segment
from .multi_universe_authority import MultiUniverseAuthorityStore
from .multi_universe_models import (
    CapitalSleeve,
    OwnerEconomicRiskAuthorization,
    SleeveAuthorityDefinition,
)
from .persistence import Database
from .sleeve_ledger import SleeveLedgerState, SleeveLedgerStore


class CapitalAmendmentError(RuntimeError):
    pass


ORIGINAL_PRINCIPAL_USD = Decimal("500.00")
AUTHORIZED_TARGET_PRINCIPAL_USD = Decimal("10000.00")
AUTHORIZED_CONTRIBUTION_USD = Decimal("9500.00")
MAX_RECONCILIATION_AGE_SECONDS = 300.0


def _utc(value: datetime, reason: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CapitalAmendmentError(reason)
    return value.astimezone(timezone.utc)


def _state_sha256(state: SleeveLedgerState) -> str:
    return sha256_json(state.model_dump(mode="json"))


def _require_flat(state: SleeveLedgerState) -> None:
    if (
        state.positions
        or state.open_order_count != 0
        or state.reserved_liability_usd != Decimal("0")
    ):
        raise CapitalAmendmentError(f"SLEEVE_NOT_FLAT:{state.sleeve.value}")


def _require_fresh_reconciliation(
    ledger: SleeveLedgerStore,
    sleeve: CapitalSleeve,
    *,
    now_utc: datetime,
) -> None:
    event = next(
        (
            item
            for item in reversed(ledger._events())
            if item.get("sleeve") == sleeve.value
            and item.get("event_type") == "BROKER_STATE_RECONCILED"
        ),
        None,
    )
    if event is None or event.get("valuation_status") != "FRESH":
        raise CapitalAmendmentError(
            f"FRESH_BROKER_RECONCILIATION_REQUIRED:{sleeve.value}"
        )
    row = ledger.db.execute(
        "SELECT payload_json,payload_sha256 FROM experiment_state WHERE experiment_id=?",
        (ledger.RECONCILIATION_OBSERVATION_ID,),
    ).fetchone()
    if row is None:
        raise CapitalAmendmentError(
            f"FRESH_BROKER_RECONCILIATION_REQUIRED:{sleeve.value}"
        )
    try:
        import json

        observation = json.loads(str(row[0]))
        if (
            observation.get("schema") != ledger.RECONCILIATION_OBSERVATION_ID
            or sha256_json(observation) != str(row[1])
            or observation.get("broker_snapshot_sha256")
            != event.get("broker_snapshot_sha256")
            or (observation.get("sleeve_reconciliation_event_sha256") or {}).get(
                sleeve.value
            )
            != event.get("event_sha256")
        ):
            raise ValueError("observation mismatch")
        created = datetime.fromisoformat(
            str(observation["observed_at_utc"]).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (KeyError, TypeError, ValueError) as exc:
        raise CapitalAmendmentError(
            f"FRESH_BROKER_RECONCILIATION_REQUIRED:{sleeve.value}"
        ) from exc
    age = (now_utc - created).total_seconds()
    if age < -5.0 or age > MAX_RECONCILIATION_AGE_SECONDS:
        raise CapitalAmendmentError(
            f"FRESH_BROKER_RECONCILIATION_REQUIRED:{sleeve.value}"
        )


def _idempotent_target_valid(
    ledger: SleeveLedgerStore,
    authority: MultiUniverseAuthorityStore,
    *,
    amendment_id: str,
    now_utc: datetime,
    current_economic: OwnerEconomicRiskAuthorization,
    new_head: str,
) -> bool:
    roots = authority.authority_lineage_roots()
    if (
        current_economic.authorization_id != amendment_id
        or not (
            current_economic.issued_at_utc <= now_utc < current_economic.expires_at_utc
        )
        or set(roots)
        != {
            CapitalSleeve.REGULAR_SLEEVE.value,
            CapitalSleeve.CONTINUOUS_SLEEVE.value,
            "ECONOMIC",
        }
    ):
        return False
    expected_ids = {
        f"{amendment_id}:{CapitalSleeve.REGULAR_SLEEVE.value}",
        f"{amendment_id}:{CapitalSleeve.CONTINUOUS_SLEEVE.value}",
    }
    contributions = [
        event
        for event in ledger._events()
        if event.get("event_type") == "CAPITAL_CONTRIBUTION"
        and event.get("contribution_id") in expected_ids
    ]
    if (
        len(contributions) != 2
        or {event.get("contribution_id") for event in contributions} != expected_ids
    ):
        return False
    if any(
        Decimal(str(event.get("amount_usd"))) != AUTHORIZED_CONTRIBUTION_USD
        or event.get("authorization_sha256") != current_economic.sha256
        for event in contributions
    ):
        return False
    segment = latest_segment(ledger.db)
    return bool(
        segment is not None
        and segment.get("new_head") == new_head
        and all(
            Decimal(
                str(
                    ((segment.get("sleeves") or {}).get(sleeve.value) or {}).get(
                        "allocation_usd", "0"
                    )
                )
            )
            == AUTHORIZED_TARGET_PRINCIPAL_USD
            for sleeve in (
                CapitalSleeve.REGULAR_SLEEVE,
                CapitalSleeve.CONTINUOUS_SLEEVE,
            )
        )
    )


def amend_two_sleeve_capital(
    db: Database,
    *,
    target_principal_usd: Decimal,
    amendment_id: str,
    now_utc: datetime,
    expires_at_utc: datetime,
    previous_head: str,
    new_head: str,
) -> dict[str, Any]:
    """Increase both sleeves equally without resetting P&L, history, or clocks."""

    target = Decimal(target_principal_usd)
    amendment_id = str(amendment_id).strip()
    now = _utc(now_utc, "CAPITAL_AMENDMENT_TIME_INVALID")
    expires = _utc(expires_at_utc, "CAPITAL_AMENDMENT_EXPIRY_INVALID")
    if target != AUTHORIZED_TARGET_PRINCIPAL_USD:
        raise CapitalAmendmentError("UNAUTHORIZED_TARGET_PRINCIPAL")
    if not amendment_id:
        raise CapitalAmendmentError("CAPITAL_AMENDMENT_ID_REQUIRED")
    if expires <= now:
        raise CapitalAmendmentError("CAPITAL_AMENDMENT_EXPIRY_INVALID")
    for value, reason in (
        (previous_head, "PREVIOUS_HEAD_INVALID"),
        (new_head, "NEW_HEAD_INVALID"),
    ):
        if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
            raise CapitalAmendmentError(reason)

    ledger = SleeveLedgerStore(db)
    authority = MultiUniverseAuthorityStore(db)
    with db.transaction():
        before = {
            sleeve: ledger.project(sleeve)
            for sleeve in (
                CapitalSleeve.REGULAR_SLEEVE,
                CapitalSleeve.CONTINUOUS_SLEEVE,
            )
        }
        current_authorities = {
            sleeve: authority.sleeve_authority(sleeve) for sleeve in before
        }
        current_economic = authority.economic_authorization()
        if any(not state.initialized for state in before.values()):
            raise CapitalAmendmentError("SLEEVE_NOT_INITIALIZED")
        if (
            any(item is None for item in current_authorities.values())
            or current_economic is None
        ):
            raise CapitalAmendmentError("CAPITAL_AUTHORITY_MISSING")
        for state in before.values():
            _require_flat(state)
            _require_fresh_reconciliation(ledger, state.sleeve, now_utc=now)

        already_target = all(
            state.allocation_usd == target
            and current_authorities[sleeve].authorized_principal_usd == target
            for sleeve, state in before.items()
        ) and (
            current_economic.regular_allocation_usd == target
            and current_economic.extended_allocation_usd == target
        )
        if already_target:
            if not _idempotent_target_valid(
                ledger,
                authority,
                amendment_id=amendment_id,
                now_utc=now,
                current_economic=current_economic,
                new_head=new_head,
            ):
                raise CapitalAmendmentError("CAPITAL_TARGET_STATE_AMBIGUOUS")
            return {
                "status": "PASS",
                "idempotent": True,
                "amendment_id": amendment_id,
                "target_principal_usd": str(target),
                "economic_authorization_sha256": current_economic.sha256,
            }

        prior_allocations = {state.allocation_usd for state in before.values()}
        prior_principals = {
            item.authorized_principal_usd for item in current_authorities.values()
        }
        if (
            len(prior_allocations) != 1
            or len(prior_principals) != 1
            or prior_allocations != prior_principals
            or prior_allocations != {ORIGINAL_PRINCIPAL_USD}
        ):
            raise CapitalAmendmentError("CAPITAL_BASE_MISMATCH")
        contribution = target - next(iter(prior_allocations))
        if contribution != AUTHORIZED_CONTRIBUTION_USD:
            raise CapitalAmendmentError("UNAUTHORIZED_CAPITAL_CONTRIBUTION")

        baseline_audit_sha256 = sha256_json(
            {
                "amendment_id": amendment_id,
                "before": {
                    sleeve.value: state.model_dump(mode="json")
                    for sleeve, state in before.items()
                },
            }
        )

        amended_authorities: list[SleeveAuthorityDefinition] = []
        for sleeve, state in before.items():
            prior = current_authorities[sleeve]
            amended_authorities.append(
                prior.model_copy(
                    update={
                        "authorized_principal_usd": target,
                        "opening_equity_usd": target + prior.opening_pnl_usd,
                        "source_state_sha256": _state_sha256(state),
                    }
                )
            )
        amended_economic = current_economic.model_copy(
            update={
                "authorization_id": amendment_id,
                "regular_allocation_usd": target,
                "extended_allocation_usd": target,
                "issued_at_utc": now,
                "expires_at_utc": expires,
            }
        )
        for sleeve in before:
            ledger.contribute_capital_in_transaction(
                sleeve,
                amount_usd=contribution,
                contribution_id=f"{amendment_id}:{sleeve.value}",
                authorization_sha256=amended_economic.sha256,
            )
        receipt = authority.amend_capital_in_transaction(
            amendment_id=amendment_id,
            sleeve_authorities=tuple(amended_authorities),
            economic_authorization=amended_economic,
        )
        segment = record_measurement_segment(
            db,
            previous_head=previous_head,
            new_head=new_head,
            reason="owner-capital-contribution-10k-per-sleeve",
            baseline_audit_sha256=baseline_audit_sha256,
            now_utc=now,
        )
        after = {sleeve: ledger.project(sleeve) for sleeve in before}
        for sleeve in before:
            if (
                after[sleeve].allocation_usd != target
                or after[sleeve].realized_pnl_usd != before[sleeve].realized_pnl_usd
                or after[sleeve].unrealized_pnl_usd != before[sleeve].unrealized_pnl_usd
                or after[sleeve].fees_usd != before[sleeve].fees_usd
                or after[sleeve].fill_count != before[sleeve].fill_count
            ):
                raise CapitalAmendmentError("CAPITAL_AMENDMENT_INVARIANT_FAILED")

    return {
        "status": "PASS",
        "idempotent": False,
        "amendment_id": amendment_id,
        "target_principal_usd": str(target),
        "contribution_per_sleeve_usd": str(contribution),
        "regular_sleeve_authority_sha256": receipt.regular_sleeve_authority_sha256,
        "continuous_sleeve_authority_sha256": receipt.continuous_sleeve_authority_sha256,
        "economic_authorization_sha256": receipt.economic_risk_authorization_sha256,
        "measurement_segment_id": segment["segment_id"],
        "baseline_audit_sha256": baseline_audit_sha256,
    }
