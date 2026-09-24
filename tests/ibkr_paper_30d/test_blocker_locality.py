from __future__ import annotations

import inspect

import ibkr_paper_30d.interference_observability as interference


def observation(**overrides):
    base = {
        "outcome": {
            "decision": "PROPOSE_TRADE",
            "accepted": False,
            "validation": "BLOCK",
            "reason_codes": [],
        },
        "execution": None,
        "execute_paper": True,
        "provider_failure_code": None,
    }
    base.update(overrides)
    return interference.build_interference_observation(**base)


def test_concrete_capital_boundary_reason_maps_to_capital_boundary_class():
    item = observation(
        outcome={
            "decision": "PROPOSE_TRADE",
            "accepted": False,
            "validation": "BLOCK",
            "reason_codes": ["EXPERIMENT_CAPITAL_BOUNDARY"],
        }
    )
    assert item["interference_source"] == "EXPERIMENT_CAPITAL_BOUNDARY"


def test_concrete_host_capability_reason_maps_to_host_capability_class():
    item = observation(
        outcome={
            "decision": "PROPOSE_TRADE",
            "accepted": False,
            "validation": "BLOCK",
            "reason_codes": ["UNVERIFIED_MULTI_LEG_INSTRUMENT"],
        }
    )
    assert item["interference_source"] == "HOST_CAPABILITY_LIMITATION"


def test_concrete_broker_reason_maps_to_broker_feasibility_class():
    item = observation(
        outcome={
            "decision": "PROPOSE_TRADE",
            "accepted": False,
            "validation": "BLOCK",
            "reason_codes": ["BROKER_FEASIBILITY_FAILED"],
        }
    )
    assert item["interference_source"] == "BROKER_OR_EXECUTION_FEASIBILITY"


def test_unknown_reason_code_is_not_attributed_to_a_specific_host_layer():
    item = observation(
        outcome={
            "decision": "PROPOSE_TRADE",
            "accepted": False,
            "validation": "BLOCK",
            "reason_codes": ["SOME_NEW_UNCLASSIFIED_CODE"],
        }
    )
    assert item["interference_source"] == "UNATTRIBUTED_BLOCK"
    assert item["provider_policy_attribution"] == "UNDETERMINED"


def test_absence_of_action_never_attributed_to_provider_or_model_policy():
    source = inspect.getsource(interference)
    assert '"PROVIDER_POLICY"' not in source
    assert '"MODEL_POLICY"' not in source
    assert '"LLM_POLICY"' not in source
    assert 'interference_source="PROVIDER_RUNTIME"' in source
    assert '"provider_policy_attribution": "UNDETERMINED"' in source


def test_scanner_prefixed_reasons_are_not_blanket_classified():
    """Ruling U5: no generic SCANNER_* -> HOST_CAPABILITY mapping.

    Only concrete codes with observable causality may classify; anything
    else must remain unattributed rather than guessed.
    """
    source = inspect.getsource(interference)
    assert 'code.startswith("SCANNER_")' not in source
    item = observation(
        outcome={
            "decision": "PROPOSE_TRADE",
            "accepted": False,
            "validation": "BLOCK",
            "reason_codes": ["SCANNER_SOMETHING_AMBIGUOUS"],
        }
    )
    assert item["interference_source"] == "UNATTRIBUTED_BLOCK"


def test_blocker_never_disables_unrelated_opportunity_space():
    """A blocker classification is observational and local: it must never be
    consumed as a global restriction. No global blacklist/whitelist state
    may derive from interference observations."""

    source = inspect.getsource(interference)
    for forbidden in (
        "blacklist",
        "whitelist",
        "disabled_instrument",
        "disabled_asset_class",
        "disabled_strategy",
        "frozen_universe",
    ):
        assert forbidden not in source.lower()


def test_local_blocker_still_allows_continuing_discovery():
    """Interference summary preserves model autonomy: blocked actions are
    counted, never translated into forced trades or forced waits."""

    summary = interference.summarize_interference(
        [
            observation(
                outcome={
                    "decision": "PROPOSE_TRADE",
                    "accepted": False,
                    "validation": "BLOCK",
                    "reason_codes": ["EXPERIMENT_CAPITAL_BOUNDARY"],
                }
            ),
            observation(
                outcome={
                    "decision": "NO_TRADE",
                    "accepted": True,
                    "validation": "PASS",
                    "reason_codes": ["NO_EDGE_FOUND"],
                }
            ),
        ]
    )
    assert summary["blocked_proposed_action_count"] == 1
    assert "forced_trade" not in str(summary).lower()