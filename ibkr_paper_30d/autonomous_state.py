from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Mapping

from .autonomous_research import ResearchRequest, ResearchTool
from .canonical import sha256_json
from .continuity_store import ContinuityStore
from .contract_ownership import ContractOwnershipStore
from .multi_universe_models import CapitalSleeve, TransitionPhase
from .multi_universe_transition import (
    MultiUniverseTransitionError,
    active_cash_classifications,
)
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
from .product_capability import ProductFamilyCertificationStore
from .runtime_integrity import RuntimeMarketDataGate
from .sleeve_ledger import SleeveLedgerStore
from .sleeve_reconciliation import SleeveReconciler
from .successor_clock import clock_for_epoch
from .successor_epoch import (
    SuccessorEpochError,
    current_epoch_authority_bindings,
)
from .trader_invocation import TraderInputBundle
from .types import new_uuid7


class AutonomousStateBuildError(RuntimeError):
    pass


class TransientBrokerStateBuildError(AutonomousStateBuildError):
    pass


PROCESS_OBSERVATION_CYCLE_LIMIT = 20
PROVIDER_STATE_CONTEXT_LIMIT = 5


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
        sleeve_ledger_store: SleeveLedgerStore | None = None,
        contract_ownership_store: ContractOwnershipStore | None = None,
        product_certification_store: ProductFamilyCertificationStore | None = None,
        session_evidence_reader: Callable[[], dict[str, Any] | None] | None = None,
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
        stores = (
            sleeve_ledger_store,
            contract_ownership_store,
            product_certification_store,
        )
        if any(store is not None for store in stores) and not all(
            store is not None for store in stores
        ):
            raise ValueError("V4 state dependencies must be supplied together")
        self.sleeve_ledger_store = sleeve_ledger_store
        self.contract_ownership_store = contract_ownership_store
        self.product_certification_store = product_certification_store
        self.session_evidence_reader = session_evidence_reader
        self._latest_executions: list[dict[str, Any]] = []

    def _tool(self, tool: ResearchTool, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        request = ResearchRequest(
            request_id=f"state-{new_uuid7()}",
            tool=tool,
            arguments=arguments or {},
            purpose="Build fresh autonomous experiment state",
        )
        result = self.toolbox.execute(request, self._minimal_placeholder_bundle())
        if not result.success:
            message = f"{tool.value}_FAILED:{result.error}"
            error_type = str(result.error or "").partition(":")[0]
            if error_type in {
                "TimeoutError",
                "ConnectionError",
                "ConnectionAbortedError",
                "ConnectionRefusedError",
                "ConnectionResetError",
                "BrokenPipeError",
                "OSError",
            }:
                raise TransientBrokerStateBuildError(message)
            raise AutonomousStateBuildError(message)
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
        self._latest_executions = list(executions.get("executions", []) or [])
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

    def _sync_and_reconcile_v4(
        self,
        *,
        account: dict[str, Any],
        broker_positions: dict[str, Any],
        open_orders: dict[str, Any],
    ) -> dict[str, Any]:
        if self.sleeve_ledger_store is None:
            raise AutonomousStateBuildError("V4_STATE_DEPENDENCIES_REQUIRED")
        assert self.contract_ownership_store is not None
        ownership = self.contract_ownership_store.projection()
        ownership_records = (
            *ownership.active_contracts,
            *getattr(ownership, "released_contracts", ()),
        )
        by_con_id = {
            int(item.contract.con_id): item.contract_identity_sha256
            for item in ownership_records
            if int(item.contract.con_id) > 0
        }

        def contract_hash(raw: dict[str, Any]) -> str:
            contract = raw.get("contract") or {}
            con_id = int(
                contract.get("conId")
                or contract.get("con_id")
                or raw.get("contract_id")
                or 0
            )
            return str(by_con_id.get(con_id) or "")

        positions: list[dict[str, Any]] = []
        for raw in broker_positions.get("positions", ()) or ():
            quantity = Decimal(str(raw.get("position") or raw.get("quantity") or "0"))
            if quantity == 0:
                continue
            multiplier = Decimal(str((raw.get("contract") or {}).get("multiplier") or "1"))
            average_cost = Decimal(str(raw.get("avgCost") or raw.get("average_cost") or "0"))
            positions.append(
                {
                    "contract_identity_sha256": contract_hash(raw),
                    "quantity": str(quantity),
                    "multiplier": str(multiplier),
                    "average_cost": str(average_cost),
                    "mark": str(max(average_cost, Decimal("0"))),
                    "market_value_usd": str(quantity * multiplier * average_cost),
                }
            )
        orders = [
            {"contract_identity_sha256": contract_hash(raw)}
            for raw in open_orders.get("open_orders", ()) or ()
            if str(raw.get("orderRef") or "").startswith(
                f"{EXPERIMENT_ORDER_PREFIX}-"
            )
        ]
        executions = [
            {
                "contract_identity_sha256": contract_hash(raw),
                "execution_id_hash": raw.get("execution_id_hash"),
                "commission": raw.get("commission"),
            }
            for raw in self._latest_executions
            if str(raw.get("orderRef") or "").startswith(
                f"{EXPERIMENT_ORDER_PREFIX}-"
            )
        ]
        broker_snapshot = {
            "positions": positions,
            "open_orders": orders,
            "executions": executions,
        }
        self.sleeve_ledger_store.reconcile_broker_snapshot(
            broker_snapshot, ownership
        )
        ledgers = self.sleeve_ledger_store.project_all()
        ledger_payload = self._dump(ledgers)
        try:
            account_snapshot = dict(
                self.toolbox.account_reconciliation_snapshot()
            )
        except Exception as exc:
            raise AutonomousStateBuildError(
                "V4_BROKER_CASH_EVIDENCE_REQUIRED"
            ) from exc
        account_snapshot.update(self._transition_cash_classifications())
        account_snapshot.update({
            "positions": positions,
            "open_orders": orders,
            "executions": executions,
            "fees": [
                {
                    "contract_identity_sha256": item["contract_identity_sha256"],
                    "amount": item["commission"],
                }
                for item in executions
                if item.get("commission") not in {None, ""}
            ],
            "financing": [],
        })
        receipt = SleeveReconciler.reconcile(
            account_snapshot, ledger_payload, self._dump(ownership)
        )
        if receipt.status == "PASS":
            from .sleeve_execution_authority import (
                SleeveAuthorityReservationStore,
            )

            terminal_snapshot = {
                **broker_snapshot,
                "pending_execution_contract_sha256": [],
                "fill_ambiguity": False,
                "fresh": True,
            }
            finalized = SleeveAuthorityReservationStore(
                self.db
            ).finalize_terminal_reservations(
                terminal_snapshot,
                observation_id=sha256_json(
                    {
                        "account": account,
                        "broker_snapshot": broker_snapshot,
                        "observed_at_utc": utc_now(),
                    }
                ),
            )
            if finalized["released"]:
                ownership = self.contract_ownership_store.projection()
                self.sleeve_ledger_store.reconcile_broker_snapshot(
                    broker_snapshot, ownership
                )
                ledgers = self.sleeve_ledger_store.project_all()
                receipt = SleeveReconciler.reconcile(
                    account_snapshot,
                    self._dump(ledgers),
                    self._dump(ownership),
                )
        return receipt.model_dump(mode="json")

    def _transition_cash_classifications(
        self,
    ) -> dict[str, list[dict[str, str]]]:
        try:
            return active_cash_classifications(self.db)
        except MultiUniverseTransitionError as exc:
            raise AutonomousStateBuildError(
                "V4_ACTIVE_CASH_CLASSIFICATION_REQUIRED"
            ) from exc

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

    @staticmethod
    def _json_mapping(raw: Any) -> dict[str, Any] | None:
        try:
            value = json.loads(str(raw))
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _process_observation(
        self,
        *,
        positions_snapshot: list[dict[str, Any]],
        equity: Decimal,
        limit: int = PROCESS_OBSERVATION_CYCLE_LIMIT,
    ) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT decision_cycle_id,invocation_id,payload_json,payload_sha256 "
            "FROM autonomous_research_events WHERE event_type='final_outcome' "
            "ORDER BY sequence DESC LIMIT ?",
            (limit,),
        ).fetchall()
        trigger_counts: dict[str, int] = {}
        decision_counts: dict[str, int] = {}
        symbol_cycle_counts: dict[str, int] = {}
        tools_used: set[str] = set()
        accepted_results = 0
        rejected_results = 0
        telemetry_cycles_observed = 0
        cycles_with_no_candidates = 0
        cycles_without_research_requests = 0
        consecutive_cycles_with_no_candidates = 0
        still_counting_no_candidates = True
        aggregate_fields = {
            "research_requests_executed": 0,
            "scanner_queries": 0,
            "scanner_results_received": 0,
            "option_chains_queried": 0,
            "feasibility_checks": 0,
            "blocked_requests": 0,
        }

        cycles_observed = 0
        for cycle_id, invocation_id, final_json, final_sha256 in rows:
            final = self._json_mapping(final_json)
            if final is None or sha256_json(final) != str(final_sha256):
                continue
            cycles_observed += 1
            if final.get("accepted") is True:
                accepted_results += 1
            else:
                rejected_results += 1
            decision = str(final.get("decision") or "UNKNOWN")
            decision_counts[decision] = decision_counts.get(decision, 0) + 1

            invocation_row = self.db.execute(
                "SELECT payload_json,payload_sha256 FROM trader_invocations "
                "WHERE invocation_id=? AND decision_cycle_id=?",
                (str(invocation_id), str(cycle_id)),
            ).fetchone()
            invocation = None
            if invocation_row is not None:
                candidate = self._json_mapping(invocation_row[0])
                if (
                    candidate is not None
                    and sha256_json(candidate) == str(invocation_row[1])
                ):
                    invocation = candidate
            trigger = str(
                (invocation or {}).get("invocation_trigger") or "UNKNOWN"
            )
            trigger_counts[trigger] = trigger_counts.get(trigger, 0) + 1

            telemetry_row = self.db.execute(
                "SELECT payload_json,payload_sha256 "
                "FROM autonomous_research_events "
                "WHERE decision_cycle_id=? AND invocation_id=? "
                "AND event_type='research_telemetry_summary' "
                "ORDER BY sequence DESC LIMIT 1",
                (str(cycle_id), str(invocation_id)),
            ).fetchone()
            telemetry_wrapper = None
            if telemetry_row is not None:
                candidate = self._json_mapping(telemetry_row[0])
                if (
                    candidate is not None
                    and sha256_json(candidate) == str(telemetry_row[1])
                ):
                    telemetry_wrapper = candidate
            telemetry = (telemetry_wrapper or {}).get("event")
            if not isinstance(telemetry, dict):
                still_counting_no_candidates = False
                continue
            telemetry_cycles_observed += 1
            for field in aggregate_fields:
                try:
                    aggregate_fields[field] += int(telemetry.get(field) or 0)
                except (TypeError, ValueError):
                    continue
            cycle_symbols = {
                str(symbol).upper()
                for symbol in telemetry.get("symbols_examined", []) or []
                if str(symbol).strip()
            }
            for symbol in cycle_symbols:
                symbol_cycle_counts[symbol] = symbol_cycle_counts.get(symbol, 0) + 1
            tools_used.update(
                str(tool)
                for tool in telemetry.get("tools_used", []) or []
                if str(tool).strip()
            )
            try:
                candidates = int(telemetry.get("candidates_generated") or 0)
                requests = int(telemetry.get("research_requests_executed") or 0)
            except (TypeError, ValueError):
                still_counting_no_candidates = False
                continue
            if candidates == 0:
                cycles_with_no_candidates += 1
                if still_counting_no_candidates:
                    consecutive_cycles_with_no_candidates += 1
            else:
                still_counting_no_candidates = False
            if requests == 0:
                cycles_without_research_requests += 1

        largest_position_symbol = None
        largest_position_value = Decimal("0")
        for position in positions_snapshot:
            try:
                market_value = abs(Decimal(str(position.get("market_value") or 0)))
            except Exception:
                continue
            if market_value > largest_position_value:
                largest_position_value = market_value
                largest_position_symbol = str(position.get("symbol") or "") or None
        largest_share = Decimal("0")
        if equity.is_finite() and equity > 0:
            largest_share = (largest_position_value / equity).quantize(
                Decimal("0.0001")
            )

        return {
            "schema": "AUTONOMOUS_PROCESS_OBSERVATION_V1",
            "telemetry_source": "SYSTEM_GENERATED_DURABLE_EVENTS",
            "window_cycle_limit": limit,
            "cycles_observed": cycles_observed,
            "telemetry_cycles_observed": telemetry_cycles_observed,
            "accepted_results": accepted_results,
            "rejected_results": rejected_results,
            "trigger_counts": dict(sorted(trigger_counts.items())),
            "decision_counts": dict(sorted(decision_counts.items())),
            "symbols_examined": sorted(symbol_cycle_counts),
            "symbol_cycle_counts": dict(sorted(symbol_cycle_counts.items())),
            "tools_used": sorted(tools_used),
            **aggregate_fields,
            "cycles_with_no_candidates": cycles_with_no_candidates,
            "consecutive_cycles_with_no_candidates": (
                consecutive_cycles_with_no_candidates
            ),
            "cycles_without_research_requests": cycles_without_research_requests,
            "largest_position_symbol": largest_position_symbol,
            "largest_position_market_value": str(largest_position_value),
            "largest_position_share_of_equity": str(largest_share),
        }

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

    @staticmethod
    def _clock_datetime(clock: dict[str, Any]) -> datetime:
        raw = clock.get("now_utc")
        if isinstance(raw, datetime):
            value = raw
        else:
            try:
                value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError as exc:
                raise AutonomousStateBuildError("EXPERIMENT_CLOCK_INVALID") from exc
        if value.tzinfo is None or value.utcoffset() is None:
            raise AutonomousStateBuildError("EXPERIMENT_CLOCK_INVALID")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _plan_has_open_order(plan: Any, open_orders: list[dict[str, Any]]) -> bool:
        binding = plan.order_binding
        for order in open_orders:
            if str(order.get("orderRef") or "") != binding.order_ref:
                continue
            if (
                binding.ibkr_order_id is not None
                and int(order.get("orderId") or 0) != binding.ibkr_order_id
            ):
                continue
            if (
                binding.perm_id is not None
                and int(order.get("permId") or 0) != binding.perm_id
            ):
                continue
            return True
        return False

    def _plan_bound_position_present(
        self,
        plan: Any,
        positions_snapshot: list[dict[str, Any]],
    ) -> bool:
        position_contract_ids: set[int] = set()
        for position in positions_snapshot:
            try:
                contract_id = int(position.get("contract_id") or 0)
                quantity = Decimal(str(position.get("quantity") or 0))
            except Exception:
                continue
            if contract_id > 0 and quantity.is_finite() and quantity != 0:
                position_contract_ids.add(contract_id)
        if not position_contract_ids:
            return False
        rows = self.db.execute(
            "SELECT contract_id,payload_json,payload_sha256 "
            "FROM experiment_order_registry WHERE order_ref=? "
            "ORDER BY sequence DESC",
            (plan.order_binding.order_ref,),
        ).fetchall()
        for contract_id, payload_json, payload_sha256 in rows:
            payload = self._json_mapping(payload_json)
            if payload is None or sha256_json(payload) != str(payload_sha256):
                continue
            if payload.get("lifecycle_event") not in {
                "BROKER_BOUND",
                "BROKER_IDENTITY_BOUND",
            }:
                continue
            try:
                registry_contract_id = int(contract_id or 0)
            except (TypeError, ValueError):
                continue
            return registry_contract_id in position_contract_ids
        return False

    def _continuity_context(
        self,
        clock: dict[str, Any],
        *,
        open_orders_snapshot: list[dict[str, Any]] | None = None,
        positions_snapshot: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        installed = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='continuity_plan_events'"
        ).fetchone()
        if installed is None:
            return {
                "status": "NOT_INSTALLED",
                "authority_contract_required": False,
                "active_plans": [],
                "inactive_plan_summaries": [],
                "provider_states": [],
                "provider_state_summary": {
                    "total_invocations": 0,
                    "state_counts": {},
                    "recent_states_limit": PROVIDER_STATE_CONTEXT_LIMIT,
                },
                "pending_factual_reports": [],
                "prior_reflections": [],
            }
        authority = None
        if clock.get("epoch_state") == "ACTIVE":
            try:
                authority = current_epoch_authority_bindings(self.db)
            except SuccessorEpochError as exc:
                raise AutonomousStateBuildError(
                    "CONTINUITY_AUTHORITY_INVALID"
                ) from exc
            if authority is None or any(
                clock.get(key) != authority[key]
                for key in (
                    "epoch_id",
                    "definition_sha256",
                    "clock_event_sha256",
                )
            ):
                raise AutonomousStateBuildError(
                    "CONTINUITY_AUTHORITY_BINDING_MISMATCH"
                )
        store = ContinuityStore(self.db)
        order_refs = [
            str(row[0])
            for row in self.db.execute(
                "SELECT DISTINCT order_ref FROM continuity_plan_events"
            ).fetchall()
        ]
        active_plans = []
        inactive_plan_summaries = []
        current_time = self._clock_datetime(clock)
        open_orders = open_orders_snapshot or []
        positions = positions_snapshot or []
        for order_ref in order_refs:
            plan = store.active_plan(order_ref)
            if plan is not None:
                expired_with_position = (
                    plan.plan_valid_until <= current_time
                    and not self._plan_has_open_order(plan, open_orders)
                    and self._plan_bound_position_present(plan, positions)
                )
                if expired_with_position:
                    inactive_plan_summaries.append(
                        {
                            "plan_id": plan.plan_id,
                            "plan_sha256": plan.sha256,
                            "order_ref": plan.order_binding.order_ref,
                            "plan_valid_until": plan.model_dump(mode="json")[
                                "plan_valid_until"
                            ],
                            "reason": "EXPIRED_NO_OPEN_ORDER_POSITION_PRESENT",
                        }
                    )
                    continue
                active_plans.append(
                    {
                        "plan": plan.model_dump(mode="json"),
                        "plan_sha256": plan.sha256,
                    }
                )
        provider_ids = [
            str(row[0])
            for row in self.db.execute(
                "SELECT invocation_id,MAX(sequence) AS latest_sequence "
                "FROM provider_invocation_events GROUP BY invocation_id "
                "ORDER BY latest_sequence DESC"
            ).fetchall()
        ]
        all_provider_states = [
            store.provider_projection(invocation_id)
            for invocation_id in provider_ids
        ]
        provider_state_counts: dict[str, int] = {}
        for state in all_provider_states:
            name = str(state.get("state") or "UNKNOWN")
            provider_state_counts[name] = provider_state_counts.get(name, 0) + 1
        provider_states = all_provider_states[:PROVIDER_STATE_CONTEXT_LIMIT]
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
            "clock_event_sha256": (
                authority["clock_event_sha256"]
                if authority is not None
                else clock.get("clock_event_sha256")
            ),
            "owner_authorization_sha256": (
                authority["owner_authorization_receipt_sha256"]
                if authority is not None
                else clock.get("owner_authorization_sha256")
                or clock.get("owner_authorization_receipt_sha256")
            ),
            "active_plans": active_plans,
            "inactive_plan_summaries": inactive_plan_summaries,
            "provider_states": provider_states,
            "provider_state_summary": {
                "total_invocations": len(all_provider_states),
                "state_counts": dict(sorted(provider_state_counts.items())),
                "recent_states_limit": PROVIDER_STATE_CONTEXT_LIMIT,
            },
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

    @staticmethod
    def _dump(value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return dict(value.model_dump(mode="json"))
        return dict(value)

    def _multi_sleeve_context(
        self,
        *,
        reconciliation: dict[str, Any],
        account: dict[str, Any],
        broker_positions: dict[str, Any],
        open_orders: dict[str, Any],
        transition_phase: str = TransitionPhase.ACTIVE.value,
        transition_target_sha256: str | None = None,
        writer_binding_sha256: str | None = None,
        family_sessions: Mapping[str, Mapping[str, Any]] | None = None,
        regular_entry_open: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        if (
            self.sleeve_ledger_store is None
            or self.contract_ownership_store is None
            or self.product_certification_store is None
        ):
            raise AutonomousStateBuildError("V4_STATE_DEPENDENCIES_REQUIRED")
        ledger = self._dump(self.sleeve_ledger_store.project_all())
        continuous_ledger = ledger.get("continuous") or ledger.get("extended") or {}
        canonical_ledger = {
            "regular": ledger.get("regular") or {},
            "continuous": continuous_ledger,
        }
        if not all(
            bool((canonical_ledger.get(name) or {}).get("initialized"))
            for name in ("regular", "continuous")
        ):
            raise AutonomousStateBuildError("V4_SLEEVE_BOOTSTRAP_REQUIRED")
        ownership_projection = self._dump(
            self.contract_ownership_store.projection()
        )
        capabilities = [
            self._dump(item)
            for item in self.product_certification_store.projections()
        ]
        capability_by_sha = {
            str(item.get("family_sha256") or ""): item
            for item in capabilities
            if item.get("family_sha256")
        }
        authenticated_sessions = {
            family_sha: dict(evidence)
            for family_sha, evidence in sorted((family_sessions or {}).items())
            if family_sha in capability_by_sha
            and isinstance(evidence, Mapping)
        }
        executable_family_sha256 = sorted(
            family_sha
            for family_sha, item in capability_by_sha.items()
            if item.get("executable") is True
        )
        open_family_sha256 = sorted(
            family_sha
            for family_sha in executable_family_sha256
            if (authenticated_sessions.get(family_sha) or {}).get("authenticated")
            is True
            and (
                (authenticated_sessions.get(family_sha) or {}).get("tradable_now")
                is True
                or str(
                    (authenticated_sessions.get(family_sha) or {}).get("session")
                    or ""
                ).upper()
                == "REGULAR"
            )
        )
        eligible_families_by_sleeve: dict[str, list[str]] = {
            CapitalSleeve.REGULAR_SLEEVE.value: [],
            CapitalSleeve.CONTINUOUS_SLEEVE.value: [],
        }
        for family_sha in open_family_sha256:
            declared = tuple(
                str(item)
                for item in (
                    authenticated_sessions[family_sha].get("eligible_sleeves")
                    or (CapitalSleeve.CONTINUOUS_SLEEVE.value,)
                )
            )
            for sleeve_name in declared:
                if sleeve_name in eligible_families_by_sleeve:
                    eligible_families_by_sleeve[sleeve_name].append(family_sha)
        regular_eligible_families = eligible_families_by_sleeve[
            CapitalSleeve.REGULAR_SLEEVE.value
        ]
        continuous_eligible_families = eligible_families_by_sleeve[
            CapitalSleeve.CONTINUOUS_SLEEVE.value
        ]
        phase_active = transition_phase == TransitionPhase.ACTIVE.value
        reconciliation_pass = reconciliation.get("status") == "PASS"

        def entry_eligibility(
            *, available: bool, eligible_families: list[str]
        ) -> dict[str, Any]:
            reasons: list[str] = []
            if not phase_active:
                reasons.append("SUCCESSOR_NOT_ACTIVE")
            if not reconciliation_pass:
                reasons.append("BROKER_RECONCILIATION_REQUIRED")
            if not available:
                reasons.append("FAMILY_SESSION_CLOSED")
            return {
                "status": "PASS" if not reasons else "BLOCK",
                "reason_codes": reasons,
                "eligible_family_sha256": eligible_families,
            }

        contract_sleeves: dict[str, str] = {}
        management_eligibility: dict[str, dict[str, Any]] = {}
        account_positions = list(broker_positions.get("positions", []) or [])
        account_orders = list(open_orders.get("open_orders", []) or [])

        def observed_contract_id(raw: Mapping[str, Any]) -> int:
            contract = raw.get("contract") or {}
            return int(
                raw.get("contract_id")
                or raw.get("con_id")
                or contract.get("conId")
                or contract.get("con_id")
                or 0
            )

        for item in ownership_projection.get("active_contracts", []):
            contract = item.get("contract") or {}
            contract_id = int(
                contract.get("con_id") or contract.get("conId") or 0
            )
            if contract_id > 0:
                contract_sleeves[str(contract_id)] = str(item.get("sleeve") or "")
                observations = [
                    raw
                    for raw in (*account_positions, *account_orders)
                    if observed_contract_id(raw) == contract_id
                ]
                owner_sleeve = str(item.get("sleeve") or "")
                explicitly_manageable = any(
                    raw.get("management_tradable") is True for raw in observations
                )
                observed_families = {
                    str(raw.get("product_family_sha256") or "")
                    for raw in observations
                    if raw.get("product_family_sha256")
                }
                manageable = bool(
                    explicitly_manageable
                    or (
                        owner_sleeve == CapitalSleeve.REGULAR_SLEEVE.value
                        and regular_entry_open
                    )
                    or observed_families.intersection(
                        continuous_eligible_families
                    )
                )
                management_eligibility[str(contract_id)] = {
                    "status": "PASS" if manageable else "BLOCK",
                    "reason_codes": (
                        []
                        if manageable
                        else ["INSTRUMENT_NOT_CURRENTLY_MANAGEABLE"]
                    ),
                    "capital_sleeve": owner_sleeve,
                    "contract_identity_sha256": item.get(
                        "contract_identity_sha256"
                    ),
                }
        redacted_account = {
            key: value
            for key, value in account.items()
            if key.lower() not in {"account", "account_id", "account_code"}
        }
        portfolio = {
            "schema": "MULTI_SLEEVE_PORTFOLIO_V4",
            "sleeves": {
                name: {
                    **dict(canonical_ledger.get(name) or {}),
                    "equity_usd": str(
                        Decimal(str((canonical_ledger.get(name) or {}).get("allocation_usd") or "0"))
                        + Decimal(str((canonical_ledger.get(name) or {}).get("realized_pnl_usd") or "0"))
                        + Decimal(str((canonical_ledger.get(name) or {}).get("unrealized_pnl_usd") or "0"))
                        - Decimal(str((canonical_ledger.get(name) or {}).get("fees_usd") or "0"))
                    ),
                }
                for name in ("regular", "continuous")
            },
            "transition_phase": transition_phase,
            "transition_target_sha256": transition_target_sha256,
            "writer_binding_sha256": writer_binding_sha256,
            "entry_eligibility": {
                CapitalSleeve.REGULAR_SLEEVE.value: entry_eligibility(
                    available=(
                        regular_entry_open and bool(regular_eligible_families)
                    ),
                    eligible_families=regular_eligible_families,
                ),
                CapitalSleeve.CONTINUOUS_SLEEVE.value: entry_eligibility(
                    available=bool(continuous_eligible_families),
                    eligible_families=continuous_eligible_families,
                ),
            },
            "management_eligibility": management_eligibility,
            "aggregate_currency_balances": ledger.get(
                "aggregate_currency_balances", []
            ),
            "account_observation": {
                "authority": False,
                "account_state": redacted_account,
                "positions": account_positions,
                "open_orders": account_orders,
                "position_count": len(account_positions),
                "open_order_count": len(account_orders),
            },
            "reconciliation": dict(reconciliation),
            "new_entries_enabled": reconciliation.get("status") == "PASS",
        }
        ownership = {
            **ownership_projection,
            "contract_sleeves": contract_sleeves,
        }
        capability_snapshot = {
            "families": capabilities,
            "executable_family_sha256": executable_family_sha256,
            "authenticated_sessions": authenticated_sessions,
        }
        return portfolio, ownership, capability_snapshot

    def _multi_universe_transition_context(self) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT phase,payload_json FROM successor_transition_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return {
                "phase": TransitionPhase.PREPARED.value,
                "target_sha256": None,
                "writer_binding_sha256": None,
            }
        try:
            payload = json.loads(str(row[1]))
            target = dict(payload.get("target") or {})
            phase = TransitionPhase(str(row[0])).value
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AutonomousStateBuildError(
                "TRANSITION_PROJECTION_AMBIGUOUS"
            ) from exc
        return {
            "phase": phase,
            "target_sha256": payload.get("target_sha256"),
            "writer_binding_sha256": target.get("writer_binding_sha256"),
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
        if self.sleeve_ledger_store is not None:
            reconciliation = self._sync_and_reconcile_v4(
                account=account,
                broker_positions=broker_positions,
                open_orders=open_orders,
            )
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
        projected_benchmark_state = dict(benchmark_state or {})
        projected_benchmark_state["autonomous_process_observation"] = (
            self._process_observation(
                positions_snapshot=isolated_positions,
                equity=ledger_state.equity,
            )
        )
        multi_sleeve_portfolio = None
        contract_ownership_snapshot = None
        product_capability_snapshot = None
        if self.sleeve_ledger_store is not None:
            transition = self._multi_universe_transition_context()
            session_evidence: dict[str, Any] = {}
            if self.session_evidence_reader is not None:
                try:
                    session_evidence = dict(self.session_evidence_reader() or {})
                except Exception:
                    session_evidence = {}
            (
                multi_sleeve_portfolio,
                contract_ownership_snapshot,
                product_capability_snapshot,
            ) = self._multi_sleeve_context(
                reconciliation=reconciliation,
                account=account,
                broker_positions=broker_positions,
                open_orders=open_orders,
                transition_phase=str(transition["phase"]),
                transition_target_sha256=transition["target_sha256"],
                writer_binding_sha256=transition["writer_binding_sha256"],
                family_sessions=(session_evidence.get("family_sessions") or {}),
                regular_entry_open=(
                    market_gate.get("gate_status") == "PASS"
                    and (
                        market_session_state.upper() == "REGULAR"
                        or str(session_evidence.get("session") or "").upper()
                        == "REGULAR"
                    )
                ),
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
            benchmark_state=projected_benchmark_state,
            experiment_clock=clock,
            continuity_context=self._continuity_context(
                clock,
                open_orders_snapshot=isolated_orders,
                positions_snapshot=isolated_positions,
            ),
            multi_sleeve_portfolio=multi_sleeve_portfolio,
            contract_ownership_snapshot=contract_ownership_snapshot,
            product_capability_snapshot=product_capability_snapshot,
        )
