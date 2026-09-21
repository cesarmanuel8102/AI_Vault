from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .autonomous_research import AutonomousPositionAction, AutonomousTradeProposal
from .ibkr_research_tools import IBKRResearchToolbox
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
    ) -> None:
        self.toolbox = toolbox
        self.armed = (
            os.environ.get("IBKR_AUTONOMOUS_PAPER_ARMED", "false").lower() == "true"
            if armed is None
            else bool(armed)
        )
        self.fill_wait_seconds = fill_wait_seconds

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

        validation = self.toolbox.validate_proposal(proposal, bundle)
        if not validation.passed:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=validation.reason_codes,
                order={},
                broker_validation=validation.broker_evidence,
            )

        from ib_insync import Order

        ib = self.toolbox._connect()
        try:
            contract = self.toolbox._proposal_contract(ib, proposal)
            order = Order(
                action=proposal.action.upper(),
                orderType=proposal.order_type.upper(),
                totalQuantity=float(proposal.quantity),
                transmit=True,
                whatIf=False,
                orderRef="codex-ibkr-paper-30d-autonomous",
            )
            if proposal.limit_price is not None:
                order.lmtPrice = float(proposal.limit_price)
            trade = ib.placeOrder(contract, order)
            ib.sleep(self.fill_wait_seconds)
            status = getattr(trade.orderStatus, "status", "UNKNOWN") or "UNKNOWN"
            payload = {
                "orderId": getattr(trade.order, "orderId", None),
                "permId": getattr(trade.order, "permId", None),
                "status": status,
                "filled": getattr(trade.orderStatus, "filled", None),
                "remaining": getattr(trade.orderStatus, "remaining", None),
                "avgFillPrice": getattr(trade.orderStatus, "avgFillPrice", None),
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

        validation = self.toolbox.validate_position_action(action, bundle, decision)
        if not validation.passed:
            return PaperExecutionResult(
                success=False,
                status="BLOCKED",
                reason_codes=validation.reason_codes,
                order={},
                broker_validation=validation.broker_evidence,
            )

        from ib_insync import Order

        ib = self.toolbox._connect()
        try:
            position = self.toolbox._resolve_open_position(ib, action)
            if position is None:
                return PaperExecutionResult(
                    success=False,
                    status="BLOCKED",
                    reason_codes=("POSITION_NOT_FOUND_AFTER_VALIDATION",),
                    order={},
                    broker_validation=validation.broker_evidence,
                )
            order = Order(
                action=action.action.upper(),
                orderType=action.order_type.upper(),
                totalQuantity=float(action.quantity),
                transmit=True,
                whatIf=False,
                orderRef="codex-ibkr-paper-30d-position-management",
            )
            if action.limit_price is not None:
                order.lmtPrice = float(action.limit_price)
            trade = ib.placeOrder(position.contract, order)
            ib.sleep(self.fill_wait_seconds)
            status = getattr(trade.orderStatus, "status", "UNKNOWN") or "UNKNOWN"
            payload = {
                "orderId": getattr(trade.order, "orderId", None),
                "permId": getattr(trade.order, "permId", None),
                "status": status,
                "filled": getattr(trade.orderStatus, "filled", None),
                "remaining": getattr(trade.orderStatus, "remaining", None),
                "avgFillPrice": getattr(trade.orderStatus, "avgFillPrice", None),
                "paper_only": True,
                "position_management": decision.value,
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
