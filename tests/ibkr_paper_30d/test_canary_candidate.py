from __future__ import annotations

import inspect
import json
import subprocess
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.canary_candidate import (
    CanaryCandidateProposal,
    CanaryDiscoveryOutcome,
    CanaryEntryTerms,
    CanaryFlatReturnPlan,
    OwnerPilotAuthorization,
    bind_canary_authorization,
    validate_canary_candidate,
)
from ibkr_paper_30d.autonomous_research import (
    AutonomousTurnMode,
    CanaryCandidateDiscoveryLoop,
    CanaryDiscoveryTurn,
    ResearchRequest,
    ResearchResult,
    ResearchTool,
)
from ibkr_paper_30d.canonical import sha256_json
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
INVOCATION = "d" * 64
RESULT = "e" * 64


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


def _proposal(**overrides) -> CanaryCandidateProposal:
    contract = _contract()
    group = ContractOwnershipGroup(
        group_id="canary-candidate-1",
        sleeve=CapitalSleeve.CONTINUOUS_SLEEVE,
        parent_contract=contract,
        member_contracts=(contract,),
        generation=1,
    )
    values = {
        "candidate_id": "candidate-1",
        "invocation_id": "invocation-1",
        "invocation_sha256": INVOCATION,
        "result_sha256": RESULT,
        "account_identity_sha256": ACCOUNT,
        "successor_definition_sha256": SUCCESSOR,
        "approved_head": HEAD,
        "product_family": _family(),
        "canonical_contract": contract,
        "contract_group": group,
        "entry_terms": CanaryEntryTerms(
            action="BUY",
            order_type="LMT",
            limit_price=Decimal("10"),
            time_in_force="DAY",
            outside_regular_hours=True,
        ),
        "quantity": Decimal("0.001"),
        "maximum_debit_usd": Decimal("10"),
        "maximum_loss_usd": Decimal("10"),
        "fee_allowance_usd": Decimal("1"),
        "created_at_utc": NOW,
        "expires_at_utc": NOW + timedelta(minutes=20),
        "flat_return_plan": CanaryFlatReturnPlan(
            action="SELL",
            order_type="LMT",
            quantity=Decimal("0.001"),
            limit_price_rule="MODEL_REFRESHED_MARKETABLE_LIMIT",
            deadline_utc=NOW + timedelta(minutes=15),
            terminal_state="FLAT",
        ),
    }
    values.update(overrides)
    return CanaryCandidateProposal(**values)


def _evidence(proposal: CanaryCandidateProposal, **overrides):
    values = {
        "paper_only": True,
        "fresh": True,
        "broker_write_count": 0,
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
        "quantity": str(proposal.quantity),
        "maximum_debit_usd": str(proposal.maximum_debit_usd),
        "maximum_loss_usd": str(proposal.maximum_loss_usd),
        "fee_allowance_usd": str(proposal.fee_allowance_usd),
        "flat_return_plan_sha256": proposal.flat_return_plan.sha256,
        "contract_qualified": True,
        "market_data_verified": True,
        "broker_feasibility_verified": True,
        "observed_at_utc": NOW,
        "expires_at_utc": NOW + timedelta(minutes=5),
    }
    values.update(overrides)
    return values


def test_exact_read_only_candidate_validation_passes() -> None:
    proposal = _proposal()

    receipt = validate_canary_candidate(
        proposal,
        read_only_capability_evidence=_evidence(proposal),
        now_utc=NOW + timedelta(seconds=1),
    )

    assert receipt.status == "PASS"
    assert receipt.proposal_sha256 == proposal.sha256
    assert receipt.reason_codes == ()


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"invocation_id": "wrong"}, "CANARY_INVOCATION_MISMATCH"),
        ({"invocation_sha256": "0" * 64}, "CANARY_INVOCATION_HASH_MISMATCH"),
        ({"result_sha256": "0" * 64}, "CANARY_RESULT_HASH_MISMATCH"),
        ({"account_identity_sha256": "0" * 64}, "CANARY_ACCOUNT_MISMATCH"),
        ({"successor_definition_sha256": "0" * 64}, "CANARY_SUCCESSOR_MISMATCH"),
        ({"approved_head": "0" * 40}, "CANARY_HEAD_MISMATCH"),
        ({"product_family_sha256": "0" * 64}, "CANARY_FAMILY_MISMATCH"),
        ({"contract_identity_sha256": "0" * 64}, "CANARY_CONTRACT_MISMATCH"),
        ({"contract_group_sha256": "0" * 64}, "CANARY_CONTRACT_GROUP_MISMATCH"),
        ({"entry_terms_sha256": "0" * 64}, "CANARY_ENTRY_TERMS_MISMATCH"),
        ({"quantity": "0.002"}, "CANARY_QUANTITY_MISMATCH"),
        ({"maximum_loss_usd": "11"}, "CANARY_ECONOMICS_MISMATCH"),
        ({"flat_return_plan_sha256": "0" * 64}, "CANARY_FLAT_PLAN_MISMATCH"),
        ({"fresh": False}, "CANARY_CAPABILITY_EVIDENCE_STALE"),
        ({"paper_only": False}, "POSSIBLE_LIVE_CONNECTION"),
        ({"broker_write_count": 1}, "READ_ONLY_DISCOVERY_WRITE_DETECTED"),
    ],
)
def test_every_candidate_binding_fails_closed(change, reason) -> None:
    proposal = _proposal()
    receipt = validate_canary_candidate(
        proposal,
        read_only_capability_evidence=_evidence(proposal, **change),
        now_utc=NOW + timedelta(seconds=1),
    )

    assert receipt.status == "BLOCK"
    assert reason in receipt.reason_codes


def test_expired_candidate_or_capability_evidence_blocks() -> None:
    proposal = _proposal()
    assert "CANARY_CANDIDATE_EXPIRED" in validate_canary_candidate(
        proposal,
        read_only_capability_evidence=_evidence(proposal),
        now_utc=proposal.expires_at_utc,
    ).reason_codes
    assert "CANARY_CAPABILITY_EVIDENCE_STALE" in validate_canary_candidate(
        proposal,
        read_only_capability_evidence=_evidence(
            proposal, expires_at_utc=NOW
        ),
        now_utc=NOW + timedelta(seconds=1),
    ).reason_codes


def test_owner_authorization_is_reduced_to_exact_candidate() -> None:
    proposal = _proposal()
    owner = OwnerPilotAuthorization(
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

    authorization = bind_canary_authorization(
        proposal, owner, NOW + timedelta(seconds=1)
    )

    assert authorization.authorization_id.endswith(proposal.sha256)
    assert authorization.product_family_sha256 == proposal.product_family.sha256
    assert authorization.contract_scope_sha256 == (
        proposal.canonical_contract.sha256,
    )
    assert authorization.maximum_loss_usd == proposal.maximum_loss_usd
    assert authorization.maximum_debit_usd == proposal.maximum_debit_usd
    assert authorization.fee_allowance_usd == proposal.fee_allowance_usd
    assert authorization.maximum_order_count == 2
    assert authorization.expires_at_utc == proposal.expires_at_utc


def test_no_candidate_is_valid_and_host_has_no_fallback_universe() -> None:
    outcome = CanaryDiscoveryOutcome(
        decision="NO_CANDIDATE",
        invocation_sha256=INVOCATION,
        result_sha256=RESULT,
        transcript_sha256=sha256_json([]),
    )

    assert outcome.proposal is None
    source = inspect.getsource(__import__("ibkr_paper_30d.canary_candidate", fromlist=["*"]))
    assert "FALLBACK_CANDIDATE" not in source
    assert "ALLOWED_SYMBOLS" not in source
    assert "ALLOWED_SECURITY_TYPES" not in source


def test_model_authored_flat_return_plan_must_exactly_flat_candidate() -> None:
    with pytest.raises(ValueError, match="flat-return quantity"):
        _proposal(
            flat_return_plan=CanaryFlatReturnPlan(
                action="SELL",
                order_type="LMT",
                quantity=Decimal("0.002"),
                limit_price_rule="MODEL_REFRESHED_MARKETABLE_LIMIT",
                deadline_utc=NOW + timedelta(minutes=15),
                terminal_state="FLAT",
            )
        )


def test_dedicated_discovery_persists_research_and_accepted_candidate_hash() -> None:
    from test_autonomous_research import bundle, request

    candidate = _proposal()
    turns = [
        CanaryDiscoveryTurn(
            mode=AutonomousTurnMode.RESEARCH,
            research_requests=[
                ResearchRequest(
                    request_id="research-1",
                    tool=ResearchTool.RESOLVE_CONTRACT,
                    arguments={"symbol": "MODEL_SELECTED"},
                    purpose="Qualify the model-selected candidate",
                )
            ],
            reasoning_summary="Qualify the selected contract.",
        ),
        CanaryDiscoveryTurn(
            mode=AutonomousTurnMode.FINAL,
            decision="CANDIDATE",
            proposal=candidate,
            reasoning_summary="Exact candidate selected by Codex.",
        ),
    ]

    class Provider:
        def next_canary_candidate(self, *args, **kwargs):
            return turns.pop(0)

    class Toolbox:
        def manifest(self):
            return [{"name": "RESOLVE_CONTRACT", "read_only": True}]

        def execute(self, research_request, input_bundle):
            return ResearchResult(
                request_id=research_request.request_id,
                tool=research_request.tool,
                success=True,
                data={"qualified": True},
            )

    events = []
    value = bundle().model_copy(
        update={"market_data_snapshot": {"gate_status": "BLOCK"}}
    )
    outcome = CanaryCandidateDiscoveryLoop(
        Provider(), Toolbox(), event_persister=lambda kind, payload: events.append((kind, payload))
    ).run(request(value), value)

    assert outcome.decision == "CANDIDATE"
    assert outcome.proposal == candidate
    assert [kind for kind, _ in events] == [
        "CANARY_DISCOVERY_RESEARCH_EVENT",
        "CANARY_CANDIDATE_ACCEPTED",
    ]
    assert events[-1][1]["candidate_sha256"] == candidate.sha256


def test_real_codex_provider_has_attested_read_only_canary_mode() -> None:
    from test_autonomous_research import bundle, request
    from ibkr_paper_30d.autonomous_research import CodexAutonomousCLIProvider

    captured = {}
    value = bundle().model_copy(
        update={"market_data_snapshot": {"gate_status": "BLOCK"}}
    )
    invocation = request(value)

    def runner(command, **kwargs):
        captured["command"] = command
        captured["payload"] = json.loads(kwargs["input"])
        output_path = command[command.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "mode": "FINAL",
                    "research_requests": [],
                    "decision": "NO_CANDIDATE",
                    "proposal": None,
                    "reasoning_summary": "No exact candidate is justified.",
                },
                handle,
            )
        stdout = "\n".join(
            [
                json.dumps(
                    {
                        "type": "thread.started",
                        "thread_id": "t",
                        "actual_model": invocation.requested_model,
                    }
                ),
                json.dumps({"type": "turn.completed"}),
            ]
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    turn = CodexAutonomousCLIProvider(runner=runner).next_canary_candidate(
        invocation, value, [], [{"tool": "RESOLVE_CONTRACT"}]
    )

    assert turn.decision == "NO_CANDIDATE"
    assert captured["command"][captured["command"].index("--sandbox") + 1] == "read-only"
    assert captured["payload"]["mandate"]["predefined_symbol_universe"] is False
    assert captured["payload"]["mandate"]["broker_writes_prohibited"] is True
