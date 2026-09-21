from __future__ import annotations

import itertools
import math
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from ibapi.client import EClient
from ibapi.contract import ComboLeg, Contract
from ibapi.order import Order
from ibapi.scanner import ScannerSubscription
from ibapi.wrapper import EWrapper

from .autonomous_research import ResearchRequest
from .ibkr_readonly_session import IBKRReadOnlySessionCollector
from .trader_invocation import TraderInputBundle


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _finite_float(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _contract_payload(contract: Any) -> dict[str, Any]:
    return {
        "contract_id": int(getattr(contract, "conId", 0) or 0),
        "symbol": str(getattr(contract, "symbol", "") or ""),
        "security_type": str(getattr(contract, "secType", "") or ""),
        "exchange": str(getattr(contract, "exchange", "") or ""),
        "primary_exchange": str(getattr(contract, "primaryExchange", "") or ""),
        "currency": str(getattr(contract, "currency", "") or ""),
        "local_symbol": str(getattr(contract, "localSymbol", "") or ""),
        "trading_class": str(getattr(contract, "tradingClass", "") or ""),
        "expiry": str(getattr(contract, "lastTradeDateOrContractMonth", "") or ""),
        "strike": _finite_float(getattr(contract, "strike", None)),
        "right": str(getattr(contract, "right", "") or ""),
        "multiplier": str(getattr(contract, "multiplier", "") or ""),
    }


def _contract_from_args(arguments: dict[str, Any]) -> Contract:
    contract = Contract()
    contract.conId = int(arguments.get("contract_id") or 0)
    contract.symbol = str(arguments.get("symbol") or "").upper()
    contract.secType = str(arguments.get("security_type") or "STK").upper()
    contract.exchange = str(arguments.get("exchange") or "SMART")
    contract.currency = str(arguments.get("currency") or "USD").upper()
    if arguments.get("primary_exchange"):
        contract.primaryExchange = str(arguments["primary_exchange"])
    if arguments.get("expiry"):
        contract.lastTradeDateOrContractMonth = str(arguments["expiry"])
    if arguments.get("strike") is not None:
        contract.strike = float(arguments["strike"])
    if arguments.get("right"):
        contract.right = str(arguments["right"]).upper()
    if arguments.get("multiplier"):
        contract.multiplier = str(arguments["multiplier"])
    if arguments.get("trading_class"):
        contract.tradingClass = str(arguments["trading_class"])
    if arguments.get("local_symbol"):
        contract.localSymbol = str(arguments["local_symbol"])
    return contract


class _ResearchClient(EWrapper, EClient):
    """Read/query client. It intentionally exposes no trading decision logic."""

    def __init__(self) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        self.ready = threading.Event()
        self.events: dict[int, threading.Event] = {}
        self.contract_details_values: dict[int, list[dict[str, Any]]] = {}
        self.symbol_samples_values: dict[int, list[dict[str, Any]]] = {}
        self.quote_values: dict[int, dict[str, Any]] = {}
        self.historical_values: dict[int, list[dict[str, Any]]] = {}
        self.option_chain_values: dict[int, list[dict[str, Any]]] = {}
        self.scanner_values: dict[int, list[dict[str, Any]]] = {}
        self.news_providers_event = threading.Event()
        self.news_providers_value: list[dict[str, str]] = []
        self.historical_news_values: dict[int, list[dict[str, Any]]] = {}
        self.errors: list[dict[str, Any]] = []
        self.next_order_id: int | None = None
        self.what_if_values: dict[int, dict[str, Any]] = {}

    def event_for(self, request_id: int) -> threading.Event:
        return self.events.setdefault(request_id, threading.Event())

    def nextValidId(self, orderId: int) -> None:
        self.next_order_id = int(orderId)
        self.ready.set()

    def error(
        self,
        reqId: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        self.errors.append(
            {
                "request_id": reqId,
                "code": errorCode,
                "message": str(errorString)[:500],
            }
        )

    def contractDetails(self, reqId: int, contractDetails: object) -> None:
        contract = getattr(contractDetails, "contract", None)
        if contract is None:
            return
        item = _contract_payload(contract)
        item.update(
            {
                "long_name": str(getattr(contractDetails, "longName", "") or ""),
                "market_name": str(getattr(contractDetails, "marketName", "") or ""),
                "min_tick": _finite_float(getattr(contractDetails, "minTick", None)),
                "valid_exchanges": str(
                    getattr(contractDetails, "validExchanges", "") or ""
                ),
            }
        )
        self.contract_details_values.setdefault(reqId, []).append(item)

    def contractDetailsEnd(self, reqId: int) -> None:
        self.event_for(reqId).set()

    def symbolSamples(self, reqId: int, contractDescriptions: list[object]) -> None:
        rows: list[dict[str, Any]] = []
        for description in contractDescriptions:
            contract = getattr(description, "contract", None)
            if contract is None:
                continue
            row = _contract_payload(contract)
            row["derivative_security_types"] = list(
                getattr(description, "derivativeSecTypes", []) or []
            )
            rows.append(row)
        self.symbol_samples_values[reqId] = rows
        self.event_for(reqId).set()

    def marketDataType(self, reqId: int, marketDataType: int) -> None:
        self.quote_values.setdefault(reqId, {})["market_data_type"] = marketDataType

    def tickPrice(self, reqId: int, tickType: int, price: float, attrib: object) -> None:
        fields = {1: "bid", 2: "ask", 4: "last", 6: "high", 7: "low", 9: "close"}
        field = fields.get(tickType)
        if field is not None and price is not None and price >= 0:
            self.quote_values.setdefault(reqId, {})[field] = float(price)
            self.quote_values[reqId]["received_utc"] = _utc_now()

    def tickSize(self, reqId: int, tickType: int, size: object) -> None:
        fields = {0: "bid_size", 3: "ask_size", 5: "last_size", 8: "volume"}
        field = fields.get(tickType)
        if field is not None:
            self.quote_values.setdefault(reqId, {})[field] = str(size)

    def tickOptionComputation(
        self,
        reqId: int,
        tickType: int,
        tickAttrib: int,
        impliedVol: float,
        delta: float,
        optPrice: float,
        pvDividend: float,
        gamma: float,
        vega: float,
        theta: float,
        undPrice: float,
    ) -> None:
        self.quote_values.setdefault(reqId, {})["option_computation"] = {
            "tick_type": tickType,
            "implied_volatility": _finite_float(impliedVol),
            "delta": _finite_float(delta),
            "option_price": _finite_float(optPrice),
            "pv_dividend": _finite_float(pvDividend),
            "gamma": _finite_float(gamma),
            "vega": _finite_float(vega),
            "theta": _finite_float(theta),
            "underlying_price": _finite_float(undPrice),
        }

    def tickSnapshotEnd(self, reqId: int) -> None:
        self.event_for(reqId).set()

    def historicalData(self, reqId: int, bar: object) -> None:
        self.historical_values.setdefault(reqId, []).append(
            {
                "date": str(getattr(bar, "date", "") or ""),
                "open": _finite_float(getattr(bar, "open", None)),
                "high": _finite_float(getattr(bar, "high", None)),
                "low": _finite_float(getattr(bar, "low", None)),
                "close": _finite_float(getattr(bar, "close", None)),
                "volume": str(getattr(bar, "volume", "") or ""),
                "bar_count": int(getattr(bar, "barCount", 0) or 0),
                "wap": str(getattr(bar, "wap", "") or ""),
            }
        )

    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
        self.event_for(reqId).set()

    def securityDefinitionOptionParameter(
        self,
        reqId: int,
        exchange: str,
        underlyingConId: int,
        tradingClass: str,
        multiplier: str,
        expirations: set[str],
        strikes: set[float],
    ) -> None:
        self.option_chain_values.setdefault(reqId, []).append(
            {
                "exchange": exchange,
                "underlying_contract_id": int(underlyingConId),
                "trading_class": tradingClass,
                "multiplier": multiplier,
                "expirations": sorted(str(item) for item in expirations),
                "strikes": sorted(float(item) for item in strikes),
            }
        )

    def securityDefinitionOptionParameterEnd(self, reqId: int) -> None:
        self.event_for(reqId).set()

    def scannerData(
        self,
        reqId: int,
        rank: int,
        contractDetails: object,
        distance: str,
        benchmark: str,
        projection: str,
        legsStr: str,
    ) -> None:
        contract = getattr(contractDetails, "contract", None)
        if contract is None:
            return
        row = _contract_payload(contract)
        row.update(
            {
                "rank": rank,
                "distance": distance,
                "benchmark": benchmark,
                "projection": projection,
            }
        )
        self.scanner_values.setdefault(reqId, []).append(row)

    def scannerDataEnd(self, reqId: int) -> None:
        self.event_for(reqId).set()

    def newsProviders(self, newsProviders: list[object]) -> None:
        self.news_providers_value = [
            {
                "provider_code": str(getattr(item, "code", "") or ""),
                "provider_name": str(getattr(item, "name", "") or ""),
            }
            for item in newsProviders
        ]
        self.news_providers_event.set()

    def historicalNews(
        self,
        reqId: int,
        time_value: str,
        providerCode: str,
        articleId: str,
        headline: str,
    ) -> None:
        self.historical_news_values.setdefault(reqId, []).append(
            {
                "time": time_value,
                "provider_code": providerCode,
                "article_id": articleId,
                "headline": headline,
            }
        )

    def historicalNewsEnd(self, reqId: int, hasMore: bool) -> None:
        self.historical_news_values.setdefault(reqId, [])
        self.historical_news_values[reqId].append({"has_more": bool(hasMore)})
        self.event_for(reqId).set()

    def openOrder(
        self, orderId: int, contract: object, order: object, orderState: object
    ) -> None:
        # Used only for whatIf=True, transmit=False feasibility previews.
        if not bool(getattr(order, "whatIf", False)):
            return
        self.what_if_values[orderId] = {
            "status": str(getattr(orderState, "status", "") or ""),
            "init_margin_before": str(
                getattr(orderState, "initMarginBefore", "") or ""
            ),
            "init_margin_change": str(
                getattr(orderState, "initMarginChange", "") or ""
            ),
            "init_margin_after": str(
                getattr(orderState, "initMarginAfter", "") or ""
            ),
            "maint_margin_before": str(
                getattr(orderState, "maintMarginBefore", "") or ""
            ),
            "maint_margin_change": str(
                getattr(orderState, "maintMarginChange", "") or ""
            ),
            "maint_margin_after": str(
                getattr(orderState, "maintMarginAfter", "") or ""
            ),
            "equity_with_loan_change": str(
                getattr(orderState, "equityWithLoanChange", "") or ""
            ),
            "commission": _finite_float(getattr(orderState, "commission", None)),
            "min_commission": _finite_float(
                getattr(orderState, "minCommission", None)
            ),
            "max_commission": _finite_float(
                getattr(orderState, "maxCommission", None)
            ),
            "commission_currency": str(
                getattr(orderState, "commissionCurrency", "") or ""
            ),
        }
        self.event_for(orderId).set()


class IBKRResearchToolbox:
    """
    Broker-driven research surface for Codex.

    No symbol list or strategy list is embedded.  Every instrument starts from
    a Codex request and is resolved against IBKR.  The only hard endpoint is
    the local paper Gateway (4002).
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 4002,
        options_permission_level: int = 4,
        timeout_seconds: float = 15.0,
        external_research: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        if host not in {"127.0.0.1", "localhost"} or port != 4002:
            raise ValueError("autonomous research requires local IBKR paper Gateway :4002")
        self.host = host
        self.port = port
        self.options_permission_level = options_permission_level
        self.timeout_seconds = timeout_seconds
        self.external_research = external_research
        self._client_ids = itertools.count(19800)
        self.experimental_equity = Decimal("500.00")
        self.last_bundle_hash: str | None = None

    def bind_bundle(self, bundle: TraderInputBundle) -> None:
        raw = bundle.experiment_subledger_snapshot.get("equity", "0")
        equity = Decimal(str(raw))
        if not equity.is_finite() or equity < 0:
            raise ValueError("invalid experimental equity")
        self.experimental_equity = equity
        self.last_bundle_hash = bundle.sha256

    def manifest(self) -> dict[str, Any]:
        tools: dict[str, Any] = {
            "account_state": {
                "purpose": "Current cash, buying power, NLV, positions/orders visibility and configured options level.",
                "arguments": {},
            },
            "contract_search": {
                "purpose": "Discover IBKR contracts from a free-form symbol/name pattern.",
                "arguments": {"pattern": "string"},
            },
            "contract_details": {
                "purpose": "Resolve/validate any IBKR contract specification and obtain conId/exchanges/min tick.",
                "arguments": {
                    "symbol": "string optional when contract_id supplied",
                    "security_type": "STK|OPT|FUT|FOP|CASH|IND|CFD|BOND|BAG|...",
                    "contract_id": "integer optional",
                    "expiry": "optional",
                    "strike": "optional",
                    "right": "C|P optional",
                    "exchange": "optional, defaults SMART",
                    "currency": "optional, defaults USD",
                },
            },
            "market_scanner": {
                "purpose": "Ask IBKR scanner to discover market opportunities dynamically; max rows is broker-limited.",
                "arguments": {
                    "instrument": "e.g. STK",
                    "location_code": "e.g. STK.US.MAJOR",
                    "scan_code": "IBKR scanner code chosen by Codex",
                    "number_of_rows": "1..50",
                    "above_price": "optional",
                    "below_price": "optional",
                    "above_volume": "optional",
                    "market_cap_above": "optional",
                    "market_cap_below": "optional",
                },
            },
            "quote": {
                "purpose": "Fresh broker quote and, for options when available, Greeks/implied volatility.",
                "arguments": {"contract specification": "same fields as contract_details"},
            },
            "historical_bars": {
                "purpose": "Historical IBKR bars for a Codex-selected contract/timeframe/window.",
                "arguments": {
                    "contract specification": "same fields as contract_details",
                    "duration": "e.g. 2 D, 1 M, 1 Y",
                    "bar_size": "e.g. 1 min, 5 mins, 1 hour, 1 day",
                    "what_to_show": "TRADES|MIDPOINT|BID|ASK|ADJUSTED_LAST|...",
                    "use_rth": "boolean",
                },
            },
            "option_chain": {
                "purpose": "Discover broker-listed option expirations, strikes, exchanges and multipliers for an underlying.",
                "arguments": {
                    "symbol": "underlying symbol",
                    "underlying_contract_id": "optional; resolved automatically if omitted",
                    "underlying_security_type": "defaults STK",
                },
            },
            "news": {
                "purpose": "Retrieve broker news headlines for a resolved contract when account entitlements provide providers.",
                "arguments": {
                    "contract_id": "IBKR conId",
                    "start_datetime": "optional IBKR format",
                    "end_datetime": "optional IBKR format",
                    "total_results": "1..100",
                    "provider_codes": "optional + separated codes",
                },
            },
            "capital_feasibility": {
                "purpose": "Compare a proposed defined maximum loss/capital requirement with current experimental equity and broker buying power.",
                "arguments": {
                    "maximum_loss": "USD",
                    "capital_required": "USD optional",
                    "security_type": "optional",
                    "structure": "free-form description",
                },
            },
            "what_if_order": {
                "purpose": "IBKR what-if preview for commission and margin impact. Never transmits an order.",
                "arguments": {
                    "contract": "single contract specification OR BAG metadata",
                    "legs": "optional list of resolved conId/ratio/action/exchange for BAG",
                    "action": "BUY|SELL",
                    "quantity": "positive number",
                    "order_type": "MKT|LMT",
                    "limit_price": "required for LMT",
                },
            },
        }
        if self.external_research is not None:
            tools["external_research"] = {
                "purpose": "External read-only research/news search. Query is chosen entirely by Codex.",
                "arguments": {"query": "string", "recency_days": "optional integer"},
            }
        return {
            "schema": "AUTONOMOUS_RESEARCH_TOOL_MANIFEST_V1",
            "paper_only": True,
            "broker_endpoint": "IBKR_GATEWAY_PAPER_4002",
            "configured_options_permission_level": self.options_permission_level,
            "experimental_equity": str(self.experimental_equity),
            "tools": tools,
        }

    def execute(self, request: ResearchRequest) -> dict[str, Any]:
        tool = request.tool
        args = dict(request.arguments or {})
        handlers = {
            "account_state": self._account_state,
            "contract_search": lambda: self._contract_search(args),
            "contract_details": lambda: self._contract_details(args),
            "market_scanner": lambda: self._market_scanner(args),
            "quote": lambda: self._quote(args),
            "historical_bars": lambda: self._historical_bars(args),
            "option_chain": lambda: self._option_chain(args),
            "news": lambda: self._news(args),
            "capital_feasibility": lambda: self._capital_feasibility(args),
            "what_if_order": lambda: self._what_if_order(args),
        }
        if tool == "external_research":
            if self.external_research is None:
                return {"status": "UNAVAILABLE", "reason_code": "EXTERNAL_RESEARCH_NOT_CONFIGURED"}
            result = self.external_research(args)
            return {"status": "PASS", "tool": tool, "result": result}
        handler = handlers.get(tool)
        if handler is None:
            return {
                "status": "ERROR",
                "reason_code": "UNKNOWN_RESEARCH_TOOL",
                "available_tools": sorted(self.manifest()["tools"]),
            }
        result = handler()
        return {"status": "PASS", "tool": tool, "result": result}

    def _client(self) -> tuple[_ResearchClient, threading.Thread]:
        client = _ResearchClient()
        client.connect(self.host, self.port, next(self._client_ids))
        if not client.isConnected():
            raise ConnectionError("IBKR paper Gateway connection failed")
        thread = threading.Thread(target=client.run, daemon=True)
        thread.start()
        if not client.ready.wait(self.timeout_seconds):
            client.disconnect()
            raise TimeoutError("IBKR research client handshake timed out")
        return client, thread

    def _finish(self, client: _ResearchClient, thread: threading.Thread) -> None:
        if client.isConnected():
            client.disconnect()
        thread.join(timeout=2)

    def _wait(self, client: _ResearchClient, request_id: int) -> None:
        if not client.event_for(request_id).wait(self.timeout_seconds):
            raise TimeoutError(f"IBKR research request {request_id} timed out")

    def _account_state(self) -> dict[str, Any]:
        evidence = IBKRReadOnlySessionCollector().collect(
            host=self.host,
            port=self.port,
            client_id=next(self._client_ids),
            timeout_seconds=self.timeout_seconds,
            symbols=(),
        )
        summaries = list(evidence.account_summary.values())
        summary = summaries[0] if summaries else {}
        return {
            "experimental_equity": str(self.experimental_equity),
            "cash": summary.get("TotalCashValue"),
            "settled_cash": summary.get("SettledCash"),
            "buying_power": summary.get("BuyingPower"),
            "net_liquidation": summary.get("NetLiquidation"),
            "account_type": summary.get("AccountType"),
            "configured_options_permission_level": self.options_permission_level,
            "positions": [
                {k: v for k, v in item.items() if k != "account"}
                for item in evidence.positions
            ],
            "open_orders": list(evidence.open_orders),
            "paper_only": True,
            "heartbeat_ok": evidence.heartbeat_ok,
        }

    def _contract_search(self, args: dict[str, Any]) -> dict[str, Any]:
        pattern = str(args.get("pattern") or "").strip()
        if not pattern:
            raise ValueError("contract_search requires pattern")
        client, thread = self._client()
        request_id = 1001
        try:
            client.reqMatchingSymbols(request_id, pattern)
            self._wait(client, request_id)
            return {
                "pattern": pattern,
                "matches": client.symbol_samples_values.get(request_id, []),
                "errors": client.errors,
            }
        finally:
            self._finish(client, thread)

    def _contract_details(self, args: dict[str, Any]) -> dict[str, Any]:
        client, thread = self._client()
        request_id = 1002
        try:
            client.reqContractDetails(request_id, _contract_from_args(args))
            self._wait(client, request_id)
            return {
                "contracts": client.contract_details_values.get(request_id, []),
                "errors": client.errors,
            }
        finally:
            self._finish(client, thread)

    def _quote(self, args: dict[str, Any]) -> dict[str, Any]:
        client, thread = self._client()
        request_id = 1003
        try:
            client.quote_values[request_id] = {
                "requested_contract": {
                    k: v for k, v in args.items() if k not in {"account"}
                }
            }
            client.reqMarketDataType(1)
            client.reqMktData(request_id, _contract_from_args(args), "", True, False, [])
            self._wait(client, request_id)
            client.cancelMktData(request_id)
            return {
                "quote": client.quote_values.get(request_id, {}),
                "errors": client.errors,
            }
        finally:
            self._finish(client, thread)

    def _historical_bars(self, args: dict[str, Any]) -> dict[str, Any]:
        client, thread = self._client()
        request_id = 1004
        try:
            client.reqHistoricalData(
                request_id,
                _contract_from_args(args),
                str(args.get("end_datetime") or ""),
                str(args.get("duration") or "5 D"),
                str(args.get("bar_size") or "5 mins"),
                str(args.get("what_to_show") or "TRADES"),
                1 if bool(args.get("use_rth", True)) else 0,
                1,
                False,
                [],
            )
            self._wait(client, request_id)
            bars = client.historical_values.get(request_id, [])
            return {
                "bar_count": len(bars),
                "bars": bars,
                "errors": client.errors,
            }
        finally:
            self._finish(client, thread)

    def _option_chain(self, args: dict[str, Any]) -> dict[str, Any]:
        symbol = str(args.get("symbol") or "").upper()
        if not symbol:
            raise ValueError("option_chain requires symbol")
        con_id = int(args.get("underlying_contract_id") or 0)
        if not con_id:
            details = self._contract_details(
                {
                    "symbol": symbol,
                    "security_type": str(
                        args.get("underlying_security_type") or "STK"
                    ),
                    "exchange": str(args.get("exchange") or "SMART"),
                    "currency": str(args.get("currency") or "USD"),
                }
            )
            contracts = details.get("contracts", [])
            if not contracts:
                return {
                    "symbol": symbol,
                    "chains": [],
                    "reason_code": "UNDERLYING_CONTRACT_UNRESOLVED",
                    "contract_details": details,
                }
            con_id = int(contracts[0]["contract_id"])

        client, thread = self._client()
        request_id = 1005
        try:
            client.reqSecDefOptParams(
                request_id,
                symbol,
                str(args.get("fut_fop_exchange") or ""),
                str(args.get("underlying_security_type") or "STK"),
                con_id,
            )
            self._wait(client, request_id)
            chains = client.option_chain_values.get(request_id, [])
            normalized: list[dict[str, Any]] = []
            for chain in chains:
                expirations = chain["expirations"]
                strikes = chain["strikes"]
                normalized.append(
                    {
                        **chain,
                        "expirations": expirations[:250],
                        "strikes": strikes[:2000],
                        "expirations_truncated": len(expirations) > 250,
                        "strikes_truncated": len(strikes) > 2000,
                    }
                )
            return {
                "symbol": symbol,
                "underlying_contract_id": con_id,
                "chains": normalized,
                "errors": client.errors,
            }
        finally:
            self._finish(client, thread)

    def _market_scanner(self, args: dict[str, Any]) -> dict[str, Any]:
        client, thread = self._client()
        request_id = 1006
        subscription = ScannerSubscription()
        subscription.numberOfRows = max(1, min(50, int(args.get("number_of_rows") or 25)))
        subscription.instrument = str(args.get("instrument") or "STK")
        subscription.locationCode = str(args.get("location_code") or "STK.US.MAJOR")
        subscription.scanCode = str(args.get("scan_code") or "MOST_ACTIVE")
        for field, source in (
            ("abovePrice", "above_price"),
            ("belowPrice", "below_price"),
            ("marketCapAbove", "market_cap_above"),
            ("marketCapBelow", "market_cap_below"),
        ):
            value = _finite_float(args.get(source))
            if value is not None:
                setattr(subscription, field, value)
        if args.get("above_volume") is not None:
            subscription.aboveVolume = int(args["above_volume"])
        try:
            client.reqScannerSubscription(request_id, subscription, [], [])
            self._wait(client, request_id)
            client.cancelScannerSubscription(request_id)
            return {
                "scanner": {
                    "instrument": subscription.instrument,
                    "location_code": subscription.locationCode,
                    "scan_code": subscription.scanCode,
                },
                "results": client.scanner_values.get(request_id, []),
                "errors": client.errors,
            }
        finally:
            self._finish(client, thread)

    def _news(self, args: dict[str, Any]) -> dict[str, Any]:
        con_id = int(args.get("contract_id") or 0)
        if con_id <= 0:
            raise ValueError("news requires contract_id")
        client, thread = self._client()
        request_id = 1007
        try:
            client.reqNewsProviders()
            client.news_providers_event.wait(self.timeout_seconds)
            available_codes = [
                item["provider_code"]
                for item in client.news_providers_value
                if item["provider_code"]
            ]
            provider_codes = str(args.get("provider_codes") or "+".join(available_codes))
            if not provider_codes:
                return {
                    "providers": client.news_providers_value,
                    "headlines": [],
                    "reason_code": "NO_NEWS_PROVIDER_ENTITLEMENT",
                }
            total_results = max(1, min(100, int(args.get("total_results") or 25)))
            client.reqHistoricalNews(
                request_id,
                con_id,
                provider_codes,
                str(args.get("start_datetime") or ""),
                str(args.get("end_datetime") or ""),
                total_results,
                [],
            )
            self._wait(client, request_id)
            return {
                "providers": client.news_providers_value,
                "headlines": client.historical_news_values.get(request_id, []),
                "errors": client.errors,
            }
        finally:
            self._finish(client, thread)

    def _capital_feasibility(self, args: dict[str, Any]) -> dict[str, Any]:
        maximum_loss = Decimal(str(args.get("maximum_loss") or "0"))
        capital_required = Decimal(str(args.get("capital_required") or maximum_loss))
        if maximum_loss < 0 or capital_required < 0:
            raise ValueError("maximum_loss/capital_required cannot be negative")
        account = self._account_state()
        buying_power_raw = account.get("buying_power")
        buying_power = (
            Decimal(str(buying_power_raw))
            if buying_power_raw not in (None, "")
            else Decimal("0")
        )
        return {
            "experimental_equity": str(self.experimental_equity),
            "maximum_loss": str(maximum_loss),
            "capital_required": str(capital_required),
            "buying_power": str(buying_power),
            "configured_options_permission_level": self.options_permission_level,
            "within_experiment_liability": maximum_loss <= self.experimental_equity,
            "within_current_buying_power": capital_required <= buying_power,
            "feasible_by_known_constraints": (
                maximum_loss <= self.experimental_equity
                and capital_required <= buying_power
            ),
            "structure": args.get("structure"),
            "security_type": args.get("security_type"),
            "note": "Final broker feasibility should use what_if_order for margin-sensitive structures.",
        }

    def _what_if_order(self, args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action") or "").upper()
        if action not in {"BUY", "SELL"}:
            raise ValueError("what_if_order action must be BUY or SELL")
        quantity = Decimal(str(args.get("quantity") or "0"))
        if quantity <= 0:
            raise ValueError("what_if_order quantity must be positive")
        order_type = str(args.get("order_type") or "MKT").upper()
        limit_price = args.get("limit_price")

        contract_args = dict(args.get("contract") or {})
        legs = list(args.get("legs") or [])
        contract = _contract_from_args(contract_args)
        if legs:
            contract.secType = "BAG"
            contract.comboLegs = []
            for item in legs:
                leg = ComboLeg()
                leg.conId = int(item["contract_id"])
                leg.ratio = int(item.get("ratio") or 1)
                leg.action = str(item["action"]).upper()
                leg.exchange = str(item.get("exchange") or "SMART")
                contract.comboLegs.append(leg)

        client, thread = self._client()
        try:
            if client.next_order_id is None:
                raise RuntimeError("IBKR did not provide nextValidId")
            order_id = int(client.next_order_id)
            order = Order()
            order.action = action
            order.totalQuantity = quantity
            order.orderType = order_type
            if order_type == "LMT":
                if limit_price is None:
                    raise ValueError("LMT what-if requires limit_price")
                order.lmtPrice = float(limit_price)
            order.whatIf = True
            order.transmit = False
            client.event_for(order_id)
            client.placeOrder(order_id, contract, order)
            self._wait(client, order_id)
            return {
                "paper_only": True,
                "what_if": True,
                "transmit": False,
                "preview": client.what_if_values.get(order_id, {}),
                "errors": client.errors,
            }
        finally:
            self._finish(client, thread)
