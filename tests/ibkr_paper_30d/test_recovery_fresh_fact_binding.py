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
