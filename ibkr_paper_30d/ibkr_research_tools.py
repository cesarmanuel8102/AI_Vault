from __future__ import annotations

import random
from decimal import Decimal
from typing import Any

from .autonomous_research import (
    AutonomousTradeProposal,
    ProposalValidation,
    ResearchRequest,
    ResearchResult,
    ResearchTool,
)
from .risk import CapitalBoundaryInputs, CapitalBoundaryRiskEngine, RiskResult
from .trader_invocation import TraderInputBundle


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
    ) -> None:
        if host not in PAPER_HOSTS or port != PAPER_PORT:
            raise ValueError("autonomous research requires local IBKR paper Gateway :4002")
        self.host = host
        self.port = port
        self.client_id_min = client_id_min
        self.client_id_max = client_id_max
        self.timeout_seconds = timeout_seconds
        self.declared_options_level = declared_options_level
        self.risk_engine = CapitalBoundaryRiskEngine.aggressive_month1()

    def manifest(self) -> list[dict[str, Any]]:
        return [
            {"tool": ResearchTool.ACCOUNT_STATE.value, "purpose": "Current paper balances, NLV, cash, buying power and declared option permission level."},
            {"tool": ResearchTool.POSITIONS.value, "purpose": "Current paper positions."},
            {"tool": ResearchTool.OPEN_ORDERS.value, "purpose": "Current paper open orders."},
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

    def validate_proposal(
        self, proposal: AutonomousTradeProposal, bundle: TraderInputBundle
    ) -> ProposalValidation:
        equity = Decimal(str(bundle.experiment_subledger_snapshot.get("equity", "0")))
        risk = self.risk_engine.evaluate(
            CapitalBoundaryInputs(
                experiment_equity=equity,
                maximum_loss=proposal.maximum_loss,
                liability_is_bounded=proposal.loss_is_bounded,
                uses_external_capital=False,
            )
        )
        if risk.result != RiskResult.PASS:
            return ProposalValidation(
                passed=False,
                reason_codes=risk.reason_codes,
                broker_evidence={"risk_policy": risk.model_dump(mode="json")},
            )

        structural = self._bounded_structure_reason(proposal)
        if structural is not None:
            return ProposalValidation(
                passed=False,
                reason_codes=(structural,),
                broker_evidence={"risk_policy": risk.model_dump(mode="json")},
            )

        feasibility = self._broker_feasibility(proposal)
        if not feasibility.get("success"):
            return ProposalValidation(
                passed=False,
                reason_codes=("BROKER_FEASIBILITY_FAILED",),
                broker_evidence=feasibility,
            )
        return ProposalValidation(
            passed=True,
            reason_codes=(),
            broker_evidence={
                "risk_policy": risk.model_dump(mode="json"),
                "what_if": feasibility,
            },
        )

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
                })
            return {"success": True, "open_orders": items}
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
    def _bounded_structure_reason(proposal: AutonomousTradeProposal) -> str | None:
        if not proposal.loss_is_bounded:
            return "UNBOUNDED_LIABILITY"
        if not proposal.legs:
            if proposal.action.upper() == "SELL" and proposal.sec_type.upper() in {"STK", "OPT"}:
                return "UNBOUNDED_SINGLE_SHORT_POSITION"
            return None

        shorts = [
            leg for leg in proposal.legs
            if leg.action.upper() == "SELL" and leg.sec_type.upper() == "OPT"
        ]
        longs = [
            leg for leg in proposal.legs
            if leg.action.upper() == "BUY" and leg.sec_type.upper() == "OPT"
        ]
        for short in shorts:
            protectors = [
                leg for leg in longs
                if leg.symbol == short.symbol
                and leg.expiry == short.expiry
                and (leg.right or "").upper() == (short.right or "").upper()
            ]
            if sum(leg.ratio for leg in protectors) < short.ratio:
                return "SHORT_OPTION_LEG_NOT_FULLY_BOUNDED"
        return None
