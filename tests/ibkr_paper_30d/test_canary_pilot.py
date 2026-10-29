from __future__ import annotations

from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from ibkr_paper_30d.canary_candidate import (
    CanaryCandidateProposal,
    CanaryDiscoveryOutcome,
    CanaryEntryTerms,
    CanaryFlatReturnPlan,
    OwnerPilotAuthorization,
)
from ibkr_paper_30d.canary_execution import CanaryExecutionResult
from ibkr_paper_30d.canary_pilot import (
    CanaryPilotOrchestrator,
    collect_canary_capability_evidence,
)
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.product_capability import ProductCapabilityError
from ibkr_paper_30d.autonomous_research import ResearchResult, ResearchTool
from ibkr_paper_30d.multi_universe_models import (
    CapitalSleeve,
    CanonicalContractIdentity,
    ContractOwnershipGroup,
    ProductFamilyKey,
)


NOW = datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc)
ACCOUNT = "a" * 64
SUCCESSOR = "b" * 64
HEAD = "c" * 40
WRITER = "d" * 64


def _family() -> ProductFamilyKey:
    return ProductFamilyKey(
        security_type="CRYPTO",
        venue_or_routing="PAXOS",
        quantity_semantics="BASE_UNITS",
        order_representation="LIMIT",
        lifecycle_behavior="CONTINUOUS",
    )


def _contract() -> CanonicalContractIdentity:
    return CanonicalContractIdentity(
        con_id=479624278,
        security_type="CRYPTO",
        currency="USD",
        exchange="PAXOS",
        primary_exchange="",
        local_symbol="BTC.USD",
        trading_class="BTC",
        multiplier="1",
    )


def _proposal() -> CanaryCandidateProposal:
    contract = _contract()
    return CanaryCandidateProposal(
        candidate_id="candidate-1",
        invocation_id="invocation-1",
        invocation_sha256="1" * 64,
        result_sha256="2" * 64,
        account_identity_sha256=ACCOUNT,
        successor_definition_sha256=SUCCESSOR,
        approved_head=HEAD,
        product_family=_family(),
        canonical_contract=contract,
        contract_group=ContractOwnershipGroup(
            group_id="group-1",
            sleeve=CapitalSleeve.CONTINUOUS_SLEEVE,
            parent_contract=contract,
            member_contracts=(contract,),
            generation=1,
        ),
        entry_terms=CanaryEntryTerms(
            action="BUY",
            order_type="LMT",
            limit_price=Decimal("10"),
            time_in_force="DAY",
            outside_regular_hours=True,
        ),
        quantity=Decimal("0.001"),
        maximum_debit_usd=Decimal("10"),
        maximum_loss_usd=Decimal("10"),
        fee_allowance_usd=Decimal("1"),
        created_at_utc=NOW,
        expires_at_utc=NOW + timedelta(minutes=30),
        flat_return_plan=CanaryFlatReturnPlan(
            action="SELL",
            order_type="LMT",
            quantity=Decimal("0.001"),
            limit_price_rule="MODEL_REFRESHED_MARKETABLE_LIMIT",
            deadline_utc=NOW + timedelta(minutes=20),
            terminal_state="FLAT",
        ),
    )


def _evidence(proposal: CanaryCandidateProposal) -> dict:
    return {
        "invocation_id": proposal.invocation_id,
        "invocation_sha256": proposal.invocation_sha256,
        "result_sha256": proposal.result_sha256,
        "account_identity_sha256": proposal.account_identity_sha256,
        "successor_definition_sha256": proposal.successor_definition_sha256,
        "approved_head": proposal.approved_head,
        "product_family_sha256": proposal.product_family.sha256,
        "contract_identity_sha256": proposal.canonical_contract.sha256,
        "contract_group_sha256": proposal.contract_group.sha256,
        "entry_terms_sha256": proposal.entry_terms.sha256,
        "flat_return_plan_sha256": proposal.flat_return_plan.sha256,
        "quantity": str(proposal.quantity),
        "maximum_debit_usd": str(proposal.maximum_debit_usd),
        "maximum_loss_usd": str(proposal.maximum_loss_usd),
        "fee_allowance_usd": str(proposal.fee_allowance_usd),
        "paper_only": True,
        "fresh": True,
        "broker_write_count": 0,
        "contract_qualified": True,
        "market_data_verified": True,
        "broker_feasibility_verified": True,
        "observed_at_utc": NOW,
        "expires_at_utc": NOW + timedelta(minutes=5),
    }


class Store:
    def __init__(self):
        self.candidate = None
        self.result = None
        self.request = None
        self.claimed_execution_keys = set()
        self.authorizations = []
        self.discovery_events = []
        self.recovered_result = None

    def load_candidate(self):
        return self.candidate

    def persist_candidate(self, outcome, evidence, validation):
        self.candidate = (outcome, evidence, validation)

    def persist_discovery_event(self, kind, payload):
        self.discovery_events.append((kind, payload))

    def persist_authorization(self, *, candidate_sha256, authorization):
        self.authorizations.append((candidate_sha256, authorization))
        return authorization.sha256

    def load_result(self, candidate_sha256):
        return self.result

    def recover_terminal_result(self, candidate_sha256):
        return self.recovered_result

    def persist_result(self, candidate_sha256, result):
        self.result = result

    def load_request(self, candidate_sha256):
        return self.request

    def persist_request(self, candidate_sha256, request):
        self.request = request

    def execution_claimed(self, execution_key):
        return execution_key in self.claimed_execution_keys

    def expire_unused_candidate(self, candidate_sha256, now_utc):
        del now_utc
        if self.candidate is None:
            return False
        if self.candidate[0].proposal.sha256 != candidate_sha256:
            return False
        if self.authorizations or self.request is not None:
            return False
        self.candidate = None
        return True


class Coordinator:
    def __init__(self, result):
        self.requests = []
        self.result = result

    def submit(self, request):
        self.requests.append(request)
        future = Future()
        future.set_result(
            self.result(request) if callable(self.result) else self.result
        )
        return future


def _owner() -> OwnerPilotAuthorization:
    return OwnerPilotAuthorization(
        authorization_id="owner-pilot-1",
        owner_id="owner",
        account_identity_sha256=ACCOUNT,
        successor_definition_sha256=SUCCESSOR,
        approved_head=HEAD,
        maximum_debit_usd=Decimal("20"),
        maximum_loss_usd=Decimal("20"),
        fee_allowance_usd=Decimal("2"),
        maximum_order_count=2,
        issued_at_utc=NOW - timedelta(minutes=1),
        expires_at_utc=NOW + timedelta(hours=1),
    )


def test_discovery_persists_only_model_selected_exact_candidate() -> None:
    proposal = _proposal()
    outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=proposal.invocation_sha256,
        result_sha256=proposal.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=proposal,
    )
    store = Store()

    controller = CanaryPilotOrchestrator(
        discovery_runner=lambda _bundle, persister: outcome,
        capability_evidence_collector=lambda _bundle, actual: _evidence(actual),
        store=store,
        coordinator=Coordinator(None),
        owner_pilot_authorization=_owner(),
        writer_binding_sha256=WRITER,
        durable_sequence_allocator=lambda: 1,
        now_utc=lambda: NOW + timedelta(seconds=1),
    )

    result = controller.discover(object())

    assert result["status"] == "PASS"
    assert result["decision"] == "CANDIDATE_READY"
    assert store.candidate[0].proposal == proposal
    assert store.authorizations == []


def test_execution_revalidates_then_submits_exact_request_once() -> None:
    proposal = _proposal()
    outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=proposal.invocation_sha256,
        result_sha256=proposal.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=proposal,
    )
    store = Store()
    store.candidate = (outcome, _evidence(proposal), object())
    coordinator = Coordinator(
        lambda request: CanaryExecutionResult(
            status="TERMINAL_NO_FILL",
            request_sha256=request.sha256,
            broker_write_boundary_crossed=True,
        )
    )
    sequences = iter((7, 8))
    controller = CanaryPilotOrchestrator(
        discovery_runner=lambda *_args: (_ for _ in ()).throw(
            AssertionError("discovery must not rerun in CANARY_EXCLUSIVE")
        ),
        capability_evidence_collector=lambda _bundle, actual: _evidence(actual),
        store=store,
        coordinator=coordinator,
        owner_pilot_authorization=_owner(),
        writer_binding_sha256=WRITER,
        durable_sequence_allocator=lambda: next(sequences),
        now_utc=lambda: NOW + timedelta(seconds=1),
    )

    first = controller.execute(object())
    second = controller.execute(object())

    assert first["status"] == "TERMINAL_NO_FILL"
    assert second == first
    assert len(coordinator.requests) == 1
    request = coordinator.requests[0]
    assert request.candidate_sha256 == proposal.sha256
    assert request.authorization_sha256 == store.authorizations[0][1].sha256
    assert request.writer_binding_sha256 == WRITER
    assert request.durable_sequence == 7


def test_read_only_refresh_never_submits_an_order() -> None:
    proposal = _proposal()
    outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=proposal.invocation_sha256,
        result_sha256=proposal.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=proposal,
    )
    store = Store()
    store.candidate = (outcome, _evidence(proposal), object())
    coordinator = Coordinator(
        lambda _request: (_ for _ in ()).throw(
            AssertionError("read-only refresh must not submit")
        )
    )
    finalized = []
    controller = CanaryPilotOrchestrator(
        discovery_runner=lambda *_args: outcome,
        capability_evidence_collector=lambda _bundle, actual: _evidence(actual),
        store=store,
        coordinator=coordinator,
        owner_pilot_authorization=_owner(),
        writer_binding_sha256=WRITER,
        durable_sequence_allocator=lambda: 1,
        now_utc=lambda: NOW + timedelta(seconds=1),
        read_only_recertification_finalizer=lambda *args, **kwargs: finalized.append(
            (args, kwargs)
        ),
    )

    result = controller.refresh_read_only(object())

    assert result["status"] == "PASS"
    assert result["decision"] == "CERTIFICATION_REFRESHED_READ_ONLY"
    assert result["broker_write_count"] == 0
    assert len(finalized) == 1
    assert coordinator.requests == []


def test_execution_finalizes_and_persists_recovered_terminal_result() -> None:
    proposal = _proposal()
    outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=proposal.invocation_sha256,
        result_sha256=proposal.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=proposal,
    )
    store = Store()
    store.candidate = (outcome, _evidence(proposal), object())
    store.recovered_result = {
        "authorization_sha256": "f" * 64,
        "result": CanaryExecutionResult(
            status="TERMINAL_NO_FILL",
            request_sha256="e" * 64,
            broker_write_boundary_crossed=True,
        ),
    }
    finalized = []
    coordinator = Coordinator(
        lambda _request: (_ for _ in ()).throw(
            AssertionError("recovered execution must not be resubmitted")
        )
    )
    controller = CanaryPilotOrchestrator(
        discovery_runner=lambda *_args: (_ for _ in ()).throw(
            AssertionError("discovery must not rerun during recovery")
        ),
        capability_evidence_collector=lambda _bundle, actual: _evidence(actual),
        store=store,
        coordinator=coordinator,
        owner_pilot_authorization=_owner(),
        writer_binding_sha256=WRITER,
        durable_sequence_allocator=lambda: 1,
        now_utc=lambda: NOW + timedelta(hours=1),
        lifecycle_finalizer=lambda *args: finalized.append(args),
    )

    result = controller.execute(object())

    assert result["status"] == "TERMINAL_NO_FILL"
    assert result["decision"] == "CANARY_EXECUTED"
    assert result["candidate_sha256"] == proposal.sha256
    assert store.result == result
    assert len(finalized) == 1
    assert coordinator.requests == []


def test_execution_retires_expired_candidate_and_executes_replacement_same_cycle() -> None:
    expired = _proposal()
    expired_outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=expired.invocation_sha256,
        result_sha256=expired.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=expired,
    )
    replacement = expired.model_copy(
        update={
            "candidate_id": "candidate-2",
            "invocation_id": "invocation-2",
            "invocation_sha256": "3" * 64,
            "result_sha256": "4" * 64,
            "created_at_utc": NOW + timedelta(minutes=31),
            "expires_at_utc": NOW + timedelta(minutes=61),
            "flat_return_plan": expired.flat_return_plan.model_copy(
                update={"deadline_utc": NOW + timedelta(minutes=51)}
            ),
        }
    )
    replacement_outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=replacement.invocation_sha256,
        result_sha256=replacement.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=replacement,
    )
    store = Store()
    store.candidate = (expired_outcome, _evidence(expired), object())
    coordinator = Coordinator(
        lambda request: CanaryExecutionResult(
            status="TERMINAL_NO_FILL",
            request_sha256=request.sha256,
            broker_write_boundary_crossed=True,
        )
    )
    controller = CanaryPilotOrchestrator(
        discovery_runner=lambda *_args: replacement_outcome,
        capability_evidence_collector=lambda _bundle, actual: {
            **_evidence(actual),
            "observed_at_utc": NOW + timedelta(minutes=31),
            "expires_at_utc": NOW + timedelta(minutes=36),
        },
        store=store,
        coordinator=coordinator,
        owner_pilot_authorization=_owner().model_copy(
            update={"expires_at_utc": NOW + timedelta(hours=2)}
        ),
        writer_binding_sha256=WRITER,
        durable_sequence_allocator=lambda: 1,
        now_utc=lambda: NOW + timedelta(minutes=31),
    )

    result = controller.execute(object())

    assert result["status"] == "TERMINAL_NO_FILL"
    assert result["decision"] == "CANARY_EXECUTED"
    assert result["candidate_sha256"] == replacement.sha256
    assert store.candidate[0].proposal == replacement
    assert len(store.authorizations) == 1
    assert len(coordinator.requests) == 1


def test_execution_rejects_result_for_a_different_request() -> None:
    proposal = _proposal()
    outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=proposal.invocation_sha256,
        result_sha256=proposal.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=proposal,
    )
    store = Store()
    store.candidate = (outcome, _evidence(proposal), object())
    coordinator = Coordinator(
        CanaryExecutionResult(
            status="TERMINAL_NO_FILL",
            request_sha256="f" * 64,
            broker_write_boundary_crossed=True,
        )
    )
    finalized = []
    controller = CanaryPilotOrchestrator(
        discovery_runner=lambda *_args: outcome,
        capability_evidence_collector=lambda _bundle, actual: _evidence(actual),
        store=store,
        coordinator=coordinator,
        owner_pilot_authorization=_owner(),
        writer_binding_sha256=WRITER,
        durable_sequence_allocator=lambda: 1,
        now_utc=lambda: NOW + timedelta(seconds=1),
        lifecycle_finalizer=lambda *args: finalized.append(args),
    )

    result = controller.execute(object())

    assert result["status"] == "BLOCK"
    assert result["reason_codes"] == ["CANARY_EXECUTION_RESULT_MISMATCH"]
    assert store.result is None
    assert finalized == []


def test_claimed_durable_request_blocks_restart_resubmission() -> None:
    proposal = _proposal()
    outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=proposal.invocation_sha256,
        result_sha256=proposal.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=proposal,
    )
    store = Store()
    store.candidate = (outcome, _evidence(proposal), object())
    coordinator = Coordinator(None)
    controller = CanaryPilotOrchestrator(
        discovery_runner=lambda *_args: outcome,
        capability_evidence_collector=lambda _bundle, actual: _evidence(actual),
        store=store,
        coordinator=coordinator,
        owner_pilot_authorization=_owner(),
        writer_binding_sha256=WRITER,
        durable_sequence_allocator=lambda: 1,
        now_utc=lambda: NOW + timedelta(seconds=1),
    )
    first = controller.execute(object())
    assert first["status"] == "BLOCK"
    assert len(coordinator.requests) == 1

    store.result = None
    store.claimed_execution_keys.add(store.request.execution_key)
    coordinator.requests.clear()
    restarted = controller.execute(object())

    assert restarted["status"] == "BLOCK"
    assert restarted["reason_codes"] == ["CANARY_RECOVERY_REQUIRED"]
    assert coordinator.requests == []


def test_no_candidate_never_creates_host_fallback_or_broker_request() -> None:
    outcome = CanaryDiscoveryOutcome(
        decision="NO_CANDIDATE",
        invocation_sha256="1" * 64,
        result_sha256="2" * 64,
        transcript_sha256=sha256_json([]),
    )
    coordinator = Coordinator(None)
    controller = CanaryPilotOrchestrator(
        discovery_runner=lambda _bundle, _persister: outcome,
        capability_evidence_collector=lambda *_args: (_ for _ in ()).throw(
            AssertionError("no candidate has no capability probe")
        ),
        store=Store(),
        coordinator=coordinator,
        owner_pilot_authorization=_owner(),
        writer_binding_sha256=WRITER,
        durable_sequence_allocator=lambda: 1,
        now_utc=lambda: NOW,
    )

    result = controller.discover(object())

    assert result["decision"] == "NO_CANDIDATE"
    assert coordinator.requests == []


def test_stale_revalidation_blocks_before_exact_authorization_or_submit() -> None:
    proposal = _proposal()
    outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=proposal.invocation_sha256,
        result_sha256=proposal.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=proposal,
    )
    store = Store()
    store.candidate = (outcome, _evidence(proposal), object())
    coordinator = Coordinator(None)
    stale = _evidence(proposal)
    stale["fresh"] = False
    controller = CanaryPilotOrchestrator(
        discovery_runner=lambda *_args: outcome,
        capability_evidence_collector=lambda *_args: stale,
        store=store,
        coordinator=coordinator,
        owner_pilot_authorization=_owner(),
        writer_binding_sha256=WRITER,
        durable_sequence_allocator=lambda: 1,
        now_utc=lambda: NOW + timedelta(seconds=1),
    )

    result = controller.execute(object())

    assert result["status"] == "BLOCK"
    assert "CANARY_CAPABILITY_EVIDENCE_STALE" in result["reason_codes"]
    assert store.authorizations == []
    assert coordinator.requests == []


def test_capability_collector_rechecks_exact_contract_quote_and_whatif() -> None:
    proposal = _proposal()
    observed = []

    class Toolbox:
        def execute(self, request, bundle):
            observed.append((request, bundle))
            if request.tool is ResearchTool.RESOLVE_CONTRACT:
                data = {
                    "contracts": [
                        {
                            "conId": proposal.canonical_contract.con_id,
                            "secType": proposal.canonical_contract.security_type,
                        }
                    ]
                }
            elif request.tool is ResearchTool.QUOTE:
                data = {
                    "contract": {
                        "conId": proposal.canonical_contract.con_id,
                    },
                    "bid": "9.90",
                    "ask": "10.10",
                }
            else:
                data = {
                    "paper_only": True,
                    "whatIf": True,
                    "broker_economics_computed": True,
                }
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=True,
                data=data,
            )

    bundle = object()
    evidence = collect_canary_capability_evidence(
        Toolbox(), bundle, proposal, now_utc=NOW + timedelta(seconds=1)
    )

    assert evidence["fresh"] is True
    assert evidence["broker_write_count"] == 0
    assert evidence["contract_qualified"] is True
    assert evidence["market_data_verified"] is True
    assert evidence["broker_feasibility_verified"] is True
    assert [item[0].tool for item in observed] == [
        ResearchTool.RESOLVE_CONTRACT,
        ResearchTool.QUOTE,
        ResearchTool.BROKER_FEASIBILITY,
    ]
    assert all(item[1] is bundle for item in observed)


def test_capability_collector_uses_host_bindings_not_proposal_claims() -> None:
    proposal = _proposal()
    host_bindings = {
        "invocation_id": "host-invocation",
        "invocation_sha256": "3" * 64,
        "result_sha256": "4" * 64,
        "account_identity_sha256": "5" * 64,
        "successor_definition_sha256": "6" * 64,
        "approved_head": "7" * 40,
    }

    class Toolbox:
        def execute(self, request, bundle):
            del bundle
            if request.tool is ResearchTool.RESOLVE_CONTRACT:
                data = {
                    "contracts": [
                        {
                            "conId": proposal.canonical_contract.con_id,
                            "secType": proposal.canonical_contract.security_type,
                        }
                    ]
                }
            elif request.tool is ResearchTool.QUOTE:
                data = {
                    "contract": {"conId": proposal.canonical_contract.con_id},
                    "bid": "9.90",
                    "ask": "10.10",
                }
            else:
                data = {"paper_only": True, "whatIf": True}
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=True,
                data=data,
            )

    evidence = collect_canary_capability_evidence(
        Toolbox(),
        object(),
        proposal,
        now_utc=NOW + timedelta(seconds=1),
        expected_candidate_bindings=host_bindings,
    )

    for field, expected in host_bindings.items():
        assert evidence[field] == expected


@pytest.mark.parametrize("fee_allowance,allowed", [("0.25", False), ("0.49", False), ("0.50", True), ("1", True)])
def test_capability_collector_accepts_cash_debit_only_within_candidate_bounds(fee_allowance, allowed) -> None:
    proposal = _proposal().model_copy(
        update={
            "maximum_debit_usd": Decimal("10"),
            "maximum_loss_usd": Decimal("10"),
            "fee_allowance_usd": Decimal(fee_allowance),
        }
    )

    class Toolbox:
        def execute(self, request, bundle):
            del bundle
            if request.tool is ResearchTool.RESOLVE_CONTRACT:
                data = {
                    "contracts": [
                        {
                            "conId": proposal.canonical_contract.con_id,
                            "secType": "CRYPTO",
                        }
                    ]
                }
            elif request.tool is ResearchTool.QUOTE:
                data = {
                    "contract": {"conId": proposal.canonical_contract.con_id},
                    "bid": "9990",
                    "ask": "10000",
                }
            else:
                data = {
                    "paper_only": True,
                    "whatIf": True,
                    "what_if_status": "BROKER_CASH_DEBIT_COMPUTED",
                    "broker_economics_computed": True,
                    "cash_notional_usd": "10.00",
                    "estimated_commission_usd": "0.25",
                    "maximum_cash_debit_usd": "10.25",
                }
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=True,
                data=data,
            )

    evidence = collect_canary_capability_evidence(
        Toolbox(), object(), proposal, now_utc=NOW + timedelta(seconds=1)
    )

    assert evidence["broker_feasibility_verified"] is allowed
    assert evidence["broker_economics_within_candidate_bounds"] is allowed
    assert evidence["fresh"] is allowed
    assert evidence["estimated_round_trip_commission_usd"] == "0.50"
    assert evidence["round_trip_commission_is_estimate"] is True


def test_capability_collector_rejects_underdeclared_cash_economics() -> None:
    proposal = _proposal()

    class Toolbox:
        def execute(self, request, bundle):
            del bundle
            if request.tool is ResearchTool.RESOLVE_CONTRACT:
                data = {
                    "contracts": [
                        {
                            "conId": proposal.canonical_contract.con_id,
                            "secType": "CRYPTO",
                        }
                    ]
                }
            elif request.tool is ResearchTool.QUOTE:
                data = {
                    "contract": {"conId": proposal.canonical_contract.con_id},
                    "bid": "9990",
                    "ask": "10000",
                }
            else:
                data = {
                    "paper_only": True,
                    "whatIf": True,
                    "what_if_status": "BROKER_CASH_DEBIT_COMPUTED",
                    "broker_economics_computed": True,
                    "cash_notional_usd": "10.01",
                    "estimated_commission_usd": "1.01",
                    "maximum_cash_debit_usd": "11.02",
                }
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=True,
                data=data,
            )

    evidence = collect_canary_capability_evidence(
        Toolbox(), object(), proposal, now_utc=NOW + timedelta(seconds=1)
    )

    assert evidence["broker_feasibility_verified"] is False
    assert evidence["broker_economics_within_candidate_bounds"] is False


def test_discovery_certification_error_returns_block_without_killing_service() -> None:
    """A ProductCapabilityError from candidate_finalizer must become a deterministic
    BLOCK result so the canary fails safely without killing the whole service."""

    proposal = _proposal()
    outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=proposal.invocation_sha256,
        result_sha256=proposal.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=proposal,
    )
    store = Store()

    def failing_finalizer(_proposal, _evidence, _validation, *, bundle=None):
        del bundle
        raise ProductCapabilityError("CERTIFICATION_ADAPTER_DRIFT")

    controller = CanaryPilotOrchestrator(
        discovery_runner=lambda _bundle, persister: outcome,
        capability_evidence_collector=lambda _bundle, actual: _evidence(actual),
        store=store,
        coordinator=Coordinator(None),
        owner_pilot_authorization=_owner(),
        writer_binding_sha256=WRITER,
        durable_sequence_allocator=lambda: 1,
        now_utc=lambda: NOW + timedelta(seconds=1),
        candidate_finalizer=failing_finalizer,
    )

    result = controller.discover(object())

    assert result["status"] == "BLOCK"
    assert result["decision"] == "CANARY_BLOCKED"
    assert "CANARY_CERTIFICATION_ADAPTER_DRIFT" in result["reason_codes"]
    assert any(
        event[0] == "CANARY_DISCOVERY_CERTIFICATION_BLOCK"
        for event in store.discovery_events
    )
