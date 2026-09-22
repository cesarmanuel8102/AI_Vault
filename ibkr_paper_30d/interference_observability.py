from __future__ import annotations

from typing import Any


_PROVIDER_POLICY_VISIBILITY = "NOT_DIRECTLY_OBSERVABLE"


def _reason_codes(payload: dict[str, Any] | None) -> tuple[str, ...]:
    if not payload:
        return ()
    raw = payload.get("reason_codes") or ()
    return tuple(str(item) for item in raw)


def _block_source(reason_codes: tuple[str, ...]) -> str:
    if any(
        code in {
            "LONG_INSTRUMENT_MAX_LOSS_NOT_PROVEN",
            "MULTI_EXPIRY_SHORT_STRUCTURE_NOT_PROVEN_BOUNDED",
            "UNVERIFIED_MULTI_LEG_INSTRUMENT",
        }
        for code in reason_codes
    ):
        return "HOST_CAPABILITY_LIMITATION"
    if any(
        code in {
            "EXPERIMENT_CAPITAL_BOUNDARY",
            "EXPERIMENT_CAPITAL_BOUNDARY_AFTER_COSTS",
            "UNBOUNDED_LIABILITY",
            "UNBOUNDED_SHORT_STOCK",
            "UNCOVERED_SHORT_CALL",
            "UNBOUNDED_OR_UNVERIFIED_SHORT_INSTRUMENT",
            "UNBOUNDED_UPSIDE_LIABILITY",
            "DECLARED_MAX_LOSS_UNDERSTATES_STRUCTURE",
            "BROKER_MARGIN_EXCEEDS_EXPERIMENT_EQUITY",
        }
        for code in reason_codes
    ):
        return "EXPERIMENT_CAPITAL_BOUNDARY"
    if any(
        code.startswith("BROKER_")
        or code.startswith("POSITION_ACTION_")
        or code.startswith("ORDER_")
        for code in reason_codes
    ):
        return "BROKER_OR_EXECUTION_FEASIBILITY"
    if any(
        code.startswith("MARKET_DATA_")
        or code.startswith("BROKER_RECONCILIATION")
        for code in reason_codes
    ):
        return "MARKET_STATE_OR_DATA_INTEGRITY"
    if any(
        code.startswith("KILL_SWITCH")
        or code.startswith("OWNER_AUTHORIZATION")
        or code.startswith("AUDITOR_GATE")
        for code in reason_codes
    ):
        return "OPERATOR_OR_AUDITOR_CONTROL"
    if any(
        code in {
            "CYCLE_MISMATCH",
            "INPUT_HASH_MISMATCH",
            "MISSING_PROPOSAL",
            "MISSING_POSITION_ACTION",
        }
        for code in reason_codes
    ):
        return "EXPERIMENT_INTEGRITY"
    if any(
        code in {"RESEARCH_REQUEST_BATCH_TOO_LARGE", "RESEARCH_ROUND_LIMIT_REACHED"}
        for code in reason_codes
    ):
        return "HOST_RUNTIME_LIMIT"
    return "UNATTRIBUTED_BLOCK"


def build_interference_observation(
    *,
    outcome: dict[str, Any],
    execution: dict[str, Any] | None,
    execute_paper: bool,
    provider_failure_code: str | None = None,
) -> dict[str, Any]:
    """Build telemetry describing who stopped or allowed a model-directed action.

    This function is intentionally observational. It MUST NOT participate in
    authorization, proposal validation, sizing, or broker execution.

    Provider/developer policy influence is not inferred from model behavior.
    Unless the provider exposes an explicit machine-readable signal, that
    influence remains un-attributed rather than guessed.
    """

    decision = str(outcome.get("decision") or "")
    accepted = bool(outcome.get("accepted"))
    validation = str(outcome.get("validation") or "")
    research_reasons = _reason_codes(outcome)

    observation: dict[str, Any] = {
        "schema": "CODEX_POLICY_INTERFERENCE_OBSERVATION_V1",
        "model_decision": decision,
        "research_accepted": accepted,
        "research_validation": validation,
        "research_reason_codes": list(research_reasons),
        "execute_paper_requested": bool(execute_paper),
        "execution_attempted": execution is not None,
        "execution_success": None if execution is None else bool(execution.get("success")),
        "execution_status": None if execution is None else str(execution.get("status") or ""),
        "execution_reason_codes": [] if execution is None else list(_reason_codes(execution)),
        "provider_failure_code": provider_failure_code,
        "provider_policy_visibility": _PROVIDER_POLICY_VISIBILITY,
        "provider_policy_attribution": "UNDETERMINED",
        "blocked": False,
        "interference_source": "NONE",
        "disposition": "ALLOWED",
    }

    if provider_failure_code:
        observation.update(
            blocked=True,
            interference_source="PROVIDER_RUNTIME",
            disposition="PROVIDER_FAILURE",
        )
        return observation

    if not accepted:
        observation.update(
            blocked=True,
            interference_source=_block_source(research_reasons),
            disposition="BLOCKED_BEFORE_EXECUTION",
        )
        return observation

    if decision in {"NO_TRADE", "MONITOR_POSITION", "PAUSE_FOR_REVIEW"}:
        observation.update(
            interference_source="MODEL_DECISION",
            disposition="MODEL_CHOSE_NO_NEW_EXECUTION",
        )
        return observation

    if not execute_paper:
        observation.update(
            interference_source="HOST_CONFIGURATION",
            disposition="OBSERVATION_ONLY",
        )
        return observation

    if execution is None:
        observation.update(
            blocked=True,
            interference_source="HOST_RUNTIME",
            disposition="EXPECTED_EXECUTION_MISSING",
        )
        return observation

    execution_reasons = _reason_codes(execution)
    if bool(execution.get("success")):
        observation.update(
            interference_source="NONE",
            disposition="EXECUTED",
        )
        return observation

    observation.update(
        blocked=True,
        interference_source=_block_source(execution_reasons),
        disposition="BLOCKED_DURING_EXECUTION",
    )
    return observation


def summarize_interference(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate immutable observations without imposing a target block rate."""

    total = len(observations)
    proposed_actions = [
        item
        for item in observations
        if item.get("model_decision") in {"PROPOSE_TRADE", "REDUCE_POSITION", "CLOSE_POSITION"}
    ]
    blocked_actions = [item for item in proposed_actions if bool(item.get("blocked"))]

    by_source: dict[str, int] = {}
    by_disposition: dict[str, int] = {}
    for item in observations:
        source = str(item.get("interference_source") or "UNKNOWN")
        disposition = str(item.get("disposition") or "UNKNOWN")
        by_source[source] = by_source.get(source, 0) + 1
        by_disposition[disposition] = by_disposition.get(disposition, 0) + 1

    infrastructure_block_rate = None
    auditor_control_rate = None
    host_capability_limit_rate = None
    if proposed_actions:
        denominator = len(proposed_actions)
        infrastructure_block_rate = len(blocked_actions) / denominator
        auditor_control_rate = sum(
            1
            for item in proposed_actions
            if item.get("interference_source") == "OPERATOR_OR_AUDITOR_CONTROL"
        ) / denominator
        host_capability_limit_rate = sum(
            1
            for item in proposed_actions
            if item.get("interference_source") == "HOST_CAPABILITY_LIMITATION"
        ) / denominator

    return {
        "schema": "CODEX_POLICY_INTERFERENCE_SUMMARY_V1",
        "observation_count": total,
        "proposed_action_count": len(proposed_actions),
        "blocked_proposed_action_count": len(blocked_actions),
        "infrastructure_block_rate": infrastructure_block_rate,
        "auditor_interference_rate": auditor_control_rate,
        "host_capability_limit_rate": host_capability_limit_rate,
        "by_source": by_source,
        "by_disposition": by_disposition,
        "provider_policy_visibility": _PROVIDER_POLICY_VISIBILITY,
        "note": (
            "infrastructure_block_rate counts every blocked model-proposed executable action; "
            "auditor_interference_rate counts only operator/auditor-control blocks. "
            "provider/developer policy influence is only attributable when an explicit "
            "machine-readable provider signal exists; model caution alone is not treated "
            "as evidence of provider-policy interference"
        ),
    }
