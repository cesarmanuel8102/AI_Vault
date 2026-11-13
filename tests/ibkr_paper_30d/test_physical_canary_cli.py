from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ibkr_paper_30d.cli import (
    inspect_physical_canary,
    request_physical_canary,
)
from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.physical_canary import (
    PhysicalCanaryError,
    PhysicalCanaryState,
    PhysicalCanaryStore,
)


HEAD = "b" * 40
OWNER_AUTH = "a" * 64


def _request(path, *, sleeve, canary_id):
    return request_physical_canary(
        database_path=path,
        sleeve=sleeve,
        canary_id=canary_id,
        approved_head=HEAD,
        owner_authorization_sha256=OWNER_AUTH,
        requested_at_utc=datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc),
        current_head=HEAD,
    )


def test_request_physical_canary_requires_exact_current_head(tmp_path):
    path = tmp_path / "head.sqlite3"

    with pytest.raises(PhysicalCanaryError, match="APPROVED_HEAD_MISMATCH"):
        request_physical_canary(
            database_path=path,
            sleeve=CapitalSleeve.REGULAR_SLEEVE,
            canary_id="regular-e2e-1",
            approved_head=HEAD,
            owner_authorization_sha256=OWNER_AUTH,
            requested_at_utc=datetime.now(timezone.utc),
            current_head="c" * 40,
        )


def test_same_physical_canary_request_is_idempotent_and_broker_free(tmp_path):
    path = tmp_path / "idempotent.sqlite3"

    first = _request(
        path,
        sleeve=CapitalSleeve.REGULAR_SLEEVE,
        canary_id="regular-e2e-1",
    )
    second = _request(
        path,
        sleeve=CapitalSleeve.REGULAR_SLEEVE,
        canary_id="regular-e2e-1",
    )
    third = request_physical_canary(
        database_path=path,
        sleeve=CapitalSleeve.REGULAR_SLEEVE,
        canary_id="regular-e2e-1",
        approved_head=HEAD,
        owner_authorization_sha256=OWNER_AUTH,
        requested_at_utc=datetime(2026, 11, 13, 19, 0, tzinfo=timezone.utc),
        current_head=HEAD,
    )

    assert first == second == third
    assert first["state"] == "REQUESTED"
    assert first["broker_calls_made"] == 0


def test_continuous_request_requires_regular_flat_reconciliation(tmp_path):
    path = tmp_path / "sequence.sqlite3"
    _request(
        path,
        sleeve=CapitalSleeve.REGULAR_SLEEVE,
        canary_id="regular-e2e-1",
    )

    with pytest.raises(
        PhysicalCanaryError, match="REGULAR_PHYSICAL_CANARY_NOT_FLAT"
    ):
        _request(
            path,
            sleeve=CapitalSleeve.CONTINUOUS_SLEEVE,
            canary_id="continuous-e2e-1",
        )

    with Database.open(path) as db:
        store = PhysicalCanaryStore(db)
        for state in (
            PhysicalCanaryState.ENTRY_SELECTED,
            PhysicalCanaryState.ISSUED_PRE_SEND,
            PhysicalCanaryState.BROKER_BOUND,
            PhysicalCanaryState.ACTIVE_MANAGEMENT,
            PhysicalCanaryState.FLAT_RECONCILED,
        ):
            store.append_transition(
                "regular-e2e-1",
                state,
                capital_sleeve=CapitalSleeve.REGULAR_SLEEVE,
                evidence={"test": state.value},
            )

    result = _request(
        path,
        sleeve=CapitalSleeve.CONTINUOUS_SLEEVE,
        canary_id="continuous-e2e-1",
    )

    assert result["state"] == "REQUESTED"
    assert result["capital_sleeve"] == "CONTINUOUS_SLEEVE"


def test_inspection_is_read_only_and_reports_durable_projection(tmp_path):
    path = tmp_path / "inspect.sqlite3"
    _request(
        path,
        sleeve=CapitalSleeve.REGULAR_SLEEVE,
        canary_id="regular-e2e-1",
    )

    report = inspect_physical_canary(
        database_path=path, canary_id="regular-e2e-1"
    )

    assert report["schema"] == "PHYSICAL_CANARY_INSPECTION_V1"
    assert report["projection"]["state"] == "REQUESTED"
    assert report["broker_calls_made"] == 0
    assert report["real_broker_writes"] == 0
