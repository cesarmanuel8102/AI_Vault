from __future__ import annotations

from ibkr_paper_30d.interference_observability import (
    build_interference_observation,
    summarize_interference,
)


def test_model_no_trade_is_observed_not_treated_as_policy_interference():
    item = build_interference_observation(
        outcome={
            "decision": "NO_TRADE",
            "accepted": True,
            "validation": "PASS",
            "reason_codes": ["NO_EDGE_FOUND"],
        },
        execution=None,
        execute_paper=True,
    )

    assert item["blocked"] is False
    assert item["interference_source"] == "MODEL_DECISION"
    assert item["disposition"] == "MODEL_CHOSE_NO_NEW_EXECUTION"
    assert item["provider_policy_attribution"] == "UNDETERMINED"


def test_capital_boundary_is_distinguished_from_provider_policy():
    item = build_interference_observation(
        outcome={
            "decision": "NO_TRADE",
            "accepted": False,
            "validation": "BLOCK",
            "reason_codes": ["EXPERIMENT_CAPITAL_BOUNDARY"],
        },
        execution=None,
        execute_paper=True,
    )

    assert item["blocked"] is True
    assert item["interference_source"] == "EXPERIMENT_CAPITAL_BOUNDARY"
    assert item["provider_policy_attribution"] == "UNDETERMINED"


def test_successful_paper_execution_has_no_interference_source():
    item = build_interference_observation(
        outcome={
            "decision": "PROPOSE_TRADE",
            "accepted": True,
            "validation": "PASS",
            "reason_codes": [],
        },
        execution={
            "success": True,
            "status": "FILLED",
            "reason_codes": [],
        },
        execute_paper=True,
    )

    assert item["blocked"] is False
    assert item["interference_source"] == "NONE"
    assert item["disposition"] == "EXECUTED"


def test_provider_runtime_failure_is_not_mislabeled_as_provider_policy():
    item = build_interference_observation(
        outcome={
            "decision": "NO_TRADE",
            "accepted": False,
            "validation": "BLOCK",
            "reason_codes": [],
        },
        execution=None,
        execute_paper=True,
        provider_failure_code="RETURN_CODE_1",
    )

    assert item["blocked"] is True
    assert item["interference_source"] == "PROVIDER_RUNTIME"
    assert item["provider_policy_attribution"] == "UNDETERMINED"


def test_interference_rate_uses_model_proposed_actions_as_denominator():
    observations = [
        build_interference_observation(
            outcome={
                "decision": "NO_TRADE",
                "accepted": True,
                "validation": "PASS",
                "reason_codes": ["WAIT"],
            },
            execution=None,
            execute_paper=True,
        ),
        build_interference_observation(
            outcome={
                "decision": "PROPOSE_TRADE",
                "accepted": False,
                "validation": "BLOCK",
                "reason_codes": ["EXPERIMENT_CAPITAL_BOUNDARY"],
            },
            execution=None,
            execute_paper=True,
        ),
        build_interference_observation(
            outcome={
                "decision": "PROPOSE_TRADE",
                "accepted": True,
                "validation": "PASS",
                "reason_codes": [],
            },
            execution={
                "success": True,
                "status": "FILLED",
                "reason_codes": [],
            },
            execute_paper=True,
        ),
    ]

    summary = summarize_interference(observations)

    assert summary["observation_count"] == 3
    assert summary["proposed_action_count"] == 2
    assert summary["blocked_proposed_action_count"] == 1
    assert summary["auditor_interference_rate"] == 0.5


def test_structural_instrument_gap_is_classified_as_host_capability_limitation():
    item = build_interference_observation(
        outcome={
            "decision": "NO_TRADE",
            "accepted": False,
            "validation": "BLOCK",
            "reason_codes": ["LONG_INSTRUMENT_MAX_LOSS_NOT_PROVEN"],
        },
        execution=None,
        execute_paper=True,
    )

    assert item["blocked"] is True
    assert item["interference_source"] == "HOST_CAPABILITY_LIMITATION"
    assert item["provider_policy_attribution"] == "UNDETERMINED"


def test_unbounded_liability_stays_capital_boundary_not_host_capability():
    item = build_interference_observation(
        outcome={
            "decision": "NO_TRADE",
            "accepted": False,
            "validation": "BLOCK",
            "reason_codes": ["UNBOUNDED_UPSIDE_LIABILITY"],
        },
        execution=None,
        execute_paper=True,
    )

    assert item["blocked"] is True
    assert item["interference_source"] == "EXPERIMENT_CAPITAL_BOUNDARY"
