from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
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
from .autonomy_toolbox import AutonomyToolbox
from .autonomy_workspace import AutonomyWorkspace
from .canonical import canonical_bytes, sha256_json
from .experiment_control import (
    ExperimentClock,
    ExperimentClockStore,
    KillSwitchStore,
    OwnerAuthorizationStore,
)
from .successor_authorization import (
    SuccessorAuthorizationError,
    validate_successor_authorization_record,
)
from .successor_clock import clock_for_epoch
from .experiment_epoch import ExperimentEpochStore
from .experiment_ledger import AutonomousExperimentLedger
from .ibkr_research_tools import IBKRResearchToolbox
from .market_data import DecisionClass
from .persistence import Database
from .repositories import EventRepository, utc_now
from .research_sandbox import WSLResearchSandbox
from .runtime_integrity import RuntimeAuditorGate, RuntimeMarketDataGate
from .trader_invocation import TraderDecision
from .types import new_uuid7


class AutonomousServiceError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        reason_codes: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.reason_codes = reason_codes


OPERATIONAL_DECISIONS = frozenset(
    {
        "NO_TRADE",
        "PROPOSE_TRADE",
        "CANCEL_ORDER",
        "MODIFY_ORDER",
        "MONITOR_POSITION",
        "REDUCE_POSITION",
        "CLOSE_POSITION",
    }
)


def _append_alert(db: Database, event_type: str, payload: dict[str, Any]) -> None:
    body = {
        "schema": "AUTONOMOUS_SERVICE_ALERT_V1",
        "event_type": event_type,
        "created_at_utc": utc_now(),
        **payload,
    }
    db.execute(
        "INSERT INTO alerts(alert_id,event_type,payload_json,payload_sha256,created_at_utc) "
        "VALUES(?,?,?,?,?)",
        (
            str(new_uuid7()),
            event_type,
            canonical_bytes(body).decode("utf-8"),
            sha256_json(body),
            utc_now(),
        ),
    )


def _append_state_event(db: Database, event_type: str, payload: dict[str, Any]) -> None:
    body = {
        "schema": "AUTONOMOUS_SERVICE_STATE_EVENT_V1",
        "event_type": event_type,
        "created_at_utc": utc_now(),
        **payload,
    }
    EventRepository(db).append(event_type, body)


class AutonomousExperimentService:
    """Continuous capital-adaptive 30-day PAPER experiment service.

    Discovery and position cadences are observation/reasoning clocks, never a
    requirement to trade. Every executable action is gated again immediately
    before broker transmission.
    """

    def __init__(
        self,
        db: Database,
        *,
        experiment_start_utc: datetime | None,
        experiment_clock: ExperimentClock | None = None,
        successor_owner_authorization_receipt: dict[str, Any] | None = None,
        successor_owner_sid: str | None = None,
        allocation: Decimal = Decimal("500.00"),
        duration_days: int = 30,
        scan_interval_seconds: float = 300.0,
        position_interval_seconds: float = 60.0,
        model: str = "gpt-5.6-sol",
        reasoning_effort: str = "max",
        timeout_seconds: int = 180,
        options_level: int | None = 4,
        execute_paper: bool = False,
        toolbox: Any | None = None,
        provider: Any | None = None,
        executor: Any | None = None,
        runtime_market_gate: RuntimeMarketDataGate | None = None,
        runtime_auditor_gate: RuntimeAuditorGate | None = None,
        broker_now: Callable[[], datetime] | None = None,
        launch_attempt_id: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if scan_interval_seconds < 60:
            raise ValueError("scan cadence below 60 seconds is unsupported")
        if position_interval_seconds < 60:
            raise ValueError("position cadence below 60 seconds is unsupported")
        if model != "gpt-5.6-sol":
            raise ValueError("autonomous experiment requires gpt-5.6-sol")
        if reasoning_effort.lower() != "max":
            raise ValueError("autonomous experiment requires max reasoning effort")

        self.db = db
        self.allocation = allocation
        self.duration_days = duration_days
        if experiment_clock is None:
            self.clock = ExperimentClockStore(db).initialize_or_load(
                requested_start_utc=experiment_start_utc,
                duration_days=duration_days,
                initial_allocation=allocation,
            )
        else:
            if (
                experiment_clock.epoch_id is None
                or experiment_start_utc != experiment_clock.start_utc
                or experiment_clock.duration_days != duration_days
                or experiment_clock.initial_allocation != allocation
                or clock_for_epoch(db, experiment_clock.epoch_id).event_sha256
                != experiment_clock.event_sha256
            ):
                raise AutonomousServiceError("SUCCESSOR_CLOCK_BINDING_MISMATCH")
            self.clock = experiment_clock
        self.successor_owner_authorization_receipt = (
            successor_owner_authorization_receipt
        )
        self.successor_owner_sid = successor_owner_sid
        self.epoch_store = ExperimentEpochStore(db)
        self.epoch_state = self.epoch_store.projection(datetime.now(timezone.utc))
        self.experiment_start_utc = self.clock.start_utc
        self.scan_interval_seconds = scan_interval_seconds
        self.position_interval_seconds = position_interval_seconds
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds
        self.options_level = options_level
        self.execute_paper = execute_paper
        base_toolbox = toolbox or IBKRResearchToolbox(
            declared_options_level=options_level
        )
        workspace_root = Path(
            os.environ.get(
                "IBKR_AUTONOMY_WORKSPACE_ROOT",
                "state/ibkr_paper_30d/autonomy_workspace",
            )
        )
        self.workspace = AutonomyWorkspace(
            workspace_root,
            sandbox=WSLResearchSandbox(repo_root=Path(__file__).resolve().parents[1]),
        )
        self.toolbox = (
            base_toolbox
            if isinstance(base_toolbox, AutonomyToolbox)
            else AutonomyToolbox(base_toolbox, self.workspace)
        )
        self.broker_now = broker_now or self._read_broker_time
        self.launch_attempt_id = launch_attempt_id
        self._running_event_emitted = False
        self._service_started_at_utc: datetime | None = None
        expected_hash = getattr(self.toolbox, "expected_account_hash", None)
        self.runtime_market_gate = runtime_market_gate or (
            RuntimeMarketDataGate(
                expected_account_hash=expected_hash,
                now_utc=self.broker_now,
            )
            if expected_hash
            else None
        )
        self.runtime_auditor_gate = runtime_auditor_gate or RuntimeAuditorGate(
            now_utc=self.broker_now
        )
        self.kill_switch = KillSwitchStore(db)
        self.owner_authorization = OwnerAuthorizationStore(db)
        self.provider = provider or CodexAutonomousCLIProvider()
        self.executor = executor or AutonomousPaperExecutor(
            self.toolbox,
            database=db,
            fresh_safety_check=self._fresh_execution_safety,
            operator_control_check=self._fresh_operator_controls,
        )
        self.sleep = sleep
        self.monotonic = monotonic
        self.stop_event = threading.Event()

        if execute_paper:
            self._assert_arm_prerequisites()
        else:
            _append_alert(
                self.db,
                "PAPER_EXECUTION_UNARMED",
                {"message": "service started in observation/reasoning-only mode"},
            )

    def stop(self) -> None:
        self.stop_event.set()

    def _owner_authorization_is_current(self) -> bool:
        if self.clock.epoch_id is None:
            return (
                self.owner_authorization.current(
                    clock_event_sha256=self.clock.event_sha256
                )
                == "AUTHORIZED"
            )
        if (
            self.successor_owner_authorization_receipt is None
            or not self.successor_owner_sid
        ):
            return False
        try:
            current = self.epoch_store.current()
            if current is None or current.epoch_id != self.clock.epoch_id:
                return False
            validate_successor_authorization_record(
                db=self.db,
                epoch_id=self.clock.epoch_id,
                definition_sha256=current.definition_sha256,
                expected_actor_sid=self.successor_owner_sid,
                receipt=self.successor_owner_authorization_receipt,
            )
        except (SuccessorAuthorizationError, RuntimeError):
            return False
        return True

    def _read_broker_time(self) -> datetime:
        raw = self.toolbox.broker_server_time_utc()
        if not isinstance(raw, str) or not raw:
            raise AutonomousServiceError("broker server time unavailable")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AutonomousServiceError("broker server time invalid") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise AutonomousServiceError("broker server time invalid")
        return parsed.astimezone(timezone.utc)

    def _fresh_execution_safety(self, scope: str) -> tuple[str, ...]:
        reasons: list[str] = []
        try:
            broker_now = self.broker_now()
        except Exception:
            reasons.append("BROKER_TIME_UNAVAILABLE_FRESH")
            broker_now = None
        clock_snapshot = (
            self.clock.snapshot(broker_now)
            if broker_now is not None
            else {"not_started": True, "expired": True}
        )
        if clock_snapshot.get("not_started"):
            reasons.append("EXPERIMENT_NOT_STARTED_FRESH")
        if clock_snapshot.get("expired"):
            reasons.append("EXPERIMENT_EXPIRED_FRESH")
        if self.kill_switch.current() != "KILL_SWITCH_CLEAR":
            reasons.append("KILL_SWITCH_TRIGGERED_FRESH")
        if not self._owner_authorization_is_current():
            reasons.append("OWNER_AUTHORIZATION_REQUIRED_FRESH")
        auditor = self.runtime_auditor_gate.evaluate()
        if auditor.get("gate_status") != "PASS":
            reasons.append("AUDITOR_GATE_BLOCK_FRESH")
            reasons.extend(str(x) for x in auditor.get("reason_codes", []) or [])
        if self.runtime_market_gate is None:
            reasons.append("MARKET_DATA_GATE_UNAVAILABLE_FRESH")
        else:
            decision_class = (
                DecisionClass.OPEN_POSITION_MANAGEMENT
                if scope == "POSITION_MANAGEMENT"
                else DecisionClass.NEW_TRADE
            )
            market = self.runtime_market_gate.evaluate(decision_class)
            if market.get("gate_status") != "PASS":
                reasons.append("MARKET_DATA_GATE_BLOCK_FRESH")
                reasons.extend(str(x) for x in market.get("reason_codes", []) or [])
        return tuple(dict.fromkeys(reasons))

    def _fresh_operator_controls(self) -> tuple[str, ...]:
        """DB-only controls checked immediately before broker transmission."""
        reasons: list[str] = []
        if self.kill_switch.current() != "KILL_SWITCH_CLEAR":
            reasons.append("KILL_SWITCH_TRIGGERED_IMMEDIATE")
        if not self._owner_authorization_is_current():
            reasons.append("OWNER_AUTHORIZATION_REQUIRED_IMMEDIATE")
        return tuple(reasons)

    def _assert_arm_prerequisites(self) -> None:
        if not getattr(self.executor, "armed", False):
            raise AutonomousServiceError(
                "paper execution requested but IBKR_AUTONOMOUS_PAPER_ARMED is not true",
                reason_codes=("PAPER_EXECUTION_UNARMED",),
            )
        if not self._owner_authorization_is_current():
            raise AutonomousServiceError(
                "paper execution requires explicit owner authorization bound to this experiment clock",
                reason_codes=("OWNER_AUTHORIZATION_REQUIRED_FRESH",),
            )
        reasons = self._fresh_execution_safety("NEW_TRADE")
        if reasons:
            raise AutonomousServiceError(
                "paper execution prerequisites are not PASS: " + ",".join(reasons),
                reason_codes=reasons,
            )
        # Expiry/not-started is already evaluated from broker server time by
        # _fresh_execution_safety; do not reintroduce wall-clock authority here.

    def _builder(self) -> AutonomousStateBuilder:
        return AutonomousStateBuilder(
            self.db,
            self.toolbox,
            allocation=self.allocation,
            experiment_start_utc=self.experiment_start_utc,
            duration_days=self.duration_days,
            runtime_market_gate=self.runtime_market_gate,
        )

    def _run_cycle(
        self,
        trigger: str,
        *,
        allow_execution: bool | None = None,
    ) -> dict[str, Any]:
        auditor = self.runtime_auditor_gate.evaluate()
        if auditor.get("gate_status") != "PASS":
            return {
                "schema": "CODEX_IBKR_AUTONOMOUS_SERVICE_CYCLE_V2",
                "status": "STATE_GATE_BLOCK",
                "gate": "AUDITOR",
                "auditor": auditor,
            }

        bundle = self._builder().build(trigger=trigger)
        if bundle.experiment_clock.get("not_started"):
            return {
                "schema": "CODEX_IBKR_AUTONOMOUS_SERVICE_CYCLE_V2",
                "status": "EXPERIMENT_NOT_STARTED",
                "bundle": bundle.model_dump(mode="json"),
            }
        if bundle.experiment_clock.get("expired"):
            return {
                "schema": "CODEX_IBKR_AUTONOMOUS_SERVICE_CYCLE_V2",
                "status": "EXPERIMENT_EXPIRED",
                "bundle": bundle.model_dump(mode="json"),
            }
        state_reasons: list[str] = []
        if bundle.reconciliation_receipt.get("status") != "PASS":
            state_reasons.append("BROKER_RECONCILIATION_REQUIRED")
        if bundle.kill_switch_state != "KILL_SWITCH_CLEAR":
            state_reasons.append("KILL_SWITCH_TRIGGERED")
        if bundle.market_data_snapshot.get("gate_status") != "PASS":
            state_reasons.append("MARKET_DATA_GATE_BLOCK")
        if state_reasons:
            return {
                "schema": "CODEX_IBKR_AUTONOMOUS_SERVICE_CYCLE_V2",
                "status": "STATE_GATE_BLOCK",
                "reason_codes": state_reasons,
                "bundle": bundle.model_dump(mode="json"),
                "auditor": auditor,
            }

        execution_allowed = (
            self.execute_paper if allow_execution is None else bool(allow_execution)
        )
        try:
            result = run_autonomous_cycle(
                bundle,
                model=self.model,
                reasoning_effort=self.reasoning_effort,
                timeout_seconds=self.timeout_seconds,
                trigger=trigger,
                options_level=self.options_level,
                execute_paper=execution_allowed,
                database=self.db,
                provider=self.provider,
                toolbox=self.toolbox,
                executor=self.executor,
            )
        except Exception as exc:
            provider_failure_code = getattr(self.provider, "last_failure_code", None)
            if provider_failure_code:
                _append_alert(
                    self.db,
                    "AUTONOMOUS_PROVIDER_FAILURE_OBSERVATION",
                    {
                        "provider_failure_code": str(provider_failure_code),
                        "error_type": type(exc).__name__,
                        "provider_policy_attribution": "UNDETERMINED",
                        "provider_policy_visibility": "NOT_DIRECTLY_OBSERVABLE",
                    },
                )
            raise
        outcome = result.get("outcome") or {}
        if "status" not in result:
            result["status"] = (
                "PASS"
                if outcome.get("validation") == "PASS"
                and str(outcome.get("decision") or "") in OPERATIONAL_DECISIONS
                else "BLOCK"
            )
        result["auditor_gate"] = auditor
        return result

    def _handle_pause(self, result: dict[str, Any]) -> bool:
        outcome = result.get("outcome") or {}
        if str(outcome.get("decision") or "") != TraderDecision.PAUSE_FOR_REVIEW.value:
            return False
        self.kill_switch.set(
            "KILL_SWITCH_TRIGGERED",
            reason="Codex requested PAUSE_FOR_REVIEW",
            actor="codex",
        )
        _append_alert(
            self.db,
            "PAUSE_FOR_REVIEW",
            {
                "decision_cycle_id": (result.get("request") or {}).get(
                    "decision_cycle_id"
                ),
                "reason_codes": outcome.get("reason_codes", []),
            },
        )
        self.stop_event.set()
        return True

    def _terminal_event(self, reason: str) -> None:
        projected = AutonomousExperimentLedger(
            self.db, allocation=self.allocation
        ).project()
        _append_state_event(
            self.db,
            "EXPERIMENT_TERMINAL",
            {
                "reason": reason,
                "cash": str(projected.cash),
                "market_value": str(projected.market_value),
                "equity": str(projected.equity),
                "fees": str(projected.fees),
                "open_positions": [
                    {
                        "contract_id": item.contract_id,
                        "symbol": item.symbol,
                        "quantity": str(item.quantity),
                        "mark": str(item.mark),
                    }
                    for item in projected.positions
                ],
                "manual_close_required": bool(projected.positions),
            },
        )
        self.kill_switch.set(
            "KILL_SWITCH_TRIGGERED",
            reason=f"terminal experiment state: {reason}",
            actor="runtime",
        )

    @staticmethod
    def _needs_observation_only_refresh(result: dict[str, Any]) -> bool:
        execution = result.get("execution") or {}
        execution_order = execution.get("order") or {}
        if execution_order.get("fills", []) or []:
            return True
        order_management = str(execution_order.get("order_management") or "")
        if order_management not in {"CANCEL_ORDER", "MODIFY_ORDER"}:
            return False
        return bool(execution.get("success")) or str(execution.get("status") or "") in {
            "UNCERTAIN",
            "FILLED",
        }

    def _observation_only_follow_up(
        self, result: dict[str, Any]
    ) -> dict[str, Any] | None:
        if self.stop_event.is_set() or not self._needs_observation_only_refresh(result):
            return None
        return self._run_cycle_with_lifecycle("POSITION_EVENT", allow_execution=False)

    def _run_cycle_with_lifecycle(
        self,
        trigger: str,
        *,
        allow_execution: bool | None = None,
    ) -> dict[str, Any]:
        _append_state_event(
            self.db,
            "AUTONOMOUS_CYCLE_STARTED",
            {"trigger": trigger},
        )
        try:
            result = self._run_cycle(trigger, allow_execution=allow_execution)
        except Exception as exc:
            _append_state_event(
                self.db,
                "AUTONOMOUS_CYCLE_FAILED",
                {"trigger": trigger, "error_type": type(exc).__name__},
            )
            raise

        status = str(result.get("status") or "UNKNOWN")
        outcome = result.get("outcome") or {}
        decision = str(outcome.get("decision") or "UNKNOWN")
        request = result.get("request") or {}
        decision_cycle_id = str(request.get("decision_cycle_id") or "")
        _append_state_event(
            self.db,
            "AUTONOMOUS_CYCLE_COMPLETED",
            {
                "trigger": trigger,
                "status": status,
                "decision": decision,
                "decision_cycle_id": decision_cycle_id,
            },
        )
        if (
            not self._running_event_emitted
            and status == "PASS"
            and decision in OPERATIONAL_DECISIONS
        ):
            actual_start = self._service_started_at_utc or datetime.now(timezone.utc)
            delay_seconds = max(
                0.0, (actual_start - self.clock.start_utc).total_seconds()
            )
            _append_state_event(
                self.db,
                "AUTONOMOUS_PAPER_EXPERIMENT_RUNNING",
                {
                    "decision_cycle_id": decision_cycle_id,
                    "decision": decision,
                    "launch_attempt_id": self.launch_attempt_id or "",
                    "epoch_id": self.clock.epoch_id,
                    "definition_sha256": self.epoch_state.get("definition_sha256"),
                    "clock_event_sha256": self.clock.event_sha256,
                    "model": self.model,
                    "reasoning_effort": self.reasoning_effort,
                    "pid": os.getpid(),
                    "scheduled_start_utc": self.clock.start_utc,
                    "actual_service_start_utc": actual_start,
                    "delay_seconds": delay_seconds,
                },
            )
            self._running_event_emitted = True
        return result

    def run_once(self, trigger: str = "SCHEDULED_SCAN") -> dict[str, Any]:
        result = self._run_cycle_with_lifecycle(trigger)
        self._handle_pause(result)
        follow_up = self._observation_only_follow_up(result)
        if follow_up is not None:
            result["observation_only_follow_up"] = follow_up
            if str(follow_up.get("status") or "") == "EXPERIMENT_EXPIRED":
                self._terminal_event("CLOCK_EXPIRED")
            else:
                self._handle_pause(follow_up)
        return result

    def run_forever(self) -> None:
        self._service_started_at_utc = datetime.now(timezone.utc)
        _append_state_event(
            self.db,
            "AUTONOMOUS_SERVICE_STARTED",
            {
                "launch_attempt_id": self.launch_attempt_id or "",
                "epoch_id": self.clock.epoch_id,
                "definition_sha256": self.epoch_state.get("definition_sha256"),
                "clock_event_sha256": self.clock.event_sha256,
                "model": self.model,
                "reasoning_effort": self.reasoning_effort,
                "pid": os.getpid(),
                "scheduled_start_utc": self.clock.start_utc,
                "actual_service_start_utc": self._service_started_at_utc,
                "delay_seconds": max(
                    0.0,
                    (
                        self._service_started_at_utc - self.clock.start_utc
                    ).total_seconds(),
                ),
            },
        )
        next_scan = self.monotonic()
        next_position = self.monotonic()
        while not self.stop_event.is_set():
            try:
                projected = AutonomousExperimentLedger(
                    self.db, allocation=self.allocation
                ).project()
                if not projected.valid:
                    raise AutonomousServiceError(
                        "experiment ledger invalid: " + ",".join(projected.reason_codes)
                    )
                if projected.equity <= 0:
                    self._terminal_event("EQUITY_DEPLETED")
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

                result = self._run_cycle_with_lifecycle(trigger)
                status = str(result.get("status") or "")
                if status == "EXPERIMENT_NOT_STARTED":
                    self.sleep(
                        min(
                            self.position_interval_seconds,
                            self.scan_interval_seconds,
                        )
                    )
                    continue
                if status == "EXPERIMENT_EXPIRED":
                    self._terminal_event("CLOCK_EXPIRED")
                    return
                if self._handle_pause(result):
                    return
                if status == "STATE_GATE_BLOCK":
                    self.sleep(
                        min(
                            self.position_interval_seconds,
                            self.scan_interval_seconds,
                        )
                    )
                    continue

                follow_up = self._observation_only_follow_up(result)
                if follow_up is not None:
                    next_position = self.monotonic() + self.position_interval_seconds
                    if str(follow_up.get("status") or "") == "EXPERIMENT_EXPIRED":
                        self._terminal_event("CLOCK_EXPIRED")
                        return
                    if self._handle_pause(follow_up):
                        return
            except sqlite3.DatabaseError:
                _append_alert(
                    self.db,
                    "FATAL_DATABASE_ERROR",
                    {"message": "database integrity/runtime failure"},
                )
                raise
            except AutonomousServiceError as exc:
                _append_alert(
                    self.db,
                    "FATAL_AUTONOMOUS_STATE_ERROR",
                    {
                        "error_type": type(exc).__name__,
                        "message": str(exc)[:500],
                    },
                )
                raise
            except Exception as exc:
                try:
                    _append_alert(
                        self.db,
                        "RECOVERABLE_RUNTIME_ERROR",
                        {
                            "error_type": type(exc).__name__,
                            "message": str(exc)[:500],
                        },
                    )
                except Exception:
                    pass
                if getattr(self.provider, "last_failure_code", None):
                    retry_delay = min(
                        self.position_interval_seconds,
                        self.scan_interval_seconds,
                    )
                    self.sleep(retry_delay)
                    next_scan = self.monotonic()
                    next_position = self.monotonic()
                    continue
                raise


def _parse_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("start time must include timezone")
    return parsed.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ibkr_paper_30d.autonomous_service")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("state/ibkr_paper_30d/autonomous.sqlite3"),
    )
    parser.add_argument("--start-utc")
    parser.add_argument("--allocation", default="500.00")
    parser.add_argument("--duration-days", type=int, default=30)
    parser.add_argument("--scan-seconds", type=float, default=300)
    parser.add_argument("--position-seconds", type=float, default=60)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="max")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--options-level", type=int, default=4)
    parser.add_argument("--execute-paper", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--authorize-start", action="store_true")
    parser.add_argument("--revoke-start", action="store_true")
    parser.add_argument("--authorization-phrase")
    parser.add_argument(
        "--kill-switch",
        choices=("status", "clear", "trigger"),
    )
    parser.add_argument("--kill-reason", default="operator command")
    args = parser.parse_args(argv)

    with Database.open(args.db) as db:
        if args.kill_switch:
            store = KillSwitchStore(db)
            if args.kill_switch == "status":
                print(json.dumps({"kill_switch_state": store.current()}))
                return 0
            state = (
                "KILL_SWITCH_CLEAR"
                if args.kill_switch == "clear"
                else "KILL_SWITCH_TRIGGERED"
            )
            event_id = store.set(
                state,
                reason=args.kill_reason,
                actor="operator",
            )
            print(
                json.dumps(
                    {
                        "kill_switch_state": state,
                        "event_id": event_id,
                    },
                    sort_keys=True,
                )
            )
            return 0

        requested_start = _parse_utc(args.start_utc)
        if args.authorize_start or args.revoke_start:
            clock = ExperimentClockStore(db).initialize_or_load(
                requested_start_utc=requested_start,
                duration_days=args.duration_days,
                initial_allocation=Decimal(args.allocation),
            )
            auth_store = OwnerAuthorizationStore(db)
            if args.authorize_start:
                expected_phrase = "AUTHORIZE 30-DAY PAPER EXPERIMENT"
                if args.authorization_phrase != expected_phrase:
                    raise AutonomousServiceError(
                        "exact authorization phrase required: " + expected_phrase
                    )
                event_id = auth_store.set(
                    "AUTHORIZED",
                    clock_event_sha256=clock.event_sha256,
                    reason="explicit owner authorization for Day 1",
                    actor="owner",
                )
                print(
                    json.dumps(
                        {
                            "status": "AUTHORIZED",
                            "event_id": event_id,
                            "clock_event_sha256": clock.event_sha256,
                            "paper_execution_armed": False,
                        },
                        sort_keys=True,
                    )
                )
                return 0
            event_id = auth_store.set(
                "REVOKED",
                clock_event_sha256=clock.event_sha256,
                reason="explicit owner revocation",
                actor="owner",
            )
            print(
                json.dumps(
                    {
                        "status": "REVOKED",
                        "event_id": event_id,
                        "paper_execution_armed": False,
                    },
                    sort_keys=True,
                )
            )
            return 0

        service = AutonomousExperimentService(
            db,
            experiment_start_utc=requested_start,
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
        if not args.execute_paper:
            print(
                "WARNING: autonomous service is UNARMED; no paper orders will be transmitted.",
                file=sys.stderr,
            )
        if args.once:
            result = service.run_once()
            print(json.dumps(result, sort_keys=True, default=str))
            return 0
        service.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
