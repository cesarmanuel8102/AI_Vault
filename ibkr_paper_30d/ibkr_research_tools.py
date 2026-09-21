from __future__ import annotations

import os
import random
from decimal import Decimal
from pathlib import Path
from typing import Any

from .autonomous_research import (
    AutonomousPositionAction,
    AutonomousTradeProposal,
    ProposalValidation,
    ResearchRequest,
    ResearchResult,
    ResearchTool,
)
from .ibkr_readonly import expected_identity_hash
from .ibkr_readonly_session import ExpectedPaperIdentityStore
from .risk import CapitalBoundaryInputs, CapitalBoundaryRiskEngine, RiskResult
from .trader_invocation import TraderDecision, TraderInputBundle


PAPER_HOSTS = {"127.0.0.1", "localhost"}
PAPER_PORT = 4002


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
            {"tool": ResearchTool.ACCOUNT_STATE.value, "purpose": "Current paper balances, NLV, cash, buying power and declared option permission level."},
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
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=False,
                data={},
                error=f"{type(exc).__name__}:{exc}",
            )

    WARNING_BLOCK_TOKENS = (
        "not allowed",
        "cannot",
        "rejected",
        "insufficient",
        "incompatible",
        "missing",
    )

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
        feasibility_ok, feasibility_reasons = self._feasibility_common(
            feasibility, equity=equity
        )
        if not feasibility_ok:
            return ProposalValidation(
                passed=False,
                reason_codes=feasibility_reasons,
                broker_evidence=feasibility,
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
                broker_evidence=feasibility,
            )

        return ProposalValidation(
            passed=True,
            reason_codes=(),
            broker_evidence={
                "risk_policy": risk.model_dump(mode="json"),
                "structural_loss_floor": str(structural_floor),
                "effective_maximum_loss": str(effective_maximum_loss),
                "what_if": feasibility,
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
    ) -> ProposalValidation:
        from ib_insync import Order

        ib = self._connect()
        try:
            matched = self._resolve_open_position(ib, action)
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

            order = Order(
                action=action.action.upper(),
                orderType=action.order_type.upper(),
                totalQuantity=float(quantity),
                transmit=False,
                whatIf=True,
            )
            if action.limit_price is not None:
                order.lmtPrice = float(action.limit_price)
            state = ib.whatIfOrder(matched.contract, order)
            evidence = {
                "contract": self._serialize_contract(matched.contract),
                "current_position": str(position),
                "requested_quantity": str(quantity),
                "whatIf": True,
                "commission": getattr(state, "commission", None),
                "warningText": getattr(state, "warningText", None),
            }
            warning = str(evidence.get("warningText") or "").lower()
            if any(token in warning for token in ("not allowed", "cannot", "rejected")):
                return ProposalValidation(
                    passed=False,
                    reason_codes=("BROKER_FEASIBILITY_WARNING_BLOCK",),
                    broker_evidence=evidence,
                )
            return ProposalValidation(
                passed=True,
                reason_codes=(),
                broker_evidence=evidence,
            )
        finally:
            ib.disconnect()

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

    def _connect(self):
        from ib_insync import IB

        ib = IB()
        client_id = random.randint(self.client_id_min, self.client_id_max)
        ib.connect(self.host, self.port, clientId=client_id, timeout=self.timeout_seconds)
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

    @staticmethod
    def _contract_from_spec(spec: dict[str, Any]):
        from ib_insync import Contract

        sec_type = str(spec.get("sec_type") or spec.get("secType") or "STK").upper()
        contract = Contract(
            symbol=str(spec.get("symbol", "")).upper(),
            secType=sec_type,
            exchange=str(spec.get("exchange") or "SMART"),
            currency=str(spec.get("currency") or "USD"),
        )
        if spec.get("primary_exchange"):
            contract.primaryExchange = str(spec["primary_exchange"])
        if spec.get("expiry"):
            contract.lastTradeDateOrContractMonth = str(spec["expiry"])
        if spec.get("strike") is not None:
            contract.strike = float(spec["strike"])
        if spec.get("right"):
            contract.right = str(spec["right"]).upper()
        if spec.get("multiplier"):
            contract.multiplier = str(spec["multiplier"])
        if spec.get("conId") or spec.get("con_id"):
            contract.conId = int(spec.get("conId") or spec.get("con_id"))
        return contract

    def _qualify(self, ib: Any, spec: dict[str, Any]):
        contract = self._contract_from_spec(spec)
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            raise LookupError(f"IBKR contract not found for {spec}")
        return qualified[0]

    def _account_state(self, _: dict[str, Any]) -> dict[str, Any]:
        ib = self._connect()
        try:
            values = ib.accountSummary()
            wanted = {
                "NetLiquidation", "TotalCashValue", "SettledCash", "BuyingPower",
                "AvailableFunds", "ExcessLiquidity", "InitMarginReq", "MaintMarginReq",
            }
            summary: dict[str, str] = {}
            for item in values:
                if item.tag in wanted:
                    summary[item.tag] = str(item.value)
            return {
                "success": True,
                "paper_account": True,
                "declared_options_level": self.declared_options_level,
                "summary": summary,
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
            items = []
            for trade in ib.openTrades():
                items.append({
                    "contract": self._serialize_contract(trade.contract),
                    "orderId": int(getattr(trade.order, "orderId", 0) or 0),
                    "action": str(getattr(trade.order, "action", "")),
                    "orderType": str(getattr(trade.order, "orderType", "")),
                    "quantity": str(getattr(trade.order, "totalQuantity", "")),
                    "status": str(getattr(trade.orderStatus, "status", "")),
                    "orderRef": str(getattr(trade.order, "orderRef", "") or ""),
                })
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
                    "execution_time": str(getattr(execution, "time", "") or ""),
                    "cumQty": str(getattr(execution, "cumQty", "") or ""),
                    "avgPrice": str(getattr(execution, "avgPrice", "") or ""),
                    "side": side,
                    "quantity": str(getattr(execution, "shares", "") or ""),
                    "price": str(getattr(execution, "price", "") or ""),
                    "commission": str(getattr(commission_report, "commission", 0) or 0),
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
        proposal = AutonomousTradeProposal.model_validate(args["proposal"])
        return self._broker_feasibility(proposal)

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

    def _broker_feasibility(self, proposal: AutonomousTradeProposal) -> dict[str, Any]:
        from ib_insync import Order

        ib = self._connect()
        try:
            contract = self._proposal_contract(ib, proposal)
            order = Order(
                action=proposal.action.upper(),
                orderType=proposal.order_type.upper(),
                totalQuantity=float(proposal.quantity),
                transmit=False,
                whatIf=True,
            )
            if proposal.limit_price is not None:
                order.lmtPrice = float(proposal.limit_price)
            state = ib.whatIfOrder(contract, order)
            return {
                "success": True,
                "contract": self._serialize_contract(contract),
                "commission": getattr(state, "commission", None),
                "minCommission": getattr(state, "minCommission", None),
                "maxCommission": getattr(state, "maxCommission", None),
                "initMarginBefore": getattr(state, "initMarginBefore", None),
                "initMarginChange": getattr(state, "initMarginChange", None),
                "initMarginAfter": getattr(state, "initMarginAfter", None),
                "maintMarginBefore": getattr(state, "maintMarginBefore", None),
                "maintMarginChange": getattr(state, "maintMarginChange", None),
                "maintMarginAfter": getattr(state, "maintMarginAfter", None),
                "equityWithLoanBefore": getattr(state, "equityWithLoanBefore", None),
                "equityWithLoanChange": getattr(state, "equityWithLoanChange", None),
                "equityWithLoanAfter": getattr(state, "equityWithLoanAfter", None),
                "warningText": getattr(state, "warningText", None),
                "whatIf": True,
                "paper_only": True,
            }
        finally:
            ib.disconnect()

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
            initial_cash = (
                -Decimal(str(proposal.capital_required))
                if action == "BUY"
                else Decimal("0")
            )

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
