from __future__ import annotations

import argparse
import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper

from .canonical import canonical_bytes
from .ibkr_readonly import expected_identity_hash
from .ibkr_readonly_session import ExpectedPaperIdentityStore, ReadOnlyMessageGuard


SCHEMA = "IBKR_CAPABILITY_DISCOVERY_V1"
PAPER_HOSTS = {"127.0.0.1", "localhost"}
PAPER_PORT = 4002

MARKET_DATA_TYPES = {
    1: "REALTIME",
    2: "FROZEN",
    3: "DELAYED",
    4: "DELAYED_FROZEN",
}


@dataclass(frozen=True)
class ProbeSpec:
    label: str
    symbol: str
    sec_type: str
    exchange: str
    currency: str = "USD"
    primary_exchange: str = ""
    con_id: int = 0
    expiry: str = ""
    strike: float = 0.0
    right: str = ""
    multiplier: str = ""
    quote: bool = True

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ProbeSpec":
        return cls(
            label=str(value["label"]),
            symbol=str(value.get("symbol", "")).upper(),
            sec_type=str(value.get("sec_type") or value.get("secType") or "STK").upper(),
            exchange=str(value.get("exchange") or "SMART").upper(),
            currency=str(value.get("currency") or "USD").upper(),
            primary_exchange=str(value.get("primary_exchange") or value.get("primaryExchange") or "").upper(),
            con_id=int(value.get("con_id") or value.get("conId") or 0),
            expiry=str(value.get("expiry") or ""),
            strike=float(value.get("strike") or 0.0),
            right=str(value.get("right") or "").upper(),
            multiplier=str(value.get("multiplier") or ""),
            quote=bool(value.get("quote", True)),
        )


DEFAULT_PROBES: tuple[ProbeSpec, ...] = (
    ProbeSpec("AAPL_STK_SMART", "AAPL", "STK", "SMART", primary_exchange="NASDAQ"),
    ProbeSpec("AAPL_STK_OVERNIGHT", "AAPL", "STK", "OVERNIGHT", primary_exchange="NASDAQ"),
    ProbeSpec("SPY_STK_SMART", "SPY", "STK", "SMART", primary_exchange="ARCA"),
    ProbeSpec("SPY_STK_OVERNIGHT", "SPY", "STK", "OVERNIGHT", primary_exchange="ARCA"),
    ProbeSpec("EURUSD_CASH_IDEALPRO", "EUR", "CASH", "IDEALPRO", currency="USD"),
    ProbeSpec("ES_FUT_CME", "ES", "FUT", "CME", currency="USD"),
    ProbeSpec("SPX_IND_CBOE", "SPX", "IND", "CBOE", currency="USD"),
    ProbeSpec("BTC_CRYPTO_PAXOS", "BTC", "CRYPTO", "PAXOS", currency="USD"),
)


def _safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _contract_from_spec(spec: ProbeSpec) -> Contract:
    contract = Contract()
    contract.symbol = spec.symbol
    contract.secType = spec.sec_type
    contract.exchange = spec.exchange
    contract.currency = spec.currency
    if spec.primary_exchange:
        contract.primaryExchange = spec.primary_exchange
    if spec.con_id:
        contract.conId = spec.con_id
    if spec.expiry:
        contract.lastTradeDateOrContractMonth = spec.expiry
    if spec.strike:
        contract.strike = spec.strike
    if spec.right:
        contract.right = spec.right
    if spec.multiplier:
        contract.multiplier = spec.multiplier
    return contract


def _serialize_contract(contract: Any) -> dict[str, Any]:
    return {
        "conId": int(getattr(contract, "conId", 0) or 0),
        "symbol": str(getattr(contract, "symbol", "") or ""),
        "localSymbol": str(getattr(contract, "localSymbol", "") or ""),
        "secType": str(getattr(contract, "secType", "") or ""),
        "exchange": str(getattr(contract, "exchange", "") or ""),
        "primaryExchange": str(getattr(contract, "primaryExchange", "") or ""),
        "currency": str(getattr(contract, "currency", "") or ""),
        "expiry": str(getattr(contract, "lastTradeDateOrContractMonth", "") or ""),
        "strike": _safe_scalar(getattr(contract, "strike", 0)),
        "right": str(getattr(contract, "right", "") or ""),
        "multiplier": str(getattr(contract, "multiplier", "") or ""),
        "tradingClass": str(getattr(contract, "tradingClass", "") or ""),
    }


def _serialize_contract_details(details: Any) -> dict[str, Any]:
    return {
        "contract": _serialize_contract(getattr(details, "contract", None)),
        "marketName": str(getattr(details, "marketName", "") or ""),
        "longName": str(getattr(details, "longName", "") or ""),
        "minTick": _safe_scalar(getattr(details, "minTick", None)),
        "orderTypes": str(getattr(details, "orderTypes", "") or ""),
        "validExchanges": str(getattr(details, "validExchanges", "") or ""),
        "priceMagnifier": _safe_scalar(getattr(details, "priceMagnifier", None)),
        "underConId": _safe_scalar(getattr(details, "underConId", None)),
        "contractMonth": str(getattr(details, "contractMonth", "") or ""),
        "timeZoneId": str(getattr(details, "timeZoneId", "") or ""),
        "tradingHours": str(getattr(details, "tradingHours", "") or ""),
        "liquidHours": str(getattr(details, "liquidHours", "") or ""),
        "marketRuleIds": str(getattr(details, "marketRuleIds", "") or ""),
        "realExpirationDate": str(getattr(details, "realExpirationDate", "") or ""),
        "stockType": str(getattr(details, "stockType", "") or ""),
        "minSize": _safe_scalar(getattr(details, "minSize", None)),
        "sizeIncrement": _safe_scalar(getattr(details, "sizeIncrement", None)),
        "suggestedSizeIncrement": _safe_scalar(getattr(details, "suggestedSizeIncrement", None)),
        "aggGroup": _safe_scalar(getattr(details, "aggGroup", None)),
    }


def _expiry_sort_key(details: Any) -> tuple[int, str]:
    contract = getattr(details, "contract", None)
    raw = str(getattr(contract, "lastTradeDateOrContractMonth", "") or "")
    digits = "".join(ch for ch in raw if ch.isdigit())
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    if len(digits) >= 8:
        date_key = digits[:8]
    elif len(digits) >= 6:
        date_key = digits[:6] + "99"
    else:
        return (2, raw)
    return (0 if date_key >= today else 1, date_key)


def _select_detail(spec: ProbeSpec, details: list[Any]) -> Any | None:
    if not details:
        return None
    if spec.con_id:
        for item in details:
            if int(getattr(getattr(item, "contract", None), "conId", 0) or 0) == spec.con_id:
                return item
    if len(details) == 1:
        return details[0]
    if spec.sec_type in {"FUT", "FOP", "OPT"}:
        return sorted(details, key=_expiry_sort_key)[0]
    return None


class _CapabilityClient(EWrapper, EClient):
    def __init__(self) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        self.ready = threading.Event()
        self.managed_accounts_event = threading.Event()
        self.current_time_event = threading.Event()
        self.managed_accounts_value: tuple[str, ...] = ()
        self.server_timestamp: int | None = None
        self.contract_events: dict[int, threading.Event] = {}
        self.contract_values: dict[int, list[Any]] = {}
        self.market_type_events: dict[int, threading.Event] = {}
        self.market_data_types: dict[int, int] = {}
        self.quotes: dict[int, dict[str, Any]] = {}
        self.errors: list[dict[str, Any]] = []
        self.outbound_message_ids: list[int] = []

    def sendMsg(self, msg: str) -> None:
        message_id = ReadOnlyMessageGuard.validate(msg)
        self.outbound_message_ids.append(message_id)
        super().sendMsg(msg)

    def nextValidId(self, orderId: int) -> None:
        self.ready.set()

    def managedAccounts(self, accountsList: str) -> None:
        self.managed_accounts_value = tuple(
            value.strip() for value in accountsList.split(",") if value.strip()
        )
        self.managed_accounts_event.set()

    def currentTime(self, time_value: int) -> None:
        self.server_timestamp = int(time_value)
        self.current_time_event.set()

    def contractDetails(self, reqId: int, contractDetails: Any) -> None:
        self.contract_values.setdefault(reqId, []).append(contractDetails)

    def contractDetailsEnd(self, reqId: int) -> None:
        self.contract_events.setdefault(reqId, threading.Event()).set()

    def marketDataType(self, reqId: int, marketDataType: int) -> None:
        self.market_data_types[reqId] = int(marketDataType)
        self.market_type_events.setdefault(reqId, threading.Event()).set()

    def tickPrice(self, reqId: int, tickType: int, price: float, attrib: Any) -> None:
        quote = self.quotes.setdefault(reqId, {})
        if tickType == 1:
            quote["bid"] = price
        elif tickType == 2:
            quote["ask"] = price
        elif tickType == 4:
            quote["last"] = price
        elif tickType == 9:
            quote["close"] = price
        quote["last_update_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def tickSize(self, reqId: int, tickType: int, size: Any) -> None:
        quote = self.quotes.setdefault(reqId, {})
        if tickType == 0:
            quote["bid_size"] = _safe_scalar(size)
        elif tickType == 3:
            quote["ask_size"] = _safe_scalar(size)
        elif tickType == 5:
            quote["last_size"] = _safe_scalar(size)

    def error(
        self,
        reqId: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        self.errors.append(
            {
                "request_id": int(reqId),
                "code": int(errorCode),
                "message": str(errorString)[:500],
            }
        )


def _probe_market_data(
    client: _CapabilityClient,
    request_id: int,
    contract: Contract,
    *,
    requested_exchange: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    contract.exchange = requested_exchange
    client.market_type_events[request_id] = threading.Event()
    client.quotes[request_id] = {}
    client.reqMktData(request_id, contract, "", False, False, [])
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        market_type = client.market_data_types.get(request_id)
        quote = client.quotes.get(request_id, {})
        if market_type is not None and any(quote.get(key) is not None for key in ("bid", "ask", "last")):
            break
        time.sleep(0.05)
    client.cancelMktData(request_id)
    raw_type = client.market_data_types.get(request_id)
    quote = dict(client.quotes.get(request_id, {}))
    return {
        "requested_market_data_type": "LIVE",
        "actual_market_data_type": MARKET_DATA_TYPES.get(raw_type, "UNKNOWN"),
        "actual_market_data_type_code": raw_type,
        "bid": quote.get("bid"),
        "ask": quote.get("ask"),
        "last": quote.get("last"),
        "close": quote.get("close"),
        "bid_size": quote.get("bid_size"),
        "ask_size": quote.get("ask_size"),
        "last_size": quote.get("last_size"),
        "last_update_utc": quote.get("last_update_utc"),
        "has_bid_ask": quote.get("bid") is not None and quote.get("ask") is not None,
    }


def discover_capabilities(
    probes: Sequence[ProbeSpec],
    *,
    host: str = "127.0.0.1",
    port: int = PAPER_PORT,
    client_id: int = 19751,
    timeout_seconds: float = 8.0,
    expected_account_hash: str | None = None,
) -> dict[str, Any]:
    if host not in PAPER_HOSTS or port != PAPER_PORT:
        raise ValueError("capability discovery requires local IBKR PAPER Gateway :4002")
    if not probes:
        raise ValueError("at least one capability probe is required")

    expected = expected_account_hash
    if expected is None:
        store = ExpectedPaperIdentityStore(Path("Secrets/expected_paper_account_identity_v1.json"))
        if store.path.exists():
            expected = store.load_hash()
    if not expected:
        raise PermissionError("expected paper account identity hash is required")

    client = _CapabilityClient()
    thread: threading.Thread | None = None
    started_at = datetime.now(timezone.utc)
    try:
        client.connect(host, port, client_id)
        if not client.isConnected():
            raise ConnectionError("IBKR PAPER Gateway connection failed")
        thread = threading.Thread(target=client.run, daemon=True)
        thread.start()
        if not client.ready.wait(timeout_seconds):
            raise TimeoutError("IBKR handshake timeout")

        client.reqManagedAccts()
        if not client.managed_accounts_event.wait(timeout_seconds):
            raise TimeoutError("managed account timeout")
        if len(client.managed_accounts_value) != 1:
            raise PermissionError("single paper account required")
        account = client.managed_accounts_value[0]
        if not account.upper().startswith("DU"):
            raise PermissionError("paper account DU namespace required")
        actual_hash = expected_identity_hash(account)
        if actual_hash != expected.lower():
            raise PermissionError("paper account identity mismatch")

        client.reqCurrentTime()
        client.current_time_event.wait(timeout_seconds)
        client.reqMarketDataType(1)

        results: list[dict[str, Any]] = []
        request_id = 30_000
        market_request_id = 40_000
        for spec in probes:
            event = threading.Event()
            client.contract_events[request_id] = event
            client.contract_values[request_id] = []
            client.reqContractDetails(request_id, _contract_from_spec(spec))
            event.wait(timeout_seconds)
            details = list(client.contract_values.get(request_id, []))
            selected = _select_detail(spec, details)
            row: dict[str, Any] = {
                "probe": asdict(spec),
                "contract_detail_count": len(details),
                "contract_details": [
                    _serialize_contract_details(item) for item in details[:12]
                ],
                "contract_details_truncated": len(details) > 12,
                "selected_contract": (
                    None
                    if selected is None
                    else _serialize_contract_details(selected)
                ),
                "market_data": None,
                "status": "UNRESOLVED" if not details else "RESOLVED",
            }
            if selected is None and details:
                row["status"] = "AMBIGUOUS"
            if spec.quote and selected is not None:
                selected_contract = getattr(selected, "contract")
                row["market_data"] = _probe_market_data(
                    client,
                    market_request_id,
                    selected_contract,
                    requested_exchange=spec.exchange,
                    timeout_seconds=min(timeout_seconds, 5.0),
                )
                market_request_id += 1
            results.append(row)
            request_id += 1

        server_timestamp = (
            None
            if client.server_timestamp is None
            else datetime.fromtimestamp(client.server_timestamp, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        completed_at = datetime.now(timezone.utc)
        report = {
            "schema": SCHEMA,
            "status": "PASS",
            "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
            "completed_at_utc": completed_at.isoformat().replace("+00:00", "Z"),
            "gateway": {
                "host": host,
                "port": port,
                "mode": "PAPER",
                "server_version": client.serverVersion(),
                "connection_time": client.twsConnectionTime(),
                "server_timestamp_utc": server_timestamp,
            },
            "paper_identity": {
                "gate": "PASS",
                "expected_account_identity_hash": expected.lower(),
                "account_fingerprint": actual_hash[:16],
                "raw_account_identity_persisted": False,
            },
            "probes": results,
            "broker_errors": client.errors,
            "outbound_message_ids": client.outbound_message_ids,
            "read_only_transport_guard": True,
            "real_order_writes_attempted": 0,
            "paper_execution_armed": False,
        }
        return report
    finally:
        if client.isConnected():
            client.disconnect()
        if thread is not None:
            thread.join(timeout=2)


def _parse_probe_json(values: Sequence[str]) -> list[ProbeSpec]:
    probes: list[ProbeSpec] = []
    for raw in values:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("--probe-json must decode to an object")
        probes.append(ProbeSpec.from_mapping(parsed))
    return probes


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ibkr-capability-discovery")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=PAPER_PORT)
    parser.add_argument("--client-id", type=int, default=19751)
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--expected-account-sha256")
    parser.add_argument("--no-default-probes", action="store_true")
    parser.add_argument("--probe-json", action="append", default=[])
    args = parser.parse_args(argv)

    probes: list[ProbeSpec] = []
    if not args.no_default_probes:
        probes.extend(DEFAULT_PROBES)
    probes.extend(_parse_probe_json(args.probe_json))
    report = discover_capabilities(
        probes,
        host=args.host,
        port=args.port,
        client_id=args.client_id,
        timeout_seconds=args.timeout_seconds,
        expected_account_hash=args.expected_account_sha256,
    )
    print(canonical_bytes(report).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
