from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from .autonomous_research import AutonomousPositionAction, AutonomousTradeProposal
from .canonical import canonical_bytes, sha256_json
from .ibkr_research_tools import IBKRResearchToolbox
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

    def __init__(
        self,
        toolbox: IBKRResearchToolbox,
        *,
        armed: bool | None = None,
        fill_wait_seconds: float = 3.0,
        database: Database | None = None,
        fresh_safety_check: Callable[[str], tuple[str, ...]] | None = None,
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

    @staticmethod
    def _fills_payload(trade: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
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
                "side": side,
                "quantity": str(getattr(execution, "shares", "") or ""),
                "price": str(getattr(execution, "price", "") or ""),
                "commission": str(getattr(commission_report, "commission", 0) or 0),
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

    def _register_order(
        self,
        *,
        trade: Any,
        contract: Any,
        order_ref: str,
        action: str,
        quantity: Decimal,
    ) -> None:
        if self.database is None:
            raise RuntimeError("persistent database required for armed paper execution")
        payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V1",
            "order_ref": order_ref,
            "client_order_id": int(getattr(trade.order, "orderId", 0) or 0),
            "perm_id": int(getattr(trade.order, "permId", 0) or 0),
            "ibkr_order_id": int(getattr(trade.order, "orderId", 0) or 0),
            "contract_id": int(getattr(contract, "conId", 0) or 0),
            "action": action,
            "quantity": str(quantity),
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

    def execute(
        self,
        proposal: AutonomousTradeProposal,
        bundle: TraderInputBundle,
    ) -> PaperExecutionResult:
        if not self.armed:
            raise AutonomousPaperExecutionNotArmed(
                "set IBKR_AUTONOMOUS_PAPER_ARMED=true only when the paper experiment is explicitly started"
            )
        if self.database is None:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=("PERSISTENT_ORDER_REGISTRY_REQUIRED",),
                order={},
                broker_validation={},
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

        from ib_insync import Order

        ib = self.toolbox._connect()
        try:
            validation = self.toolbox.validate_proposal(proposal, bundle, ib=ib)
            if not validation.passed:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=validation.reason_codes,
                    order={},
                    broker_validation=validation.broker_evidence,
                )

            fresh_reasons = self._fresh_safety_reasons("NEW_TRADE")
            if fresh_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=fresh_reasons,
                    order={},
                    broker_validation=validation.broker_evidence,
                )

            contract = self.toolbox._proposal_contract(ib, proposal)
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
            trade = ib.placeOrder(contract, order)
            self._register_order(
                trade=trade,
                contract=contract,
                order_ref=order_ref,
                action=proposal.action.upper(),
                quantity=proposal.quantity,
            )
            ib.sleep(self.fill_wait_seconds)
            status = getattr(trade.orderStatus, "status", "UNKNOWN") or "UNKNOWN"
            payload = {
                "orderId": getattr(trade.order, "orderId", None),
                "permId": getattr(trade.order, "permId", None),
                "orderRef": order_ref,
                "status": status,
                "filled": getattr(trade.orderStatus, "filled", None),
                "remaining": getattr(trade.orderStatus, "remaining", None),
                "avgFillPrice": getattr(trade.orderStatus, "avgFillPrice", None),
                "fills": self._fills_payload(trade),
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
        if self.database is None:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=("PERSISTENT_ORDER_REGISTRY_REQUIRED",),
                order={},
                broker_validation={},
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

        from ib_insync import Order

        ib = self.toolbox._connect()
        try:
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

            # Re-issue what-if against the same connection immediately before send.
            final_validation = self.toolbox.validate_position_action(
                action, bundle, decision, ib=ib
            )
            if not final_validation.passed:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=final_validation.reason_codes,
                    order={},
                    broker_validation=final_validation.broker_evidence,
                )

            fresh_reasons = self._fresh_safety_reasons("POSITION_MANAGEMENT")
            if fresh_reasons:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=fresh_reasons,
                    order={},
                    broker_validation=final_validation.broker_evidence,
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
            final_size = abs(Decimal(str(position.position)))
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
            trade = ib.placeOrder(position.contract, order)
            self._register_order(
                trade=trade,
                contract=position.contract,
                order_ref=order_ref,
                action=action.action.upper(),
                quantity=action.quantity,
            )
            ib.sleep(self.fill_wait_seconds)
            status = getattr(trade.orderStatus, "status", "UNKNOWN") or "UNKNOWN"
            payload = {
                "orderId": getattr(trade.order, "orderId", None),
                "permId": getattr(trade.order, "permId", None),
                "orderRef": order_ref,
                "status": status,
                "filled": getattr(trade.orderStatus, "filled", None),
                "remaining": getattr(trade.orderStatus, "remaining", None),
                "avgFillPrice": getattr(trade.orderStatus, "avgFillPrice", None),
                "fills": self._fills_payload(trade),
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

