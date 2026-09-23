from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from .autonomous_research import (
    AutonomousOpenOrderAction,
    AutonomousPositionAction,
    AutonomousTradeProposal,
)
from .canonical import canonical_bytes, sha256_json
from .ibkr_research_tools import IBKRResearchToolbox
from .open_order_management import (
    ACTIONABLE_ORDER_STATUSES,
    CANCELLED_ORDER_STATUSES,
    EXECUTION_CLIENT_ID,
    OpenOrderOwnershipError,
    canonical_open_order,
    lifecycle_attempt_exists,
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


class AutonomousPaperExecutor:
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

    def _connect_execution(self):
        return self.toolbox._connect(client_id=self.execution_client_id)

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
        payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V1",
            "order_ref": order_ref,
            "client_order_id": int(getattr(order, "orderId", 0) or 0),
            "perm_id": int(getattr(order, "permId", 0) or 0),
            "ibkr_order_id": int(getattr(order, "orderId", 0) or 0),
            "contract_id": int(getattr(contract, "conId", 0) or 0),
            "action": action,
            "quantity": str(quantity),
            "execution_client_id": self.execution_client_id,
            "lifecycle_event": lifecycle_event,
            "created_at_utc": utc_now(),
        }
        self.database.execute(
            "INSERT INTO experiment_order_registry("
            "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
            "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(new_uuid7()),
                order_ref,
                payload["client_order_id"],
                payload["perm_id"],
                payload["ibkr_order_id"],
                payload["contract_id"],
                action,
                str(quantity),
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                utc_now(),
            ),
        )

    def _register_lifecycle_event(
        self,
        *,
        lifecycle_event: str,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
        snapshot: dict[str, Any],
        reason_codes: tuple[str, ...] = (),
        broker_evidence: dict[str, Any] | None = None,
    ) -> None:
        if self.database is None:
            raise RuntimeError("persistent database required for lifecycle evidence")
        payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_LIFECYCLE_V1",
            "lifecycle_event": lifecycle_event,
            "decision_cycle_id": bundle.decision_cycle_id,
            "decision": TraderDecision.CANCEL_ORDER.value,
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
    ) -> PaperExecutionResult:
        if decision == TraderDecision.CANCEL_ORDER:
            return self._cancel_open_order(action, bundle)
        if decision == TraderDecision.MODIFY_ORDER:
            return self._modify_open_order(action, bundle)
        raise ValueError("unsupported open-order decision")

    def _modify_open_order(
        self,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
    ) -> PaperExecutionResult:
        return PaperExecutionResult(
            success=False,
            status="BLOCKED",
            reason_codes=("MODIFY_ORDER_NOT_IMPLEMENTED",),
            order={},
            broker_validation={},
        )

    def _cancel_open_order(
        self,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
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
            try:
                self._register_lifecycle_event(
                    lifecycle_event="CANCEL_ATTEMPT",
                    action=action,
                    bundle=bundle,
                    snapshot=snapshot,
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
            except ConnectionError:
                return PaperExecutionResult(
                    success=False,
                    status="UNCERTAIN",
                    reason_codes=("BROKER_CONFIRMATION_UNAVAILABLE",),
                    order={"pre_action_state": snapshot},
                    broker_validation={},
                )
            except Exception as exc:
                reason_codes = ("BROKER_CANCEL_REJECTED",)
                evidence = {"exception_type": type(exc).__name__}
                return self._cancel_result(
                    action=action,
                    bundle=bundle,
                    snapshot=snapshot,
                    success=False,
                    status="BLOCKED",
                    reason_codes=reason_codes,
                    post_action_reconciliation={"target_actionable": True},
                    broker_evidence=evidence,
                )

            try:
                ib.sleep(self.fill_wait_seconds)
                refreshed = list(ib.reqOpenOrders())
            except Exception:
                return PaperExecutionResult(
                    success=False,
                    status="UNCERTAIN",
                    reason_codes=("BROKER_CONFIRMATION_UNAVAILABLE",),
                    order={"pre_action_state": snapshot},
                    broker_validation={},
                )
            refreshed_snapshots = [canonical_open_order(item) for item in refreshed]
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
            reconciliation = {
                "target_present": bool(target_snapshots),
                "target_actionable": target_actionable,
                "target_cancelled": target_cancelled,
                "open_order_count": len(refreshed_snapshots),
            }
            success = not target_actionable and (target_cancelled or not target_snapshots)
            reason_codes = () if success else ("BROKER_CANCELLATION_UNCONFIRMED",)
            return self._cancel_result(
                action=action,
                bundle=bundle,
                snapshot=snapshot,
                success=success,
                status="CANCELLED" if success else "UNCERTAIN",
                reason_codes=reason_codes,
                post_action_reconciliation=reconciliation,
            )
        finally:
            ib.disconnect()

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
    ) -> PaperExecutionResult:
        evidence = {
            **(broker_evidence or {}),
            "post_action_reconciliation": post_action_reconciliation,
        }
        try:
            self._register_lifecycle_event(
                lifecycle_event="CANCEL_RESULT",
                action=action,
                bundle=bundle,
                snapshot=snapshot,
                reason_codes=reason_codes,
                broker_evidence=evidence,
            )
        except Exception:
            return PaperExecutionResult(
                success=False,
                status="UNCERTAIN",
                reason_codes=("LIFECYCLE_RESULT_PERSISTENCE_FAILED",),
                order={
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
                "pre_action_state": snapshot,
                "post_action_reconciliation": post_action_reconciliation,
            },
            broker_validation=evidence,
        )

    def execute(
        self,
        proposal: AutonomousTradeProposal,
        bundle: TraderInputBundle,
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

            order_ref = f"codex-ibkr-paper-30d-a-{bundle.decision_cycle_id[-12:]}"
            order = Order(
                action=proposal.action.upper(),
                orderType=proposal.order_type.upper(),
                totalQuantity=float(proposal.quantity),
                transmit=True,
                whatIf=False,
                orderRef=order_ref,
            )
            if proposal.limit_price is not None:
                order.lmtPrice = float(proposal.limit_price)
            if not int(getattr(order, "orderId", 0) or 0):
                order.orderId = int(ib.client.getReqId())
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
            trade = ib.placeOrder(contract, order)
            ib.sleep(self.fill_wait_seconds)
            if int(getattr(trade.order, "permId", 0) or 0) > 0:
                self._register_order(
                    order=trade.order,
                    contract=contract,
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
            return PaperExecutionResult(
                success=not failed,
                status=str(status),
                reason_codes=() if not failed else ("BROKER_REJECTED_OR_CANCELLED",),
                order=payload,
                broker_validation=validation.broker_evidence,
            )
        finally:
            ib.disconnect()


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
            trade = ib.placeOrder(position.contract, order)
            ib.sleep(self.fill_wait_seconds)
            if int(getattr(trade.order, "permId", 0) or 0) > 0:
                self._register_order(
                    order=trade.order,
                    contract=position.contract,
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
            return PaperExecutionResult(
                success=not failed,
                status=str(status),
                reason_codes=() if not failed else ("BROKER_REJECTED_OR_CANCELLED",),
                order=payload,
                broker_validation=final_validation.broker_evidence,
            )
        finally:
            ib.disconnect()
