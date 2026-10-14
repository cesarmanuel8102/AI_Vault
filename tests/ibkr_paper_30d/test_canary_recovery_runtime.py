from datetime import datetime, timezone
from test_canary_ownership_reservation import _setup
from ibkr_paper_30d.canary_recovery_runtime import CanaryRecoveryStore
from ibkr_paper_30d.autonomous_execution import PaperExecutionResult
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.production_continuity_runtime import _ProductionCanaryStore


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


def test_result_dataclass_is_persisted_without_losing_order_identity(tmp_path):
    path, store, _, original = _setup(tmp_path)
    store.begin_write(original.execution_key)
    recovery = CanaryRecoveryStore(path)
    request = recovery.authorize(original, entry_execution_id_sha256="a" * 64,
                                 owner_decision_sha256="b" * 64,
                                 approved_head="c" * 40, now=datetime.now(timezone.utc))
    result = PaperExecutionResult(success=False, status="REJECTED_PRE_BROKER",
                                 reason_codes=("IBKR_VALIDATION_REJECTED:321",),
                                 order={"orderId": 229, "permId": 0}, broker_validation={})
    recovery.persist_result(request, result)
    with Database.open(path) as db:
        last = _ProductionCanaryStore._verified_events(db)[-1]
    assert last["result"]["order"] == {"orderId": 229, "permId": 0}


def test_fresh_explicit_owner_decision_has_its_own_one_attempt_limit(tmp_path):
    path, store, _, original = _setup(tmp_path)
    store.begin_write(original.execution_key)
    recovery = CanaryRecoveryStore(path)
    first = recovery.authorize(original, entry_execution_id_sha256="a" * 64,
                               owner_decision_sha256="b" * 64, approved_head="c" * 40,
                               now=datetime.now(timezone.utc))
    second = recovery.authorize(original, entry_execution_id_sha256="a" * 64,
                                owner_decision_sha256="d" * 64, approved_head="e" * 40,
                                now=datetime.now(timezone.utc))
    assert second.sha256 != first.sha256
    assert recovery.load_authorized(original, "d" * 64).sha256 == second.sha256
    facts = {"request_sha256": second.sha256,
             "original_request_sha256": original.sha256,
             "entry_execution_id_sha256": "a" * 64,
             "account_identity_sha256": original.account_identity_sha256,
             "contract_identity_sha256": original.canonical_contract.sha256,
             "position_quantity": str(original.quantity)}
    assert recovery.claim(second, facts) is True
    assert recovery.claim(second, facts) is False
