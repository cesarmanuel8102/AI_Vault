from types import SimpleNamespace

import pytest

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.continuity_binding import build_v4_new_proposal_bindings
from ibkr_paper_30d.contract_ownership import canonical_contract_identity
from ibkr_paper_30d.multi_universe_models import CapitalSleeve, ContractOwnershipGroup


def inputs():
    bundle = SimpleNamespace(
        multi_sleeve_v4_active=True,
        multi_sleeve_portfolio={"sleeve_authority_sha256": {"CONTINUOUS_SLEEVE": "a" * 64}},
        contract_ownership_snapshot={"projection_sha256": "b" * 64},
    )
    proposal = SimpleNamespace(capital_sleeve=CapitalSleeve.CONTINUOUS_SLEEVE, product_family_sha256="c" * 64, quantity="0.20", action="BUY")
    evidence = {"success": True, "contract": {"conId": 495759171, "secType": "CRYPTO", "symbol": "ETH", "exchange": "PAXOS", "currency": "USD", "localSymbol": "ETH.USD"}, "continuity_host_bindings": {"account_identity_sha256": "d" * 64}}
    evidence["continuity_host_bindings"]["canonical_contract_identity_v4"] = canonical_contract_identity(evidence["contract"]).model_dump(mode="json")
    return bundle, proposal, evidence


def bag_inputs():
    bundle, proposal, evidence = inputs()
    evidence["contract"] = {
        "conId": 0,
        "secType": "BAG",
        "symbol": "HIMS",
        "exchange": "SMART",
        "currency": "USD",
        "comboLegs": [
            {"conId": 101, "ratio": 1, "action": "BUY", "exchange": "SMART"},
            {"conId": 102, "ratio": 1, "action": "SELL", "exchange": "SMART"},
        ],
    }
    parent = canonical_contract_identity(evidence["contract"])
    leg1 = canonical_contract_identity(
        {"conId": 101, "secType": "OPT", "currency": "USD", "exchange": "SMART"}
    )
    leg2 = canonical_contract_identity(
        {"conId": 102, "secType": "OPT", "currency": "USD", "exchange": "SMART"}
    )
    evidence["continuity_host_bindings"].update(
        canonical_contract_identity_v4=parent.model_dump(mode="json"),
        ownership_contracts_v4=[
            parent.model_dump(mode="json"),
            leg1.model_dump(mode="json"),
            leg2.model_dump(mode="json"),
        ],
    )
    return bundle, proposal, evidence, parent, leg1, leg2


def test_v4_new_position_bindings_are_host_derived_and_reproducible():
    bundle, proposal, evidence = inputs()
    result = build_v4_new_proposal_bindings(bundle, proposal, evidence, "order-ref")
    assert result == build_v4_new_proposal_bindings(bundle, proposal, evidence, "order-ref")
    assert result["canonical_contract_sha256"] == canonical_contract_identity(evidence["contract"]).sha256
    assert result["sleeve_authority_sha256"] == "a" * 64
    assert result["ownership_projection_sha256"] == "b" * 64
    assert result["capital_sleeve"] == "CONTINUOUS_SLEEVE"
    assert len(result["ownership_group_sha256"]) == 64
    assert result["position_identity_sha256"] != sha256_json({})
    assert result != build_v4_new_proposal_bindings(bundle, proposal, evidence, "another-order")


def test_v4_bag_bindings_hash_exact_parent_and_qualified_members():
    bundle, proposal, evidence, parent, leg1, leg2 = bag_inputs()

    result = build_v4_new_proposal_bindings(bundle, proposal, evidence, "bag-order")

    expected = ContractOwnershipGroup(
        group_id="order:bag-order",
        sleeve=CapitalSleeve.CONTINUOUS_SLEEVE,
        parent_contract=parent,
        member_contracts=(parent, leg1, leg2),
        generation=1,
    )
    assert result["canonical_contract_sha256"] == parent.sha256
    assert result["ownership_group_sha256"] == expected.sha256


@pytest.mark.parametrize("mutation", ["missing_leg", "extra_leg", "duplicate_leg"])
def test_v4_bag_bindings_reject_inexact_member_closure(mutation):
    bundle, proposal, evidence, _parent, _leg1, leg2 = bag_inputs()
    ownership = evidence["continuity_host_bindings"]["ownership_contracts_v4"]
    if mutation == "missing_leg":
        ownership.pop()
    elif mutation == "extra_leg":
        ownership.append(
            canonical_contract_identity(
                {"conId": 103, "secType": "OPT", "currency": "USD", "exchange": "SMART"}
            ).model_dump(mode="json")
        )
    else:
        ownership[-1] = leg2.model_dump(mode="json")
        ownership.append(leg2.model_dump(mode="json"))

    with pytest.raises(ValueError, match="V4_CONTINUITY_BAG_MEMBER_EVIDENCE"):
        build_v4_new_proposal_bindings(bundle, proposal, evidence, "bag-order")


@pytest.mark.parametrize("missing", ["authority", "ownership", "account", "contract", "broker_success"])
def test_missing_v4_binding_source_fails_closed(missing):
    bundle, proposal, evidence = inputs()
    if missing == "authority":
        bundle.multi_sleeve_portfolio = {}
    elif missing == "ownership":
        bundle.contract_ownership_snapshot = {}
    elif missing == "account":
        evidence["continuity_host_bindings"] = {}
    elif missing == "contract":
        evidence["contract"] = {}
    else:
        evidence["success"] = False
    with pytest.raises(ValueError):
        build_v4_new_proposal_bindings(bundle, proposal, evidence, "order-ref")


@pytest.mark.parametrize("field", ["capital_sleeve", "canonical_contract_sha256", "ownership_group_sha256", "product_family_sha256", "position_identity_sha256", "sleeve_authority_sha256", "ownership_projection_sha256"])
def test_final_validation_rejects_forged_v4_host_fields(field):
    from ibkr_paper_30d.autonomous_research import AutonomousResearchLoop
    from ibkr_paper_30d.open_order_management import EXPERIMENT_ORDER_PREFIX

    bundle, proposal, evidence = inputs()
    invocation = SimpleNamespace(decision_cycle_id="cycle-new-entry")
    order_ref = f"{EXPERIMENT_ORDER_PREFIX}-a-{invocation.decision_cycle_id[-12:]}"
    host = evidence["continuity_host_bindings"]
    host.update(contract_identity_sha256="e" * 64, execution_client_id=19761)
    values = build_v4_new_proposal_bindings(bundle, proposal, evidence, order_ref)
    binding = SimpleNamespace(order_ref=order_ref, account_identity_sha256=host["account_identity_sha256"], contract_identity_sha256="e" * 64, execution_client_id=19761)
    plan = SimpleNamespace(schema="CODEX_ORDER_CONTINUITY_PLAN_V4", order_binding=binding, model_dump=lambda **_: values)
    kwargs = dict(request=invocation, broker_evidence={"what_if": evidence}, bundle=bundle, proposal=proposal)
    assert AutonomousResearchLoop._validate_new_proposal_host_bindings(plan, **kwargs) is None
    values[field] = "REGULAR_SLEEVE" if field == "capital_sleeve" else "f" * 64
    assert AutonomousResearchLoop._validate_new_proposal_host_bindings(plan, **kwargs) == "V4_CONTINUITY_HOST_BINDING_MISMATCH"
