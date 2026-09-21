from __future__ import annotations

import argparse
import json
import os
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from .autonomous_execution import AutonomousPaperExecutor
from .autonomous_research import CodexAutonomousCLIProvider
from .autonomous_runtime import run_autonomous_cycle
from .autonomous_state import AutonomousStateBuilder
from .experiment_ledger import AutonomousExperimentLedger
from .ibkr_research_tools import IBKRResearchToolbox
from .persistence import Database


def current_kill_switch_state(db: Database) -> str:
    row = db.execute(
        "SELECT state FROM kill_switch_events ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    if row is not None:
        return str(row[0])
    configured = os.environ.get("IBKR_AUTONOMOUS_KILL_SWITCH", "").upper()
    return "KILL_SWITCH_CLEAR" if configured == "CLEAR" else "KILL_SWITCH_TRIGGERED"


class AutonomousExperimentService:
    """Continuous capital-adaptive 30-day paper experiment service.

    Discovery cadence and position-management cadence are operational clocks,
    not mandatory trade frequency. Codex can always choose NO_TRADE or
    MONITOR_POSITION.
    """

    def __init__(
        self,
        db: Database,
        *,
        experiment_start_utc: datetime,
        allocation: Decimal = Decimal("500.00"),
        duration_days: int = 30,
        scan_interval_seconds: float = 300.0,
        position_interval_seconds: float = 60.0,
        model: str = "gpt-5.5",
        reasoning_effort: str = "high",
        timeout_seconds: int = 180,
        options_level: int | None = 4,
        execute_paper: bool = False,
        toolbox: Any | None = None,
        provider: Any | None = None,
        executor: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if scan_interval_seconds < 60:
            raise ValueError("scan cadence below 60 seconds is unsupported")
        if position_interval_seconds < 60:
            raise ValueError("position cadence below 60 seconds is unsupported")
        self.db = db
        self.experiment_start_utc = experiment_start_utc
        self.allocation = allocation
        self.duration_days = duration_days
        self.scan_interval_seconds = scan_interval_seconds
        self.position_interval_seconds = position_interval_seconds
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds
        self.options_level = options_level
        self.execute_paper = execute_paper
        self.toolbox = toolbox or IBKRResearchToolbox(
            declared_options_level=options_level
        )
        self.provider = provider or CodexAutonomousCLIProvider()
        self.executor = executor or AutonomousPaperExecutor(self.toolbox)
        self.sleep = sleep
        self.monotonic = monotonic
        self.stop_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def _builder(self) -> AutonomousStateBuilder:
        return AutonomousStateBuilder(
            self.db,
            self.toolbox,
            allocation=self.allocation,
            experiment_start_utc=self.experiment_start_utc,
            duration_days=self.duration_days,
            kill_switch_state=current_kill_switch_state(self.db),
        )

    def _run_cycle(self, trigger: str) -> dict[str, Any]:
        bundle = self._builder().build(trigger=trigger)
        if bundle.experiment_clock.get("expired"):
            return {
                "schema": "CODEX_IBKR_AUTONOMOUS_SERVICE_CYCLE_V1",
                "status": "EXPERIMENT_EXPIRED",
                "bundle": bundle.model_dump(mode="json"),
            }
        if bundle.market_data_snapshot.get("gate_status") != "PASS":
            return {
                "schema": "CODEX_IBKR_AUTONOMOUS_SERVICE_CYCLE_V1",
                "status": "STATE_GATE_BLOCK",
                "bundle": bundle.model_dump(mode="json"),
            }
        return run_autonomous_cycle(
            bundle,
            model=self.model,
            reasoning_effort=self.reasoning_effort,
            timeout_seconds=self.timeout_seconds,
            trigger=trigger,
            options_level=self.options_level,
            execute_paper=self.execute_paper,
            database=self.db,
            provider=self.provider,
            toolbox=self.toolbox,
            executor=self.executor,
        )

    def run_once(self, trigger: str = "SCHEDULED_SCAN") -> dict[str, Any]:
        return self._run_cycle(trigger)

    def run_forever(self) -> None:
        next_scan = self.monotonic()
        next_position = self.monotonic()
        while not self.stop_event.is_set():
            projected = AutonomousExperimentLedger(
                self.db, allocation=self.allocation
            ).project()
            if projected.equity <= 0:
                return

            now = self.monotonic()
            has_positions = bool(projected.positions)
            trigger = None
            if has_positions and now >= next_position:
                trigger = "POSITION_EVENT"
                next_position = now + self.position_interval_seconds
            elif now >= next_scan:
                trigger = "SCHEDULED_SCAN"
                next_scan = now + self.scan_interval_seconds

            if trigger is None:
                waits = [max(0.0, next_scan - now)]
                if has_positions:
                    waits.append(max(0.0, next_position - now))
                self.sleep(min(waits))
                continue

            result = self._run_cycle(trigger)
            status = str(result.get("status") or "")
            if status == "EXPERIMENT_EXPIRED":
                return
            if status == "STATE_GATE_BLOCK":
                self.sleep(min(self.position_interval_seconds, self.scan_interval_seconds))
                continue

            execution = result.get("execution") or {}
            fills = (execution.get("order") or {}).get("fills", []) or []
            if fills and not self.stop_event.is_set():
                # Immediate post-fill re-evaluation. This is monitoring, not an
                # instruction to trade again.
                follow_up = self._run_cycle("POSITION_EVENT")
                if str(follow_up.get("status") or "") == "EXPERIMENT_EXPIRED":
                    return


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("start time must include timezone")
    return parsed.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ibkr_paper_30d.autonomous_service"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("state/ibkr_paper_30d/autonomous.sqlite3"),
    )
    parser.add_argument("--start-utc", required=True)
    parser.add_argument("--allocation", default="500.00")
    parser.add_argument("--duration-days", type=int, default=30)
    parser.add_argument("--scan-seconds", type=float, default=300)
    parser.add_argument("--position-seconds", type=float, default=60)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--options-level", type=int, default=4)
    parser.add_argument("--execute-paper", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)

    with Database.open(args.db) as db:
        service = AutonomousExperimentService(
            db,
            experiment_start_utc=_parse_utc(args.start_utc),
            allocation=Decimal(args.allocation),
            duration_days=args.duration_days,
            scan_interval_seconds=args.scan_seconds,
            position_interval_seconds=args.position_seconds,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            timeout_seconds=args.timeout_seconds,
            options_level=args.options_level,
            execute_paper=args.execute_paper,
        )
        if args.once:
            result = service.run_once()
            print(json.dumps(result, sort_keys=True, default=str))
            return 0
        service.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
