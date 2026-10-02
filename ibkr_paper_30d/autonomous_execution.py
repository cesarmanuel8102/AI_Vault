from __future__ import annotations

import copy
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timezone
from decimal import Decimal
from typing import Any, Callable

from .autonomous_research import (
    AutonomousOpenOrderAction,
    AutonomousPositionAction,
    AutonomousTradeProposal,
)
from .canonical import canonical_bytes, sha256_json
from .continuity_binding import (
    ContinuityBindingError,
    ContinuityBindingService,
    PendingContinuityBinding,
)
from .continuity_models import CodexOrderContinuityPlan
from .ibkr_research_tools import IBKRResearchToolbox
from .open_order_management import (
    ACTIONABLE_ORDER_STATUSES,
    CANCELLED_ORDER_STATUSES,
    EXECUTION_CLIENT_ID,
    EXPERIMENT_ORDER_PREFIX,
    OpenOrderOwnershipError,
    append_order_registry_event,
    canonical_contract_identity,
    canonical_open_order,
    lifecycle_attempt_exists,
    preserved_open_order_sha256,
    resolve_owned_open_trade,
)
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7
from .trader_invocation import TraderDecision, TraderInputBundle


class AutonomousPaperExecutionNotArmed(PermissionError):
    pass


@dataclass(frozen=True)
class PaperExecutionResult:
    success: bool
    status: str
    reason_codes: tuple[str, ...]
    order: dict[str, Any]
    broker_validation: dict[str, Any]


class WriterOwnedModelExecutionMechanics:
    """Paper-only executor for an already researched Codex proposal.

    No strategy-level percentage caps are enforced here. Immediately before
    transmission, the proposal is revalidated against the current isolated
    experimental equity and IBKR what-if feasibility.
    """

    execution_client_id = EXECUTION_CLIENT_ID

    def __init__(
        self,
        toolbox: IBKRResearchToolbox,
        *,
        armed: bool | None = None,
        fill_wait_seconds: float = 3.0,
        database: Database | None = None,
        fresh_safety_check: Callable[[str], tuple[str, ...]] | None = None,
        operator_control_check: Callable[[], tuple[str, ...]] | None = None,
        continuity_binding_service: ContinuityBindingService | None = None,
    ) -> None:
        self.toolbox = toolbox
        self.armed = (
            os.environ.get("IBKR_AUTONOMOUS_PAPER_ARMED", "false").lower() == "true"
            if armed is None
            else bool(armed)
        )
        self.fill_wait_seconds = fill_wait_seconds
        self.database = database
        self.fresh_safety_check = fresh_safety_check
        self.operator_control_check = operator_control_check
        self.continuity_binding_service = continuity_binding_service
        self._writer_owned_broker: Any | None = None
        self._final_write_authority_check: Callable[[], tuple[str, ...]] | None = None

    @staticmethod
    def _fills_payload(
        trade: Any,
        *,
        fallback_order_ref: str = "",
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        trade_order = getattr(trade, "order", None)
        for fill in getattr(trade, "fills", []) or []:
            execution = getattr(fill, "execution", None)
            contract = getattr(fill, "contract", None)
            commission_report = getattr(fill, "commissionReport", None)
            raw_side = str(getattr(execution, "side", "") or "").upper()
            side = "BUY" if raw_side in {"BOT", "BUY"} else "SELL" if raw_side in {"SLD", "SELL"} else raw_side
            execution_id = str(getattr(execution, "execId", "") or "")
            import hashlib
            items.append({
                "execution_id_hash": hashlib.sha256(execution_id.encode("utf-8")).hexdigest() if execution_id else None,
                "orderRef": str(
                    getattr(execution, "orderRef", "")
                    or fallback_order_ref
                    or getattr(trade_order, "orderRef", "")
                    or ""
                ),
                "permId": int(
                    getattr(execution, "permId", 0)
                    or getattr(trade_order, "permId", 0)
                    or 0
                ),
                "orderId": int(
                    getattr(execution, "orderId", 0)
                    or getattr(trade_order, "orderId", 0)
                    or 0
                ),
                "clientId": int(
                    getattr(execution, "clientId", 0)
                    or getattr(trade_order, "clientId", 0)
                    or 0
                ),
                "account": str(
                    getattr(execution, "acctNumber", "")
                    or getattr(trade_order, "account", "")
                    or ""
                ),
                "execution_time": str(getattr(execution, "time", "") or ""),
                "cumQty": str(getattr(execution, "cumQty", "") or ""),
                "avgPrice": str(getattr(execution, "avgPrice", "") or ""),
                "side": side,
                "quantity": str(getattr(execution, "shares", "") or ""),
                "price": str(getattr(execution, "price", "") or ""),
                "commission": (
                    None
                    if commission_report is None
                    else str(getattr(commission_report, "commission", 0))
                ),
                "contract": {
                    "conId": int(getattr(contract, "conId", 0) or 0),
                    "symbol": str(getattr(contract, "symbol", "") or ""),
                    "localSymbol": str(getattr(contract, "localSymbol", "") or ""),
                    "secType": str(getattr(contract, "secType", "") or ""),
                    "exchange": str(getattr(contract, "exchange", "") or ""),
                    "currency": str(getattr(contract, "currency", "") or ""),
                    "expiry": str(getattr(contract, "lastTradeDateOrContractMonth", "") or ""),
                    "strike": str(getattr(contract, "strike", 0) or 0),
                    "right": str(getattr(contract, "right", "") or ""),
                    "multiplier": str(getattr(contract, "multiplier", "") or "1"),
                },
            })
        return items

    def _fresh_safety_reasons(self, scope: str) -> tuple[str, ...]:
        if self.fresh_safety_check is None:
            return ("FRESH_SAFETY_CHECK_REQUIRED",)
        try:
            return tuple(self.fresh_safety_check(scope))
        except Exception as exc:
            return (f"FRESH_SAFETY_CHECK_FAILED:{type(exc).__name__}",)

    def _operator_control_reasons(self) -> tuple[str, ...]:
        if self.operator_control_check is None:
            return ("FRESH_OPERATOR_CONTROL_CHECK_REQUIRED",)
        try:
            return tuple(self.operator_control_check())
        except Exception as exc:
            return (f"FRESH_OPERATOR_CONTROL_CHECK_FAILED:{type(exc).__name__}",)

    def _final_write_authority_reasons(self) -> tuple[str, ...]:
        if self._final_write_authority_check is None:
            return ()
        try:
            return tuple(self._final_write_authority_check())
        except Exception as exc:
            return (f"FINAL_WRITE_AUTHORITY_CHECK_FAILED:{type(exc).__name__}",)

    def _connect_execution(self):
        if self._writer_owned_broker is None:
            raise AutonomousPaperExecutionNotArmed("WRITER_OWNED_BROKER_REQUIRED")
        return self._writer_owned_broker

    def _disconnect_execution(self, ib: Any) -> None:
        if ib is not self._writer_owned_broker:
            raise RuntimeError("WRITER_BROKER_IDENTITY_MISMATCH")

    @contextmanager
    def _using_writer_owned_broker(
        self,
        broker: Any,
        final_write_authority_check: Callable[[], tuple[str, ...]] | None,
    ):
        if broker is None:
            raise ValueError("writer-owned broker is required")
        if self._writer_owned_broker is not None:
            raise RuntimeError("WRITER_BROKER_ALREADY_BOUND")
        self._writer_owned_broker = broker
        self._final_write_authority_check = final_write_authority_check
        try:
            yield
        finally:
            self._final_write_authority_check = None
            self._writer_owned_broker = None

    def execute_with_broker(
        self,
        broker: Any,
        proposal: AutonomousTradeProposal,
        bundle: TraderInputBundle,
        *,
        continuity_plan: CodexOrderContinuityPlan | None = None,
        invocation_id: str | None = None,
        final_write_authority_check: Callable[[], tuple[str, ...]] | None = None,
    ) -> PaperExecutionResult:
        with self._using_writer_owned_broker(broker, final_write_authority_check):
            return self.execute(
                proposal,
                bundle,
                continuity_plan=continuity_plan,
                invocation_id=invocation_id,
            )

    def execute_open_order_action_with_broker(
        self,
        broker: Any,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
        decision: TraderDecision,
        *,
        invocation_id: str | None = None,
        final_write_authority_check: Callable[[], tuple[str, ...]] | None = None,
    ) -> PaperExecutionResult:
        with self._using_writer_owned_broker(broker, final_write_authority_check):
            return self.execute_open_order_action(
                action,
                bundle,
                decision,
                invocation_id=invocation_id,
            )

    def execute_position_action_with_broker(
        self,
        broker: Any,
        action: AutonomousPositionAction,
        bundle: TraderInputBundle,
        decision: TraderDecision,
        *,
        final_write_authority_check: Callable[[], tuple[str, ...]] | None = None,
    ) -> PaperExecutionResult:
        with self._using_writer_owned_broker(broker, final_write_authority_check):
            return self.execute_position_action(action, bundle, decision)

    def _reconcile_post_send_trade(
        self,
        ib: Any,
        trade: Any,
        *,
        submitted_contract: Any,
        order_ref: str,
    ) -> Any:
        trade_identity = canonical_contract_identity(trade.contract)
        needs_resolved_bag_identity = (
            trade_identity["secType"] == "BAG" and trade_identity["conId"] <= 0
        )
        if (
            int(getattr(trade.order, "permId", 0) or 0) > 0
            and not needs_resolved_bag_identity
        ):
            return trade
        reader = ib
        auxiliary = None
        if self._writer_owned_broker is None:
            try:
                auxiliary = self.toolbox._connect()
                if auxiliary is not None:
                    reader = auxiliary
            except Exception:
                auxiliary = None
        request_open_orders = getattr(reader, "reqAllOpenOrders", None)
        if not callable(request_open_orders):
            if reader is not ib:
                reader.disconnect()
            return trade

        submitted_order = trade.order
        submitted_identity = canonical_contract_identity(submitted_contract)
        submitted_quantity = Decimal(
            str(getattr(submitted_order, "totalQuantity", 0) or 0)
        )
        try:
            for attempt in range(20):
                candidates = list(request_open_orders())
                exact = []
                for candidate in candidates:
                    snapshot = canonical_open_order(candidate)
                    contract_identity = snapshot["contract"]
                    if submitted_identity["secType"] == "BAG":
                        contract_matches = (
                            contract_identity["secType"] == "BAG"
                            and contract_identity["symbol"]
                            == submitted_identity["symbol"]
                            and contract_identity["currency"]
                            == submitted_identity["currency"]
                            and contract_identity["comboLegs"]
                            == submitted_identity["comboLegs"]
                            and contract_identity["conId"] > 0
                        )
                    else:
                        contract_matches = (
                            contract_identity["conId"]
                            == submitted_identity["conId"]
                            and contract_identity["conId"] > 0
                        )
                    if (
                        snapshot["orderRef"] == order_ref
                        and snapshot["orderId"]
                        == int(getattr(submitted_order, "orderId", 0) or 0)
                        and snapshot["clientId"] == self.execution_client_id
                        and snapshot["account"]
                        == str(getattr(submitted_order, "account", "") or "")
                        and snapshot["action"]
                        == str(getattr(submitted_order, "action", "") or "").upper()
                        and Decimal(snapshot["totalQuantity"])
                        == submitted_quantity
                        and snapshot["permId"] > 0
                        and contract_matches
                    ):
                        exact.append(candidate)
                if len(exact) == 1:
                    return exact[0]
                if len(exact) > 1:
                    break
                if attempt < 19:
                    reader.sleep(0.5)
        except Exception:
            pass
        finally:
            if reader is not ib:
                try:
                    reader.disconnect()
                except Exception:  # nosec B110
                    pass
        return trade

    @staticmethod
    def _execution_account(ib: Any) -> str:
        accounts = list(ib.managedAccounts())
        if len(accounts) != 1 or not str(accounts[0]).upper().startswith("DU"):
            raise PermissionError("single DU paper account identity required")
        return str(accounts[0])

    def _register_order(
        self,
        *,
        order: Any,
        contract: Any,
        order_ref: str,
        action: str,
        quantity: Decimal,
        lifecycle_event: str,
    ) -> None:
        if self.database is None:
            raise RuntimeError("persistent database required for armed paper execution")
        account = str(getattr(order, "account", "") or "")
        if not account:
            raise RuntimeError("order account identity required")
        payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
            "order_ref": order_ref,
            "client_order_id": int(getattr(order, "orderId", 0) or 0),
            "perm_id": int(getattr(order, "permId", 0) or 0),
            "ibkr_order_id": int(getattr(order, "orderId", 0) or 0),
            "contract_id": int(getattr(contract, "conId", 0) or 0),
            "action": action,
            "quantity": str(quantity),
            "execution_client_id": self.execution_client_id,
            "account": account,
            "contract": canonical_contract_identity(contract),
            "lifecycle_event": lifecycle_event,
            "created_at_utc": utc_now(),
        }
        append_order_registry_event(self.database, payload)

    @staticmethod
    def _broker_bound_identity_available(trade: Any) -> bool:
        identity = canonical_contract_identity(trade.contract)
        return int(getattr(trade.order, "permId", 0) or 0) > 0 and (
            identity["secType"] != "BAG" or identity["conId"] > 0
        )

    def _register_lifecycle_event(
        self,
        *,
        lifecycle_event: str,
        decision: TraderDecision,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
        snapshot: dict[str, Any],
        reason_codes: tuple[str, ...] = (),
        broker_evidence: dict[str, Any] | None = None,
        invocation_id: str | None = None,
    ) -> None:
        if self.database is None:
            raise RuntimeError("persistent database required for lifecycle evidence")
        payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_LIFECYCLE_V1",
            "lifecycle_event": lifecycle_event,
            "decision_cycle_id": bundle.decision_cycle_id,
            "decision": decision.value,
            "order_ref": action.order_ref,
            "order_id": action.order_id,
            "perm_id": action.perm_id,
            "execution_client_id": self.execution_client_id,
            "account": snapshot.get("account", ""),
            "contract_id": action.contract_id,
            "side": snapshot.get("action", ""),
            "quantity": snapshot.get("totalQuantity", "0"),
            "observed_state_sha256": action.observed_state_sha256,
            "reason_codes": list(reason_codes),
            "broker_evidence": broker_evidence or {},
            "previous_snapshot": snapshot,
            "requested_change": {
                "new_total_quantity": (
                    None
                    if action.new_total_quantity is None
                    else str(action.new_total_quantity)
                ),
                "new_limit_price": (
                    None
                    if action.new_limit_price is None
                    else str(action.new_limit_price)
                ),
            },
            "action_invocation_id": invocation_id
            or f"{bundle.decision_cycle_id}:{decision.value}:{action.order_id}",
            "confirmation_state_sha256": (
                (broker_evidence or {})
                .get("post_action_reconciliation", {})
                .get("confirmed_state_sha256")
            ),
            "created_at_utc": utc_now(),
        }
        self.database.execute(
            "INSERT INTO experiment_order_registry("
            "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
            "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(new_uuid7()),
                action.order_ref,
                action.order_id,
                int(action.perm_id or 0),
                action.order_id,
                action.contract_id,
                str(snapshot.get("action") or ""),
                str(snapshot.get("totalQuantity") or "0"),
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                utc_now(),
            ),
        )

    @staticmethod
    def _frozen_bundle_reasons(bundle: TraderInputBundle) -> tuple[str, ...]:
        reasons = []
        if bundle.reconciliation_receipt.get("status") != "PASS":
            reasons.append("BROKER_RECONCILIATION_REQUIRED")
        if bundle.kill_switch_state != "KILL_SWITCH_CLEAR":
            reasons.append("KILL_SWITCH_TRIGGERED")
        if bundle.market_data_snapshot.get("gate_status") != "PASS":
            reasons.append("MARKET_DATA_GATE_BLOCK")
        return tuple(reasons)

    def execute_open_order_action(
        self,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
        decision: TraderDecision,
        *,
        invocation_id: str | None = None,
    ) -> PaperExecutionResult:
        if decision == TraderDecision.CANCEL_ORDER:
            return self._cancel_open_order(
                action, bundle, invocation_id=invocation_id
            )
        if decision == TraderDecision.MODIFY_ORDER:
            return self._modify_open_order(
                action, bundle, invocation_id=invocation_id
            )
        raise ValueError("unsupported open-order decision")

    def _modify_open_order(
        self,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
        *,
        invocation_id: str | None = None,
    ) -> PaperExecutionResult:
        if not self.armed:
            raise AutonomousPaperExecutionNotArmed(
                "set IBKR_AUTONOMOUS_PAPER_ARMED=true only when the paper experiment is explicitly started"
            )
        frozen_reasons = self._frozen_bundle_reasons(bundle)
        if frozen_reasons:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=frozen_reasons,
                order={},
                broker_validation={},
            )
        if self.database is None:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=("PERSISTENT_ORDER_REGISTRY_REQUIRED",),
                order={},
                broker_validation={},
            )
        fresh_reasons = self._fresh_safety_reasons("OPEN_ORDER_MANAGEMENT")
        if fresh_reasons:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=fresh_reasons,
                order={},
                broker_validation={},
            )

        try:
            ib = self._connect_execution()
        except Exception:
            try:
                ib = self._connect_execution()
            except Exception as exc:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=(f"BROKER_CONNECTION_FAILED:{type(exc).__name__}",),
                    order={},
                    broker_validation={},
                )

        try:
            trades = list(ib.reqOpenOrders())
            if lifecycle_attempt_exists(
                self.database,
                order_ref=action.order_ref,
                decision_cycle_id=bundle.decision_cycle_id,
            ):
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("DUPLICATE_ORDER_ACTION_REQUEST",),
                    order={},
                    broker_validation={},
                )
            try:
                selected_trade, snapshot = resolve_owned_open_trade(
                    self.database,
                    trades,
                    action,
                    execution_client_id=self.execution_client_id,
                )
            except OpenOrderOwnershipError as exc:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=(exc.reason_code,),
                    order={},
                    broker_validation={},
                )

            validation = self.toolbox.validate_open_order_action(
                action,
                bundle,
                TraderDecision.MODIFY_ORDER,
                ib=ib,
            )
            if not validation.passed:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=validation.reason_codes,
                    order={},
                    broker_validation=validation.broker_evidence,
                )

            try:
                selected_trade, refreshed_snapshot = resolve_owned_open_trade(
                    self.database,
                    list(ib.reqOpenOrders()),
                    action,
                    execution_client_id=self.execution_client_id,
                )
            except OpenOrderOwnershipError as exc:
                reason = (
                    "OPEN_ORDER_STATE_CHANGED_AFTER_WHAT_IF"
                    if exc.reason_code == "OPEN_ORDER_STATE_CHANGED"
                    else exc.reason_code
                )
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=(reason,),
                    order={},
                    broker_validation=validation.broker_evidence,
                )

            operator_reasons = self._operator_control_reasons()
            if operator_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=operator_reasons,
                    order={},
                    broker_validation=validation.broker_evidence,
                )

            requested_total = (
                action.new_total_quantity
                if action.new_total_quantity is not None
                else Decimal(refreshed_snapshot["totalQuantity"])
            )
            requested_limit = (
                action.new_limit_price
                if action.new_limit_price is not None
                else Decimal(refreshed_snapshot["limitPrice"])
            )
            requested_tif = (
                action.new_tif.value
                if action.new_tif is not None
                else str(refreshed_snapshot["tif"])
            )
            requested_good_till = (
                action.new_good_till_date_utc.astimezone(timezone.utc).strftime(
                    "%Y%m%d %H:%M:%S UTC"
                )
                if action.new_good_till_date_utc is not None
                else str(
                    (refreshed_snapshot.get("orderAttributes") or {}).get(
                        "goodTillDate"
                    )
                    or ""
                )
            )
            expected_preserved_sha256 = preserved_open_order_sha256(
                refreshed_snapshot
            )
            modified = copy.deepcopy(selected_trade.order)
            modified.totalQuantity = float(requested_total)
            if action.new_limit_price is not None:
                modified.lmtPrice = float(requested_limit)
            if action.new_tif is not None:
                modified.tif = requested_tif
                modified.goodTillDate = requested_good_till

            final_authority_reasons = self._final_write_authority_reasons()
            if final_authority_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=final_authority_reasons,
                    order={},
                    broker_validation=validation.broker_evidence,
                )

            try:
                self._register_lifecycle_event(
                    lifecycle_event="MODIFY_ATTEMPT",
                    decision=TraderDecision.MODIFY_ORDER,
                    action=action,
                    bundle=bundle,
                    snapshot=refreshed_snapshot,
                    broker_evidence=validation.broker_evidence,
                    invocation_id=invocation_id,
                )
            except sqlite3.IntegrityError as exc:
                if "experiment_order_registry_action_cycle" in str(exc):
                    return PaperExecutionResult(
                        success=False,
                        status="BLOCKED",
                        reason_codes=("DUPLICATE_ORDER_ACTION_REQUEST",),
                        order={},
                        broker_validation=validation.broker_evidence,
                    )
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("LIFECYCLE_ATTEMPT_PERSISTENCE_FAILED",),
                    order={},
                    broker_validation=validation.broker_evidence,
                )
            except Exception:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("LIFECYCLE_ATTEMPT_PERSISTENCE_FAILED",),
                    order={},
                    broker_validation=validation.broker_evidence,
                )

            try:
                ib.placeOrder(selected_trade.contract, modified)
            except Exception as exc:
                return self._modify_result(
                    action=action,
                    bundle=bundle,
                    snapshot=refreshed_snapshot,
                    success=False,
                    status="UNCERTAIN",
                    reason_codes=("BROKER_CONFIRMATION_UNAVAILABLE",),
                    post_action_reconciliation={
                        "acknowledged": False,
                        "confirmation_stage": "BROKER_INVOCATION",
                    },
                    broker_evidence={
                        **validation.broker_evidence,
                        "confirmation_stage": "BROKER_INVOCATION",
                        "exception_type": type(exc).__name__,
                    },
                    invocation_id=invocation_id,
                )
            try:
                ib.sleep(self.fill_wait_seconds)
                post_trades = list(ib.reqOpenOrders())
                post_snapshots = [canonical_open_order(item) for item in post_trades]
                matching = [
                    item
                    for item in post_snapshots
                    if item["orderRef"] == action.order_ref
                    and item["orderId"] == action.order_id
                    and item["clientId"] == action.client_id
                    and item["contract"]["conId"] == action.contract_id
                ]
                confirmed_state = matching[0] if len(matching) == 1 else None
                confirmed_preserved_sha256 = (
                    preserved_open_order_sha256(confirmed_state)
                    if confirmed_state is not None
                    else None
                )
                preserved_state_matches = (
                    confirmed_preserved_sha256 == expected_preserved_sha256
                )
                acknowledged = (
                    len(matching) == 1
                    and Decimal(matching[0]["totalQuantity"]) == requested_total
                    and Decimal(matching[0]["limitPrice"]) == requested_limit
                    and matching[0]["tif"] == requested_tif
                    and str(
                        (matching[0].get("orderAttributes") or {}).get(
                            "goodTillDate"
                        )
                        or ""
                    )
                    == requested_good_till
                    and matching[0]["status"].upper() in ACTIONABLE_ORDER_STATUSES
                    and preserved_state_matches
                )
                post_reconciliation = {
                    "acknowledged": acknowledged,
                    "matching_order_count": len(matching),
                    "requested_total_quantity": str(requested_total),
                    "requested_limit_price": str(requested_limit),
                    "requested_tif": requested_tif,
                    "requested_good_till_date": requested_good_till,
                    "confirmed_state": confirmed_state,
                    "confirmed_state_sha256": (
                        confirmed_state.get("state_sha256")
                        if confirmed_state is not None
                        else None
                    ),
                    "expected_preserved_state_sha256": expected_preserved_sha256,
                    "confirmed_preserved_state_sha256": confirmed_preserved_sha256,
                    "preserved_state_matches": preserved_state_matches,
                }
            except Exception as exc:
                return self._modify_result(
                    action=action,
                    bundle=bundle,
                    snapshot=refreshed_snapshot,
                    success=False,
                    status="UNCERTAIN",
                    reason_codes=("BROKER_CONFIRMATION_UNAVAILABLE",),
                    post_action_reconciliation={
                        "acknowledged": False,
                        "confirmation_stage": "POST_WRITE_RECONCILIATION",
                    },
                    broker_evidence={
                        **validation.broker_evidence,
                        "confirmation_stage": "POST_WRITE_RECONCILIATION",
                        "exception_type": type(exc).__name__,
                    },
                    invocation_id=invocation_id,
                )
            reasons = () if acknowledged else ("BROKER_MODIFICATION_UNCONFIRMED",)
            return self._modify_result(
                action=action,
                bundle=bundle,
                snapshot=refreshed_snapshot,
                success=acknowledged,
                status="SUBMITTED" if acknowledged else "UNCERTAIN",
                reason_codes=reasons,
                post_action_reconciliation=post_reconciliation,
                broker_evidence=validation.broker_evidence,
                invocation_id=invocation_id,
            )
        finally:
            try:
                self._disconnect_execution(ib)
            # Durable broker confirmation is authoritative; teardown is best effort.
            except Exception:  # nosec B110
                pass

    def _modify_result(
        self,
        *,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
        snapshot: dict[str, Any],
        success: bool,
        status: str,
        reason_codes: tuple[str, ...],
        post_action_reconciliation: dict[str, Any],
        broker_evidence: dict[str, Any],
        invocation_id: str | None = None,
    ) -> PaperExecutionResult:
        evidence = {
            **broker_evidence,
            "post_action_reconciliation": post_action_reconciliation,
        }
        try:
            self._register_lifecycle_event(
                lifecycle_event="MODIFY_RESULT",
                decision=TraderDecision.MODIFY_ORDER,
                action=action,
                bundle=bundle,
                snapshot=snapshot,
                reason_codes=reason_codes,
                broker_evidence=evidence,
                invocation_id=invocation_id,
            )
        except Exception:
            return PaperExecutionResult(
                success=False,
                status="UNCERTAIN",
                reason_codes=("LIFECYCLE_RESULT_PERSISTENCE_FAILED",),
                order={
                    "order_management": TraderDecision.MODIFY_ORDER.value,
                    "pre_action_state": snapshot,
                    "post_action_reconciliation": post_action_reconciliation,
                },
                broker_validation=evidence,
            )
        return PaperExecutionResult(
            success=success,
            status=status,
            reason_codes=reason_codes,
            order={
                "order_management": TraderDecision.MODIFY_ORDER.value,
                "pre_action_state": snapshot,
                "post_action_reconciliation": post_action_reconciliation,
            },
            broker_validation=evidence,
        )

    def _cancel_open_order(
        self,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
        *,
        invocation_id: str | None = None,
    ) -> PaperExecutionResult:
        if not self.armed:
            raise AutonomousPaperExecutionNotArmed(
                "set IBKR_AUTONOMOUS_PAPER_ARMED=true only when the paper experiment is explicitly started"
            )
        frozen_reasons = self._frozen_bundle_reasons(bundle)
        if frozen_reasons:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=frozen_reasons,
                order={},
                broker_validation={},
            )
        if self.database is None:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=("PERSISTENT_ORDER_REGISTRY_REQUIRED",),
                order={},
                broker_validation={},
            )
        fresh_reasons = self._fresh_safety_reasons("OPEN_ORDER_MANAGEMENT")
        if fresh_reasons:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=fresh_reasons,
                order={},
                broker_validation={},
            )

        try:
            ib = self._connect_execution()
        except Exception:
            try:
                ib = self._connect_execution()
            except Exception as exc:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=(f"BROKER_CONNECTION_FAILED:{type(exc).__name__}",),
                    order={},
                    broker_validation={},
                )

        try:
            trades = list(ib.reqOpenOrders())
            if lifecycle_attempt_exists(
                self.database,
                order_ref=action.order_ref,
                decision_cycle_id=bundle.decision_cycle_id,
            ):
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("DUPLICATE_ORDER_ACTION_REQUEST",),
                    order={},
                    broker_validation={},
                )
            try:
                selected_trade, snapshot = resolve_owned_open_trade(
                    self.database,
                    trades,
                    action,
                    execution_client_id=self.execution_client_id,
                )
            except OpenOrderOwnershipError as exc:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=(exc.reason_code,),
                    order={},
                    broker_validation={},
                )

            operator_reasons = self._operator_control_reasons()
            if operator_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=operator_reasons,
                    order={},
                    broker_validation={},
                )
            final_authority_reasons = self._final_write_authority_reasons()
            if final_authority_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=final_authority_reasons,
                    order={},
                    broker_validation={},
                )
            try:
                self._register_lifecycle_event(
                    lifecycle_event="CANCEL_ATTEMPT",
                    decision=TraderDecision.CANCEL_ORDER,
                    action=action,
                    bundle=bundle,
                    snapshot=snapshot,
                    invocation_id=invocation_id,
                )
            except sqlite3.IntegrityError as exc:
                if "experiment_order_registry_action_cycle" in str(exc):
                    return PaperExecutionResult(
                        success=False,
                        status="BLOCKED",
                        reason_codes=("DUPLICATE_ORDER_ACTION_REQUEST",),
                        order={},
                        broker_validation={},
                    )
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("LIFECYCLE_ATTEMPT_PERSISTENCE_FAILED",),
                    order={},
                    broker_validation={},
                )
            except Exception:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("LIFECYCLE_ATTEMPT_PERSISTENCE_FAILED",),
                    order={},
                    broker_validation={},
                )

            try:
                ib.cancelOrder(selected_trade.order)
            except Exception as exc:
                return self._cancel_result(
                    action=action,
                    bundle=bundle,
                    snapshot=snapshot,
                    success=False,
                    status="UNCERTAIN",
                    reason_codes=("BROKER_CONFIRMATION_UNAVAILABLE",),
                    post_action_reconciliation={
                        "target_actionable": True,
                        "confirmation_stage": "BROKER_INVOCATION",
                    },
                    broker_evidence={
                        "confirmation_stage": "BROKER_INVOCATION",
                        "exception_type": type(exc).__name__,
                    },
                    invocation_id=invocation_id,
                )

            try:
                ib.sleep(self.fill_wait_seconds)
                refreshed = list(ib.reqOpenOrders())
                refreshed_snapshots = [
                    canonical_open_order(item) for item in refreshed
                ]
                target_snapshots = [
                    item
                    for item in refreshed_snapshots
                    if item["orderRef"] == action.order_ref
                    and item["orderId"] == action.order_id
                ]
                target_actionable = any(
                    item["status"].upper() in ACTIONABLE_ORDER_STATUSES
                    for item in target_snapshots
                )
                target_cancelled = (
                    str(getattr(selected_trade.orderStatus, "status", "")).upper()
                    in CANCELLED_ORDER_STATUSES
                )
                selected_status = str(
                    getattr(selected_trade.orderStatus, "status", "") or ""
                ).upper()
                selected_filled = Decimal(
                    str(getattr(selected_trade.orderStatus, "filled", 0) or 0)
                )
                selected_remaining = Decimal(
                    str(getattr(selected_trade.orderStatus, "remaining", 0) or 0)
                )
                target_filled = selected_status == "FILLED" or (
                    selected_filled > 0 and selected_remaining == 0
                )
                terminal_snapshot = canonical_open_order(selected_trade)
                reconciliation = {
                    "target_present": bool(target_snapshots),
                    "target_actionable": target_actionable,
                    "target_cancelled": target_cancelled,
                    "target_filled": target_filled,
                    "open_order_count": len(refreshed_snapshots),
                    "confirmed_state": terminal_snapshot,
                    "confirmed_state_sha256": terminal_snapshot["state_sha256"],
                }
                success = not target_actionable and target_cancelled
                if success:
                    status = "CANCELLED"
                    reason_codes = ()
                elif target_filled:
                    status = "FILLED"
                    reason_codes = ("ORDER_FILLED_DURING_CANCELLATION",)
                else:
                    status = "UNCERTAIN"
                    reason_codes = ("BROKER_CANCELLATION_UNCONFIRMED",)
            except Exception as exc:
                return self._cancel_result(
                    action=action,
                    bundle=bundle,
                    snapshot=snapshot,
                    success=False,
                    status="UNCERTAIN",
                    reason_codes=("BROKER_CONFIRMATION_UNAVAILABLE",),
                    post_action_reconciliation={
                        "target_actionable": True,
                        "confirmation_stage": "POST_WRITE_RECONCILIATION",
                    },
                    broker_evidence={
                        "confirmation_stage": "POST_WRITE_RECONCILIATION",
                        "exception_type": type(exc).__name__,
                    },
                    invocation_id=invocation_id,
                )
            return self._cancel_result(
                action=action,
                bundle=bundle,
                snapshot=snapshot,
                success=success,
                status=status,
                reason_codes=reason_codes,
                post_action_reconciliation=reconciliation,
                invocation_id=invocation_id,
            )
        finally:
            try:
                self._disconnect_execution(ib)
            # Durable broker confirmation is authoritative; teardown is best effort.
            except Exception:  # nosec B110
                pass

    def _cancel_result(
        self,
        *,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
        snapshot: dict[str, Any],
        success: bool,
        status: str,
        reason_codes: tuple[str, ...],
        post_action_reconciliation: dict[str, Any],
        broker_evidence: dict[str, Any] | None = None,
        invocation_id: str | None = None,
    ) -> PaperExecutionResult:
        evidence = {
            **(broker_evidence or {}),
            "post_action_reconciliation": post_action_reconciliation,
        }
        try:
            self._register_lifecycle_event(
                lifecycle_event="CANCEL_RESULT",
                decision=TraderDecision.CANCEL_ORDER,
                action=action,
                bundle=bundle,
                snapshot=snapshot,
                reason_codes=reason_codes,
                broker_evidence=evidence,
                invocation_id=invocation_id,
            )
        except Exception:
            return PaperExecutionResult(
                success=False,
                status="UNCERTAIN",
                reason_codes=("LIFECYCLE_RESULT_PERSISTENCE_FAILED",),
                order={
                    "order_management": TraderDecision.CANCEL_ORDER.value,
                    "pre_action_state": snapshot,
                    "post_action_reconciliation": post_action_reconciliation,
                },
                broker_validation=evidence,
            )
        return PaperExecutionResult(
            success=success,
            status=status,
            reason_codes=reason_codes,
            order={
                "order_management": TraderDecision.CANCEL_ORDER.value,
                "pre_action_state": snapshot,
                "post_action_reconciliation": post_action_reconciliation,
            },
            broker_validation=evidence,
        )

    def execute(
        self,
        proposal: AutonomousTradeProposal,
        bundle: TraderInputBundle,
        *,
        continuity_plan: CodexOrderContinuityPlan | None = None,
        invocation_id: str | None = None,
    ) -> PaperExecutionResult:
        if not self.armed:
            raise AutonomousPaperExecutionNotArmed(
                "set IBKR_AUTONOMOUS_PAPER_ARMED=true only when the paper experiment is explicitly started"
            )
        safety_reasons = []
        if bundle.reconciliation_receipt.get("status") != "PASS":
            safety_reasons.append("BROKER_RECONCILIATION_REQUIRED")
        if bundle.kill_switch_state != "KILL_SWITCH_CLEAR":
            safety_reasons.append("KILL_SWITCH_TRIGGERED")
        if bundle.market_data_snapshot.get("gate_status") != "PASS":
            safety_reasons.append("MARKET_DATA_GATE_BLOCK")
        if safety_reasons:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=tuple(safety_reasons),
                order={},
                broker_validation={},
            )
        if self.database is None:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=("PERSISTENT_ORDER_REGISTRY_REQUIRED",),
                order={},
                broker_validation={},
            )
        continuity_required = bool(
            bundle.continuity_context.get("authority_contract_required", False)
        )
        if continuity_required and continuity_plan is None:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=("CONTINUITY_PLAN_REQUIRED",),
                order={},
                broker_validation={},
            )
        if continuity_plan is not None and self.continuity_binding_service is None:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=("CONTINUITY_BINDING_SERVICE_REQUIRED",),
                order={},
                broker_validation={},
            )

        from ib_insync import Order

        ib = self._connect_execution()
        try:
            fresh_reasons = self._fresh_safety_reasons("NEW_TRADE")
            if fresh_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=fresh_reasons,
                    order={},
                    broker_validation={},
                )

            contract = self.toolbox._proposal_contract(ib, proposal)
            live_quote = self.toolbox.live_contract_quote_evidence(ib, contract)
            if not live_quote.get("success"):
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=(
                        "TRADE_CONTRACT_MARKET_DATA_BLOCK",
                        str(live_quote.get("reason") or "UNKNOWN"),
                    ),
                    order={},
                    broker_validation={"trade_contract_market_data": live_quote},
                )

            # Final broker what-if occurs after fresh gates and exact-contract
            # market data, leaving only a DB-only operator-control check before send.
            validation = self.toolbox.validate_proposal(proposal, bundle, ib=ib)
            if not validation.passed:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=validation.reason_codes,
                    order={},
                    broker_validation={
                        **validation.broker_evidence,
                        "trade_contract_market_data": live_quote,
                    },
                )

            operator_reasons = self._operator_control_reasons()
            if operator_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=operator_reasons,
                    order={},
                    broker_validation={
                        **validation.broker_evidence,
                        "trade_contract_market_data": live_quote,
                    },
                )

            order_ref = (
                continuity_plan.order_binding.order_ref
                if continuity_plan is not None
                else f"{EXPERIMENT_ORDER_PREFIX}-a-{bundle.decision_cycle_id[-12:]}"
            )
            if not order_ref.startswith(f"{EXPERIMENT_ORDER_PREFIX}-"):
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("CONTINUITY_ORDER_REF_NAMESPACE_MISMATCH",),
                    order={},
                    broker_validation=validation.broker_evidence,
                )
            order = Order(
                action=proposal.action.upper(),
                orderType=proposal.order_type.upper(),
                totalQuantity=float(proposal.quantity),
                transmit=True,
                whatIf=False,
                orderRef=order_ref,
                account=self._execution_account(ib),
            )
            if proposal.limit_price is not None:
                order.lmtPrice = float(proposal.limit_price)
            if not int(getattr(order, "orderId", 0) or 0):
                order.orderId = int(ib.client.getReqId())
            pending_binding: PendingContinuityBinding | None = None
            if continuity_plan is None:
                self._register_order(
                    order=order,
                    contract=contract,
                    order_ref=order_ref,
                    action=proposal.action.upper(),
                    quantity=proposal.quantity,
                    lifecycle_event="ISSUED_PRE_SEND",
                )
            operator_reasons = self._operator_control_reasons()
            if operator_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=operator_reasons,
                    order={},
                    broker_validation={
                        **validation.broker_evidence,
                        "trade_contract_market_data": live_quote,
                    },
                )
            if continuity_plan is not None:
                assert self.continuity_binding_service is not None
                try:
                    identity = canonical_contract_identity(contract)
                    pending_binding = self.continuity_binding_service.stage_new_order(
                        continuity_plan,
                        proposal_sha256=sha256_json(proposal),
                        order_ref=order_ref,
                        client_order_id=int(order.orderId),
                        contract_identity=identity,
                        account=str(order.account),
                        action=proposal.action.upper(),
                        quantity=str(proposal.quantity),
                        order_type=proposal.order_type.upper(),
                        routing=str(identity.get("exchange") or "").upper(),
                        execution_client_id=self.execution_client_id,
                        invocation_id=str(invocation_id or ""),
                        attempt_id=str(new_uuid7()),
                    )
                except ContinuityBindingError as exc:
                    return PaperExecutionResult(
                        success=False,
                        status="BLOCKED",
                        reason_codes=(f"CONTINUITY_BINDING_FAILED:{exc}",),
                        order={},
                        broker_validation={
                            **validation.broker_evidence,
                            "trade_contract_market_data": live_quote,
                        },
                    )
            final_authority_reasons = self._final_write_authority_reasons()
            if final_authority_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=final_authority_reasons,
                    order={},
                    broker_validation={
                        **validation.broker_evidence,
                        "trade_contract_market_data": live_quote,
                    },
                )
            trade = ib.placeOrder(contract, order)
            ib.sleep(self.fill_wait_seconds)
            trade = self._reconcile_post_send_trade(
                ib,
                trade,
                submitted_contract=contract,
                order_ref=order_ref,
            )
            broker_identity_available = self._broker_bound_identity_available(trade)
            if broker_identity_available:
                if pending_binding is not None:
                    assert self.continuity_binding_service is not None
                    try:
                        self.continuity_binding_service.activate_broker_binding(
                            pending_binding,
                            canonical_open_order(trade),
                            plan_sha256=continuity_plan.sha256,
                        )
                    except ContinuityBindingError as exc:
                        return PaperExecutionResult(
                            success=False,
                            status="UNCERTAIN",
                            reason_codes=(
                                f"CONTINUITY_BROKER_BINDING_UNCERTAIN:{exc}",
                            ),
                            order={
                                "orderId": getattr(trade.order, "orderId", None),
                                "permId": getattr(trade.order, "permId", None),
                                "orderRef": order_ref,
                            },
                            broker_validation=validation.broker_evidence,
                        )
                else:
                    self._register_order(
                        order=trade.order,
                        contract=trade.contract,
                        order_ref=order_ref,
                        action=proposal.action.upper(),
                        quantity=proposal.quantity,
                        lifecycle_event="BROKER_BOUND",
                    )
            status = getattr(trade.orderStatus, "status", "UNKNOWN") or "UNKNOWN"
            payload = {
                "orderId": getattr(trade.order, "orderId", None),
                "permId": getattr(trade.order, "permId", None),
                "orderRef": order_ref,
                "status": status,
                "filled": getattr(trade.orderStatus, "filled", None),
                "remaining": getattr(trade.orderStatus, "remaining", None),
                "avgFillPrice": getattr(trade.orderStatus, "avgFillPrice", None),
                "fills": self._fills_payload(trade, fallback_order_ref=order_ref),
                "paper_only": True,
            }
            failed = str(status).upper() in {"INACTIVE", "CANCELLED", "API CANCELLED"}
            if not failed and not broker_identity_available:
                return PaperExecutionResult(
                    success=False,
                    status="UNCERTAIN",
                    reason_codes=("BROKER_IDENTITY_UNRESOLVED",),
                    order=payload,
                    broker_validation=validation.broker_evidence,
                )
            return PaperExecutionResult(
                success=not failed,
                status=str(status),
                reason_codes=() if not failed else ("BROKER_REJECTED_OR_CANCELLED",),
                order=payload,
                broker_validation=validation.broker_evidence,
            )
        finally:
            self._disconnect_execution(ib)


    def execute_position_action(
        self,
        action: AutonomousPositionAction,
        bundle: TraderInputBundle,
        decision: TraderDecision,
    ) -> PaperExecutionResult:
        if not self.armed:
            raise AutonomousPaperExecutionNotArmed(
                "set IBKR_AUTONOMOUS_PAPER_ARMED=true only when the paper experiment is explicitly started"
            )
        safety_reasons = []
        if bundle.reconciliation_receipt.get("status") != "PASS":
            safety_reasons.append("BROKER_RECONCILIATION_REQUIRED")
        if bundle.kill_switch_state != "KILL_SWITCH_CLEAR":
            safety_reasons.append("KILL_SWITCH_TRIGGERED")
        if bundle.market_data_snapshot.get("gate_status") != "PASS":
            safety_reasons.append("MARKET_DATA_GATE_BLOCK")
        if safety_reasons:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=tuple(safety_reasons),
                order={},
                broker_validation={},
            )
        if self.database is None:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=("PERSISTENT_ORDER_REGISTRY_REQUIRED",),
                order={},
                broker_validation={},
            )

        from ib_insync import Order

        ib = self._connect_execution()
        try:
            fresh_reasons = self._fresh_safety_reasons("POSITION_MANAGEMENT")
            if fresh_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=fresh_reasons,
                    order={},
                    broker_validation={},
                )

            validation = self.toolbox.validate_position_action(
                action, bundle, decision, ib=ib
            )
            if not validation.passed:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=validation.reason_codes,
                    order={},
                    broker_validation=validation.broker_evidence,
                )

            position = self.toolbox._resolve_open_position(ib, action)
            if position is None:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("POSITION_NOT_FOUND_AFTER_VALIDATION",),
                    order={},
                    broker_validation=validation.broker_evidence,
                )
            current_position = Decimal(str(position.position))
            required_action = "SELL" if current_position > 0 else "BUY"
            if action.action.upper() != required_action:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("POSITION_ACTION_WOULD_INCREASE_EXPOSURE_AFTER_RECHECK",),
                    order={},
                    broker_validation=validation.broker_evidence,
                )
            current_size = abs(current_position)
            if action.quantity > current_size:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("POSITION_ACTION_EXCEEDS_OPEN_SIZE_AFTER_RECHECK",),
                    order={},
                    broker_validation=validation.broker_evidence,
                )
            if decision == TraderDecision.CLOSE_POSITION and action.quantity != current_size:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("CLOSE_POSITION_SIZE_CHANGED_AFTER_VALIDATION",),
                    order={},
                    broker_validation=validation.broker_evidence,
                )
            if decision == TraderDecision.REDUCE_POSITION and action.quantity >= current_size:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("REDUCE_POSITION_SIZE_CHANGED_AFTER_VALIDATION",),
                    order={},
                    broker_validation=validation.broker_evidence,
                )

            live_quote = self.toolbox.live_contract_quote_evidence(ib, position.contract)
            if not live_quote.get("success"):
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=(
                        "TRADE_CONTRACT_MARKET_DATA_BLOCK",
                        str(live_quote.get("reason") or "UNKNOWN"),
                    ),
                    order={},
                    broker_validation={
                        **validation.broker_evidence,
                        "trade_contract_market_data": live_quote,
                    },
                )

            # Re-issue what-if against the same connection after exact-contract
            # market data and immediately before the final position/control checks.
            final_validation = self.toolbox.validate_position_action(
                action, bundle, decision, ib=ib
            )
            if not final_validation.passed:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=final_validation.reason_codes,
                    order={},
                    broker_validation={
                        **final_validation.broker_evidence,
                        "trade_contract_market_data": live_quote,
                    },
                )

            # One final quantity snapshot after the final what-if.
            position = self.toolbox._resolve_open_position(ib, action)
            if position is None:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("POSITION_NOT_FOUND_BEFORE_SEND",),
                    order={},
                    broker_validation=final_validation.broker_evidence,
                )
            final_position = Decimal(str(position.position))
            final_required_action = "SELL" if final_position > 0 else "BUY"
            if action.action.upper() != final_required_action:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("POSITION_ACTION_WOULD_INCREASE_EXPOSURE_BEFORE_SEND",),
                    order={},
                    broker_validation=final_validation.broker_evidence,
                )
            final_size = abs(final_position)
            if action.quantity > final_size:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("POSITION_ACTION_EXCEEDS_OPEN_SIZE_BEFORE_SEND",),
                    order={},
                    broker_validation=final_validation.broker_evidence,
                )
            if decision == TraderDecision.CLOSE_POSITION and action.quantity != final_size:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("CLOSE_POSITION_SIZE_CHANGED_BEFORE_SEND",),
                    order={},
                    broker_validation=final_validation.broker_evidence,
                )

            operator_reasons = self._operator_control_reasons()
            if operator_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=operator_reasons,
                    order={},
                    broker_validation={
                        **final_validation.broker_evidence,
                        "trade_contract_market_data": live_quote,
                    },
                )

            order_ref = f"codex-ibkr-paper-30d-p-{bundle.decision_cycle_id[-12:]}"
            order = Order(
                action=action.action.upper(),
                orderType=action.order_type.upper(),
                totalQuantity=float(action.quantity),
                transmit=True,
                whatIf=False,
                orderRef=order_ref,
                account=self._execution_account(ib),
            )
            if action.limit_price is not None:
                order.lmtPrice = float(action.limit_price)
            if not int(getattr(order, "orderId", 0) or 0):
                order.orderId = int(ib.client.getReqId())
            self._register_order(
                order=order,
                contract=position.contract,
                order_ref=order_ref,
                action=action.action.upper(),
                quantity=action.quantity,
                lifecycle_event="ISSUED_PRE_SEND",
            )
            operator_reasons = self._operator_control_reasons()
            if operator_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=operator_reasons,
                    order={},
                    broker_validation={
                        **final_validation.broker_evidence,
                        "trade_contract_market_data": live_quote,
                    },
                )
            final_authority_reasons = self._final_write_authority_reasons()
            if final_authority_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=final_authority_reasons,
                    order={},
                    broker_validation={
                        **final_validation.broker_evidence,
                        "trade_contract_market_data": live_quote,
                    },
                )
            trade = ib.placeOrder(position.contract, order)
            ib.sleep(self.fill_wait_seconds)
            trade = self._reconcile_post_send_trade(
                ib,
                trade,
                submitted_contract=position.contract,
                order_ref=order_ref,
            )
            broker_identity_available = self._broker_bound_identity_available(trade)
            if broker_identity_available:
                self._register_order(
                    order=trade.order,
                    contract=trade.contract,
                    order_ref=order_ref,
                    action=action.action.upper(),
                    quantity=action.quantity,
                    lifecycle_event="BROKER_BOUND",
                )
            status = getattr(trade.orderStatus, "status", "UNKNOWN") or "UNKNOWN"
            payload = {
                "orderId": getattr(trade.order, "orderId", None),
                "permId": getattr(trade.order, "permId", None),
                "orderRef": order_ref,
                "status": status,
                "filled": getattr(trade.orderStatus, "filled", None),
                "remaining": getattr(trade.orderStatus, "remaining", None),
                "avgFillPrice": getattr(trade.orderStatus, "avgFillPrice", None),
                "fills": self._fills_payload(trade, fallback_order_ref=order_ref),
                "paper_only": True,
                "position_management": decision.value,
            }
            failed = str(status).upper() in {"INACTIVE", "CANCELLED", "API CANCELLED"}
            if not failed and not broker_identity_available:
                return PaperExecutionResult(
                    success=False,
                    status="UNCERTAIN",
                    reason_codes=("BROKER_IDENTITY_UNRESOLVED",),
                    order=payload,
                    broker_validation=final_validation.broker_evidence,
                )
            return PaperExecutionResult(
                success=not failed,
                status=str(status),
                reason_codes=() if not failed else ("BROKER_REJECTED_OR_CANCELLED",),
                order=payload,
                broker_validation=final_validation.broker_evidence,
            )
        finally:
            self._disconnect_execution(ib)


class AutonomousPaperExecutor(WriterOwnedModelExecutionMechanics):
    """Explicit non-production adapter that owns a direct PAPER connection."""

    def _connect_execution(self):
        if self._writer_owned_broker is not None:
            return super()._connect_execution()
        return self.toolbox._connect(client_id=self.execution_client_id)

    def _disconnect_execution(self, ib: Any) -> None:
        if self._writer_owned_broker is not None:
            super()._disconnect_execution(ib)
            return
        ib.disconnect()
