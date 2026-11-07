from __future__ import annotations

from decimal import Decimal

import pytest

from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.sleeve_execution_authority import SleeveAuthorityReservationStore
from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from test_sleeve_execution_authority import _broker, _snapshot, _v4_request

SLEEVE = CapitalSleeve.CONTINUOUS_SLEEVE
RESERVED = Decimal("480.15")
AVG = Decimal("53.39")


@pytest.fixture()
def db(tmp_path):
    database = Database.open(tmp_path / "partial.sqlite3")
    install_successor_schema_v2(database)
    install_continuity_schema_v3(database)
    install_multi_universe_schema_v4(database)
    SleeveLedgerStore(database).bootstrap_extended()
    yield database
    database.close()


def _reserved(db) -> Decimal:
    return SleeveLedgerStore(db).project(SLEEVE).reserved_liability_usd


def _snapshot_with(request, quantity: str | None, *, open_order: bool = False, avg: Decimal = AVG):
    contract_sha = _broker(request)["contract_identity_sha256"]
    positions = (
        []
        if quantity is None
        else [{
            "contract_identity_sha256": contract_sha, "quantity": quantity,
            "multiplier": "1", "average_cost": str(avg),
        }]
    )
    return {
        "positions": positions,
        "open_orders": [{"contract_identity_sha256": contract_sha}] if open_order else [],
        "pending_execution_contract_sha256": [],
        "fill_ambiguity": False,
        "fresh": True,
    }


def _request(amount: Decimal = RESERVED, key: str | None = None):
    from ibkr_paper_30d.canonical import sha256_json

    base = _v4_request()
    payload = base.payload.model_copy(update={"maximum_loss": amount})
    data = base.model_dump()
    data.update({"payload": payload, "payload_sha256": sha256_json(payload)})
    if key is not None:
        data.update({"request_id": key, "execution_key": key,
                     "durable_sequence": base.durable_sequence + 1})
    return base.__class__.model_validate(data)


def _entry(db, request=None, amount: Decimal = RESERVED):
    request = request or _request(amount)
    store = SleeveAuthorityReservationStore(db)
    receipt = store.reserve(
        request, _broker(request), lambda: _snapshot(request, proposed_maximum_loss_usd=amount)
    )
    assert receipt.status == "PASS", receipt.reason_codes
    return request, store


def _releases(db) -> int:
    return db.execute(
        "SELECT COUNT(*) FROM sleeve_ledger_events WHERE event_type='LIABILITY_RELEASED'"
    ).fetchone()[0]


def test_buy_nine_sell_five_keeps_reservation_for_four_only(db) -> None:
    request, store = _entry(db)

    store.finalize_terminal_reservations(_snapshot_with(request, "4"), observation_id="1" * 64)

    assert _reserved(db) == (Decimal("4") * AVG).quantize(Decimal("0.01"))


def test_successive_partial_reductions_only_decrease_and_are_idempotent(db) -> None:
    request, store = _entry(db)

    store.finalize_terminal_reservations(_snapshot_with(request, "6"), observation_id="1" * 64)
    after_six = _reserved(db)
    store.finalize_terminal_reservations(_snapshot_with(request, "6"), observation_id="2" * 64)
    assert _reserved(db) == after_six
    assert _releases(db) == 1
    store.finalize_terminal_reservations(_snapshot_with(request, "4"), observation_id="3" * 64)

    assert after_six == (Decimal("6") * AVG).quantize(Decimal("0.01"))
    assert _reserved(db) == (Decimal("4") * AVG).quantize(Decimal("0.01"))
    assert _releases(db) == 2


def test_reservation_never_increases_above_original(db) -> None:
    request, store = _entry(db, amount=Decimal("100"))

    store.finalize_terminal_reservations(_snapshot_with(request, "9"), observation_id="1" * 64)

    assert _reserved(db) == Decimal("100.00")
    assert _releases(db) == 0


def test_cancelled_entry_remainder_releases_unfilled_liability(db) -> None:
    request, store = _entry(db)

    store.finalize_terminal_reservations(
        _snapshot_with(request, "5", open_order=True), observation_id="1" * 64
    )
    assert _reserved(db) == Decimal("480.15")

    store.finalize_terminal_reservations(_snapshot_with(request, "5"), observation_id="2" * 64)
    assert _reserved(db) == (Decimal("5") * AVG).quantize(Decimal("0.01"))


def test_full_close_after_partial_release_reaches_zero_without_conflict(db) -> None:
    request, store = _entry(db)
    store.finalize_terminal_reservations(_snapshot_with(request, "4"), observation_id="1" * 64)

    store.finalize_terminal_reservations(_snapshot_with(request, None), observation_id="2" * 64)
    result = store.finalize_terminal_reservations(_snapshot_with(request, None), observation_id="3" * 64)

    assert result["released"] == (request.execution_key,)
    assert _reserved(db) == Decimal("0.00")


def test_replay_after_reopen_yields_same_reservation(db, tmp_path) -> None:
    request, store = _entry(db)
    store.finalize_terminal_reservations(_snapshot_with(request, "4"), observation_id="1" * 64)
    expected = _reserved(db)
    db.close()

    with Database.open(tmp_path / "partial.sqlite3") as reopened:
        assert SleeveLedgerStore(reopened).project(SLEEVE).reserved_liability_usd == expected
        SleeveAuthorityReservationStore(reopened).finalize_terminal_reservations(
            _snapshot_with(request, "4"), observation_id="2" * 64
        )
        assert SleeveLedgerStore(reopened).project(SLEEVE).reserved_liability_usd == expected


def test_new_proposal_within_real_capital_is_not_blocked_by_stale_reservation(db) -> None:
    request, store = _entry(db)
    store.finalize_terminal_reservations(_snapshot_with(request, "4"), observation_id="1" * 64)
    reserved = _reserved(db)
    second = _request(Decimal("244.30"), "second-execution")

    receipt = store.reserve(
        second, _broker(second),
        lambda: _snapshot(second, reserved_liability_usd=reserved, proposed_maximum_loss_usd=Decimal("244.30")),
    )

    assert receipt.status == "PASS", receipt.reason_codes


def test_reservations_can_never_exceed_sleeve_equity(db) -> None:
    request, store = _entry(db)
    second = _request(Decimal("20"), "second-execution")

    receipt = store.reserve(
        second, _broker(second),
        lambda: _snapshot(second, reserved_liability_usd=RESERVED, proposed_maximum_loss_usd=Decimal("20")),
    )

    assert receipt.status == "BLOCK"


def test_aggregate_reservation_is_bounded_by_equity_not_nominal_allocation(db) -> None:
    SleeveLedgerStore(db).append(SLEEVE, "CURRENCY_CREDIT", {"amount": "14.23"})
    request = _request(Decimal("505"))
    store = SleeveAuthorityReservationStore(db)

    receipt = store.reserve(
        request, _broker(request),
        lambda: _snapshot(request, equity_usd=Decimal("514.23"), proposed_maximum_loss_usd=Decimal("505")),
    )

    assert receipt.status == "PASS", receipt.reason_codes
    assert _reserved(db) == Decimal("505.00")
