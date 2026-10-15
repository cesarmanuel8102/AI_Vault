from dataclasses import replace
from datetime import datetime, timezone
import pytest
from test_canary_ownership_reservation import _setup
from ibkr_paper_30d.canary_authority import CanaryBrokerLifecycleReceipt
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.ibkr_readonly import expected_identity_hash
from ibkr_paper_30d.ibkr_readonly_session import ReadOnlyBrokerEvidence
from ibkr_paper_30d.persistence import Database


@pytest.fixture(autouse=True)
def account_binding(monkeypatch):
    import test_canary_pilot
    monkeypatch.setattr(test_canary_pilot, 'ACCOUNT', expected_identity_hash('DU1234567'))


def fixture(tmp_path):
    account = 'DU1234567'
    path, store, proposal, request = _setup(tmp_path, proposal_updates={'account_identity_sha256': expected_identity_hash(account)})
    assert store.begin_write(request.execution_key)
    receipt = CanaryBrokerLifecycleReceipt(
        canary_id=request.canary_id, step='SUBMITTED', endpoint='PAPER',
        account_identity_sha256=request.account_identity_sha256,
        product_family_sha256=request.product_family.sha256,
        contract_identity_sha256=request.canonical_contract.sha256,
        broker_event_id_sha256=sha256_json({'request_sha256':request.sha256,'step':'SUBMITTED'}),
        broker_snapshot_sha256=sha256_json({'request_sha256':request.sha256,'pre_write':True}),
        observed_at_utc=datetime.now(timezone.utc), open_orders=0, positions=0, economics_reconciled=False)
    store.persist_receipt(receipt)
    store.persist_result(proposal.sha256, {'status':'BLOCKED','request_sha256':request.sha256,
        'broker_write_boundary_crossed':False,'projection':None})
    evidence=ReadOnlyBrokerEvidence(True,True,178,None,(account,),{},(),(),(),(),
        datetime.now(timezone.utc).isoformat(),True,
        {k:True for k in ('managed_accounts','account_summary','account_values','positions','open_orders','executions','current_time')},(),())
    return store,request,evidence


def test_prewrite_abort_settles_without_certifying_or_replaying(tmp_path):
    store,request,evidence=fixture(tmp_path)
    assert store.has_orphaned_durable_state()
    assert store.reconcile_prewrite_abort(request,evidence) is True
    assert store.has_orphaned_durable_state() is False
    assert store.load_candidate() is None
    assert store.begin_write(request.execution_key) is False
    assert store.reconcile_prewrite_abort(request,evidence) is False


@pytest.mark.parametrize('change',[
    {'authenticated':False}, {'query_completeness':{'positions':True}},
    {'open_orders':({'order_id':1},)}, {'managed_accounts':('DU999999',)},
    {'server_timestamp_utc':'2020-01-01T00:00:00Z'},
])
def test_unproven_flat_evidence_cannot_settle(tmp_path,change):
    store,request,evidence=fixture(tmp_path)
    with pytest.raises(ValueError):store.reconcile_prewrite_abort(request,replace(evidence,**change))
    assert store.has_orphaned_durable_state()


def test_unknown_execution_cannot_settle(tmp_path):
    store,request,evidence=fixture(tmp_path)
    with pytest.raises(ValueError):
        store.reconcile_prewrite_abort(request,replace(evidence,executions=({'contract_id':request.canonical_contract.con_id,'execution_id_sha256':'f'*64},)))
    assert store.has_orphaned_durable_state()


def test_broker_bound_receipt_cannot_be_hidden_by_prewrite_result(tmp_path):
    store,request,evidence=fixture(tmp_path)
    with Database.open(store.db_path) as db, db.transaction():
        store._append_in_transaction(db,authorization_id=request.canary_id,event_type='LIFECYCLE_RECEIPT',body={'receipt':{'canary_id':request.canary_id,'step':'BROKER_BOUND'}})
    with pytest.raises(ValueError):store.reconcile_prewrite_abort(request,evidence)
    assert store.has_orphaned_durable_state()


def test_canary_waits_for_completed_healthy_poll():
    from ibkr_paper_30d.authoritative_broker_writer import AuthoritativeBrokerWriter
    writer=object.__new__(AuthoritativeBrokerWriter)
    values=iter([False,True])
    writer.canary_supervision_verifier=lambda:next(values)
    assert writer._canary_supervision_ready() is True


def test_canary_never_ignores_persistent_unhealthy_supervision(monkeypatch):
    import ibkr_paper_30d.authoritative_broker_writer as module
    writer=object.__new__(module.AuthoritativeBrokerWriter)
    writer.canary_supervision_verifier=lambda:False
    values=iter([0.0,6.0])
    monkeypatch.setattr(module.time,'monotonic',lambda:next(values))
    assert writer._canary_supervision_ready() is False


def test_readonly_execution_retains_broker_order_identity():
    from types import SimpleNamespace
    from ibkr_paper_30d.ibkr_readonly_session import _ReadOnlyIBClient
    c=_ReadOnlyIBClient()
    c.execDetails(1,SimpleNamespace(conId=10,symbol='BTC'),SimpleNamespace(execId='old-fill',shares=1,price=80,orderRef='historical-canary',orderId=17,clientId=19761,permId=55))
    assert c.executions_value[0]['order_ref']=='historical-canary'
    assert c.executions_value[0]['perm_id']==55


def test_runtime_automatically_settles_only_proven_prewrite_abort(tmp_path,monkeypatch):
    from ibkr_paper_30d.ibkr_readonly_session import IBKRReadOnlySessionCollector
    store,request,evidence=fixture(tmp_path)
    monkeypatch.setattr(IBKRReadOnlySessionCollector,'collect',lambda *_args,**kwargs:evidence)
    store.settle_prewrite_aborts()
    assert store.has_orphaned_durable_state() is False
