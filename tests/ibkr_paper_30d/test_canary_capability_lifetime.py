from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.broker_write_coordinator import BrokerWriteCoordinator
from ibkr_paper_30d.production_continuity_runtime import create_canary_pilot_orchestrator, _ProductionCanaryStore
import ibkr_paper_30d.canary_pilot as pilot_module
from test_canary_pilot import _proposal


@pytest.mark.parametrize("expired,owner_expired", [(False,False),(True,False),(False,True)])
def test_technical_capability_lease_is_distinct_from_quote_freshness(tmp_path, monkeypatch, expired, owner_expired):
    captured = []
    monkeypatch.setattr(_ProductionCanaryStore, "persist_owner_pilot_authorization", lambda *_: None)
    monkeypatch.setattr(pilot_module, "CanaryPilotOrchestrator", lambda **kwargs: SimpleNamespace(**kwargs))
    store = SimpleNamespace(current_adapter_sha256="a" * 64,
        record_read_only_candidate_evidence=lambda *args, **kwargs: captured.append(kwargs),
        projection=lambda _: SimpleNamespace(adapter_sha256="a"*64),
        record_canary_lifecycle=lambda *args, **kwargs: captured.append(kwargs))
    now = datetime.now(timezone.utc)
    owner_expiry = now-timedelta(seconds=1) if owner_expired else now+timedelta(days=3)
    orchestrator = create_canary_pilot_orchestrator(coordinator=BrokerWriteCoordinator(), db_path=tmp_path/"unused.sqlite3",
        provider=None, toolbox=None, owner_pilot_authorization=SimpleNamespace(expires_at_utc=owner_expiry), writer_binding_sha256="b"*64,
        model="test", reasoning_effort="max", timeout_seconds=60, product_certification_store=store,
        effective_approved_head="c"*40)
    observed = now-timedelta(seconds=130) if expired else now
    evidence = {"observed_at_utc":observed,"expires_at_utc":observed+timedelta(seconds=120)}
    original_expiry = evidence["expires_at_utc"]
    bundle = SimpleNamespace(multi_sleeve_portfolio={"account_observation":{"positions":[],"open_orders":[]},"transition_phase":"CANARY_EXCLUSIVE"}, reconciliation_receipt={"status":"PASS"})
    if expired or owner_expired:
        reason = "CANARY_CAPABILITY_EVIDENCE_STALE" if expired else "CANARY_CAPABILITY_OWNER_WINDOW_EXPIRED"
        with pytest.raises(RuntimeError, match=reason):
            orchestrator.candidate_finalizer(_proposal(),evidence,SimpleNamespace(capability_evidence_sha256="d"*64),bundle=bundle)
        assert captured == []
    else:
        orchestrator.candidate_finalizer(_proposal(),evidence,SimpleNamespace(capability_evidence_sha256="d"*64),bundle=bundle)
        assert captured[0]["expires_at_utc"] == owner_expiry
        assert captured[0]["observed_at_utc"] == observed
        orchestrator.lifecycle_finalizer(_proposal(),SimpleNamespace(projection=object(), status="TERMINAL_NO_FILL"))
        assert captured[1]["expires_at_utc"] == owner_expiry
    assert evidence["expires_at_utc"] == original_expiry


def test_discovery_receives_signed_owner_limits_without_rebinding_them(tmp_path, monkeypatch):
    import ibkr_paper_30d.autonomous_research as research_module
    from test_autonomous_research import bundle
    from test_canary_pilot import _owner
    owner = _owner()
    captured = []
    monkeypatch.setattr(_ProductionCanaryStore, "persist_owner_pilot_authorization", lambda *_: None)
    monkeypatch.setattr(pilot_module, "CanaryPilotOrchestrator", lambda **kwargs: SimpleNamespace(**kwargs))
    class Loop:
        def __init__(self, *args, **kwargs): pass
        def run(self, request, value): captured.append(request); return object()
    monkeypatch.setattr(research_module, "CanaryCandidateDiscoveryLoop", Loop)
    orchestrator = create_canary_pilot_orchestrator(coordinator=BrokerWriteCoordinator(), db_path=tmp_path/"unused.sqlite3",
        provider=None, toolbox=None, owner_pilot_authorization=owner, writer_binding_sha256="b"*64,
        model="gpt-5.6-sol", reasoning_effort="max", timeout_seconds=60,
        product_certification_store=SimpleNamespace(current_adapter_sha256="a"*64), effective_approved_head="c"*40)
    orchestrator.discovery_runner(bundle(), lambda *_: None)
    limits = captured[0].model_configuration["canary_pilot_limits"]
    assert limits["authorization_sha256"] == owner.sha256
    assert limits["maximum_debit_usd"] == str(owner.maximum_debit_usd)
    assert limits["maximum_loss_usd"] == str(owner.maximum_loss_usd)
    assert limits["total_fee_allowance_usd"] == str(owner.fee_allowance_usd)
    assert limits["maximum_order_count"] == owner.maximum_order_count
    assert limits["expires_at_utc"] == owner.expires_at_utc.isoformat()
    assert captured[0].model_configuration["canary_authority_context"]["approved_head"] == "c"*40
