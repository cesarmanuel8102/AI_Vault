from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .autonomous_research import ResearchRequest, ResearchTool
from .canonical import sha256_json
from .continuity_store import ContinuityStore
from .experiment_control import ExperimentClock, ExperimentClockStore, KillSwitchStore
from .experiment_epoch import ExperimentEpochStore
from .experiment_ledger import AutonomousExperimentLedger
from .ibkr_research_tools import IBKRResearchToolbox
from .open_order_management import (
    EXECUTION_CLIENT_ID,
    EXPERIMENT_ORDER_PREFIX,
    V2_OWNERSHIP_ANCHOR_KEYS,
)
from .persistence import Database
from .market_data import DecisionClass
from .repositories import utc_now
from .runtime_integrity import RuntimeMarketDataGate
from .successor_clock import clock_for_epoch
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
        experiment_start_utc: datetime | None,
        experiment_clock: ExperimentClock | None = None,
        duration_days: int = 30,
        kill_switch_state: str | None = None,
        runtime_market_gate: RuntimeMarketDataGate | None = None,
    ) -> None:
        if (
            experiment_start_utc is not None
            and (experiment_start_utc.tzinfo is None or experiment_start_utc.utcoffset() is None)
        ):
            raise ValueError("experiment_start_utc must be timezone-aware")
        if duration_days <= 0:
            raise ValueError("duration_days must be positive")
        self.db = db
        self.toolbox = toolbox
        self.ledger = AutonomousExperimentLedger(db, allocation=allocation)
        if experiment_clock is None:
            self.experiment_clock = ExperimentClockStore(db).initialize_or_load(
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
                raise AutonomousStateBuildError("SUCCESSOR_CLOCK_BINDING_MISMATCH")
            self.experiment_clock = experiment_clock
        self.epoch_store = ExperimentEpochStore(db)
        self.kill_switch_store = KillSwitchStore(db)
        if (
            kill_switch_state is not None
            and kill_switch_state != self.kill_switch_store.current()
        ):
            raise AutonomousStateBuildError("KILL_SWITCH_OVERRIDE_FORBIDDEN")
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
            market_data_snapshot={
                "gate_status": "BLOCK",
                "scope": "state_builder_placeholder",
                "reason_codes": ["PLACEHOLDER_BUNDLE_FAIL_CLOSED"],
            },
            candidate_screen_results=[],
            relevant_previous_immutable_decisions=[],
            process_policy_version="AUTONOMOUS_RESEARCH_V1",
            execution_realism_version="PAPER_V1",
            benchmark_state={},
            experiment_clock={"expired": True, "remaining_seconds": 0},
            continuity_context={
                "status": "NOT_INSTALLED",
                "authority_contract_required": False,
            },
        )

    def _registered_fill(self, fill: dict[str, Any]) -> bool:
        order_ref = str(fill.get("orderRef") or "")
        if not order_ref.startswith(f"{EXPERIMENT_ORDER_PREFIX}-"):
            return False
        try:
            order_id = int(fill.get("orderId") or 0)
            perm_id = int(fill.get("permId") or 0)
            client_id = int(fill.get("clientId") or 0)
            contract_id = int((fill.get("contract") or {}).get("conId") or 0)
        except (TypeError, ValueError):
            return False
        side = str(fill.get("side") or "").upper()
        if (
            order_id <= 0
            or client_id != EXECUTION_CLIENT_ID
            or contract_id <= 0
            or side not in {"BUY", "SELL"}
        ):
            return False
        rows = self.db.execute(
            "SELECT client_order_id,perm_id,ibkr_order_id,contract_id,action,"
            "quantity,payload_json,payload_sha256 "
            "FROM experiment_order_registry "
            "WHERE order_ref=? ORDER BY sequence DESC",
            (order_ref,),
        ).fetchall()
        anchors: list[tuple[Any, dict[str, Any]]] = []
        for row in rows:
            try:
                payload = json.loads(row[6] or "{}")
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict) or payload.get("schema") not in {
                "EXPERIMENT_ORDER_REGISTRY_V2",
                "EXPERIMENT_ORDER_REGISTRY_V3",
            }:
                continue
            if payload.get("lifecycle_event") not in {
                "ISSUED_PRE_SEND",
                "BROKER_BOUND",
                "BROKER_IDENTITY_BOUND",
            }:
                continue
            required_keys = set(V2_OWNERSHIP_ANCHOR_KEYS)
            if payload.get("schema") == "EXPERIMENT_ORDER_REGISTRY_V3":
                required_keys.add("contract")
            if (
                not required_keys.issubset(payload)
                or sha256_json(payload) != str(row[7] or "")
            ):
                return False
            try:
                coherent = (
                    str(payload.get("order_ref") or "") == order_ref
                    and int(payload.get("client_order_id") or 0)
                    == int(row[0] or 0)
                    and int(payload.get("perm_id") or 0) == int(row[1] or 0)
                    and int(payload.get("ibkr_order_id") or 0)
                    == int(row[2] or 0)
                    and int(payload.get("contract_id") or 0)
                    == int(row[3] or 0)
                    and str(payload.get("action") or "").upper()
                    == str(row[4] or "").upper()
                    and Decimal(str(payload.get("quantity") or 0))
                    == Decimal(str(row[5] or 0))
                    and (
                        payload.get("schema") != "EXPERIMENT_ORDER_REGISTRY_V3"
                        or int((payload.get("contract") or {}).get("conId") or 0)
                        == int(payload.get("contract_id") or 0)
                    )
                )
            except (TypeError, ValueError):
                return False
            if not coherent:
                return False
            anchors.append((row, payload))

        if not anchors:
            return False
        source_anchor_hashes = [
            str(row[7] or "")
            for row, payload in reversed(anchors)
            if payload.get("lifecycle_event") != "BROKER_IDENTITY_BOUND"
        ]
        if any(
            payload.get("source_anchor_sha256") != source_anchor_hashes
            for _, payload in anchors
            if payload.get("lifecycle_event") == "BROKER_IDENTITY_BOUND"
        ):
            return False
        if any(
            int(row[0] or 0) != order_id
            or int(row[2] or 0) != order_id
            or int(payload.get("execution_client_id") or 0)
            != EXECUTION_CLIENT_ID
            or not str(payload.get("account") or "")
            for row, payload in anchors
        ):
            return False
        positive_perm_ids = {
            int(row[1]) for row, _ in anchors if int(row[1] or 0) > 0
        }
        if positive_perm_ids and positive_perm_ids != {perm_id}:
            return False
        try:
            issued_quantities = {
                Decimal(str(row[5] or 0)) for row, _ in anchors
            }
            fill_quantity = Decimal(
                str(fill.get("quantity") or fill.get("shares") or 0)
            )
            cumulative_quantity = Decimal(
                str(fill.get("cumQty") or fill_quantity)
            )
        except (TypeError, ValueError):
            return False
        if (
            len(issued_quantities) != 1
            or not all(value.is_finite() and value > 0 for value in issued_quantities)
            or not fill_quantity.is_finite()
            or fill_quantity <= 0
            or not cumulative_quantity.is_finite()
            or cumulative_quantity < fill_quantity
        ):
            return False

        v3_contracts = [
            payload.get("contract")
            for _, payload in anchors
            if payload.get("schema") == "EXPERIMENT_ORDER_REGISTRY_V3"
        ]
        bag_contracts = [
            contract
            for contract in v3_contracts
            if isinstance(contract, dict)
            and str(contract.get("secType") or "").upper() == "BAG"
        ]
        if bag_contracts:
            if len(bag_contracts) != len(v3_contracts):
                return False
            positive_parent_ids = {
                int(contract.get("conId") or 0)
                for contract in bag_contracts
                if int(contract.get("conId") or 0) > 0
            }
            if len(positive_parent_ids) != 1:
                return False
            canonical_legs = bag_contracts[-1].get("comboLegs")
            if not isinstance(canonical_legs, list) or not canonical_legs:
                return False
            if any(contract.get("comboLegs") != canonical_legs for contract in bag_contracts):
                return False
            expected_accounts = {
                str(payload.get("account") or "") for _, payload in anchors
            }
            if expected_accounts != {str(fill.get("account") or "")}:
                return False
            matching_legs = [
                leg
                for leg in canonical_legs
                if int(leg.get("conId") or 0) == contract_id
                and str(leg.get("action") or "").upper() == side
            ]
            if len(matching_legs) != 1:
                return False
            try:
                ratio = Decimal(str(matching_legs[0].get("ratio") or 0))
            except (TypeError, ValueError):
                return False
            maximum_leg_quantity = next(iter(issued_quantities)) * ratio
            return (
                ratio.is_finite()
                and ratio > 0
                and fill_quantity <= maximum_leg_quantity
                and cumulative_quantity <= maximum_leg_quantity
            )

        issued_quantity = next(iter(issued_quantities))
        return (
            all(int(row[3] or 0) == contract_id for row, _ in anchors)
            and all(str(row[4] or "").upper() == side for row, _ in anchors)
            and fill_quantity <= issued_quantity
            and cumulative_quantity <= issued_quantity
        )

    def _sync_executions(self) -> list[str]:
        executions = self._tool(ResearchTool.EXECUTIONS)
        reasons: list[str] = []
        for fill in executions.get("executions", []) or []:
            order_ref = str(fill.get("orderRef") or "")
            if not order_ref.startswith("codex-ibkr-paper-30d-"):
                continue
            if not self._registered_fill(fill):
                reasons.append(
                    f"UNREGISTERED_EXPERIMENT_FILL:{int(fill.get('orderId') or 0)}"
                )
                continue
            self.ledger.record_fill(fill)
        return reasons

    def _mark_open_positions(self) -> list[str]:
        state = self.ledger.project()
        reasons: list[str] = []
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
                reasons.append(f"MARK_QUOTE_FAILED:{position.contract_id}")
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
                reasons.append(f"MARK_QUOTE_INVALID:{position.contract_id}")
                continue
            if price.is_finite() and price > 0:
                self.ledger.record_mark(
                    contract_id=position.contract_id,
                    symbol=position.symbol,
                    price=price,
                )
            else:
                reasons.append(f"MARK_QUOTE_INVALID:{position.contract_id}")
        return reasons

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
        snapshot = self.experiment_clock.snapshot(now)
        epoch = self.epoch_store.projection(now)
        snapshot.update(
            {
                "epoch_state": epoch["state"],
                "epoch_id": epoch["epoch_id"],
                "epoch_activation_required": epoch["activation_required"],
                "historical_cycle_count": epoch["historical_cycle_count"],
                "historical_ledger_event_count": epoch[
                    "historical_ledger_event_count"
                ],
                "previous_history_classification": epoch[
                    "previous_history_classification"
                ],
            }
        )
        if epoch["state"] == "ACTIVE":
            snapshot.update(
                {
                    key: value
                    for key, value in epoch.items()
                    if key not in {"state", "activation_required"}
                }
            )
        return snapshot

    def _continuity_context(self, clock: dict[str, Any]) -> dict[str, Any]:
        installed = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='continuity_plan_events'"
        ).fetchone()
        if installed is None:
            return {
                "status": "NOT_INSTALLED",
                "authority_contract_required": False,
                "active_plans": [],
                "provider_states": [],
                "pending_factual_reports": [],
                "prior_reflections": [],
            }
        store = ContinuityStore(self.db)
        order_refs = [
            str(row[0])
            for row in self.db.execute(
                "SELECT DISTINCT order_ref FROM continuity_plan_events"
            ).fetchall()
        ]
        active_plans = []
        for order_ref in order_refs:
            plan = store.active_plan(order_ref)
            if plan is not None:
                active_plans.append(
                    {
                        "plan": plan.model_dump(mode="json"),
                        "plan_sha256": plan.sha256,
                    }
                )
        provider_states = [
            store.provider_projection(str(row[0]))
            for row in self.db.execute(
                "SELECT DISTINCT invocation_id FROM provider_invocation_events"
            ).fetchall()
        ]
        reflections = []
        for reflection_id, payload_json in self.db.execute(
            "SELECT reflection_id,payload_json FROM continuity_reflection_events "
            "ORDER BY sequence"
        ).fetchall():
            reflections.append(
                {
                    "reflection_id": str(reflection_id),
                    "content": json.loads(str(payload_json)),
                    "trust": "UNTRUSTED_MODEL_REFLECTION",
                }
            )
        return {
            "status": "AVAILABLE",
            "authority_contract_required": True,
            "epoch_id": clock.get("epoch_id"),
            "definition_sha256": clock.get("definition_sha256"),
            "clock_event_sha256": clock.get("event_sha256"),
            "owner_authorization_sha256": (
                clock.get("owner_authorization_sha256")
                or clock.get("owner_authorization_receipt_sha256")
            ),
            "active_plans": active_plans,
            "provider_states": provider_states,
            "pending_factual_reports": store.pending_reports(),
            "prior_reflections": reflections,
        }

    @staticmethod
    def _broker_now(account: dict[str, Any]) -> datetime:
        raw = account.get("server_time_utc")
        if not isinstance(raw, str) or not raw:
            raise AutonomousStateBuildError("BROKER_SERVER_TIME_MISSING")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AutonomousStateBuildError("BROKER_SERVER_TIME_INVALID") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise AutonomousStateBuildError("BROKER_SERVER_TIME_INVALID")
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _broker_snapshot(account: dict[str, Any], equity: Decimal) -> dict[str, Any]:
        experiment_buying_power = max(equity, Decimal("0"))
        return {
            "paper_account": bool(account.get("paper_account")),
            "declared_options_level": account.get("declared_options_level"),
            "experiment_buying_power": str(experiment_buying_power),
            "global_broker_balances_redacted": True,
            "note": (
                "Model-facing buying power is limited to isolated experiment equity; "
                "broker feasibility is enforced separately by per-order what-if validation."
            ),
        }

    def build(
        self,
        *,
        trigger: str,
        market_session_state: str = "UNKNOWN",
        benchmark_state: dict[str, Any] | None = None,
    ) -> TraderInputBundle:
        execution_reasons = self._sync_executions()
        mark_reasons = self._mark_open_positions()
        ledger_state = self.ledger.project()
        account = self._tool(ResearchTool.ACCOUNT_STATE)
        broker_positions = self._tool(ResearchTool.POSITIONS)
        open_orders = self._tool(ResearchTool.OPEN_ORDERS)
        reconciliation = self._reconcile(ledger_state, broker_positions)
        state_reasons = execution_reasons + mark_reasons
        if state_reasons:
            reconciliation["status"] = "BLOCK"
            reconciliation["reason_codes"] = list(
                dict.fromkeys(
                    list(reconciliation.get("reason_codes", [])) + state_reasons
                )
            )
        now = self._broker_now(account)
        clock = self._clock(now)

        isolated_orders = [
            item
            for item in open_orders.get("open_orders", []) or []
            if str(item.get("orderRef") or "").startswith(
                "codex-ibkr-paper-30d-"
            )
        ]
        isolated_positions = [
            {
                "contract_id": item.contract_id,
                "symbol": item.symbol,
                "sec_type": item.sec_type,
                "multiplier": str(item.multiplier),
                "quantity": str(item.quantity),
                "average_cost": str(item.average_cost),
                "mark": str(item.mark),
                "market_value": str(item.market_value),
            }
            for item in ledger_state.positions
        ]

        kill_switch_state = self.kill_switch_store.current()
        decision_class = (
            DecisionClass.OPEN_POSITION_MANAGEMENT
            if trigger == "POSITION_EVENT"
            else DecisionClass.NEW_TRADE
        )
        if self.runtime_market_gate is None:
            market_gate = {
                "gate_status": "BLOCK",
                "reason_codes": ["EXPECTED_PAPER_IDENTITY_REQUIRED_FOR_MARKET_GATE"],
            }
        else:
            market_gate = self.runtime_market_gate.evaluate(decision_class)
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
            broker_account_snapshot=self._broker_snapshot(
                account, ledger_state.equity
            ),
            positions_snapshot=isolated_positions,
            open_orders_snapshot=isolated_orders,
            risk_snapshot={
                "policy": "AGGRESSIVE_CAPITAL_BOUNDARY_V1",
                "maximum_experiment_liability": str(max(ledger_state.equity, Decimal("0"))),
                "fixed_percent_limits": False,
            },
            kill_switch_state=kill_switch_state,
            market_data_snapshot={
                **market_gate,
                "scope": "runtime_frozen_policy_and_fresh_ibkr_quotes",
                "specific_contract_data_validated_on_demand": True,
            },
            candidate_screen_results=[],
            relevant_previous_immutable_decisions=self._previous_decisions(),
            process_policy_version="AUTONOMOUS_RESEARCH_V1",
            execution_realism_version="IBKR_PAPER_WHATIF_AND_PAPER_EXECUTION_V1",
            benchmark_state=benchmark_state or {},
            experiment_clock=clock,
            continuity_context=self._continuity_context(clock),
        )
