from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .autonomous_execution import AutonomousPaperExecutor, PaperExecutionResult
from .autonomous_research import AutonomousResearchLoop, CodexAutonomousCLIProvider
from .autonomy_bootstrap import AutonomyBootstrapBuilder
from .canonical import canonical_bytes, sha256_json
from .continuity_reporting import ContinuityReviewGate
from .decision_diagnostics import (
    build_risk_diagnostics,
    extract_regret_observations,
    load_pending_regret_records,
    load_regret_outcome_source_keys,
    match_post_outcome_observations,
    persist_analytical_failure,
    persist_regret_outcome,
    persist_regret_record,
    persist_risk_diagnostics,
)
from .experiment_ledger import AutonomousExperimentLedger
from .ibkr_research_tools import IBKRResearchToolbox
from .interference_observability import build_interference_observation
from .persistence import Database
from .repositories import utc_now
from .trader_invocation import InvocationRequest, TraderDecision, TraderInputBundle
from .types import new_uuid7


def build_request(
    bundle: TraderInputBundle,
    *,
    model: str,
    reasoning_effort: str,
    experiment_id: str,
    timeout_seconds: int,
    trigger: str,
) -> InvocationRequest:
    if model != "gpt-5.6-sol":
        raise ValueError("autonomous experiment requires gpt-5.6-sol")
    if reasoning_effort.lower() != "max":
        raise ValueError("autonomous experiment requires max reasoning effort")
    invocation_id = f"autonomous-{new_uuid7()}"
    return InvocationRequest(
        decision_cycle_id=bundle.decision_cycle_id,
        invocation_id=invocation_id,
        utc_timestamp=utc_now(),
        requested_model=model,
        actual_model=model,
        model_configuration={
            "provider": "codex-cli",
            "mode": "host-mediated-autonomous-research",
            "predefined_universe": False,
            "predefined_strategy": False,
        },
        reasoning_effort=reasoning_effort,
        input_bundle_sha256=bundle.sha256,
        risk_policy_version="AGGRESSIVE_CAPITAL_BOUNDARY_V1",
        experiment_id=experiment_id,
        invocation_trigger=trigger,
        timeout_seconds=timeout_seconds,
    )


def _canonical_result_payload(
    bundle: TraderInputBundle,
    request: InvocationRequest,
    outcome: Any,
    *,
    continuity_reviews: Any | None = None,
) -> dict[str, Any]:
    reviews = (
        outcome.continuity_reviews
        if continuity_reviews is None
        else continuity_reviews
    )
    return {
        "decision_cycle_id": bundle.decision_cycle_id,
        "invocation_id": request.invocation_id,
        "accepted": outcome.accepted,
        "validation": outcome.validation,
        "decision": outcome.decision.value,
        "proposal": None if outcome.proposal is None else outcome.proposal.model_dump(mode="json"),
        "position_action": None if outcome.position_action is None else outcome.position_action.model_dump(mode="json"),
        "open_order_action": (
            None
            if outcome.open_order_action is None
            else outcome.open_order_action.model_dump(mode="json")
        ),
        "reason_codes": list(outcome.reason_codes),
        "rounds": outcome.rounds,
        "transcript_sha256": outcome.transcript_sha256,
        "broker_validation": outcome.broker_validation,
        "continuity_plan": (
            None
            if outcome.continuity_plan is None
            else outcome.continuity_plan.model_dump(mode="json")
        ),
        "continuity_reviews": [
            review.model_dump(mode="json") for review in reviews
        ],
        "epistemic_status": {
            "proposal.probability_profit": "MODEL_INFERENCE",
            "proposal.probability_loss": "MODEL_INFERENCE",
            "proposal.expected_gain": "MODEL_INFERENCE",
            "proposal.expected_loss": "MODEL_INFERENCE",
            "proposal.expected_value": "MODEL_INFERENCE",
            "proposal.expected_reward_risk": "MODEL_INFERENCE",
            "proposal.confidence": "MODEL_INFERENCE",
            "proposal.capital_required": "MODEL_INFERENCE_ADVISORY",
            "proposal.maximum_loss": "MODEL_INFERENCE_STRUCTURALLY_VERIFIED_WHEN_SUPPORTED",
            "proposal.loss_is_bounded": "MODEL_INFERENCE_STRUCTURALLY_VERIFIED_WHEN_SUPPORTED",
            "broker_validation": "BROKER_OR_DETERMINISTIC_EVIDENCE",
        },
    }


def persist_outcome(
    db: Database,
    bundle: TraderInputBundle,
    request: InvocationRequest,
    outcome: Any,
) -> None:
    bundle_id = f"bundle-{bundle.decision_cycle_id}"
    bundle_payload = bundle.model_dump(mode="json")
    bundle_encoded = canonical_bytes(bundle_payload).decode("utf-8")
    existing = db.execute(
        "SELECT payload_sha256 FROM trader_input_bundles WHERE bundle_id=?",
        (bundle_id,),
    ).fetchone()
    if existing is not None and str(existing[0]) != bundle.sha256:
        raise ValueError("decision cycle already bound to different autonomous input")
    db.execute(
        "INSERT OR IGNORE INTO trader_input_bundles(bundle_id,decision_cycle_id,payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?)",
        (bundle_id, bundle.decision_cycle_id, bundle_encoded, bundle.sha256, utc_now()),
    )

    request_payload = request.model_dump(mode="json")
    db.execute(
        "INSERT INTO trader_invocations(invocation_id,decision_cycle_id,bundle_id,payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?)",
        (
            request.invocation_id,
            bundle.decision_cycle_id,
            bundle_id,
            canonical_bytes(request_payload).decode("utf-8"),
            sha256_json(request_payload),
            utc_now(),
        ),
    )

    for index, event in enumerate(outcome.transcript):
        payload = {
            "decision_cycle_id": bundle.decision_cycle_id,
            "invocation_id": request.invocation_id,
            "round": event.get("round"),
            "event_type": event.get("type"),
            "event": event.get("payload"),
        }
        db.execute(
            "INSERT INTO autonomous_research_events(event_id,decision_cycle_id,invocation_id,round_index,event_type,payload_json,payload_sha256,created_at_utc) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                str(new_uuid7()),
                bundle.decision_cycle_id,
                request.invocation_id,
                int(event.get("round") or index + 1),
                str(event.get("type") or "unknown"),
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                utc_now(),
            ),
        )
    final_payload = _canonical_result_payload(bundle, request, outcome)
    final_encoded = canonical_bytes(final_payload).decode("utf-8")
    final_hash = sha256_json(final_payload)
    db.execute(
        "INSERT INTO autonomous_research_events(event_id,decision_cycle_id,invocation_id,round_index,event_type,payload_json,payload_sha256,created_at_utc) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            str(new_uuid7()),
            bundle.decision_cycle_id,
            request.invocation_id,
            outcome.rounds,
            "final_outcome",
            final_encoded,
            final_hash,
            utc_now(),
        ),
    )
    db.execute(
        "INSERT INTO trader_results(result_id,invocation_id,decision_cycle_id,accepted,accepted_cycle_key,payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
        (
            str(new_uuid7()),
            request.invocation_id,
            bundle.decision_cycle_id,
            1 if outcome.accepted else 0,
            bundle.decision_cycle_id if outcome.accepted else None,
            final_encoded,
            final_hash,
            utc_now(),
        ),
    )


def persist_interference_observation(
    db: Database,
    *,
    bundle: TraderInputBundle,
    request: InvocationRequest,
    outcome: Any,
    observation: dict[str, Any],
) -> None:
    payload = {
        "decision_cycle_id": bundle.decision_cycle_id,
        "invocation_id": request.invocation_id,
        "observation": observation,
    }
    db.execute(
        "INSERT INTO autonomous_research_events(event_id,decision_cycle_id,invocation_id,round_index,event_type,payload_json,payload_sha256,created_at_utc) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            str(new_uuid7()),
            bundle.decision_cycle_id,
            request.invocation_id,
            int(outcome.rounds),
            "interference_observation",
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            utc_now(),
        ),
    )


def run_autonomous_cycle(
    bundle: TraderInputBundle,
    *,
    model: str = "gpt-5.6-sol",
    reasoning_effort: str = "max",
    experiment_id: str = "ibkr-paper-30d",
    timeout_seconds: int = 180,
    trigger: str = "SCHEDULED_SCAN",
    options_level: int | None = 4,
    execute_paper: bool = False,
    database: Database | None = None,
    provider: Any | None = None,
    toolbox: Any | None = None,
    executor: Any | None = None,
    provider_lifecycle: Any | None = None,
    broker_time_reader: Any | None = None,
    continuity_store: Any | None = None,
    continuity_review_gate: Any | None = None,
) -> dict[str, Any]:
    if execute_paper and database is None:
        raise ValueError("paper execution requires persistent experiment database")
    if execute_paper and executor is None:
        raise ValueError(
            "paper execution requires an explicitly safety-bound executor"
        )

    if continuity_store is not None:
        pending_context = [
            {
                **report,
                "report_sha256": sha256_json(report),
                "trust": "FACTUAL_HASH_BOUND",
            }
            for report in continuity_store.pending_reports()
        ]
        continuity_context = dict(bundle.continuity_context or {})
        continuity_context["pending_reports"] = pending_context
        bundle = bundle.model_copy(
            update={"continuity_context": continuity_context}
        )

    request = build_request(
        bundle,
        model=model,
        reasoning_effort=reasoning_effort,
        experiment_id=experiment_id,
        timeout_seconds=timeout_seconds,
        trigger=trigger,
    )
    toolbox = toolbox or IBKRResearchToolbox(declared_options_level=options_level)
    provider = provider or CodexAutonomousCLIProvider()
    if database is not None and not getattr(
        provider, "_autonomy_bootstrap_initialized", False
    ):
        bootstrap = AutonomyBootstrapBuilder(database).build(
            bundle=bundle,
            toolbox=toolbox,
            execute_paper=execute_paper,
        )
        installer = getattr(provider, "install_first_process_bootstrap", None)
        if callable(installer):
            installer(bootstrap)
        else:
            provider.first_process_bootstrap = bootstrap
        provider._autonomy_bootstrap_initialized = True
    workspace_summary = getattr(toolbox, "workspace_summary", None)
    if callable(workspace_summary):
        context = workspace_summary()
        if context is not None:
            provider.workspace_context = context
    lifecycle_token = None
    if provider_lifecycle is not None:
        if not callable(broker_time_reader):
            raise ValueError("provider lifecycle requires broker_time_reader")
        lifecycle_token = provider_lifecycle.begin(request, broker_time_reader())
    try:
        outcome = AutonomousResearchLoop(provider, toolbox).run(request, bundle)
    except TimeoutError:
        if lifecycle_token is not None:
            provider_lifecycle.fail(
                lifecycle_token, "PROVIDER_TIMEOUT", broker_time_reader()
            )
        raise
    except Exception:
        if lifecycle_token is not None:
            provider_lifecycle.fail(
                lifecycle_token, "PROVIDER_PROCESS_ERROR", broker_time_reader()
            )
        raise

    if outcome.continuity_reviews:
        core_payload = _canonical_result_payload(
            bundle, request, outcome, continuity_reviews=()
        )
        accepted_result_core_sha256 = sha256_json(core_payload)
        outcome = outcome.model_copy(
            update={
                "continuity_reviews": tuple(
                    review.model_copy(
                        update={
                            "invocation_id": request.invocation_id,
                            "accepted_result_sha256": accepted_result_core_sha256,
                        }
                    )
                    for review in outcome.continuity_reviews
                )
            }
        )

    continuity_authority = None
    if database is not None:
        persist_outcome(database, bundle, request, outcome)
        durable_result = database.execute(
            "SELECT payload_sha256 FROM trader_results WHERE invocation_id=?",
            (request.invocation_id,),
        ).fetchone()
        if durable_result is None:
            raise RuntimeError("TRADER_RESULT_NOT_DURABLE")
        if lifecycle_token is not None:
            provider_lifecycle.complete(
                lifecycle_token,
                "COMPLETED_ACCEPTED"
                if outcome.accepted
                else "COMPLETED_UNACCEPTED",
                broker_time_reader(),
                result_sha256=str(durable_result[0]),
            )
        if (
            continuity_store is not None
            and outcome.accepted
            and outcome.continuity_plan is not None
        ):
            intent = outcome.proposal or outcome.open_order_action
            continuity_store.append_plan_event(
                "VALIDATED",
                outcome.continuity_plan,
                event_id=(
                    f"continuity-validated:{request.invocation_id}:"
                    f"{outcome.continuity_plan.plan_id}"
                ),
                bindings={
                    "invocation_id": request.invocation_id,
                    "input_bundle_sha256": bundle.sha256,
                    "result_sha256": str(durable_result[0]),
                    "intent_sha256": None if intent is None else sha256_json(intent),
                    "epoch_id": outcome.continuity_plan.epoch_id,
                    "clock_event_sha256": outcome.continuity_plan.clock_event_sha256,
                    "owner_authorization_sha256": (
                        outcome.continuity_plan.owner_authorization_sha256
                    ),
                    "model_attestation_sha256": (
                        outcome.continuity_plan.model_attestation_sha256
                    ),
                },
            )
        if continuity_store is not None:
            review_gate = continuity_review_gate or ContinuityReviewGate(
                continuity_store
            )
            accepted_plan_sha256 = (
                outcome.continuity_plan.sha256
                if outcome.continuity_plan is not None
                else None
            )
            for review in outcome.continuity_reviews:
                review_gate.persist_review(
                    review, accepted_plan_sha256=accepted_plan_sha256
                )
            continuity_authority = review_gate.authorize(
                outcome,
                continuity_store.pending_reports(),
                bundle.reconciliation_receipt,
                bundle=bundle,
            )

    execution = None
    post_execution_subledger = None
    if (
        execute_paper
        and outcome.accepted
        and continuity_authority is not None
        and not continuity_authority.authorized
    ):
        execution = PaperExecutionResult(
            success=False,
            status="BLOCKED",
            reason_codes=continuity_authority.reason_codes,
            order={},
            broker_validation={},
        )
    elif execute_paper and outcome.accepted:
        assert executor is not None
        if outcome.decision == TraderDecision.PROPOSE_TRADE and outcome.proposal is not None:
            if outcome.continuity_plan is None:
                execution = executor.execute(outcome.proposal, bundle)
            else:
                execution = executor.execute(
                    outcome.proposal,
                    bundle,
                    continuity_plan=outcome.continuity_plan,
                    invocation_id=request.invocation_id,
                )
        elif outcome.decision in {TraderDecision.REDUCE_POSITION, TraderDecision.CLOSE_POSITION} and outcome.position_action is not None:
            execution = executor.execute_position_action(
                outcome.position_action,
                bundle,
                outcome.decision,
            )
        elif (
            outcome.decision
            in {TraderDecision.CANCEL_ORDER, TraderDecision.MODIFY_ORDER}
            and outcome.open_order_action is not None
        ):
            execution = executor.execute_open_order_action(
                outcome.open_order_action,
                bundle,
                outcome.decision,
                invocation_id=request.invocation_id,
            )

    if execution is not None and database is not None:
        ledger = AutonomousExperimentLedger(
            database,
            allocation=Decimal(
                str(bundle.experiment_subledger_snapshot.get("allocation", "500.00"))
            ),
        )
        ledger.record_execution_result(execution)
        projected = ledger.project()
        post_execution_subledger = {
            "cash": str(projected.cash),
            "market_value": str(projected.market_value),
            "equity": str(projected.equity),
            "high_water_mark": str(projected.high_water_mark),
            "drawdown": str(projected.drawdown),
            "fees": str(projected.fees),
            "event_count": projected.event_count,
            "valid": projected.valid,
            "reason_codes": list(projected.reason_codes),
        }
        # Observational risk diagnostics from the real ledger projection.
        # Analytical failures are noted and never affect the cycle; the
        # persistence itself is structural and must propagate its errors.
        canonical_fills = ledger.canonical_fill_events()
        try:
            diagnostics = build_risk_diagnostics(
                projected,
                fills=canonical_fills if canonical_fills else None,
            )
        except Exception as exc:
            diagnostics = None
            persist_analytical_failure(
                database,
                stage="risk_diagnostics",
                error_class=type(exc).__name__,
                decision_cycle_id=bundle.decision_cycle_id,
            )
        if diagnostics is not None:
            persist_risk_diagnostics(
                database,
                decision_cycle_id=bundle.decision_cycle_id,
                invocation_id=request.invocation_id,
                rounds=outcome.rounds,
                diagnostics=diagnostics,
            )

    execution_payload = None if execution is None else {
        "success": execution.success,
        "status": execution.status,
        "reason_codes": list(execution.reason_codes),
        "order": execution.order,
        "broker_validation": execution.broker_validation,
    }
    outcome_payload = outcome.model_dump(mode="json")
    interference = build_interference_observation(
        outcome=outcome_payload,
        execution=execution_payload,
        execute_paper=execute_paper,
        provider_failure_code=getattr(provider, "last_failure_code", None),
    )
    if database is not None:
        persist_interference_observation(
            database,
            bundle=bundle,
            request=request,
            outcome=outcome,
            observation=interference,
        )

    if database is not None:
        _observe_regrets_and_outcomes(
            database,
            bundle=bundle,
            request=request,
            outcome=outcome,
            interference=interference,
        )

    return {
        "schema": "CODEX_IBKR_AUTONOMOUS_CYCLE_V1",
        "request": request.model_dump(mode="json"),
        "outcome": outcome_payload,
        "post_execution_subledger": post_execution_subledger,
        "execution": execution_payload,
        "interference": interference,
        "continuity_authority": (
            None
            if continuity_authority is None
            else continuity_authority.model_dump(mode="json")
        ),
    }


def _observe_regrets_and_outcomes(
    database: Database,
    *,
    bundle: TraderInputBundle,
    request: InvocationRequest,
    outcome: Any,
    interference: dict[str, Any],
) -> None:
    """Observational regret wiring. Strictly non-authoritative.

    Extracts regret observations for identifiable rejected proposals and
    resolves pending regrets against evidence already observed in this
    cycle's transcript. Only the analysis steps are fail-open (sanitized
    note); structural reads and persistence errors propagate. This never
    touches decisions, risk, sizing, authorization or execution.
    """

    pending = load_pending_regret_records(database)
    known_outcome_keys = load_regret_outcome_source_keys(database)

    try:
        new_regrets = extract_regret_observations(
            outcome,
            rejection_mechanism=str(interference.get("interference_source") or ""),
            decision_cycle_id=bundle.decision_cycle_id,
        )
    except Exception as exc:
        new_regrets = []
        persist_analytical_failure(
            database,
            stage="regret_extraction",
            error_class=type(exc).__name__,
            decision_cycle_id=bundle.decision_cycle_id,
        )

    persisted_regret_keys: set[str] = set()
    for row in database.execute(
        "SELECT payload_json FROM autonomous_research_events "
        "WHERE event_type='regret_observation'"
    ).fetchall():
        payload = json.loads(str(row[0]))
        observation = payload.get("observation") if isinstance(payload, dict) else None
        if not isinstance(observation, dict):
            continue
        candidate = observation.get("candidate") or {}
        persisted_regret_keys.add(
            "{cycle}:{symbol}:{sec}".format(
                cycle=str(observation.get("decision_cycle_id") or ""),
                symbol=str(candidate.get("symbol") or "").upper(),
                sec=str(candidate.get("sec_type") or ""),
            )
        )

    for record in new_regrets:
        candidate = record.get("candidate") or {}
        key = "{cycle}:{symbol}:{sec}".format(
            cycle=str(record.get("decision_cycle_id") or ""),
            symbol=str(candidate.get("symbol") or "").upper(),
            sec=str(candidate.get("sec_type") or ""),
        )
        if key in persisted_regret_keys:
            continue
        persist_regret_record(database, record)
        persisted_regret_keys.add(key)
        pending.append(record)

    try:
        matches = match_post_outcome_observations(
            pending,
            outcome.transcript,
            current_cycle_id=bundle.decision_cycle_id,
        )
    except Exception as exc:
        matches = []
        persist_analytical_failure(
            database,
            stage="regret_outcome_matching",
            error_class=type(exc).__name__,
            decision_cycle_id=bundle.decision_cycle_id,
        )

    resolved_this_pass: set[str] = set()
    for match in matches:
        regret_record_id = str(match.get("regret_record_id") or "")
        if regret_record_id in resolved_this_pass:
            continue
        source_key = "{record}:{source}".format(
            record=regret_record_id,
            source=str(match.get("source_event_sha256") or ""),
        )
        if source_key in known_outcome_keys:
            continue
        persist_regret_outcome(database, match)
        known_outcome_keys.add(source_key)
        resolved_this_pass.add(regret_record_id)


class AutonomousTraderBoundary:
    """Adapter compatible with PaperOrchestrator.TraderBoundary."""

    def __init__(
        self,
        *,
        model: str = "gpt-5.6-sol",
        reasoning_effort: str = "max",
        experiment_id: str = "ibkr-paper-30d",
        timeout_seconds: int = 180,
        options_level: int | None = 4,
        execute_paper: bool = False,
        database: Database | None = None,
        provider: Any | None = None,
        toolbox: Any | None = None,
        executor: Any | None = None,
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.experiment_id = experiment_id
        self.timeout_seconds = timeout_seconds
        self.options_level = options_level
        self.execute_paper = execute_paper
        self.database = database
        self.provider = provider
        self.toolbox = toolbox
        self.executor = executor

    def invoke(self, trigger: str, bundle: object) -> dict[str, Any]:
        typed_bundle = (
            bundle
            if isinstance(bundle, TraderInputBundle)
            else TraderInputBundle.model_validate(bundle)
        )
        return run_autonomous_cycle(
            typed_bundle,
            model=self.model,
            reasoning_effort=self.reasoning_effort,
            experiment_id=self.experiment_id,
            timeout_seconds=self.timeout_seconds,
            trigger=trigger,
            options_level=self.options_level,
            execute_paper=self.execute_paper,
            database=self.database,
            provider=self.provider,
            toolbox=self.toolbox,
            executor=self.executor,
        )


def _load_bundle(path: Path) -> TraderInputBundle:
    return TraderInputBundle.model_validate(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ibkr_paper_30d.autonomous_runtime")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=Path("state/ibkr_paper_30d/autonomous.sqlite3"))
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="max")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--trigger", default="SCHEDULED_SCAN")
    parser.add_argument("--options-level", type=int, default=4)
    parser.add_argument("--execute-paper", action="store_true")
    args = parser.parse_args(argv)

    bundle = _load_bundle(args.bundle)
    with Database.open(args.db) as db:
        result = run_autonomous_cycle(
            bundle,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            timeout_seconds=args.timeout_seconds,
            trigger=args.trigger,
            options_level=args.options_level,
            execute_paper=args.execute_paper,
            database=db,
        )
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
