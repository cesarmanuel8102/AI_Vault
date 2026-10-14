from decimal import Decimal

import pytest

from test_canary_ownership_reservation import _setup
from ibkr_paper_30d.canary_broker_accounting import CanaryBrokerAccounting
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.experiment_ledger import normalized_money
from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore
from ibkr_paper_30d.production_continuity_runtime import _ProductionCanaryStore


@pytest.mark.parametrize("proof", ["complete", "missing", "nonflat", "wrong_hash"])
def test_owner_recovery_retires_failed_candidate_only_with_bound_flat_proof(tmp_path, proof):
    path, store, proposal, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    original = {"status": "UNCERTAIN", "broker_write_boundary_crossed": True}
    store.persist_result(proposal.sha256, original)
    fill_data = facts(request, flat=True, commission=None)
    if proof != "missing":
        recovered_facts = dict(fill_data)
        if proof == "nonflat":
            recovered_facts["position_quantity"] = "0.01"
        if proof == "wrong_hash":
            recovered_facts["request_sha256"] = "f" * 64
        with Database.open(path) as db, db.transaction():
            store._append_in_transaction(
                db, authorization_id="owner-recovery", event_type="CANARY_RECOVERY_RESULT",
                body={"candidate_sha256": proposal.sha256,
                      "original_request_sha256": request.sha256,
                      "result": {"success": True, "status": "FILLED",
                                 "broker_validation": {"broker_facts": recovered_facts}}},
            )
    observation = _pnl_observation(request, fill_data["fills"], Decimal("-0.59977"))
    CanaryBrokerAccounting(path).reconcile_terminal_recovery(request, fill_data, observation)
    if proof == "complete":
        assert store.load_candidate() is None
        assert store.has_orphaned_durable_state() is False
    else:
        assert store.load_candidate() is not None
    assert store.load_result(proposal.sha256) == original


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


def _pnl_observation(request, fills, broker_net, *, fee_allowance=None):
    gross = (
        sum(
            Decimal(f["quantity"]) * Decimal(f["price"])
            for f in fills
            if f["action"] == "SELL"
        )
        - sum(
            Decimal(f["quantity"]) * Decimal(f["price"])
            for f in fills
            if f["action"] == "BUY"
        )
    )
    broker_net_d = Decimal(str(broker_net))
    cost_diff = gross - broker_net_d
    executions = []
    for f in fills:
        executions.append(
            {
                "id_sha256": f["execution_id_sha256"],
                "side": "BOT" if f["action"] == "BUY" else "SLD",
                "quantity": str(f["quantity"]),
                "price": str(f["price"]),
            }
        )
    fee_allowance = fee_allowance if fee_allowance is not None else request.fee_allowance_usd
    return {
        "account_identity_sha256": request.account_identity_sha256,
        "candidate_sha256": request.candidate_sha256,
        "contract_id": request.canonical_contract.con_id,
        "original_request_sha256": request.sha256,
        "broker_realized_pnl_usd": str(broker_net_d),
        "gross_execution_pnl_usd": str(gross),
        "cost_difference_usd": str(cost_diff),
        "cost_difference_is_inference": True,
        "individual_commission_reports_missing": True,
        "candidate_fee_allowance_usd": str(fee_allowance),
        "evidence_sha256": sha256_json(
            {"broker_net": str(broker_net_d), "gross": str(gross)}
        ),
        "executions": executions,
    }


def test_changed_price_for_imported_execution_is_not_idempotent_success(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    data = facts(request)
    accounting(request, data)
    data["fills"][0]["price"] = "100"
    with pytest.raises(ValueError, match="CANARY_BROKER_FILL_CONFLICT"):
        accounting(request, data)


def test_broker_net_pnl_imported_when_individual_commissions_missing(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    fill_data = facts(request, flat=True, commission=None)
    assert accounting(request, fill_data) is False
    broker_net = Decimal("-0.59977")
    observation = _pnl_observation(request, fill_data["fills"], broker_net)
    result = accounting.import_broker_net_pnl(request, observation)
    assert result["integrated"] is True
    with Database.open(path) as db:
        state = SleeveLedgerStore(db).project(CapitalSleeve.CONTINUOUS_SLEEVE)
    assert state.realized_pnl_usd == broker_net
    gross = Decimal(observation["gross_execution_pnl_usd"])
    cost_diff = gross - broker_net
    assert state.balance("USD") == normalized_money(Decimal("500") + gross - cost_diff)
    assert state.fees_usd == Decimal("0")


def test_broker_net_pnl_import_is_idempotent(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    fill_data = facts(request, flat=True, commission=None)
    accounting(request, fill_data)
    observation = _pnl_observation(request, fill_data["fills"], Decimal("-0.59977"))
    assert accounting.import_broker_net_pnl(request, observation)["integrated"] is True
    assert accounting.import_broker_net_pnl(request, observation)["integrated"] is False
    with Database.open(path) as db:
        state = SleeveLedgerStore(db).project(CapitalSleeve.CONTINUOUS_SLEEVE)
    assert state.realized_pnl_usd == Decimal("-0.59977")
    gross = Decimal(observation["gross_execution_pnl_usd"])
    assert state.balance("USD") == normalized_money(
        Decimal("500") + gross - (gross - Decimal("-0.59977"))
    )


def test_broker_net_pnl_import_rejects_account_mismatch(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    fill_data = facts(request, flat=True, commission=None)
    accounting(request, fill_data)
    observation = _pnl_observation(request, fill_data["fills"], Decimal("-0.59977"))
    observation["account_identity_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="CANARY_BROKER_PNL_IDENTITY_MISMATCH"):
        accounting.import_broker_net_pnl(request, observation)


def test_broker_net_pnl_import_rejects_contract_mismatch(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    fill_data = facts(request, flat=True, commission=None)
    accounting(request, fill_data)
    observation = _pnl_observation(request, fill_data["fills"], Decimal("-0.59977"))
    observation["contract_id"] = 12345
    with pytest.raises(ValueError, match="CANARY_BROKER_PNL_IDENTITY_MISMATCH"):
        accounting.import_broker_net_pnl(request, observation)


def test_broker_net_pnl_import_rejects_gross_mismatch(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    fill_data = facts(request, flat=True, commission=None)
    accounting(request, fill_data)
    observation = _pnl_observation(request, fill_data["fills"], Decimal("-0.59977"))
    observation["gross_execution_pnl_usd"] = str(
        Decimal(observation["gross_execution_pnl_usd"]) + Decimal("0.01")
    )
    # keep cost difference consistent so validation reaches the gross-vs-fills check
    observation["cost_difference_usd"] = str(
        Decimal(observation["gross_execution_pnl_usd"]) - Decimal("-0.59977")
    )
    with pytest.raises(ValueError, match="CANARY_BROKER_PNL_GROSS_MISMATCH"):
        accounting.import_broker_net_pnl(request, observation)


def test_broker_net_pnl_import_rejects_sentinel_pnl(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    fill_data = facts(request, flat=True, commission=None)
    accounting(request, fill_data)
    observation = _pnl_observation(request, fill_data["fills"], Decimal("-0.59977"))
    observation["broker_realized_pnl_usd"] = "UNAVAILABLE_DOUBLE_SENTINEL"
    with pytest.raises(ValueError, match="CANARY_BROKER_PNL_VALUE_INVALID"):
        accounting.import_broker_net_pnl(request, observation)


def test_broker_net_pnl_import_preserves_excess_over_fee_allowance(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    fill_data = facts(request, flat=True, commission=None)
    accounting(request, fill_data)
    observation = _pnl_observation(
        request, fill_data["fills"], Decimal("-0.59977"), fee_allowance=Decimal("0.2515")
    )
    result = accounting.import_broker_net_pnl(request, observation)
    assert result["cost_difference_exceeds_candidate_fee_allowance"] is True
    assert result["candidate_fee_allowance_usd"] == Decimal("0.2515")
    with Database.open(path) as db:
        events = SleeveLedgerStore(db)._events()
    marker = next(
        e
        for e in events
        if e["event_type"] == "BROKER_NET_PNL_RECONCILED"
    )
    assert marker["cost_difference_exceeds_candidate_fee_allowance"] is True


def test_broker_net_pnl_import_rejects_foreign_execution_evidence(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    fill_data = facts(request, flat=True, commission=None)
    accounting(request, fill_data)
    foreign_fill = dict(fill_data["fills"][0])
    foreign_fill["execution_id_sha256"] = sha256_json("foreign")
    observation = _pnl_observation(request, fill_data["fills"], Decimal("-0.59977"))
    observation["executions"].append(
        {
            "id_sha256": foreign_fill["execution_id_sha256"],
            "side": "SLD",
            "quantity": foreign_fill["quantity"],
            "price": foreign_fill["price"],
        }
    )
    with pytest.raises(ValueError, match="CANARY_BROKER_PNL_EXECUTION_MISMATCH"):
        accounting.import_broker_net_pnl(request, observation)


def test_terminal_recovery_releases_liability_and_integrates_net_pnl(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    fill_data = facts(request, flat=True, commission=None)
    observation = _pnl_observation(request, fill_data["fills"], Decimal("-0.59977"))
    result = accounting.reconcile_terminal_recovery(request, fill_data, observation)
    assert result["pnl_integrated"] is True
    assert result["liability_released"] is True
    with Database.open(path) as db:
        state = SleeveLedgerStore(db).project(CapitalSleeve.CONTINUOUS_SLEEVE)
    assert state.realized_pnl_usd == Decimal("-0.59977")
    assert state.reserved_liability_usd == Decimal("0")


def test_terminal_recovery_is_idempotent(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    fill_data = facts(request, flat=True, commission=None)
    observation = _pnl_observation(request, fill_data["fills"], Decimal("-0.59977"))
    assert accounting.reconcile_terminal_recovery(request, fill_data, observation)["liability_released"] is True
    assert accounting.reconcile_terminal_recovery(request, fill_data, observation)["liability_released"] is False
    with Database.open(path) as db:
        state = SleeveLedgerStore(db).project(CapitalSleeve.CONTINUOUS_SLEEVE)
    assert state.reserved_liability_usd == Decimal("0")


def test_terminal_recovery_rejects_non_flat_position(tmp_path):
    path, store, _, request = _setup(tmp_path)
    store.begin_write(request.execution_key)
    accounting = CanaryBrokerAccounting(path)
    fill_data = facts(request, flat=False, commission=None)
    observation = _pnl_observation(request, fill_data["fills"], Decimal("-0.59977"))
    observation["position_quantity"] = str(request.quantity)
    with pytest.raises(ValueError, match="CANARY_RECOVERY_NOT_TERMINAL"):
        accounting.reconcile_terminal_recovery(request, fill_data, observation)
