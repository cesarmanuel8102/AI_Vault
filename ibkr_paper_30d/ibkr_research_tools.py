from __future__ import annotations

import copy
import os
import random
import sys
from datetime import timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .autonomous_research import (
    AutonomousOpenOrderAction,
    AutonomousPositionAction,
    AutonomousTradeProposal,
    ProposalValidation,
    ResearchRequest,
    ResearchResult,
    ResearchTool,
)
from .canonical import sha256_json
from .ibkr_readonly import expected_identity_hash
from .ibkr_readonly_session import ExpectedPaperIdentityStore
from .open_order_management import (
    ACTIONABLE_ORDER_STATUSES,
    EXECUTION_CLIENT_ID,
    MODIFIABLE_ORDER_STATUSES,
    canonical_contract_identity,
    canonical_open_order,
)
from .product_capability import ProductCapabilityEvidence
from .risk import CapitalBoundaryInputs, CapitalBoundaryRiskEngine, RiskResult
from .trader_invocation import TraderDecision, TraderInputBundle


PAPER_HOSTS = {"127.0.0.1", "localhost"}
PAPER_PORT = 4002


class PositionExecutionContractError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def capability_evidence_from_broker_checks(
    *,
    candidate: dict[str, Any],
    paper_account_sha256: str,
    contract_qualified: bool,
    permissions_verified: bool,
    market_data_verified: bool,
    order_semantics_verified: bool,
    quantity_semantics_verified: bool,
    bounded_economics_verified: bool,
    paper_limitations: tuple[str, ...],
    observed_at_utc: Any,
    expires_at_utc: Any,
) -> ProductCapabilityEvidence:
    """Normalize broker facts without converting research into authority."""
    return ProductCapabilityEvidence(
        candidate=candidate,
        paper_account_sha256=paper_account_sha256,
        contract_qualified=contract_qualified,
        permissions_verified=permissions_verified,
        market_data_verified=market_data_verified,
        order_semantics_verified=order_semantics_verified,
        quantity_semantics_verified=quantity_semantics_verified,
        bounded_economics_verified=bounded_economics_verified,
        paper_limitations=paper_limitations,
        observed_at_utc=observed_at_utc,
        expires_at_utc=expires_at_utc,
    )


def resolve_position_execution_contract(ib: Any, contract: Any) -> Any:
    """Qualify stock position actions through SMART without changing identity."""
    if str(getattr(contract, "secType", "") or "").upper() != "STK":
        return contract

    original_con_id = int(getattr(contract, "conId", 0) or 0)
    if original_con_id <= 0:
        raise PositionExecutionContractError(
            "POSITION_ACTION_CONTRACT_IDENTITY_REQUIRED"
        )

    original_exchange = str(getattr(contract, "exchange", "") or "").upper()
    expected_primary = str(
        getattr(contract, "primaryExchange", "") or ""
    ).upper()
    if not expected_primary and original_exchange not in {"", "SMART"}:
        expected_primary = original_exchange

    routed = copy.deepcopy(contract)
    routed.exchange = "SMART"
    if expected_primary:
        routed.primaryExchange = expected_primary

    try:
        qualified = list(ib.qualifyContracts(routed) or [])
    except Exception as exc:
        raise PositionExecutionContractError(
            "POSITION_ACTION_CONTRACT_QUALIFICATION_FAILED"
        ) from exc
    if not qualified:
        raise PositionExecutionContractError(
            "POSITION_ACTION_CONTRACT_QUALIFICATION_NOT_FOUND"
        )
    if len(qualified) != 1:
        raise PositionExecutionContractError(
            "POSITION_ACTION_CONTRACT_QUALIFICATION_AMBIGUOUS"
        )

    resolved = qualified[0]
    resolved_con_id = int(getattr(resolved, "conId", 0) or 0)
    resolved_sec_type = str(
        getattr(resolved, "secType", "") or ""
    ).upper()
    resolved_exchange = str(
        getattr(resolved, "exchange", "") or ""
    ).upper()
    resolved_primary = str(
        getattr(resolved, "primaryExchange", "") or ""
    ).upper()
    if resolved_con_id != original_con_id or resolved_sec_type != "STK":
        raise PositionExecutionContractError(
            "POSITION_ACTION_CONTRACT_IDENTITY_MISMATCH"
        )
    if resolved_exchange != "SMART":
        raise PositionExecutionContractError(
            "POSITION_ACTION_CONTRACT_SMART_ROUTE_REQUIRED"
        )
    if expected_primary and resolved_primary != expected_primary:
        raise PositionExecutionContractError(
            "POSITION_ACTION_CONTRACT_PRIMARY_EXCHANGE_MISMATCH"
        )
    return resolved


class IBKRResearchToolbox:
    """Primitive IBKR research tools for Codex-directed paper trading.

    The toolbox does not choose symbols, strategies, timeframes or size.
    BROKER_FEASIBILITY uses IBKR what-if and never transmits an order.
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = PAPER_PORT,
        client_id_min: int = 19800,
        client_id_max: int = 19899,
        timeout_seconds: float = 12.0,
        declared_options_level: int | None = None,
        expected_account_hash: str | None = None,
    ) -> None:
        if host not in PAPER_HOSTS or port != PAPER_PORT:
            raise ValueError("autonomous research requires local IBKR paper Gateway :4002")
        self.host = host
        self.port = port
        self.client_id_min = client_id_min
        self.client_id_max = client_id_max
        self.timeout_seconds = timeout_seconds
        self.declared_options_level = declared_options_level
        configured_hash = expected_account_hash or os.environ.get("IBKR_PAPER_ACCOUNT_SHA256")
        if configured_hash is None:
            store = ExpectedPaperIdentityStore(
                Path("Secrets/expected_paper_account_identity_v1.json")
            )
            if store.path.exists():
                configured_hash = store.load_hash()
        self.expected_account_hash = configured_hash.lower() if configured_hash else None
        self.risk_engine = CapitalBoundaryRiskEngine.aggressive_month1()

    def manifest(self) -> list[dict[str, Any]]:
        return [
            {"tool": ResearchTool.ACCOUNT_STATE.value, "purpose": "Paper-session identity context, broker server time and declared option permission level. Global broker balances are deliberately redacted."},
            {"tool": ResearchTool.POSITIONS.value, "purpose": "Current paper positions."},
            {"tool": ResearchTool.OPEN_ORDERS.value, "purpose": "Current paper open orders."},
            {"tool": ResearchTool.EXECUTIONS.value, "purpose": "Recent paper executions/fills, including orderRef for experiment reconciliation."},
            {"tool": ResearchTool.MARKET_SCANNER.value, "purpose": "IBKR scanner; Codex chooses instrument/location/scan code and filters."},
            {"tool": ResearchTool.RESOLVE_CONTRACT.value, "purpose": "Resolve any IBKR contract supported by the account."},
            {"tool": ResearchTool.QUOTE.value, "purpose": "Snapshot quote for a requested stock, ETF, option or other resolvable contract."},
            {"tool": ResearchTool.HISTORICAL_BARS.value, "purpose": "Historical bars with model-selected duration, bar size, data type and RTH policy."},
            {"tool": ResearchTool.OPTION_CHAIN.value, "purpose": "Discover option expirations, strikes, exchanges and multipliers."},
            {"tool": ResearchTool.NEWS_SEARCH.value, "purpose": "IBKR subscribed news providers and historical headlines for a resolved contract."},
            {"tool": ResearchTool.BROKER_FEASIBILITY.value, "purpose": "IBKR what-if feasibility, margin and commission check for a single or combo order."},
        ]

    def execute(self, request: ResearchRequest, bundle: TraderInputBundle) -> ResearchResult:
        try:
            dispatch = {
                ResearchTool.ACCOUNT_STATE: self._account_state,
                ResearchTool.POSITIONS: self._positions,
                ResearchTool.OPEN_ORDERS: self._open_orders,
                ResearchTool.EXECUTIONS: self._executions,
                ResearchTool.MARKET_SCANNER: self._market_scanner,
                ResearchTool.RESOLVE_CONTRACT: self._resolve_contract,
                ResearchTool.QUOTE: self._quote,
                ResearchTool.HISTORICAL_BARS: self._historical_bars,
                ResearchTool.OPTION_CHAIN: self._option_chain,
                ResearchTool.NEWS_SEARCH: self._news_search,
                ResearchTool.BROKER_FEASIBILITY: self._broker_feasibility_from_args,
            }
            data = dispatch[request.tool](dict(request.arguments))
            success = bool(data.pop("success", True))
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=success,
                data=data,
                error=None if success else str(data.get("error") or "tool_failed"),
            )
        except Exception as exc:
            if isinstance(exc, TimeoutError):
                error_type = "TimeoutError"
            elif isinstance(exc, ConnectionError):
                error_type = "ConnectionError"
            elif isinstance(exc, PermissionError):
                error_type = "PermissionError"
            elif isinstance(exc, OSError):
                error_type = "OSError"
            else:
                error_type = type(exc).__name__
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=False,
                data={},
                error=f"{error_type}:tool_failed",
            )

    WARNING_BLOCK_TOKENS = (
        "not allowed",
        "cannot",
        "rejected",
        "insufficient",
        "incompatible",
        "missing",
    )

    MODEL_SAFE_FEASIBILITY_FIELDS = frozenset(
        {
            "success",
            "error",
            "error_type",
            "error_code",
            "stage",
            "contract",
            "commission",
            "minCommission",
            "maxCommission",
            "initMarginChange",
            "maintMarginChange",
            "equityWithLoanChange",
            "warningText",
            "whatIf",
            "paper_only",
            "current_position",
            "requested_quantity",
            "what_if_status",
            "broker_whatif_reached",
            "broker_economics_computed",
            "continuity_host_bindings",
        }
    )

    @classmethod
    def _model_safe_feasibility(cls, feasibility: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in feasibility.items()
            if key in cls.MODEL_SAFE_FEASIBILITY_FIELDS
        }

    @classmethod
    def _model_research_feasibility(
        cls, feasibility: dict[str, Any]
    ) -> dict[str, Any]:
        safe = cls._model_safe_feasibility(feasibility)
        if not feasibility.get("success"):
            return safe

        init_margin = cls._decimal_or_none(feasibility.get("initMarginChange"))
        maint_margin = cls._decimal_or_none(feasibility.get("maintMarginChange"))
        if init_margin is None or maint_margin is None:
            error_code = "BROKER_MARGIN_EVIDENCE_MISSING"
        else:
            commissions = (
                cls._decimal_or_none(feasibility.get("commission")),
                cls._decimal_or_none(feasibility.get("minCommission")),
                cls._decimal_or_none(feasibility.get("maxCommission")),
            )
            error_code = (
                "BROKER_COMMISSION_EVIDENCE_MISSING"
                if all(value is None for value in commissions)
                else None
            )
        if error_code is None:
            return safe
        return {
            **safe,
            "success": False,
            "error": "BROKER_FEASIBILITY_EVIDENCE_INCOMPLETE",
            "error_type": "ValueError",
            "error_code": error_code,
            "stage": "WHAT_IF_NORMALIZATION",
        }

    def _feasibility_common(
        self,
        feasibility: dict[str, Any],
        *,
        equity: Decimal,
    ) -> tuple[bool, tuple[str, ...]]:
        if not feasibility.get("success"):
            return False, ("BROKER_FEASIBILITY_FAILED",)
        warning = str(feasibility.get("warningText") or "").lower()
        if any(token in warning for token in self.WARNING_BLOCK_TOKENS):
            return False, ("BROKER_FEASIBILITY_WARNING_BLOCK",)

        init_margin = self._decimal_or_none(feasibility.get("initMarginChange"))
        maint_margin = self._decimal_or_none(feasibility.get("maintMarginChange"))
        commission_candidates = (
            self._decimal_or_none(feasibility.get("commission")),
            self._decimal_or_none(feasibility.get("minCommission")),
            self._decimal_or_none(feasibility.get("maxCommission")),
        )
        if init_margin is None or maint_margin is None:
            return False, ("BROKER_MARGIN_EVIDENCE_MISSING",)
        if all(value is None for value in commission_candidates):
            return False, ("BROKER_COMMISSION_EVIDENCE_MISSING",)
        positive_margin = max(init_margin, maint_margin, Decimal("0"))
        if positive_margin > equity:
            return False, ("BROKER_MARGIN_EXCEEDS_EXPERIMENT_EQUITY",)
        return True, ()

    def _feasibility_exposure_reducing(
        self, feasibility: dict[str, Any]
    ) -> tuple[bool, tuple[str, ...]]:
        if not feasibility.get("success"):
            return False, ("BROKER_FEASIBILITY_FAILED",)
        warning = str(feasibility.get("warningText") or "").lower()
        if any(token in warning for token in self.WARNING_BLOCK_TOKENS):
            return False, ("BROKER_FEASIBILITY_WARNING_BLOCK",)
        return True, ()

    def validate_proposal(
        self,
        proposal: AutonomousTradeProposal,
        bundle: TraderInputBundle,
        *,
        ib: Any | None = None,
    ) -> ProposalValidation:
        equity = Decimal(str(bundle.experiment_subledger_snapshot.get("equity", "0")))
        structural_floor, structural_reason = self._structure_loss_floor(proposal, bundle)
        if structural_reason is not None:
            return ProposalValidation(
                passed=False,
                reason_codes=(structural_reason,),
                broker_evidence={"structural_loss_floor": None},
            )
        if structural_floor is None:
            structural_floor = Decimal("0")
        if proposal.maximum_loss + Decimal("0.01") < structural_floor:
            return ProposalValidation(
                passed=False,
                reason_codes=("DECLARED_MAX_LOSS_UNDERSTATES_STRUCTURE",),
                broker_evidence={
                    "declared_maximum_loss": str(proposal.maximum_loss),
                    "structural_loss_floor": str(structural_floor),
                },
            )
        effective_maximum_loss = max(proposal.maximum_loss, structural_floor)
        risk = self.risk_engine.evaluate(
            CapitalBoundaryInputs(
                experiment_equity=equity,
                maximum_loss=effective_maximum_loss,
                liability_is_bounded=proposal.loss_is_bounded,
                uses_external_capital=False,
            )
        )
        if risk.result != RiskResult.PASS:
            return ProposalValidation(
                passed=False,
                reason_codes=risk.reason_codes,
                broker_evidence={
                    "risk_policy": risk.model_dump(mode="json"),
                    "structural_loss_floor": str(structural_floor),
                },
            )

        feasibility = self._broker_feasibility(proposal, ib=ib)
        model_feasibility = self._model_safe_feasibility(feasibility)
        feasibility_ok, feasibility_reasons = self._feasibility_common(
            feasibility, equity=equity
        )
        if not feasibility_ok:
            return ProposalValidation(
                passed=False,
                reason_codes=feasibility_reasons,
                broker_evidence=model_feasibility,
            )

        commission = (
            self._decimal_or_none(feasibility.get("maxCommission"))
            or self._decimal_or_none(feasibility.get("commission"))
            or self._decimal_or_none(feasibility.get("minCommission"))
            or Decimal("0")
        )
        if effective_maximum_loss + max(commission, Decimal("0")) > equity:
            return ProposalValidation(
                passed=False,
                reason_codes=("EXPERIMENT_CAPITAL_BOUNDARY_AFTER_COSTS",),
                broker_evidence=model_feasibility,
            )

        return ProposalValidation(
            passed=True,
            reason_codes=(),
            broker_evidence={
                "risk_policy": risk.model_dump(mode="json"),
                "structural_loss_floor": str(structural_floor),
                "effective_maximum_loss": str(effective_maximum_loss),
                "what_if": model_feasibility,
            },
        )

    @staticmethod
    def _decimal_or_none(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            text = str(value).replace(",", "").strip()
            if not text:
                return None
            parsed = Decimal(text)
            return parsed if parsed.is_finite() else None
        except Exception:
            return None

    def validate_position_action(
        self,
        action: AutonomousPositionAction,
        bundle: TraderInputBundle,
        decision: TraderDecision,
        *,
        ib: Any | None = None,
    ) -> ProposalValidation:
        from ib_insync import Order

        equity = Decimal(str(bundle.experiment_subledger_snapshot.get("equity", "0")))
        owns_connection = ib is None
        broker = ib or self._connect()
        try:
            matched = self._resolve_open_position(broker, action)
            if matched is None:
                return ProposalValidation(
                    passed=False,
                    reason_codes=("POSITION_NOT_FOUND",),
                    broker_evidence={},
                )
            position = Decimal(str(matched.position))
            required_action = "SELL" if position > 0 else "BUY"
            if action.action.upper() != required_action:
                return ProposalValidation(
                    passed=False,
                    reason_codes=("POSITION_ACTION_WOULD_INCREASE_EXPOSURE",),
                    broker_evidence={"position": str(position)},
                )
            quantity = action.quantity
            current_size = abs(position)
            if quantity > current_size:
                return ProposalValidation(
                    passed=False,
                    reason_codes=("POSITION_ACTION_EXCEEDS_OPEN_SIZE",),
                    broker_evidence={"position": str(position)},
                )
            if decision == TraderDecision.CLOSE_POSITION and quantity != current_size:
                return ProposalValidation(
                    passed=False,
                    reason_codes=("CLOSE_POSITION_REQUIRES_FULL_SIZE",),
                    broker_evidence={"position": str(position)},
                )
            if decision == TraderDecision.REDUCE_POSITION and quantity >= current_size:
                return ProposalValidation(
                    passed=False,
                    reason_codes=("REDUCE_POSITION_REQUIRES_PARTIAL_SIZE",),
                    broker_evidence={"position": str(position)},
                )

            try:
                execution_contract = resolve_position_execution_contract(
                    broker, matched.contract
                )
            except PositionExecutionContractError as exc:
                return ProposalValidation(
                    passed=False,
                    reason_codes=(exc.reason_code,),
                    broker_evidence={
                        "contract": self._serialize_contract(matched.contract),
                        "current_position": str(position),
                    },
                )

            order = Order(
                action=action.action.upper(),
                orderType=action.order_type.upper(),
                totalQuantity=float(quantity),
                transmit=True,
                whatIf=True,
            )
            if action.limit_price is not None:
                order.lmtPrice = float(action.limit_price)
            try:
                state = self._request_what_if(broker, execution_contract, order)
            except Exception as exc:
                state = None
                state_error = f"{type(exc).__name__}:broker_operation_failed"
            else:
                state_error = None
            evidence = {
                "success": state is not None,
                "error": state_error or ("WHAT_IF_RETURNED_NONE" if state is None else None),
                "contract": self._serialize_contract(execution_contract),
                "current_position": str(position),
                "requested_quantity": str(quantity),
                "whatIf": True,
                "commission": getattr(state, "commission", None),
                "minCommission": getattr(state, "minCommission", None),
                "maxCommission": getattr(state, "maxCommission", None),
                "initMarginChange": getattr(state, "initMarginChange", None),
                "maintMarginChange": getattr(state, "maintMarginChange", None),
                "warningText": getattr(state, "warningText", None),
            }
            feasibility_ok, reasons = self._feasibility_exposure_reducing(evidence)
            if not feasibility_ok:
                return ProposalValidation(
                    passed=False,
                    reason_codes=reasons,
                    broker_evidence=evidence,
                )
            return ProposalValidation(
                passed=True,
                reason_codes=(),
                broker_evidence=evidence,
            )
        finally:
            if owns_connection:
                broker.disconnect()

    def validate_open_order_action(
        self,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
        decision: TraderDecision,
        *,
        ib: Any | None = None,
    ) -> ProposalValidation:
        frozen = next(
            (
                item
                for item in bundle.open_orders_snapshot
                if item.get("orderRef") == action.order_ref
                and int(item.get("orderId") or 0) == action.order_id
                and int(item.get("clientId") or 0) == action.client_id
                and int((item.get("contract") or {}).get("conId") or 0)
                == action.contract_id
            ),
            None,
        )
        if frozen is None:
            return ProposalValidation(
                passed=False,
                reason_codes=("OPEN_ORDER_FROZEN_STATE_ABSENT",),
                broker_evidence={},
            )
        if frozen.get("state_sha256") != action.observed_state_sha256:
            return ProposalValidation(
                passed=False,
                reason_codes=("OPEN_ORDER_FROZEN_STATE_MISMATCH",),
                broker_evidence={"frozen_state": frozen},
            )

        owns_connection = ib is None
        broker = ib or self._connect()
        try:
            trades = list(broker.reqAllOpenOrders())
            matches = [
                trade
                for trade in trades
                if str(getattr(trade.order, "orderRef", "") or "")
                == action.order_ref
                and int(getattr(trade.order, "orderId", 0) or 0)
                == action.order_id
                and int(getattr(trade.order, "clientId", 0) or 0)
                == action.client_id
                and int(getattr(trade.contract, "conId", 0) or 0)
                == action.contract_id
            ]
            if len(matches) != 1:
                reason = (
                    "OPEN_ORDER_IDENTITY_AMBIGUOUS"
                    if len(matches) > 1
                    else "OPEN_ORDER_NOT_FOUND"
                )
                return ProposalValidation(
                    passed=False,
                    reason_codes=(reason,),
                    broker_evidence={},
                )
            trade = matches[0]
            snapshot = canonical_open_order(trade)
            if snapshot["state_sha256"] != action.observed_state_sha256:
                return ProposalValidation(
                    passed=False,
                    reason_codes=("OPEN_ORDER_STATE_CHANGED",),
                    broker_evidence={"live_state": snapshot},
                )
            if snapshot["status"].upper() not in ACTIONABLE_ORDER_STATUSES:
                return ProposalValidation(
                    passed=False,
                    reason_codes=("OPEN_ORDER_NOT_ACTIONABLE",),
                    broker_evidence={"live_state": snapshot},
                )
            if decision == TraderDecision.CANCEL_ORDER:
                return ProposalValidation(
                    passed=True,
                    reason_codes=(),
                    broker_evidence={"old_state": snapshot},
                )
            if decision != TraderDecision.MODIFY_ORDER:
                return ProposalValidation(
                    passed=False,
                    reason_codes=("UNSUPPORTED_OPEN_ORDER_DECISION",),
                    broker_evidence={},
                )
            if snapshot["status"].upper() not in MODIFIABLE_ORDER_STATUSES:
                return ProposalValidation(
                    passed=False,
                    reason_codes=("OPEN_ORDER_PENDING_CANCEL",),
                    broker_evidence={"live_state": snapshot},
                )

            current_total = Decimal(snapshot["totalQuantity"])
            filled = Decimal(snapshot["filled"])
            requested_total = action.new_total_quantity or current_total
            requested_limit = (
                action.new_limit_price
                if action.new_limit_price is not None
                else Decimal(snapshot["limitPrice"])
            )
            requested_tif = (
                action.new_tif.value
                if action.new_tif is not None
                else str(snapshot["tif"])
            )
            requested_good_till = (
                action.new_good_till_date_utc.astimezone(timezone.utc).strftime(
                    "%Y%m%d %H:%M:%S UTC"
                )
                if action.new_good_till_date_utc is not None
                else str((snapshot.get("orderAttributes") or {}).get("goodTillDate") or "")
            )
            if not requested_total.is_finite():
                return ProposalValidation(
                    passed=False,
                    reason_codes=("OPEN_ORDER_TOTAL_NON_FINITE",),
                    broker_evidence={"old_state": snapshot},
                )
            if not requested_limit.is_finite():
                return ProposalValidation(
                    passed=False,
                    reason_codes=("OPEN_ORDER_LIMIT_PRICE_NON_FINITE",),
                    broker_evidence={"old_state": snapshot},
                )
            if requested_total > current_total:
                return ProposalValidation(
                    passed=False,
                    reason_codes=("OPEN_ORDER_QUANTITY_INCREASE_FORBIDDEN",),
                    broker_evidence={"old_state": snapshot},
                )
            if requested_total < filled:
                return ProposalValidation(
                    passed=False,
                    reason_codes=("OPEN_ORDER_TOTAL_BELOW_FILLED",),
                    broker_evidence={"old_state": snapshot},
                )
            if requested_total == filled:
                return ProposalValidation(
                    passed=False,
                    reason_codes=("OPEN_ORDER_WOULD_HAVE_NO_REMAINING_QUANTITY",),
                    broker_evidence={"old_state": snapshot},
                )
            if (
                action.new_limit_price is not None
                and snapshot["orderType"] != "LMT"
            ):
                return ProposalValidation(
                    passed=False,
                    reason_codes=("OPEN_ORDER_LIMIT_PRICE_CHANGE_REQUIRES_LMT",),
                    broker_evidence={"old_state": snapshot},
                )
            if (
                requested_total == current_total
                and requested_limit == Decimal(snapshot["limitPrice"])
                and requested_tif == str(snapshot["tif"])
                and requested_good_till
                == str((snapshot.get("orderAttributes") or {}).get("goodTillDate") or "")
            ):
                return ProposalValidation(
                    passed=False,
                    reason_codes=("OPEN_ORDER_NO_EFFECTIVE_CHANGE",),
                    broker_evidence={"old_state": snapshot},
                )

            quote = self.live_contract_quote_evidence(broker, trade.contract)
            if not quote.get("success"):
                return ProposalValidation(
                    passed=False,
                    reason_codes=("OPEN_ORDER_QUOTE_UNUSABLE",),
                    broker_evidence={"old_state": snapshot, "quote": quote},
                )

            what_if_order = copy.deepcopy(trade.order)
            what_if_order.totalQuantity = float(requested_total)
            if action.new_limit_price is not None:
                what_if_order.lmtPrice = float(requested_limit)
            if action.new_tif is not None:
                what_if_order.tif = requested_tif
                what_if_order.goodTillDate = requested_good_till
            what_if_order.whatIf = True
            what_if_order.transmit = True
            try:
                state = self._request_what_if(broker, trade.contract, what_if_order)
            except Exception as exc:
                state = None
                state_error = f"{type(exc).__name__}:broker_operation_failed"
            else:
                state_error = None
            evidence = {
                "success": state is not None,
                "error": state_error
                or ("WHAT_IF_RETURNED_NONE" if state is None else None),
                "old_state": snapshot,
                "requested_change": {
                    "totalQuantity": str(requested_total),
                    "limitPrice": str(requested_limit),
                    "tif": requested_tif,
                    "goodTillDate": requested_good_till,
                },
                "quote": quote,
                "whatIf": True,
                "commission": getattr(state, "commission", None),
                "minCommission": getattr(state, "minCommission", None),
                "maxCommission": getattr(state, "maxCommission", None),
                "initMarginChange": getattr(state, "initMarginChange", None),
                "maintMarginChange": getattr(state, "maintMarginChange", None),
                "warningText": getattr(state, "warningText", None),
            }
            equity = Decimal(
                str(bundle.experiment_subledger_snapshot.get("equity", "0"))
            )
            feasibility_ok, reasons = self._feasibility_common(
                evidence, equity=equity
            )
            return ProposalValidation(
                passed=feasibility_ok,
                reason_codes=() if feasibility_ok else reasons,
                broker_evidence=evidence,
            )
        finally:
            if owns_connection:
                broker.disconnect()

    @staticmethod
    def _resolve_open_position(ib: Any, action: AutonomousPositionAction):
        for position in ib.positions():
            contract = position.contract
            if action.contract_id is not None and int(getattr(contract, "conId", 0) or 0) == action.contract_id:
                return position
            if str(getattr(contract, "symbol", "")).upper() != action.symbol.upper():
                continue
            if str(getattr(contract, "secType", "")).upper() != action.sec_type.upper():
                continue
            if action.expiry and str(getattr(contract, "lastTradeDateOrContractMonth", "")) != action.expiry:
                continue
            if action.strike is not None and Decimal(str(getattr(contract, "strike", 0))) != action.strike:
                continue
            if action.right and str(getattr(contract, "right", "")).upper() != action.right.upper():
                continue
            return position
        return None

    def _connect(self, *, client_id: int | None = None):
        from ib_insync import IB

        ib = IB()
        selected_client_id = (
            random.randint(self.client_id_min, self.client_id_max)
            if client_id is None
            else int(client_id)
        )
        ib.connect(
            self.host,
            self.port,
            clientId=selected_client_id,
            timeout=self.timeout_seconds,
        )
        if not ib.isConnected():
            raise ConnectionError("IBKR paper Gateway connection failed")
        accounts = ib.managedAccounts()
        if len(accounts) != 1 or not str(accounts[0]).upper().startswith("DU"):
            ib.disconnect()
            raise PermissionError("single DU paper account identity required")
        if self.expected_account_hash is None:
            ib.disconnect()
            raise PermissionError("expected paper account identity hash is required")
        actual_hash = expected_identity_hash(str(accounts[0]))
        if actual_hash != self.expected_account_hash:
            ib.disconnect()
            raise PermissionError("paper account identity mismatch")
        return ib

    @staticmethod
    def _valid_live_price(value: Any) -> bool:
        try:
            parsed = Decimal(str(value))
        except Exception:
            return False
        return parsed.is_finite() and parsed > 0

    def _single_live_quote_evidence(
        self,
        ib: Any,
        contract: Any,
        *,
        wait_seconds: float,
        max_age_seconds: float,
    ) -> dict[str, Any]:
        ib.reqMarketDataType(1)  # explicitly request LIVE data
        ticker = ib.reqMktData(contract, "", True, False)
        ib.sleep(wait_seconds)
        bid = getattr(ticker, "bid", None)
        ask = getattr(ticker, "ask", None)
        stamp = getattr(ticker, "time", None)
        actual_market_data_type = getattr(ticker, "marketDataType", None)
        if actual_market_data_type != 1:
            return {
                "success": False,
                "reason": "TRADE_CONTRACT_MARKET_DATA_NOT_REALTIME",
                "contract": self._serialize_contract(contract),
                "market_data_type": actual_market_data_type,
            }
        if not self._valid_live_price(bid) or not self._valid_live_price(ask):
            return {
                "success": False,
                "reason": "TRADE_CONTRACT_LIVE_BID_ASK_MISSING",
                "contract": self._serialize_contract(contract),
            }
        bid_d = Decimal(str(bid))
        ask_d = Decimal(str(ask))
        if bid_d > ask_d:
            return {
                "success": False,
                "reason": "TRADE_CONTRACT_CROSSED_MARKET",
                "contract": self._serialize_contract(contract),
                "bid": str(bid_d),
                "ask": str(ask_d),
            }
        if stamp is None or not hasattr(stamp, "astimezone"):
            return {
                "success": False,
                "reason": "TRADE_CONTRACT_QUOTE_TIMESTAMP_MISSING",
                "contract": self._serialize_contract(contract),
            }
        server_time = ib.reqCurrentTime()
        if server_time is None or not hasattr(server_time, "astimezone"):
            return {
                "success": False,
                "reason": "BROKER_SERVER_TIME_MISSING_FOR_TRADE_QUOTE",
                "contract": self._serialize_contract(contract),
            }
        from datetime import timezone
        quote_utc = stamp.astimezone(timezone.utc)
        broker_utc = server_time.astimezone(timezone.utc)
        age_seconds = (broker_utc - quote_utc).total_seconds()
        if age_seconds < -5.0 or age_seconds > max_age_seconds:
            return {
                "success": False,
                "reason": "TRADE_CONTRACT_QUOTE_STALE",
                "contract": self._serialize_contract(contract),
                "quote_time_utc": quote_utc.isoformat().replace("+00:00", "Z"),
                "broker_time_utc": broker_utc.isoformat().replace("+00:00", "Z"),
                "age_seconds": age_seconds,
            }
        return {
            "success": True,
            "contract": self._serialize_contract(contract),
            "bid": str(bid_d),
            "ask": str(ask_d),
            "quote_time_utc": quote_utc.isoformat().replace("+00:00", "Z"),
            "broker_time_utc": broker_utc.isoformat().replace("+00:00", "Z"),
            "age_seconds": age_seconds,
            "requested_market_data_type": "LIVE",
            "market_data_type": 1,
        }

    def live_contract_quote_evidence(
        self,
        ib: Any,
        contract: Any,
        *,
        wait_seconds: float = 2.0,
        max_age_seconds: float = 15.0,
    ) -> dict[str, Any]:
        """Require fresh live market evidence before broker transmission.

        For BAG contracts, a direct combo quote is preferred. If IBKR does not
        publish a combo bid/ask, every combo leg must independently have a fresh
        LIVE bid/ask; this preserves defined-risk multi-leg capability without
        accepting stale or delayed inputs.
        """
        try:
            direct = self._single_live_quote_evidence(
                ib,
                contract,
                wait_seconds=wait_seconds,
                max_age_seconds=max_age_seconds,
            )
            if direct.get("success"):
                return {**direct, "validation_mode": "DIRECT_CONTRACT"}

            if str(getattr(contract, "secType", "") or "").upper() != "BAG":
                return direct

            from ib_insync import Contract
            leg_results: list[dict[str, Any]] = []
            for leg in getattr(contract, "comboLegs", []) or []:
                leg_contract = Contract(
                    conId=int(getattr(leg, "conId", 0) or 0),
                    exchange=str(getattr(leg, "exchange", "") or "SMART"),
                    currency=str(getattr(contract, "currency", "") or "USD"),
                )
                qualified = ib.qualifyContracts(leg_contract)
                if not qualified:
                    return {
                        "success": False,
                        "reason": "TRADE_COMBO_LEG_UNRESOLVED",
                        "contract": self._serialize_contract(contract),
                        "failed_leg_con_id": leg_contract.conId,
                    }
                evidence = self._single_live_quote_evidence(
                    ib,
                    qualified[0],
                    wait_seconds=wait_seconds,
                    max_age_seconds=max_age_seconds,
                )
                leg_results.append(evidence)
                if not evidence.get("success"):
                    return {
                        "success": False,
                        "reason": "TRADE_COMBO_LEG_MARKET_DATA_BLOCK",
                        "contract": self._serialize_contract(contract),
                        "leg_results": leg_results,
                    }
            if not leg_results:
                return direct
            return {
                "success": True,
                "contract": self._serialize_contract(contract),
                "validation_mode": "ALL_COMBO_LEGS",
                "requested_market_data_type": "LIVE",
                "leg_results": leg_results,
            }
        except Exception as exc:
            return {
                "success": False,
                "reason": "TRADE_CONTRACT_MARKET_DATA_CHECK_FAILED",
                "error": f"{type(exc).__name__}:broker_operation_failed",
                "contract": self._serialize_contract(contract),
            }

    @staticmethod
    def _serialize_contract(contract: Any) -> dict[str, Any]:
        return {
            "conId": int(getattr(contract, "conId", 0) or 0),
            "symbol": str(getattr(contract, "symbol", "")),
            "localSymbol": str(getattr(contract, "localSymbol", "")),
            "secType": str(getattr(contract, "secType", "")),
            "exchange": str(getattr(contract, "exchange", "")),
            "primaryExchange": str(getattr(contract, "primaryExchange", "")),
            "currency": str(getattr(contract, "currency", "")),
            "expiry": str(getattr(contract, "lastTradeDateOrContractMonth", "")),
            "strike": float(getattr(contract, "strike", 0) or 0),
            "right": str(getattr(contract, "right", "")),
            "multiplier": str(getattr(contract, "multiplier", "")),
        }

    _CONTRACT_ARGUMENT_ALIASES = (
        ("symbol",),
        ("sec_type", "secType"),
        ("exchange",),
        ("currency",),
        ("primary_exchange", "primaryExchange"),
        ("expiry", "lastTradeDateOrContractMonth"),
        ("strike",),
        ("right",),
        ("multiplier",),
        ("conId", "con_id", "contract_id"),
    )

    @classmethod
    def _normalized_contract_spec(cls, spec: dict[str, Any]) -> dict[str, Any]:
        nested = spec.get("contract")
        if nested is None:
            return dict(spec)
        if not isinstance(nested, dict):
            raise ValueError("CONTRACT_ARGUMENT_OBJECT_REQUIRED")

        outer = {key: value for key, value in spec.items() if key != "contract"}
        for aliases in cls._CONTRACT_ARGUMENT_ALIASES:
            values = [
                mapping[key]
                for mapping in (outer, nested)
                for key in aliases
                if key in mapping and mapping[key] not in (None, "")
            ]
            normalized_values = {
                str(value).strip().upper() for value in values
            }
            if len(normalized_values) > 1:
                raise ValueError("CONTRACT_ARGUMENT_IDENTITY_CONFLICT")
        nested_contract = {
            key: nested[key]
            for aliases in cls._CONTRACT_ARGUMENT_ALIASES
            for key in aliases
            if key in nested
        }
        return {**outer, **nested_contract}

    @classmethod
    def _contract_from_spec(cls, spec: dict[str, Any]):
        from ib_insync import Contract

        spec = cls._normalized_contract_spec(spec)
        sec_type = str(spec.get("sec_type") or spec.get("secType") or "STK").upper()
        contract = Contract(
            symbol=str(spec.get("symbol", "")).upper(),
            secType=sec_type,
            exchange=str(spec.get("exchange") or "SMART"),
            currency=str(spec.get("currency") or "USD"),
        )
        primary_exchange = spec.get("primary_exchange") or spec.get("primaryExchange")
        if primary_exchange:
            contract.primaryExchange = str(primary_exchange)
        expiry = spec.get("expiry") or spec.get("lastTradeDateOrContractMonth")
        if expiry:
            contract.lastTradeDateOrContractMonth = str(expiry)
        if spec.get("strike") is not None:
            contract.strike = float(spec["strike"])
        if spec.get("right"):
            contract.right = str(spec["right"]).upper()
        if spec.get("multiplier"):
            contract.multiplier = str(spec["multiplier"])
        contract_id = spec.get("conId") or spec.get("con_id") or spec.get("contract_id")
        if contract_id:
            contract.conId = int(contract_id)
        return contract

    def _qualify(self, ib: Any, spec: dict[str, Any]):
        contract = self._contract_from_spec(spec)
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            raise LookupError(f"IBKR contract not found for {spec}")
        return qualified[0]

    def _account_state(self, _: dict[str, Any]) -> dict[str, Any]:
        """Return broker/session context without exposing global account capital.

        The autonomous experiment reasons from its isolated ledger equity. Raw
        account NetLiquidation/cash/buying-power/margin values are intentionally
        not returned to Codex; broker feasibility remains authoritative through
        per-order IBKR what-if checks.
        """
        ib = self._connect()
        try:
            # Touch accountSummary so connection/account health is exercised, but
            # never surface global balance fields to the model-facing tool result.
            ib.accountSummary()
            server_time = ib.reqCurrentTime()
            server_time_utc = (
                server_time.astimezone(__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z")
                if hasattr(server_time, "astimezone")
                else str(server_time)
            )
            return {
                "success": True,
                "paper_account": True,
                "declared_options_level": self.declared_options_level,
                "global_broker_balances_redacted": True,
                "server_time_utc": server_time_utc,
            }
        finally:
            ib.disconnect()

    def _positions(self, _: dict[str, Any]) -> dict[str, Any]:
        ib = self._connect()
        try:
            return {
                "success": True,
                "positions": [
                    {
                        "contract": self._serialize_contract(pos.contract),
                        "position": str(pos.position),
                        "avgCost": float(pos.avgCost),
                    }
                    for pos in ib.positions()
                ],
            }
        finally:
            ib.disconnect()

    def _open_orders(self, _: dict[str, Any]) -> dict[str, Any]:
        ib = self._connect()
        try:
            items = [canonical_open_order(trade) for trade in ib.reqAllOpenOrders()]
            return {"success": True, "open_orders": items}
        finally:
            ib.disconnect()

    def _executions(self, _: dict[str, Any]) -> dict[str, Any]:
        from ib_insync import ExecutionFilter

        ib = self._connect()
        try:
            fills = ib.reqExecutions(ExecutionFilter())
            items = []
            for fill in fills:
                execution = fill.execution
                contract = fill.contract
                commission_report = getattr(fill, "commissionReport", None)
                raw_side = str(getattr(execution, "side", "") or "").upper()
                side = "BUY" if raw_side in {"BOT", "BUY"} else "SELL" if raw_side in {"SLD", "SELL"} else raw_side
                import hashlib
                exec_id = str(getattr(execution, "execId", "") or "")
                items.append({
                    "execution_id_hash": hashlib.sha256(exec_id.encode("utf-8")).hexdigest() if exec_id else None,
                    "orderRef": str(getattr(execution, "orderRef", "") or ""),
                    "permId": int(getattr(execution, "permId", 0) or 0),
                    "orderId": int(getattr(execution, "orderId", 0) or 0),
                    "clientId": int(getattr(execution, "clientId", 0) or 0),
                    "account": str(getattr(execution, "acctNumber", "") or ""),
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
                    "contract": self._serialize_contract(contract),
                })
            return {"success": True, "executions": items}
        finally:
            ib.disconnect()

    def _resolve_contract(self, args: dict[str, Any]) -> dict[str, Any]:
        ib = self._connect()
        try:
            details = ib.reqContractDetails(self._contract_from_spec(args))
            return {
                "success": bool(details),
                "contracts": [self._serialize_contract(item.contract) for item in details],
            }
        finally:
            ib.disconnect()

    def _quote(self, args: dict[str, Any]) -> dict[str, Any]:
        ib = self._connect()
        try:
            contract = self._qualify(ib, args)
            ticker = ib.reqMktData(contract, snapshot=True)
            ib.sleep(float(args.get("wait_seconds", 2.0)))
            greeks = getattr(ticker, "modelGreeks", None)
            return {
                "success": True,
                "contract": self._serialize_contract(contract),
                "bid": ticker.bid,
                "ask": ticker.ask,
                "last": ticker.last,
                "close": ticker.close,
                "marketPrice": ticker.marketPrice(),
                "volume": ticker.volume,
                "impliedVolatility": ticker.impliedVolatility,
                "modelGreeks": None if greeks is None else {
                    "impliedVol": greeks.impliedVol,
                    "delta": greeks.delta,
                    "gamma": greeks.gamma,
                    "vega": greeks.vega,
                    "theta": greeks.theta,
                    "optPrice": greeks.optPrice,
                    "undPrice": greeks.undPrice,
                },
            }
        finally:
            ib.disconnect()

    def _historical_bars(self, args: dict[str, Any]) -> dict[str, Any]:
        ib = self._connect()
        try:
            contract = self._qualify(ib, args)
            bars = ib.reqHistoricalData(
                contract,
                endDateTime=str(args.get("end", "")),
                durationStr=str(args.get("duration", "5 D")),
                barSizeSetting=str(args.get("bar_size", "5 mins")),
                whatToShow=str(args.get("what_to_show", "TRADES")),
                useRTH=bool(args.get("use_rth", True)),
                formatDate=1,
                keepUpToDate=False,
            )
            return {
                "success": True,
                "contract": self._serialize_contract(contract),
                "bars": [
                    {
                        "date": str(bar.date), "open": bar.open, "high": bar.high,
                        "low": bar.low, "close": bar.close, "volume": bar.volume,
                        "average": bar.average, "barCount": bar.barCount,
                    }
                    for bar in bars
                ],
            }
        finally:
            ib.disconnect()

    def session_evidence(
        self,
        reference_symbols: tuple[str, ...],
    ) -> dict[str, Any] | None:
        """Authoritative IBKR session + open-order evidence for orchestration.

        Read-only: reuses _connect (single-DU PAPER + identity hash). Returns
        None whenever the calendar is not authoritatively resolvable so the
        caller can never fabricate CLOSED and always falls back to baseline
        fail-closed behaviour.

        The caller (orchestration/policy layer) supplies ``reference_symbols``
        so that this function never hard-codes a reference set.

        All required references must resolve, share the same timezone, and
        yield the same MarketSession classification at the single authoritative
        broker time.  A single missing or disagreeing reference produces None.
        """
        from datetime import timezone as tz

        from ib_insync import Contract

        from .market_observation import MarketSession, classify_session
        from .open_order_management import EXPERIMENT_ORDER_PREFIX

        try:
            ib = self._connect()
        except Exception:
            return None
        try:
            broker_time = ib.reqCurrentTime()
            if broker_time is None or not hasattr(broker_time, "astimezone"):
                return None
            broker_time_utc = broker_time.astimezone(tz.utc)

            references: list[dict[str, Any]] = []
            for symbol in sorted(reference_symbols):
                probe = Contract(
                    symbol=symbol, secType="STK", exchange="SMART", currency="USD"
                )
                details = ib.reqContractDetails(probe)
                liquid_hours = ""
                time_zone_id = ""
                for item in details or []:
                    lh = str(getattr(item, "liquidHours", "") or "")
                    tzid = str(getattr(item, "timeZoneId", "") or "")
                    if lh and tzid:
                        liquid_hours = lh
                        time_zone_id = tzid
                        break
                if not liquid_hours or not time_zone_id:
                    return None
                session = classify_session(broker_time_utc, liquid_hours, time_zone_id)
                if session is MarketSession.UNKNOWN:
                    return None
                references.append(
                    {
                        "symbol": symbol,
                        "liquid_hours": liquid_hours,
                        "timezone_id": time_zone_id,
                        "session": session.value,
                    }
                )

            if len(references) != len(reference_symbols):
                return None

            sessions = {r["session"] for r in references}
            timezones = {r["timezone_id"] for r in references}
            if len(sessions) != 1 or len(timezones) != 1:
                return None

            has_open_orders = any(
                str(getattr(trade.order, "orderRef", "") or "").startswith(
                    f"{EXPERIMENT_ORDER_PREFIX}-"
                )
                for trade in ib.reqAllOpenOrders()
            )
            return {
                "broker_time_utc": broker_time_utc.isoformat().replace("+00:00", "Z"),
                "liquid_hours": references[0]["liquid_hours"],
                "timezone_id": references[0]["timezone_id"],
                "session": references[0]["session"],
                "has_open_orders": bool(has_open_orders),
            }
        except Exception:
            return None
        finally:
            try:
                ib.disconnect()
            except Exception:
                pass

    def _option_chain(self, args: dict[str, Any]) -> dict[str, Any]:
        ib = self._connect()
        try:
            underlying_spec = dict(args)
            underlying_spec["sec_type"] = str(args.get("underlying_sec_type", "STK"))
            underlying = self._qualify(ib, underlying_spec)
            chains = ib.reqSecDefOptParams(
                underlying.symbol,
                str(args.get("fut_fop_exchange", "")),
                underlying.secType,
                underlying.conId,
            )
            return {
                "success": True,
                "underlying": self._serialize_contract(underlying),
                "chains": [
                    {
                        "exchange": chain.exchange,
                        "underlyingConId": chain.underlyingConId,
                        "tradingClass": chain.tradingClass,
                        "multiplier": chain.multiplier,
                        "expirations": sorted(chain.expirations),
                        "strikes": sorted(float(x) for x in chain.strikes),
                    }
                    for chain in chains
                ],
            }
        finally:
            ib.disconnect()

    def _market_scanner(self, args: dict[str, Any]) -> dict[str, Any]:
        from ib_insync import ScannerSubscription

        ib = self._connect()
        try:
            subscription = ScannerSubscription(
                instrument=str(args.get("instrument", "STK")),
                locationCode=str(args.get("location_code", "STK.US.MAJOR")),
                scanCode=str(args.get("scan_code", "TOP_PERC_GAIN")),
                numberOfRows=int(args.get("rows", 50)),
            )
            if args.get("above_price") is not None:
                subscription.abovePrice = float(args["above_price"])
            if args.get("below_price") is not None:
                subscription.belowPrice = float(args["below_price"])
            if args.get("above_volume") is not None:
                subscription.aboveVolume = int(args["above_volume"])
            rows = ib.reqScannerData(subscription)
            return {
                "success": True,
                "scan": {
                    "instrument": subscription.instrument,
                    "locationCode": subscription.locationCode,
                    "scanCode": subscription.scanCode,
                },
                "results": [
                    {
                        "rank": item.rank,
                        "contract": self._serialize_contract(item.contractDetails.contract),
                        "distance": item.distance,
                        "benchmark": item.benchmark,
                        "projection": item.projection,
                        "legsStr": item.legsStr,
                    }
                    for item in rows
                ],
            }
        finally:
            ib.disconnect()

    def _news_search(self, args: dict[str, Any]) -> dict[str, Any]:
        ib = self._connect()
        try:
            contract = self._qualify(ib, args)
            providers = ib.reqNewsProviders()
            selected = args.get("provider_codes")
            provider_codes = (
                "+".join(selected)
                if isinstance(selected, list)
                else str(selected or "+".join(p.code for p in providers))
            )
            headlines = ib.reqHistoricalNews(
                contract.conId,
                provider_codes,
                str(args.get("start", "")),
                str(args.get("end", "")),
                int(args.get("total_results", 50)),
            )
            return {
                "success": True,
                "contract": self._serialize_contract(contract),
                "providers": [{"code": p.code, "name": p.name} for p in providers],
                "headlines": [
                    {
                        "time": str(item.time),
                        "providerCode": item.providerCode,
                        "articleId": item.articleId,
                        "headline": item.headline,
                    }
                    for item in headlines
                ],
            }
        finally:
            ib.disconnect()

    def _broker_feasibility_from_args(self, args: dict[str, Any]) -> dict[str, Any]:
        if "proposal" in args:
            proposal = AutonomousTradeProposal.model_validate(args["proposal"])
            return self._model_research_feasibility(
                self._broker_feasibility(proposal)
            )

        try:
            args = self._normalized_contract_spec(args)
        except ValueError as exc:
            return self._model_research_feasibility(
                {
                    "success": False,
                    "error": "BROKER_FEASIBILITY_ARGUMENTS_INVALID",
                    "error_type": type(exc).__name__,
                    "error_code": str(exc),
                    "stage": "REQUEST_VALIDATION",
                    "whatIf": True,
                    "paper_only": True,
                }
            )

        validation_error = self._validate_flat_feasibility_args(args)
        if validation_error is not None:
            return self._model_research_feasibility(validation_error)

        broker = None
        try:
            broker = self._connect()
            contract = self._feasibility_contract_from_args(broker, args)
            contract_error = self._qualified_contract_error(args, contract)
            if contract_error is not None:
                return self._model_research_feasibility(contract_error)
            evidence = self._what_if_evidence(
                broker,
                contract,
                action=str(args["action"]).upper(),
                order_type=str(args["order_type"]).upper(),
                quantity=Decimal(str(args["quantity"])),
                limit_price=(
                    None
                    if args.get("limit_price") is None
                    else Decimal(str(args["limit_price"]))
                ),
                time_in_force=str(
                    args.get("time_in_force") or args.get("tif") or "DAY"
                ).upper(),
            )
            return self._model_research_feasibility(evidence)
        except Exception as exc:
            return self._model_research_feasibility(
                {
                    "success": False,
                    "error": f"{type(exc).__name__}:broker_operation_failed",
                    "error_type": type(exc).__name__,
                    "error_code": "BROKER_FEASIBILITY_BROKER_OPERATION_FAILED",
                    "stage": "BROKER_WHAT_IF",
                    "whatIf": True,
                    "paper_only": True,
                }
            )
        finally:
            if broker is not None:
                broker.disconnect()

    @staticmethod
    def _combo_leg_contract_spec(leg: dict[str, Any]) -> dict[str, Any]:
        """Return the canonical contract identity carried by a combo leg.

        A leg may express its contract either flat on the leg itself or as the
        repository's canonical nested contract object -- the same shape
        ``_serialize_contract`` emits to the model. Both are accepted so a model
        can return authoritative broker-resolved identity unchanged.
        """
        nested = leg.get("contract")
        return nested if isinstance(nested, dict) else leg

    @classmethod
    def _combo_leg_contract_id(cls, leg: dict[str, Any]) -> int | None:
        """Return the positive integer conId for a combo leg, else None."""
        spec = cls._combo_leg_contract_spec(leg)
        raw = next(
            (
                spec.get(key)
                for key in ("conId", "con_id", "contract_id")
                if spec.get(key) not in (None, "", 0, "0")
            ),
            None,
        )
        if isinstance(raw, bool):
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def _combo_leg_has_identity_conflict(leg: dict[str, Any]) -> bool:
        """Detect contradictory identity: any two positive conIds that differ.

        A leg may express identity flat on the leg itself (conId, con_id,
        contract_id) or nested inside ``leg['contract']``. A conflict exists when
        more than one positive conId is present across all sources and they are
        not equal. This prevents an adversarial payload from smuggling two
        identities simultaneously, even inside the same nested contract dict.
        """
        sources = [leg]
        nested = leg.get("contract")
        if isinstance(nested, dict):
            sources.append(nested)
        ids: set[int] = set()
        for mapping in sources:
            for key in ("conId", "con_id", "contract_id"):
                raw = mapping.get(key)
                if raw not in (None, "", 0, "0"):
                    try:
                        val = int(raw)
                        if val > 0:
                            ids.add(val)
                    except (TypeError, ValueError):
                        continue
        return len(ids) > 1

    @staticmethod
    def _combo_legs_vertical_structural_error(
        legs: list[dict[str, Any]],
    ) -> str | None:
        """Validate declared VERTICAL intent against structural consistency.

        Returns None if legs are structurally consistent with a standard
        vertical spread, else an error-code string.

        A vertical spread must have exactly two legs, same symbol, same
        expiry, same right, different strikes, opposite BUY/SELL actions.
        """
        if len(legs) != 2:
            return "BROKER_FEASIBILITY_VERTICAL_STRUCTURAL_INCONSISTENT"
        specs = [
            IBKRResearchToolbox._combo_leg_contract_spec(l) for l in legs
        ]
        fields = {
            key: [str(s.get(key) or "").strip() for s in specs]
            for key in ("symbol", "secType", "right", "expiry")
        }
        for key in ("symbol", "secType", "right", "expiry"):
            if not fields[key][0] or any(v != fields[key][0] for v in fields[key]):
                return "BROKER_FEASIBILITY_VERTICAL_STRUCTURAL_INCONSISTENT"
        actions = [str(l.get("action") or "").upper() for l in legs]
        if sorted(actions) != ["BUY", "SELL"]:
            return "BROKER_FEASIBILITY_VERTICAL_STRUCTURAL_INCONSISTENT"
        try:
            strikes = [float(s.get("strike") or 0) for s in specs]
        except (TypeError, ValueError):
            return "BROKER_FEASIBILITY_VERTICAL_STRUCTURAL_INCONSISTENT"
        if strikes[0] == strikes[1] or any(s <= 0 for s in strikes):
            return "BROKER_FEASIBILITY_VERTICAL_STRUCTURAL_INCONSISTENT"
        return None

    @classmethod
    def _validate_flat_feasibility_args(
        cls, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        def invalid(error_code: str) -> dict[str, Any]:
            return {
                "success": False,
                "error": "BROKER_FEASIBILITY_ARGUMENTS_INVALID",
                "error_type": "ValueError",
                "error_code": error_code,
                "stage": "REQUEST_VALIDATION",
                "whatIf": True,
                "paper_only": True,
            }

        has_contract_id = any(
            args.get(key) not in (None, "", 0, "0")
            for key in ("conId", "con_id", "contract_id")
        )
        if not has_contract_id and not str(args.get("symbol") or "").strip():
            return invalid("BROKER_FEASIBILITY_CONTRACT_REQUIRED")
        sec_type = str(
            args.get("sec_type") or args.get("secType") or ""
        ).upper()
        legs = args.get("legs")
        if sec_type == "BAG":
            if not isinstance(legs, list) or len(legs) < 2:
                return invalid("BROKER_FEASIBILITY_COMBO_LEGS_REQUIRED")
            seen_leg_identities: set[int] = set()
            for leg in legs:
                if not isinstance(leg, dict):
                    return invalid("BROKER_FEASIBILITY_COMBO_LEG_INVALID")
                contract_id = cls._combo_leg_contract_id(leg)
                if contract_id is None:
                    return invalid(
                        "BROKER_FEASIBILITY_COMBO_LEG_CONTRACT_REQUIRED"
                    )
                if cls._combo_leg_has_identity_conflict(leg):
                    return invalid(
                        "BROKER_FEASIBILITY_COMBO_LEG_IDENTITY_CONFLICT"
                    )
                if contract_id in seen_leg_identities:
                    return invalid("BROKER_FEASIBILITY_COMBO_LEG_DUPLICATE")
                seen_leg_identities.add(contract_id)
                if str(leg.get("action") or "").upper() not in {
                    "BUY",
                    "SELL",
                }:
                    return invalid("BROKER_FEASIBILITY_COMBO_LEG_ACTION_INVALID")
                ratio = cls._decimal_or_none(leg.get("ratio"))
                if (
                    ratio is None
                    or ratio <= 0
                    or ratio != ratio.to_integral_value()
                ):
                    return invalid(
                        "BROKER_FEASIBILITY_COMBO_LEG_RATIO_INVALID"
                    )
            if str(args.get("structure") or "").upper() == "VERTICAL":
                vert_err = cls._combo_legs_vertical_structural_error(legs)
                if vert_err is not None:
                    return invalid(vert_err)
        elif legs:
            return invalid("BROKER_FEASIBILITY_COMBO_SEC_TYPE_REQUIRED")
        if str(args.get("action") or "").upper() not in {"BUY", "SELL"}:
            return invalid("BROKER_FEASIBILITY_ACTION_INVALID")
        quantity = cls._decimal_or_none(args.get("quantity"))
        if quantity is None or quantity <= 0:
            return invalid("BROKER_FEASIBILITY_QUANTITY_INVALID")
        order_type = str(args.get("order_type") or "").upper()
        if not order_type:
            return invalid("BROKER_FEASIBILITY_ORDER_TYPE_REQUIRED")
        if order_type == "LMT":
            limit_price = cls._decimal_or_none(args.get("limit_price"))
            if limit_price is None or limit_price <= 0:
                return invalid("BROKER_FEASIBILITY_LIMIT_PRICE_INVALID")
        return None

    def _qualified_contract_error(
        self, args: dict[str, Any], contract: Any
    ) -> dict[str, Any] | None:
        requested_id = next(
            (
                args.get(key)
                for key in ("conId", "con_id", "contract_id")
                if args.get(key) not in (None, "", 0, "0")
            ),
            None,
        )
        actual_id = int(getattr(contract, "conId", 0) or 0)
        requested_symbol = str(args.get("symbol") or "").strip().upper()
        actual_symbol = str(getattr(contract, "symbol", "") or "").strip().upper()
        id_mismatch = requested_id is not None and actual_id != int(requested_id)
        symbol_mismatch = (
            bool(requested_symbol)
            and bool(actual_symbol)
            and actual_symbol != requested_symbol
        )
        if not id_mismatch and not symbol_mismatch:
            return None
        return {
            "success": False,
            "error": "BROKER_FEASIBILITY_CONTRACT_MISMATCH",
            "error_type": "ValueError",
            "error_code": "BROKER_FEASIBILITY_CONTRACT_MISMATCH",
            "stage": "CONTRACT_QUALIFICATION",
            "contract": self._serialize_contract(contract),
            "whatIf": True,
            "paper_only": True,
        }

    def _feasibility_contract_from_args(
        self, broker: Any, args: dict[str, Any]
    ) -> Any:
        sec_type = str(
            args.get("sec_type") or args.get("secType") or ""
        ).upper()
        if sec_type != "BAG":
            return self._qualify(broker, args)

        from ib_insync import ComboLeg, Contract

        combo_legs = []
        for leg in args.get("legs") or []:
            spec = self._combo_leg_contract_spec(leg)
            contract_id = self._combo_leg_contract_id(leg)
            if contract_id is None:
                raise LookupError("IBKR combo leg contract identity missing")
            leg_exchange = str(
                leg.get("exchange") or spec.get("exchange") or "SMART"
            )
            leg_contract = Contract(
                conId=contract_id,
                exchange=leg_exchange,
                currency=str(
                    leg.get("currency")
                    or spec.get("currency")
                    or args.get("currency")
                    or "USD"
                ),
            )
            qualified = broker.qualifyContracts(leg_contract)
            if not qualified:
                raise LookupError("IBKR combo leg contract not found")
            resolved = qualified[0]
            if int(getattr(resolved, "conId", 0) or 0) != contract_id:
                raise LookupError("IBKR combo leg contract mismatch")
            combo_legs.append(
                ComboLeg(
                    conId=contract_id,
                    ratio=int(leg.get("ratio") or 1),
                    action=str(leg.get("action") or "").upper(),
                    exchange=leg_exchange,
                )
            )
        return Contract(
            symbol=str(args.get("symbol") or "").upper(),
            secType="BAG",
            exchange=str(args.get("exchange") or "SMART"),
            currency=str(args.get("currency") or "USD"),
            comboLegs=combo_legs,
        )

    @staticmethod
    def _request_what_if(broker: Any, contract: Any, order: Any):
        if getattr(order, "whatIf", False) is not True:
            raise RuntimeError("BROKER_FEASIBILITY_WHAT_IF_REQUIRED")
        # IBKR requires transmit=True on a what-if request.
        # whatIf=True keeps the request simulated.
        if getattr(order, "transmit", False) is not True:
            raise RuntimeError("BROKER_FEASIBILITY_WHAT_IF_TRANSMIT_REQUIRED")
        return broker.whatIfOrder(contract, order)

    @staticmethod
    def _is_unusable_broker_economic_value(value: Any) -> bool:
        """Detect IBKR 'not computed' sentinel and other non-finite indicators.

        IBKR returns ``1.7976931348623157E308`` (DBL_MAX) when a what-if
        economic value was not meaningfully computed. It may also return
        ``inf``, ``-inf``, ``nan``, or their string equivalents.

        Valid usable values include zero, ordinary finite numbers, and
        Decimal representations thereof.
        """
        if value is None:
            return False

        # String forms observed from IBKR and common sentinels.
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in {
                "1.7976931348623157E308",
                "1.7976931348623157E+308",
                "INF",
                "INFINITY",
                "-INF",
                "-INFINITY",
                "NAN",
            }:
                return True
            try:
                decimal_val = Decimal(normalized)
            except Exception:
                return True
            return str(decimal_val).upper() == "1.7976931348623157E+308"

        if isinstance(value, (int, float)):
            if isinstance(value, float):
                if value != value:  # NaN
                    return True
                if value == float("inf") or value == float("-inf"):
                    return True
            try:
                if float(value) == sys.float_info.max:
                    return True
                decimal_val = Decimal(str(value))
                return str(decimal_val).upper() == "1.7976931348623157E+308"
            except Exception:
                return True

        if isinstance(value, Decimal):
            return str(value).upper() == "1.7976931348623157E+308"

        return True  # unknown type is unusable

    def _what_if_evidence(
        self,
        broker: Any,
        contract: Any,
        *,
        action: str,
        order_type: str,
        quantity: Decimal,
        limit_price: Decimal | None,
        time_in_force: str = "",
    ) -> dict[str, Any]:
        from ib_insync import Order

        order = Order(
            action=action,
            orderType=order_type,
            totalQuantity=float(quantity),
            tif=time_in_force,
            transmit=True,
            whatIf=True,
        )
        if limit_price is not None:
            order.lmtPrice = float(limit_price)
        state = self._request_what_if(broker, contract, order)
        if state is None:
            return {
                "success": False,
                "error": "WHAT_IF_RETURNED_NONE",
                "contract": self._serialize_contract(contract),
                "whatIf": True,
                "paper_only": True,
                "what_if_status": "BROKER_WHATIF_NO_RESPONSE",
                "broker_whatif_reached": False,
                "broker_economics_computed": False,
                "stage": "WHAT_IF_NORMALIZATION",
            }
        broker_economics = {
            key: getattr(state, key, None)
            for key in (
                "commission",
                "minCommission",
                "maxCommission",
                "initMarginBefore",
                "initMarginChange",
                "initMarginAfter",
                "maintMarginBefore",
                "maintMarginChange",
                "maintMarginAfter",
                "equityWithLoanBefore",
                "equityWithLoanChange",
                "equityWithLoanAfter",
            )
        }
        unusable_fields = {
            k for k, v in broker_economics.items() if self._is_unusable_broker_economic_value(v)
        }
        sanitized_economics = {
            key: (None if key in unusable_fields else value)
            for key, value in broker_economics.items()
        }
        required_sentinel_fields = unusable_fields.intersection(
            {"initMarginChange", "maintMarginChange"}
        )
        commission_fields = {"commission", "minCommission", "maxCommission"}
        usable_commission = any(
            sanitized_economics[key] is not None for key in commission_fields
        )
        if not usable_commission:
            required_sentinel_fields.update(unusable_fields.intersection(commission_fields))
        if required_sentinel_fields:
            return {
                "success": False,
                "error": "BROKER_WHATIF_DBL_MAX_SENTINEL",
                "error_type": "ValueError",
                "error_code": "BROKER_ECONOMICS_SENTINEL_DETECTED",
                "contract": self._serialize_contract(contract),
                "whatIf": True,
                "paper_only": True,
                "what_if_status": "BROKER_ECONOMICS_NOT_COMPUTED",
                "broker_whatif_reached": True,
                "broker_economics_computed": False,
                "stage": "WHAT_IF_NORMALIZATION",
                **sanitized_economics,
            }
        result = {
            "success": True,
            "contract": self._serialize_contract(contract),
            **sanitized_economics,
            "warningText": getattr(state, "warningText", None),
            "whatIf": True,
            "paper_only": True,
            "what_if_status": "BROKER_ECONOMICS_COMPUTED",
            "broker_whatif_reached": True,
            "broker_economics_computed": True,
        }
        if self.expected_account_hash is not None:
            result["continuity_host_bindings"] = {
                "account_identity_sha256": self.expected_account_hash,
                "contract_identity_sha256": sha256_json(
                    canonical_contract_identity(contract)
                ),
                "execution_client_id": EXECUTION_CLIENT_ID,
            }
        return result

    def _proposal_contract(self, ib: Any, proposal: AutonomousTradeProposal):
        from ib_insync import ComboLeg, Contract

        if proposal.legs:
            combo_legs = []
            for leg in proposal.legs:
                qualified = self._qualify(ib, leg.model_dump(mode="json"))
                combo_legs.append(
                    ComboLeg(
                        conId=qualified.conId,
                        ratio=leg.ratio,
                        action=leg.action.upper(),
                        exchange=leg.exchange or "SMART",
                    )
                )
            return Contract(
                symbol=proposal.symbol,
                secType="BAG",
                exchange="SMART",
                currency="USD",
                comboLegs=combo_legs,
            )
        return self._qualify(
            ib,
            {
                "symbol": proposal.symbol,
                "sec_type": proposal.sec_type,
                "expiry": proposal.expiry,
                "strike": proposal.strike,
                "right": proposal.right,
                "exchange": "SMART",
                "currency": "USD",
            },
        )

    def _broker_feasibility(
        self,
        proposal: AutonomousTradeProposal,
        *,
        ib: Any | None = None,
    ) -> dict[str, Any]:
        owns_connection = ib is None
        broker = ib or self._connect()
        try:
            contract = self._proposal_contract(broker, proposal)
            return self._what_if_evidence(
                broker,
                contract,
                action=proposal.action.upper(),
                order_type=proposal.order_type.upper(),
                quantity=proposal.quantity,
                limit_price=proposal.limit_price,
                time_in_force="DAY",
            )
        except Exception as exc:
            return {
                "success": False,
                "error": f"{type(exc).__name__}:broker_operation_failed",
                "whatIf": True,
                "paper_only": True,
            }
        finally:
            if owns_connection and broker is not None:
                broker.disconnect()

    @staticmethod
    def _covered_shares(bundle: TraderInputBundle, symbol: str) -> Decimal:
        shares = Decimal("0")
        for item in bundle.positions_snapshot:
            if (
                str(item.get("symbol") or "").upper() == symbol.upper()
                and str(item.get("sec_type") or item.get("secType") or "").upper() == "STK"
            ):
                try:
                    quantity = Decimal(str(item.get("quantity") or item.get("position") or "0"))
                except Exception:
                    continue
                if quantity > 0:
                    shares += quantity
        return shares

    @classmethod
    def _structure_loss_floor(
        cls,
        proposal: AutonomousTradeProposal,
        bundle: TraderInputBundle,
    ) -> tuple[Decimal | None, str | None]:
        if not proposal.loss_is_bounded:
            return None, "UNBOUNDED_LIABILITY"

        quantity = Decimal(str(proposal.quantity))
        action = proposal.action.upper()
        sec_type = proposal.sec_type.upper()

        if not proposal.legs:
            if action == "BUY":
                # capital_required is model-authored and therefore advisory only.
                # Prove maximum paid capital from executable order terms.
                limit_price = (
                    Decimal(str(proposal.limit_price))
                    if proposal.limit_price is not None
                    else None
                )
                if sec_type == "OPT":
                    if limit_price is None or limit_price <= 0:
                        return None, "LONG_OPTION_COST_NOT_PRETRADE_BOUNDED"
                    return limit_price * Decimal("100") * quantity, None
                if sec_type == "STK":
                    if limit_price is None or limit_price <= 0:
                        return None, "LONG_STOCK_COST_NOT_PRETRADE_BOUNDED"
                    return limit_price * quantity, None
                return None, "LONG_INSTRUMENT_MAX_LOSS_NOT_PROVEN"
            if action != "SELL":
                return None, "UNSUPPORTED_ORDER_ACTION"
            if sec_type == "STK":
                return None, "UNBOUNDED_SHORT_STOCK"
            if sec_type != "OPT":
                return None, "UNBOUNDED_OR_UNVERIFIED_SHORT_INSTRUMENT"

            right = str(proposal.right or "").upper()
            if right == "C":
                required_shares = quantity * Decimal("100")
                if cls._covered_shares(bundle, proposal.symbol) < required_shares:
                    return None, "UNCOVERED_SHORT_CALL"
                # Existing long-stock downside is already inside current equity.
                return Decimal("0"), None
            if right == "P":
                if proposal.strike is None or proposal.strike <= 0:
                    return None, "SHORT_PUT_STRIKE_REQUIRED"
                credit = max(Decimal(str(proposal.limit_price or 0)), Decimal("0"))
                per_share_loss = max(Decimal(str(proposal.strike)) - credit, Decimal("0"))
                return per_share_loss * Decimal("100") * quantity, None
            return None, "SHORT_OPTION_RIGHT_REQUIRED"

        expiries = {
            str(leg.expiry or "")
            for leg in proposal.legs
            if leg.sec_type.upper() == "OPT"
        }
        if len(expiries) > 1:
            return None, "MULTI_EXPIRY_SHORT_STRUCTURE_NOT_PROVEN_BOUNDED"

        net_upper_slope = Decimal("0")
        strikes: list[Decimal] = []
        for leg in proposal.legs:
            sign = Decimal("1") if leg.action.upper() == "BUY" else Decimal("-1")
            ratio = Decimal(str(leg.ratio))
            leg_type = leg.sec_type.upper()
            if leg_type == "STK":
                net_upper_slope += sign * ratio
            elif leg_type == "OPT":
                right = str(leg.right or "").upper()
                if leg.strike is None or leg.strike < 0 or right not in {"C", "P"}:
                    return None, "INVALID_OPTION_LEG"
                strike = Decimal(str(leg.strike))
                strikes.append(strike)
                if right == "C":
                    net_upper_slope += sign * ratio
            else:
                return None, "UNVERIFIED_MULTI_LEG_INSTRUMENT"

        if net_upper_slope < 0:
            return None, "UNBOUNDED_UPSIDE_LIABILITY"

        critical = {Decimal("0"), *strikes}
        if strikes:
            critical.add(max(strikes) * Decimal("2") + Decimal("1"))

        overall_qty = quantity
        if proposal.limit_price is not None:
            price = Decimal(str(proposal.limit_price))
            initial_cash = (
                -price * Decimal("100") * overall_qty
                if action == "BUY"
                else price * Decimal("100") * overall_qty
            )
        else:
            if action == "BUY":
                return None, "MULTI_LEG_BUY_COST_NOT_PRETRADE_BOUNDED"
            initial_cash = Decimal("0")

        minimum_pnl: Decimal | None = None
        for underlying in sorted(critical):
            pnl = initial_cash
            for leg in proposal.legs:
                sign = Decimal("1") if leg.action.upper() == "BUY" else Decimal("-1")
                ratio = Decimal(str(leg.ratio))
                leg_type = leg.sec_type.upper()
                if leg_type == "STK":
                    payoff = underlying
                    multiplier = Decimal("1")
                else:
                    strike = Decimal(str(leg.strike))
                    right = str(leg.right or "").upper()
                    payoff = (
                        max(underlying - strike, Decimal("0"))
                        if right == "C"
                        else max(strike - underlying, Decimal("0"))
                    )
                    multiplier = Decimal("100")
                pnl += sign * ratio * payoff * multiplier * overall_qty
            minimum_pnl = pnl if minimum_pnl is None else min(minimum_pnl, pnl)

        loss_floor = max(-(minimum_pnl or Decimal("0")), Decimal("0"))
        return loss_floor, None
