from decimal import Decimal

import pytest

from test_canary_ownership_reservation import _setup
from ibkr_paper_30d.canary_broker_accounting import CanaryBrokerAccounting
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore


def facts(request, *, flat=False, commission="0.01"):
    fills = [{"execution_id_sha256": sha256_json("buy-fill"),
              "action": "BUY", "quantity": str(request.quantity),
              "price": str(Decimal("10") / request.quantity),
              "commission": commission, "commission_currency": "USD"}]
    if flat:
        fills.append({"execution_id_sha256": sha256_json("sell-fill"),
                      "action": "SELL", "quantity": str(request.quantity),
                      "price": str(Decimal("9.99") / request.quantity),
                      "commission": commission, "commission_currency": "USD"})
    return {"account_identity_sha256": request.account_identity_sha256,
            "contract_identity_sha256": request.canonical_contract.sha256,
            "request_sha256": request.sha256, "complete": True,
            "position_quantity": "0" if flat else str(request.quantity),
            "average_cost": str(Decimal("10") / request.quantity),
            "open_order_count": 0, "fills": fills}


def test_actual_fill_import_is_idempotent_and_preserves_economics(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    assert accounting(request, facts(request)) is False
    assert accounting(request, facts(request, flat=True)) is True
    assert accounting(request, facts(request, flat=True)) is True
    with Database.open(path) as db:
        state = SleeveLedgerStore(db).project(CapitalSleeve.CONTINUOUS_SLEEVE)
    assert state.balance("USD") == Decimal("499.97")
    assert state.fees_usd == Decimal("0.02")
    assert state.realized_pnl_usd == Decimal("-0.03")
    assert state.fill_count == 2


def test_missing_commission_never_claims_economics_reconciled(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    assert accounting(request, facts(request, flat=True, commission=None)) is False


def test_forged_account_rejected_without_ledger_mutation(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    data = facts(request)
    data["account_identity_sha256"] = "0" * 64
    with Database.open(path) as db:
        before = SleeveLedgerStore(db).project(CapitalSleeve.CONTINUOUS_SLEEVE)
    with pytest.raises(ValueError, match="CANARY_BROKER_FACT_IDENTITY_MISMATCH"):
        CanaryBrokerAccounting(path)(request, data)
    with Database.open(path) as db:
        assert SleeveLedgerStore(db).project(CapitalSleeve.CONTINUOUS_SLEEVE) == before


def test_changed_price_for_imported_execution_is_not_idempotent_success(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    data = facts(request)
    accounting(request, data)
    data["fills"][0]["price"] = "100"
    with pytest.raises(ValueError, match="CANARY_BROKER_FILL_CONFLICT"):
        accounting(request, data)
