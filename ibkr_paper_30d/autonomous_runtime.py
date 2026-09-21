from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .autonomous_execution import AutonomousPaperExecutor
from .autonomous_research import AutonomousResearchLoop, CodexAutonomousCLIProvider
from .canonical import canonical_bytes, sha256_json
from .experiment_ledger import AutonomousExperimentLedger
from .ibkr_research_tools import IBKRResearchToolbox
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
    final_payload = {
        "decision_cycle_id": bundle.decision_cycle_id,
        "invocation_id": request.invocation_id,
        "accepted": outcome.accepted,
        "validation": outcome.validation,
        "decision": outcome.decision.value,
        "proposal": None if outcome.proposal is None else outcome.proposal.model_dump(mode="json"),
        "position_action": None if outcome.position_action is None else outcome.position_action.model_dump(mode="json"),
        "reason_codes": list(outcome.reason_codes),
        "rounds": outcome.rounds,
        "transcript_sha256": outcome.transcript_sha256,
        "broker_validation": outcome.broker_validation,
    }
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
) -> dict[str, Any]:
    if execute_paper and database is None:
        raise ValueError("paper execution requires persistent experiment database")
    if execute_paper and executor is None:
        raise ValueError(
            "paper execution requires an explicitly safety-bound executor"
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
    outcome = AutonomousResearchLoop(provider, toolbox).run(request, bundle)

    if database is not None:
        persist_outcome(database, bundle, request, outcome)

    execution = None
    post_execution_subledger = None
    if execute_paper and outcome.accepted:
        assert executor is not None
        if outcome.decision == TraderDecision.PROPOSE_TRADE and outcome.proposal is not None:
            execution = executor.execute(outcome.proposal, bundle)
        elif outcome.decision in {TraderDecision.REDUCE_POSITION, TraderDecision.CLOSE_POSITION} and outcome.position_action is not None:
            execution = executor.execute_position_action(
                outcome.position_action,
                bundle,
                outcome.decision,
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

    return {
        "schema": "CODEX_IBKR_AUTONOMOUS_CYCLE_V1",
        "request": request.model_dump(mode="json"),
        "outcome": outcome.model_dump(mode="json"),
        "post_execution_subledger": post_execution_subledger,
        "execution": None if execution is None else {
            "success": execution.success,
            "status": execution.status,
            "reason_codes": list(execution.reason_codes),
            "order": execution.order,
            "broker_validation": execution.broker_validation,
        },
    }


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
