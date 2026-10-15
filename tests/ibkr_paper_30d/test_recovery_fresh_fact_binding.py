from copy import deepcopy
import pytest
from test_canary_execution import _request
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.production_continuity_runtime import _ProductionCanaryStore


@pytest.mark.parametrize('changed',[False,True])
def test_fresh_flat_observation_can_bind_same_verified_terminal_recovery(changed):
    r=_request()
    old={'request_sha256':r.sha256,'account_identity_sha256':r.account_identity_sha256,
         'contract_identity_sha256':r.canonical_contract.sha256,'position_quantity':'0',
         'open_order_count':0,'complete':True,'observed_at_utc':'2026-10-14T12:00:00Z',
         'average_cost':'0','fills':[]}
    fresh=deepcopy(old);fresh['observed_at_utc']='2026-10-14T12:01:00Z'
    if changed:fresh['fills']=[{'execution_id_sha256':'f'*64}]
    e='a'*64
    events=[{'event_type':'EXECUTION_REQUEST','candidate_sha256':r.candidate_sha256,'request':r.model_dump(mode='json')},
        {'event_type':'CANARY_RECOVERY_RESULT','candidate_sha256':r.candidate_sha256,'original_request_sha256':r.sha256,
         'result':{'success':True,'status':'FILLED','broker_validation':{'broker_facts':old}}},
        {'event_type':'BROKER_FACTS_OBSERVED','request_sha256':r.sha256,'facts':fresh,'facts_sha256':sha256_json(fresh)},
        {'event_type':'BROKER_NET_PNL_RECONCILED','candidate_sha256':r.candidate_sha256,'request_sha256':r.sha256,'evidence_sha256':e},
        {'event_type':'CANARY_RECOVERY_RECONCILED','candidate_sha256':r.candidate_sha256,'request_sha256':r.sha256,'evidence_sha256':e,'facts_sha256':sha256_json(fresh)}]
    assert (r.candidate_sha256 in _ProductionCanaryStore._reconciled_recovery_candidates(events)) is (not changed)


@pytest.mark.parametrize('forged', [None, 'entry_id', 'exit_id', 'perm_id', 'quantity', 'action', 'client_id', 'order_ref'])
def test_immediate_fill_recovery_binds_exact_observed_executions(forged):
    r = _request()
    recovery_sha = 'b' * 64
    order = {'orderId': 360, 'permId': 123, 'clientId': 19761,
             'orderRef': f'codex-ibkr-paper-30d-canary-recovery-{recovery_sha[:12]}'}
    entry = {'execution_id_sha256': 'c' * 64, 'action': r.entry_terms.action,
             'quantity': str(r.quantity), 'price': '100', 'order_id': 348,
             'perm_id': 122, 'client_id': 19761,
             'order_ref': f'codex-ibkr-paper-30d-canary-entry-{r.sha256[:12]}'}
    exit_fill = {**entry, 'execution_id_sha256': 'd' * 64, 'action': r.flat_return_plan.action,
                 'order_id': 360, 'perm_id': 123, 'order_ref': order['orderRef']}
    compact = {'original_request_sha256': r.sha256, 'request_sha256': recovery_sha,
               'account_identity_sha256': r.account_identity_sha256,
               'contract_identity_sha256': r.canonical_contract.sha256,
               'entry_execution_id_sha256': entry['execution_id_sha256'],
               'entry_order_id': 348, 'entry_perm_id': 122, 'entry_price': '100',
               'exit_execution_ids_sha256': [exit_fill['execution_id_sha256']],
               'post_position_quantity': '0'}
    if forged == 'entry_id': entry['execution_id_sha256'] = 'e' * 64
    if forged == 'exit_id': exit_fill['execution_id_sha256'] = 'e' * 64
    if forged in {'perm_id', 'client_id'}: exit_fill[forged] = 999
    if forged == 'quantity': exit_fill['quantity'] = str(r.quantity * 2)
    if forged == 'action': exit_fill['action'] = r.entry_terms.action
    if forged == 'order_ref': exit_fill['order_ref'] = 'unrelated'
    facts = {'request_sha256': r.sha256, 'account_identity_sha256': r.account_identity_sha256,
             'contract_identity_sha256': r.canonical_contract.sha256, 'complete': True,
             'position_quantity': '0', 'open_order_count': 0, 'fills': [entry, exit_fill]}
    events = [
        {'event_type': 'EXECUTION_REQUEST', 'candidate_sha256': r.candidate_sha256, 'request': r.model_dump(mode='json')},
        {'event_type': 'CANARY_RECOVERY_RESULT', 'candidate_sha256': r.candidate_sha256,
         'original_request_sha256': r.sha256, 'request_sha256': recovery_sha,
         'result': {'success': True, 'status': 'FILLED', 'order': order, 'broker_validation': compact}},
        {'event_type': 'BROKER_FACTS_OBSERVED', 'request_sha256': r.sha256, 'facts': facts, 'facts_sha256': sha256_json(facts)},
        {'event_type': 'BROKER_NET_PNL_RECONCILED', 'candidate_sha256': r.candidate_sha256, 'request_sha256': r.sha256, 'evidence_sha256': 'a' * 64},
        {'event_type': 'CANARY_RECOVERY_RECONCILED', 'candidate_sha256': r.candidate_sha256,
         'request_sha256': r.sha256, 'evidence_sha256': 'a' * 64, 'facts_sha256': sha256_json(facts)}]
    assert (r.candidate_sha256 in _ProductionCanaryStore._reconciled_recovery_candidates(events)) is (forged is None)
