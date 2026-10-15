from types import SimpleNamespace
from decimal import Decimal
import pytest
from ibkr_paper_30d.autonomous_state import AutonomousStateBuilder
from ibkr_paper_30d.authoritative_broker_writer import AuthoritativeBrokerWriter


def test_active_identity_takes_precedence_over_released_presentation():
    class Done(Exception):pass
    captured=[]
    subject=object.__new__(AutonomousStateBuilder)
    subject._fresh_position_marks={479624278:Decimal('81000')}
    subject._extra_mark_reasons=[]
    active=SimpleNamespace(contract=SimpleNamespace(con_id=479624278),contract_identity_sha256='a'*64)
    old=SimpleNamespace(contract=SimpleNamespace(con_id=479624278),contract_identity_sha256='b'*64)
    subject.contract_ownership_store=SimpleNamespace(projection=lambda:SimpleNamespace(active_contracts=(active,),released_contracts=(old,)))
    def reconcile(snapshot,ownership):
        captured.append(snapshot['positions'][0]['contract_identity_sha256'])
        raise Done()
    subject.sleeve_ledger_store=SimpleNamespace(reconcile_broker_snapshot=reconcile)
    subject._latest_executions=[]
    with pytest.raises(Done):
        subject._sync_and_reconcile_v4(account={},broker_positions={'positions':[{'contract':{'conId':479624278},'position':'0.001'}]},open_orders={})
    assert captured==['a'*64]


def test_exit_quote_waits_for_usable_fresh_stream(monkeypatch):
    import ibkr_paper_30d.authoritative_broker_writer as module
    request=SimpleNamespace(flat_return_plan=SimpleNamespace(order_type='LMT',action='SELL'),
        canonical_contract=SimpleNamespace(con_id=479624278,security_type='CRYPTO',exchange='PAXOS',currency='USD',local_symbol='BTC.USD',trading_class='BTC',multiplier=None))
    elapsed=[0.0]
    cancelled=[]
    ticker=SimpleNamespace(bid=float('nan'),ask=float('nan'))
    def sleep(seconds):
        elapsed[0]+=seconds
        if elapsed[0]>=3:ticker.bid=81000.25
    def market(contract,**kwargs):
        assert kwargs['snapshot'] is False
        return ticker
    monkeypatch.setattr(module.time,'monotonic',lambda:elapsed[0])
    broker=SimpleNamespace(qualifyContracts=lambda c:[c],reqMktData=market,sleep=sleep,cancelMktData=lambda c:cancelled.append(c))
    writer=object.__new__(AuthoritativeBrokerWriter)
    writer.broker_request_timeout_seconds=15
    assert writer._canary_flat_return_limit_price(request,broker)==Decimal('81000.25')
    assert cancelled
