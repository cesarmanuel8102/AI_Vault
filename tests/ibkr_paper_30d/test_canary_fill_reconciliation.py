from decimal import Decimal
from types import SimpleNamespace

import pytest
import test_canary_pilot as pilot

from test_canary_ownership_reservation import _setup
from test_canary_broker_accounting import facts
from ibkr_paper_30d.autonomous_state import AutonomousStateBuilder
from ibkr_paper_30d.canary_broker_accounting import CanaryBrokerAccounting
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.ibkr_readonly import expected_identity_hash
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore
from ibkr_paper_30d.multi_universe_models import CapitalSleeve


def _bound_fill(tmp_path, monkeypatch):
    account = 'DU12345'
    account_hash = expected_identity_hash(account)
    monkeypatch.setattr(pilot, 'ACCOUNT', account_hash)
    path, store, _, request = _setup(
        tmp_path, proposal_updates={'account_identity_sha256': account_hash},
        authorization_updates={'account_identity_sha256': account_hash})
    store.begin_write(request.execution_key)
    data = facts(request)
    fill = data['fills'][0]
    fill.update(order_ref=f'codex-ibkr-paper-30d-canary-entry-{request.sha256[:12]}',
                order_id=237, perm_id=123456, client_id=19761)
    CanaryBrokerAccounting(path)(request, data)
    observed = dict(account=account, orderRef=fill['order_ref'], orderId=237,
                    permId=123456, clientId=19761, side='BUY',
                    quantity=fill['quantity'], cumQty=fill['quantity'],
                    price=fill['price'], execution_id_sha256=fill['execution_id_sha256'],
                    contract={'conId': request.canonical_contract.con_id})
    return path, observed


@pytest.mark.parametrize('changed', [None, 'account', 'orderId', 'permId', 'clientId',
                                    'quantity', 'price', 'execution_id_sha256', 'orderRef', 'contract'])
def test_sync_recognizes_only_bound_canary_fills_without_legacy_posting(tmp_path, monkeypatch, changed):
    path, fill = _bound_fill(tmp_path, monkeypatch)
    if changed:
        fill[changed] = {'account': 'DU99999', 'orderId': 238, 'permId': 123457,
                         'clientId': 19762, 'quantity': '99', 'price': '99',
                         'execution_id_sha256': 'f' * 64, 'orderRef': 'codex-ibkr-paper-30d-forged',
                         'contract': {'conId': 99999}}[changed]
    with Database.open(path) as db:
        subject = object.__new__(AutonomousStateBuilder)
        subject.db = db
        subject.sleeve_ledger_store = SleeveLedgerStore(db)
        subject.ledger = SimpleNamespace(record_fill=lambda _: pytest.fail('double posting'))
        subject._tool = lambda _: {'executions': [fill]}
        reasons = subject._sync_executions()
    assert bool(reasons) == bool(changed)


def test_currency_authority_keeps_subcent_cash(tmp_path):
    path, _, _, _ = _setup(tmp_path)
    with Database.open(path) as db, db.transaction():
        ledger = SleeveLedgerStore(db)
        ledger._insert(sleeve=CapitalSleeve.CONTINUOUS_SLEEVE, currency='USD',
                       event_type='CURRENCY_DEBIT', payload={'amount': '0.59977'})
        assert ledger.project(CapitalSleeve.CONTINUOUS_SLEEVE).balance('USD') == Decimal('499.40023')
        assert ledger.project_all().aggregate_balance('USD') == Decimal('499.40023')


@pytest.mark.parametrize('forged', [False, True])
def test_later_canary_filters_only_independently_journaled_previous_fills(tmp_path, monkeypatch, forged):
    from datetime import datetime, timezone
    from ibkr_paper_30d.authoritative_broker_writer import AuthoritativeBrokerWriter
    from ibkr_paper_30d.production_continuity_runtime import _ProductionCanaryStore
    path, observed = _bound_fill(tmp_path, monkeypatch)
    with Database.open(path) as db:
        events = _ProductionCanaryStore._verified_events(db)
    candidate = next(e['candidate_sha256'] for e in events if e['event_type'] == 'EXECUTION_REQUEST')
    original = _ProductionCanaryStore(path).load_request(candidate)
    current = original.model_copy(update={'canary_id': 'next', 'candidate_sha256': 'f'*64})
    execution = SimpleNamespace(orderRef=observed['orderRef'], acctNumber=observed['account'],
        clientId=19761, permId=observed['permId'], orderId=observed['orderId'],
        execId='buy-fill', side='BOT', shares=observed['quantity'], price='99' if forged else observed['price'],
        cumQty=observed['quantity'])
    fill = SimpleNamespace(execution=execution, contract=SimpleNamespace(conId=original.canonical_contract.con_id), commissionReport=None)
    writer = object.__new__(AuthoritativeBrokerWriter)
    writer.execution_client_id = 19761
    writer.now_utc = lambda: datetime.now(timezone.utc)
    writer.canary_broker_accounting = CanaryBrokerAccounting(path)
    writer._collect_evidence = lambda _: {'executions': [fill], 'positions': [], 'trades': []}
    if forged:
        with pytest.raises(ValueError, match='CANARY_BROKER_FILL_IDENTITY_MISMATCH'):
            writer._canary_broker_facts(current, None)
    else:
        assert writer._canary_broker_facts(current, None)['fills'] == []
