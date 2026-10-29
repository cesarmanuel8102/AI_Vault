import json
from types import SimpleNamespace
import pytest
from test_day1_launch import _launch_transition_target
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.day1_launch import _multi_universe_authority_bindings
from ibkr_paper_30d.multi_universe_models import TransitionPhase


@pytest.mark.parametrize(
    'authorized,last,expected',
    [
        (True, 'BOUNDED_ECONOMICS_VERIFIED', True),
        (True, 'CERTIFICATION_VALIDITY_REFRESHED', True),
        (False, 'BOUNDED_ECONOMICS_VERIFIED', False),
        (True, 'REVOKED', False),
    ],
)
def test_partial_recertification_keeps_only_authorized_historical_launch_binding(monkeypatch,authorized,last,expected):
    import ibkr_paper_30d.multi_universe_authority as module
    target=_launch_transition_target()
    monkeypatch.setattr(module,'MultiUniverseAuthorityStore',lambda _:SimpleNamespace(
        sleeve_authority=lambda _:SimpleNamespace(sha256='a'*64),economic_authorization=lambda:SimpleNamespace(sha256='b'*64)))
    family='f'*64
    class DB:
        def execute(self,sql,args=()):
            if 'product_family_certification_events' in sql:
                rows=[(family,'ECONOMICS_RECONCILED',json.dumps({'account_sha256':target.account_identity_sha256,'endpoint':'PAPER'})),(family,last,'{}')]
                if 'payload_json' not in sql:rows=[r[:2] for r in rows]
                return SimpleNamespace(fetchall=lambda:rows)
            return SimpleNamespace(fetchone=lambda:(json.dumps({'evidence':{'certified_family_set_sha256':sha256_json([family])}}),))
    value=_multi_universe_authority_bindings(DB(),target,TransitionPhase.ACTIVE,
        recertification_release_sha256='d'*64 if authorized else None)
    assert (value['certified_family_set_sha256']==value['expected_certified_family_set_sha256']) is expected
