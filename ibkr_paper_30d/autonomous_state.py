from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .autonomous_research import ResearchRequest, ResearchTool
from .canonical import sha256_json
from .experiment_control import ExperimentClockStore, KillSwitchStore
from .experiment_ledger import AutonomousExperimentLedger
from .ibkr_research_tools import IBKRResearchToolbox
from .persistence import Database
from .market_data import DecisionClass
from .repositories import utc_now
from .runtime_integrity import RuntimeMarketDataGate
from .trader_invocation import TraderInputBundle
from .types import new_uuid7


class AutonomousStateBuildError(RuntimeError):
    pass


class AutonomousStateBuilder:
    """Build a fresh decision bundle from isolated experiment state + IBKR.

    No predefined candidate universe is injected. The bundle contains only the
    current isolated portfolio, broker feasibility context and experiment clock.
    Opportunity discovery remains entirely model-directed.
    """

    def __init__(
        self,
        db: Database,
        toolbox: IBKRResearchToolbox,
        *,
        allocation: Decimal = Decimal("500.00"),
        experiment_start_utc: datetime,
        duration_days: int = 30,
        kill_switch_state: str | None = None,
        runtime_market_gate: RuntimeMarketDataGate | None = None,
    ) -> None:
        if experiment_start_utc.tzinfo is None or experiment_start_utc.utcoffset() is None:
            raise ValueError("experiment_start_utc must be timezone-aware")
        if duration_days <= 0:
            raise ValueError("duration_days must be positive")
        self.db = db
        self.toolbox = toolbox
        self.ledger = AutonomousExperimentLedger(db, allocation=allocation)
        self.experiment_clock = ExperimentClockStore(db).initialize_or_load(
            requested_start_utc=experiment_start_utc,
            duration_days=duration_days,
            initial_allocation=allocation,
        )
        self.kill_switch_store = KillSwitchStore(db)
        if kill_switch_state is not None and self.kill_switch_store.current() == "KILL_SWITCH_TRIGGERED":
            if kill_switch_state == "KILL_SWITCH_CLEAR":
                self.kill_switch_store.set(
                    "KILL_SWITCH_CLEAR",
                    reason="explicit builder initialization",
                    actor="runtime",
                )
        expected_hash = getattr(toolbox, "expected_account_hash", None)
        self.runtime_market_gate = runtime_market_gate or (
            RuntimeMarketDataGate(expected_account_hash=expected_hash)
            if expected_hash
            else None
        )

    def _tool(self, tool: ResearchTool, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        request = ResearchRequest(
            request_id=f"state-{new_uuid7()}",
            tool=tool,
            arguments=arguments or {},
            purpose="Build fresh autonomous experiment state",
        )
        result = self.toolbox.execute(request, self._minimal_placeholder_bundle())
        if not result.success:
            raise AutonomousStateBuildError(f"{tool.value}_FAILED:{result.error}")
        return result.data

    def _minimal_placeholder_bundle(self) -> TraderInputBundle:
        now = utc_now()
        return TraderInputBundle(
            decision_cycle_id=f"state-placeholder-{new_uuid7()}",
            utc_timestamp=now,
            market_session_state="UNKNOWN",
            reconciliation_receipt={"status": "PREFLIGHT"},
            experiment_subledger_snapshot={"equity": "0.01"},
            broker_account_snapshot={},
            positions_snapshot=[],
            open_orders_snapshot=[],
            risk_snapshot={"policy": "AGGRESSIVE_CAPITAL_BOUNDARY_V1"},
            kill_switch_state="KILL_SWITCH_TRIGGERED",
            market_data_snapshot={"gate_status": "PASS", "scope": "state_builder"},
            candidate_screen_results=[],
            relevant_previous_immutable_decisions=[],
            process_policy_version="AUTONOMOUS_RESEARCH_V1",
            execution_realism_version="PAPER_V1",
            benchmark_state={},
            experiment_clock={},
        )

    def _sync_executions(self) -> None:
        executions = self._tool(ResearchTool.EXECUTIONS)
        for fill in executions.get("executions", []) or []:
            if not str(fill.get("orderRef") or "").startswith("codex-ibkr-paper-30d"):
                continue
            self.ledger.record_fill(fill)

    def _mark_open_positions(self) -> None:
        state = self.ledger.project()
        for position in state.positions:
            result = self.toolbox.execute(
                ResearchRequest(
                    request_id=f"mark-{new_uuid7()}",
                    tool=ResearchTool.QUOTE,
                    arguments={
                        "conId": position.contract_id,
                        "symbol": position.symbol,
                        "sec_type": position.sec_type,
                    },
                    purpose="Mark isolated open position before decision",
                ),
                self._minimal_placeholder_bundle(),
            )
            if not result.success:
                continue
            raw_price = (
                result.data.get("marketPrice")
                or result.data.get("last")
                or result.data.get("bid")
                or result.data.get("ask")
            )
            try:
                price = Decimal(str(raw_price))
            except Exception:
                continue
            if price.is_finite() and price > 0:
                self.ledger.record_mark(
                    contract_id=position.contract_id,
                    symbol=position.symbol,
                    price=price,
                )

    @staticmethod
    def _broker_position_map(payload: dict[str, Any]) -> dict[int, Decimal]:
        result: dict[int, Decimal] = {}
        for item in payload.get("positions", []) or []:
            contract = item.get("contract") or {}
            con_id = int(contract.get("conId") or 0)
            if con_id <= 0:
                continue
            try:
                qty = Decimal(str(item.get("position", "0")))
            except Exception:
                continue
            result[con_id] = qty
        return result

    def _reconcile(
        self,
        ledger_state: Any,
        broker_positions: dict[str, Any],
    ) -> dict[str, Any]:
        broker_map = self._broker_position_map(broker_positions)
        reasons: list[str] = []
        for position in ledger_state.positions:
            broker_qty = broker_map.get(position.contract_id)
            if broker_qty is None:
                reasons.append(f"MISSING_BROKER_POSITION:{position.contract_id}")
            elif broker_qty != position.quantity:
                reasons.append(f"POSITION_QUANTITY_MISMATCH:{position.contract_id}")
        if not ledger_state.valid:
            reasons.extend(ledger_state.reason_codes)
        return {
            "status": "PASS" if not reasons else "BLOCK",
            "reason_codes": reasons,
            "ledger_event_count": ledger_state.event_count,
            "ledger_sha256": sha256_json({
                "equity": str(ledger_state.equity),
                "positions": [
                    {
                        "contract_id": item.contract_id,
                        "quantity": str(item.quantity),
                        "mark": str(item.mark),
                    }
                    for item in ledger_state.positions
                ],
            }),
        }

    def _previous_decisions(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT payload_json FROM autonomous_research_events "
            "WHERE event_type='final_outcome' ORDER BY sequence DESC LIMIT ?",
            (limit,),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for (payload_json,) in rows:
            try:
                items.append(json.loads(payload_json))
            except json.JSONDecodeError:
                continue
        return list(reversed(items))

    def _clock(self, now: datetime) -> dict[str, Any]:
        end = self.experiment_start_utc + timedelta(days=self.duration_days)
        remaining = max((end - now).total_seconds(), 0.0)
        elapsed = max((now - self.experiment_start_utc).total_seconds(), 0.0)
        return {
            "start_utc": self.experiment_start_utc.isoformat().replace("+00:00", "Z"),
            "end_utc": end.isoformat().replace("+00:00", "Z"),
            "now_utc": now.isoformat().replace("+00:00", "Z"),
            "duration_days": self.duration_days,
            "elapsed_days": elapsed / 86400.0,
            "remaining_days": remaining / 86400.0,
            "remaining_seconds": remaining,
            "expired": remaining <= 0,
        }

    def build(
        self,
        *,
        trigger: str,
        market_session_state: str = "UNKNOWN",
        benchmark_state: dict[str, Any] | None = None,
    ) -> TraderInputBundle:
        self._sync_executions()
        self._mark_open_positions()
        ledger_state = self.ledger.project()
        account = self._tool(ResearchTool.ACCOUNT_STATE)
        broker_positions = self._tool(ResearchTool.POSITIONS)
        open_orders = self._tool(ResearchTool.OPEN_ORDERS)
        reconciliation = self._reconcile(ledger_state, broker_positions)
        now = datetime.now(timezone.utc)
        clock = self._clock(now)

        isolated_orders = [
            item
            for item in open_orders.get("open_orders", []) or []
            if str(item.get("orderRef") or "").startswith("codex-ibkr-paper-30d")
        ]
        isolated_positions = [
            {
                "contract_id": item.contract_id,
                "symbol": item.symbol,
                "sec_type": item.sec_type,
                "multiplier": str(item.multiplier),
                "quantity": str(item.quantity),
                "mark": str(item.mark),
                "market_value": str(item.market_value),
            }
            for item in ledger_state.positions
        ]

        gate_status = (
            "PASS"
            if reconciliation.get("status") == "PASS"
            and self.kill_switch_state == "KILL_SWITCH_CLEAR"
            and not clock["expired"]
            else "BLOCK"
        )
        return TraderInputBundle(
            decision_cycle_id=f"cycle-{new_uuid7()}",
            utc_timestamp=clock["now_utc"],
            market_session_state=market_session_state,
            reconciliation_receipt=reconciliation,
            experiment_subledger_snapshot={
                "allocation": str(ledger_state.allocation),
                "cash": str(ledger_state.cash),
                "market_value": str(ledger_state.market_value),
                "equity": str(ledger_state.equity),
                "high_water_mark": str(ledger_state.high_water_mark),
                "drawdown": str(ledger_state.drawdown),
                "fees": str(ledger_state.fees),
                "valid": ledger_state.valid,
                "reason_codes": list(ledger_state.reason_codes),
            },
            broker_account_snapshot={
                "paper_account": bool(account.get("paper_account")),
                "declared_options_level": account.get("declared_options_level"),
                "broker_summary": account.get("summary", {}),
                "note": "Broker balances may exceed isolated experiment equity and are not available to the experiment.",
            },
            positions_snapshot=isolated_positions,
            open_orders_snapshot=isolated_orders,
            risk_snapshot={
                "policy": "AGGRESSIVE_CAPITAL_BOUNDARY_V1",
                "maximum_experiment_liability": str(max(ledger_state.equity, Decimal("0"))),
                "fixed_percent_limits": False,
            },
            kill_switch_state=self.kill_switch_state,
            market_data_snapshot={
                "gate_status": gate_status,
                "scope": "broker_session_and_isolated_state_readiness",
                "specific_contract_data_validated_on_demand": True,
            },
            candidate_screen_results=[],
            relevant_previous_immutable_decisions=self._previous_decisions(),
            process_policy_version="AUTONOMOUS_RESEARCH_V1",
            execution_realism_version="IBKR_PAPER_WHATIF_AND_PAPER_EXECUTION_V1",
            benchmark_state=benchmark_state or {},
            experiment_clock=clock,
        )
