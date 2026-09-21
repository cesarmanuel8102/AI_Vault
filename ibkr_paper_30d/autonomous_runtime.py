from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .autonomous_execution import AutonomousPaperExecutor
from .autonomous_research import AutonomousResearchLoop, CodexAutonomousCLIProvider
from .canonical import canonical_bytes, sha256_json
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
        "reason_codes": list(outcome.reason_codes),
        "rounds": outcome.rounds,
        "transcript_sha256": outcome.transcript_sha256,
        "broker_validation": outcome.broker_validation,
    }
    db.execute(
        "INSERT INTO autonomous_research_events(event_id,decision_cycle_id,invocation_id,round_index,event_type,payload_json,payload_sha256,created_at_utc) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            str(new_uuid7()),
            bundle.decision_cycle_id,
            request.invocation_id,
            outcome.rounds,
            "final_outcome",
            canonical_bytes(final_payload).decode("utf-8"),
            sha256_json(final_payload),
            utc_now(),
        ),
    )


def run_autonomous_cycle(
    bundle: TraderInputBundle,
    *,
    model: str = "gpt-5.5",
    reasoning_effort: str = "high",
    experiment_id: str = "ibkr-paper-30d",
    timeout_seconds: int = 180,
    trigger: str = "SCHEDULED_SCAN",
    options_level: int | None = 4,
    execute_paper: bool = False,
    database: Database | None = None,
) -> dict[str, Any]:
    request = build_request(
        bundle,
        model=model,
        reasoning_effort=reasoning_effort,
        experiment_id=experiment_id,
        timeout_seconds=timeout_seconds,
        trigger=trigger,
    )
    toolbox = IBKRResearchToolbox(declared_options_level=options_level)
    provider = CodexAutonomousCLIProvider()
    outcome = AutonomousResearchLoop(provider, toolbox).run(request, bundle)

    if database is not None:
        persist_outcome(database, bundle, request, outcome)

    execution = None
    if execute_paper and outcome.accepted and outcome.decision == TraderDecision.PROPOSE_TRADE:
        executor = AutonomousPaperExecutor(toolbox)
        execution = executor.execute(outcome.proposal, bundle)

    return {
        "schema": "CODEX_IBKR_AUTONOMOUS_CYCLE_V1",
        "request": request.model_dump(mode="json"),
        "outcome": outcome.model_dump(mode="json"),
        "execution": None if execution is None else {
            "success": execution.success,
            "status": execution.status,
            "reason_codes": list(execution.reason_codes),
            "order": execution.order,
            "broker_validation": execution.broker_validation,
        },
    }


def _load_bundle(path: Path) -> TraderInputBundle:
    return TraderInputBundle.model_validate(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ibkr_paper_30d.autonomous_runtime")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=Path("state/ibkr_paper_30d/autonomous.sqlite3"))
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning-effort", default="high")
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
