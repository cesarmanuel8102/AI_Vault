from datetime import datetime, timezone
from test_canary_ownership_reservation import _setup
from ibkr_paper_30d.canary_recovery_runtime import CanaryRecoveryStore


def test_separate_owner_authorization_allows_one_durable_recovery_claim(tmp_path):
    path, store, proposal, original = _setup(tmp_path)
    store.begin_write(original.execution_key)
    recovery = CanaryRecoveryStore(path)
    request = recovery.authorize(original, entry_execution_id_sha256="a" * 64,
                                 owner_decision_sha256="b" * 64,
                                 approved_head="c" * 40,
                                 now=datetime.now(timezone.utc))
    facts = {"request_sha256": request.sha256,
             "original_request_sha256": original.sha256,
             "entry_execution_id_sha256": "a" * 64,
             "account_identity_sha256": original.account_identity_sha256,
             "contract_identity_sha256": original.canonical_contract.sha256,
             "position_quantity": str(original.quantity)}
    assert recovery.claim(request, facts) is True
    assert recovery.claim(request, facts) is False
    assert store.load_request(proposal.sha256).sha256 == original.sha256


def test_changed_recovery_facts_cannot_claim(tmp_path):
    path, store, _, original = _setup(tmp_path)
    store.begin_write(original.execution_key)
    recovery = CanaryRecoveryStore(path)
    request = recovery.authorize(original, entry_execution_id_sha256="a" * 64,
                                 owner_decision_sha256="b" * 64,
                                 approved_head="c" * 40,
                                 now=datetime.now(timezone.utc))
    assert recovery.claim(request, {"request_sha256": "0" * 64}) is False
