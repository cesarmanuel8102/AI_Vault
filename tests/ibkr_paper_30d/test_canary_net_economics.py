from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from test_canary_ownership_reservation import _setup
from test_canary_broker_accounting import facts
from ibkr_paper_30d.canonical import sha256_json


def _observations(request):
    now = datetime.now(timezone.utc)
    before = {'account_identity_sha256': request.account_identity_sha256,
              'contract_id': request.canonical_contract.con_id,
              'request_sha256': request.sha256, 'source': 'IBKR_PAPER',
              'observed_at_utc': (now-timedelta(seconds=30)).isoformat(),
              'cash_usd': '254379.8902', 'realized_pnl_usd': None,
              'execution_ids': [], 'position_quantity': '0', 'open_order_count': 0}
    data = facts(request, flat=True, commission=None)
    after = {**before, 'observed_at_utc': now.isoformat(), 'cash_usd': '254379.7227',
             'realized_pnl_usd': '-0.167555',
             'execution_ids': [f['execution_id_sha256'] for f in data['fills']]}
    return before, after, data


@pytest.mark.parametrize('bad', [None, 'cash', 'extra_fill', 'sentinel', 'account', 'position', 'orders', 'time'])
def test_net_economics_requires_independent_cash_and_exact_executions(tmp_path, bad):
    from ibkr_paper_30d.canary_net_economics import verified_net_observation
    _, _, _, request = _setup(tmp_path)
    before, after, data = _observations(request)
    if bad == 'cash': after['cash_usd'] = '254379.9'
    if bad == 'extra_fill': after['execution_ids'].append('f'*64)
    if bad == 'sentinel': after['realized_pnl_usd'] = '1.7976931348623157e308'
    if bad == 'account': after['account_identity_sha256'] = 'f'*64
    if bad == 'position': after['position_quantity'] = '1'
    if bad == 'orders': after['open_order_count'] = 1
    if bad == 'time': after['observed_at_utc'] = before['observed_at_utc']
    if bad:
        with pytest.raises(ValueError): verified_net_observation(request, before, after, data)
    else:
        result = verified_net_observation(request, before, after, data)
        assert Decimal(result['broker_realized_pnl_usd']) == Decimal('-0.167555')
        assert result['individual_commission_reports_missing'] is True
        assert result['evidence_sha256'] == sha256_json(result['evidence'])


def test_net_economics_accepts_balanced_bounded_partial_round_trip(tmp_path):
    from ibkr_paper_30d.canary_net_economics import verified_net_observation
    _, _, _, request = _setup(tmp_path)
    before, after, data = _observations(request)
    for fill in data["fills"]:
        fill["quantity"] = str(request.quantity / 2)
    result = verified_net_observation(request, before, after, data)
    assert Decimal(result["broker_realized_pnl_usd"]) == Decimal("-0.167555")


@pytest.mark.parametrize("buy_factor,sell_factor", [("0", "0"), (".5", ".6"), ("1.1", "1.1")])
def test_net_economics_rejects_empty_unbalanced_or_oversized_round_trip(tmp_path, buy_factor, sell_factor):
    from ibkr_paper_30d.canary_net_economics import verified_net_observation
    _, _, _, request = _setup(tmp_path)
    before, after, data = _observations(request)
    for fill, factor in zip(data["fills"], (buy_factor, sell_factor)):
        fill["quantity"] = str(request.quantity * Decimal(factor))
    with pytest.raises(ValueError):
        verified_net_observation(request, before, after, data)


def test_previous_realized_pnl_is_subtracted_not_attributed_to_new_trade(tmp_path):
    from ibkr_paper_30d.canary_net_economics import verified_net_observation
    _, _, _, request = _setup(tmp_path)
    before, after, data = _observations(request)
    before['realized_pnl_usd'] = '10'
    after['realized_pnl_usd'] = '9.832445'
    result = verified_net_observation(request, before, after, data)
    assert Decimal(result['broker_realized_pnl_usd']) == Decimal('-0.167555')


def test_flat_lifecycle_completes_without_another_order_and_is_idempotent(tmp_path, monkeypatch):
    from ibkr_paper_30d.canary_broker_accounting import CanaryBrokerAccounting
    from ibkr_paper_30d.canary_authority import CanaryBrokerLifecycleReceipt, CanaryLifecycleRecorder
    from ibkr_paper_30d.persistence import Database
    from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore
    from ibkr_paper_30d.multi_universe_models import CapitalSleeve
    path, store, _, request = _setup(tmp_path, age=timedelta(minutes=1))
    store.begin_write(request.execution_key)
    before, after, data = _observations(request)
    accounting = CanaryBrokerAccounting(path)
    accounting(request, data)
    recorder = CanaryLifecycleRecorder(request.canary_id, request.account_identity_sha256,
                                        request.product_family.sha256, request.canonical_contract.sha256)
    for i, step in enumerate(recorder.sequence[:-1]):
        receipt = CanaryBrokerLifecycleReceipt(
            canary_id=request.canary_id, step=step, endpoint='PAPER',
            account_identity_sha256=request.account_identity_sha256,
            product_family_sha256=request.product_family.sha256,
            contract_identity_sha256=request.canonical_contract.sha256,
            broker_event_id_sha256=sha256_json([step, i]), broker_snapshot_sha256=sha256_json(data),
            previous_receipt_sha256=recorder.last_receipt_sha256,
            observed_at_utc=request.created_at_utc+timedelta(seconds=i),
            open_orders=0, positions=0)
        recorder.record(receipt)
        store.persist_receipt(receipt)
    accounting.record_verified_baseline(request, before)
    assert accounting.pending_flat_request().sha256 == request.sha256
    from types import SimpleNamespace
    from ibkr_paper_30d.autonomous_state import AutonomousStateBuilder
    calls = []
    with Database.open(path) as db:
        subject = object.__new__(AutonomousStateBuilder)
        subject.db = db
        subject.toolbox = SimpleNamespace(_connect=lambda: SimpleNamespace(disconnect=lambda: calls.append('disconnect')))
        def read_only_completion(self, pending, broker):
            assert db.connection.in_transaction is False
            assert pending.sha256 == request.sha256
            calls.append('complete')
        monkeypatch.setattr(CanaryBrokerAccounting, 'complete_pending_with_broker', read_only_completion)
        subject._complete_pending_canary_economics()
    assert calls == ['complete', 'disconnect']
    assert accounting.complete_flat_lifecycle(request, data, after) is True
    assert accounting.pending_flat_request() is None
    assert accounting.complete_flat_lifecycle(request, data, after) is True
    assert store.recover_terminal_result(request.candidate_sha256)['result'].status == 'PASS'
    with Database.open(path) as db:
        assert SleeveLedgerStore(db).project(CapitalSleeve.CONTINUOUS_SLEEVE).reserved_liability_usd == 0


def test_collector_refreshes_cash_and_cancels_its_own_subscriptions(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from ibkr_paper_30d.canary_net_economics import collect_net_snapshot
    from ibkr_paper_30d.ibkr_readonly import expected_identity_hash
    import test_canary_pilot as pilot
    monkeypatch.setattr(pilot, 'ACCOUNT', expected_identity_hash('DU12345'))
    _, _, _, request = _setup(tmp_path)
    calls = []
    broker = SimpleNamespace(
        managedAccounts=lambda: ['DU12345'], RequestTimeout=15,
        client=SimpleNamespace(getReqId=lambda: 20,
            reqAccountSummary=lambda *args: calls.append('refresh_cash'),
            cancelAccountSummary=lambda *args: calls.append('cancel_cash')),
        wrapper=SimpleNamespace(startReq=lambda _: None), _run=lambda _: None,
        accountSummary=lambda: [SimpleNamespace(account='DU12345', tag='$LEDGER-CashBalance', currency='USD', value='500.0000')],
        reqExecutions=lambda _: [], reqPositions=lambda: [], reqAllOpenOrders=lambda: [],
        reqPnLSingle=lambda *args: SimpleNamespace(realizedPnL=0),
        cancelPnLSingle=lambda *args: calls.append('cancel_pnl'),
        reqCurrentTime=lambda: datetime.now(timezone.utc),
        placeOrder=lambda *args: pytest.fail('broker write'))
    result = collect_net_snapshot(request, broker)
    assert calls == ['refresh_cash', 'cancel_cash', 'cancel_pnl']
    assert result['cash_usd'] == '500.0000'
    assert broker.RequestTimeout == 15
