from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.message import OUT
from ibapi.wrapper import EWrapper

from .canonical import canonical_bytes
from .ibkr_readonly import expected_identity_hash
from .ibkr_readonly_session import ReadOnlyMessageGuard, ReadOnlyTransportViolation


CAPABILITY_DISCOVERY_SCHEMA = "IBKR_CAPABILITY_DISCOVERY_V1"
MARKET_DATA_TYPES = {
    1: "REALTIME",
    2: "FROZEN",
    3: "DELAYED",
    4: "DELAYED_FROZEN",
}

REQ_SEC_DEF_OPT_PARAMS_ID = int(getattr(OUT, "REQ_SEC_DEF_OPT_PARAMS", 78))
CAPABILITY_ALLOWED_MESSAGE_IDS = frozenset(
    set(ReadOnlyMessageGuard.ALLOWED_MESSAGE_IDS) | {REQ_SEC_DEF_OPT_PARAMS_ID}
)


def validate_capability_message(message: str) -> int:
    try:
        message_id = int(message.split("\0", 1)[0])
    except (TypeError, ValueError) as exc:
        raise ReadOnlyTransportViolation("unparseable IB API message") from exc
    if message_id not in CAPABILITY_ALLOWED_MESSAGE_IDS:
        raise ReadOnlyTransportViolation(
            f"IB API message id {message_id} is outside the capability-discovery read-only allowlist"
        )
    return message_id


@dataclass(frozen=True)
class ContractCapability:
    label: str
    con_id: int
    symbol: str
    local_symbol: str
    sec_type: str
    exchange: str
    primary_exchange: str
    currency: str
    trading_class: str
    multiplier: str
    expiry: str
    min_tick: float | None
    min_size: float | None
    size_increment: float | None
    suggested_size_increment: float | None
    valid_exchanges: tuple[str, ...]
    order_types: tuple[str, ...]
    trading_hours: str
    liquid_hours: str
    time_zone_id: str
    market_rule_ids: tuple[str, ...]
    overnight_route_advertised: bool


@dataclass(frozen=True)
class MarketDataCapability:
    label: str
    requested_type: str
    effective_type: str
    has_bid: bool
    has_ask: bool
    has_last: bool
    snapshot_complete: bool
    error_codes: tuple[int, ...]


@dataclass(frozen=True)
class OptionChainCapability:
    label: str
    exchange: str
    underlying_con_id: int
    trading_class: str
    multiplier: str
    expiration_count: int
    strike_count: int
    earliest_expiration: str | None
    latest_expiration: str | None
    min_strike: float | None
    max_strike: float | None


class _CapabilityClient(EWrapper, EClient):
    def __init__(self) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        self.ready = threading.Event()
        self.managed_accounts_event = threading.Event()
        self.current_time_event = threading.Event()
        self.contract_events: dict[int, threading.Event] = {}
        self.contract_values: dict[int, list[object]] = {}
        self.secdef_events: dict[int, threading.Event] = {}
        self.secdef_values: dict[int, list[dict[str, object]]] = {}
        self.market_events: dict[int, threading.Event] = {}
        self.market_values: dict[int, dict[str, object]] = {}
        self.errors: list[dict[str, object]] = []
        self.outbound_message_ids: list[int] = []
        self.managed_accounts: tuple[str, ...] = ()
        self.server_timestamp_utc: str | None = None

    def sendMsg(self, msg: str) -> None:
        message_id = validate_capability_message(msg)
        self.outbound_message_ids.append(message_id)
        super().sendMsg(msg)

    def nextValidId(self, orderId: int) -> None:
        self.ready.set()

    def managedAccounts(self, accountsList: str) -> None:
        self.managed_accounts = tuple(
            item.strip() for item in accountsList.split(",") if item.strip()
        )
        self.managed_accounts_event.set()

    def currentTime(self, time_value: int) -> None:
        self.server_timestamp_utc = (
            datetime.fromtimestamp(time_value, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        self.current_time_event.set()

    def register_contract(self, req_id: int) -> threading.Event:
        event = threading.Event()
        self.contract_events[req_id] = event
        self.contract_values[req_id] = []
        return event

    def contractDetails(self, reqId: int, contractDetails: object) -> None:
        self.contract_values.setdefault(reqId, []).append(contractDetails)

    def contractDetailsEnd(self, reqId: int) -> None:
        event = self.contract_events.get(reqId)
        if event is not None:
            event.set()

    def register_secdef(self, req_id: int) -> threading.Event:
        event = threading.Event()
        self.secdef_events[req_id] = event
        self.secdef_values[req_id] = []
        return event

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
        self.secdef_values.setdefault(reqId, []).append(
            {
                "exchange": str(exchange),
                "underlying_con_id": int(underlyingConId),
                "trading_class": str(tradingClass),
                "multiplier": str(multiplier),
                "expirations": tuple(sorted(str(item) for item in expirations)),
                "strikes": tuple(sorted(float(item) for item in strikes)),
            }
        )

    def securityDefinitionOptionParameterEnd(self, reqId: int) -> None:
        event = self.secdef_events.get(reqId)
        if event is not None:
            event.set()

    def register_market(self, req_id: int, label: str) -> threading.Event:
        event = threading.Event()
        self.market_events[req_id] = event
        self.market_values[req_id] = {
            "label": label,
            "market_data_type": None,
            "bid": None,
            "ask": None,
            "last": None,
            "snapshot_complete": False,
        }
        return event

    def marketDataType(self, reqId: int, marketDataType: int) -> None:
        self.market_values.setdefault(reqId, {})["market_data_type"] = int(marketDataType)

    def tickPrice(self, reqId: int, tickType: int, price: float, attrib: object) -> None:
        row = self.market_values.setdefault(reqId, {})
        if tickType == 1:
            row["bid"] = float(price)
        elif tickType == 2:
            row["ask"] = float(price)
        elif tickType == 4:
            row["last"] = float(price)

    def tickSnapshotEnd(self, reqId: int) -> None:
        row = self.market_values.setdefault(reqId, {})
        row["snapshot_complete"] = True
        event = self.market_events.get(reqId)
        if event is not None:
            event.set()

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
                "message": str(errorString)[:300],
            }
        )


def _csv_values(value: object) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    )


def _float_or_none(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _contract_capability(label: str, details: object) -> ContractCapability:
    contract = getattr(details, "contract", object())
    valid_exchanges = _csv_values(getattr(details, "validExchanges", ""))
    return ContractCapability(
        label=label,
        con_id=int(getattr(contract, "conId", 0) or 0),
        symbol=str(getattr(contract, "symbol", "") or ""),
        local_symbol=str(getattr(contract, "localSymbol", "") or ""),
        sec_type=str(getattr(contract, "secType", "") or ""),
        exchange=str(getattr(contract, "exchange", "") or ""),
        primary_exchange=str(getattr(contract, "primaryExchange", "") or ""),
        currency=str(getattr(contract, "currency", "") or ""),
        trading_class=str(getattr(contract, "tradingClass", "") or ""),
        multiplier=str(getattr(contract, "multiplier", "") or ""),
        expiry=str(getattr(contract, "lastTradeDateOrContractMonth", "") or ""),
        min_tick=_float_or_none(getattr(details, "minTick", None)),
        min_size=_float_or_none(getattr(details, "minSize", None)),
        size_increment=_float_or_none(getattr(details, "sizeIncrement", None)),
        suggested_size_increment=_float_or_none(
            getattr(details, "suggestedSizeIncrement", None)
        ),
        valid_exchanges=valid_exchanges,
        order_types=_csv_values(getattr(details, "orderTypes", "")),
        trading_hours=str(getattr(details, "tradingHours", "") or ""),
        liquid_hours=str(getattr(details, "liquidHours", "") or ""),
        time_zone_id=str(getattr(details, "timeZoneId", "") or ""),
        market_rule_ids=_csv_values(getattr(details, "marketRuleIds", "")),
        overnight_route_advertised="OVERNIGHT" in valid_exchanges,
    )


def _future_sort_key(details: object) -> tuple[int, str]:
    contract = getattr(details, "contract", object())
    expiry = str(getattr(contract, "lastTradeDateOrContractMonth", "") or "")
    digits = "".join(ch for ch in expiry if ch.isdigit())
    today = date.today().strftime("%Y%m%d")
    normalized = (digits + "99999999")[:8] if digits else "99999999"
    return (0 if normalized >= today else 1, normalized)


def select_contract_details(
    details: Iterable[object],
    *,
    sec_type: str,
) -> object | None:
    rows = list(details)
    if not rows:
        return None
    if sec_type == "FUT":
        future_rows = sorted(rows, key=_future_sort_key)
        for row in future_rows:
            if _future_sort_key(row)[0] == 0:
                return row
        return future_rows[0]
    return rows[0]


def _spec(
    *,
    symbol: str,
    sec_type: str,
    exchange: str,
    currency: str,
    primary_exchange: str = "",
) -> Contract:
    contract = Contract()
    contract.symbol = symbol
    contract.secType = sec_type
    contract.exchange = exchange
    contract.currency = currency
    if primary_exchange:
        contract.primaryExchange = primary_exchange
    return contract


def _request_details(
    client: _CapabilityClient,
    *,
    req_id: int,
    contract: Contract,
    timeout_seconds: float,
) -> list[object]:
    event = client.register_contract(req_id)
    client.reqContractDetails(req_id, contract)
    event.wait(timeout_seconds)
    return list(client.contract_values.get(req_id, ()))


def _request_secdef(
    client: _CapabilityClient,
    *,
    req_id: int,
    label: str,
    symbol: str,
    exchange: str,
    underlying_sec_type: str,
    underlying_con_id: int,
    timeout_seconds: float,
) -> list[OptionChainCapability]:
    event = client.register_secdef(req_id)
    client.reqSecDefOptParams(
        req_id,
        symbol,
        exchange,
        underlying_sec_type,
        underlying_con_id,
    )
    event.wait(timeout_seconds)
    results: list[OptionChainCapability] = []
    for row in client.secdef_values.get(req_id, ()):
        expirations = tuple(row["expirations"])
        strikes = tuple(row["strikes"])
        results.append(
            OptionChainCapability(
                label=label,
                exchange=str(row["exchange"]),
                underlying_con_id=int(row["underlying_con_id"]),
                trading_class=str(row["trading_class"]),
                multiplier=str(row["multiplier"]),
                expiration_count=len(expirations),
                strike_count=len(strikes),
                earliest_expiration=expirations[0] if expirations else None,
                latest_expiration=expirations[-1] if expirations else None,
                min_strike=min(strikes) if strikes else None,
                max_strike=max(strikes) if strikes else None,
            )
        )
    return results


def _sample_derivative_spec(
    client: _CapabilityClient,
    *,
    secdef_req_id: int,
    symbol: str,
    sec_type: str,
    currency: str,
    preferred_exchange: str,
) -> Contract | None:
    rows = list(client.secdef_values.get(secdef_req_id, ()))
    if not rows:
        return None
    row = next(
        (item for item in rows if str(item.get("exchange")) == preferred_exchange),
        rows[0],
    )
    expirations = tuple(row.get("expirations", ()))
    strikes = tuple(row.get("strikes", ()))
    if not expirations or not strikes:
        return None
    expiry = next(
        (
            item
            for item in expirations
            if str(item).replace("-", "")[:8] >= date.today().strftime("%Y%m%d")
        ),
        expirations[0],
    )
    strike = strikes[len(strikes) // 2]
    contract = Contract()
    contract.symbol = symbol
    contract.secType = sec_type
    contract.exchange = str(row.get("exchange") or preferred_exchange)
    contract.currency = currency
    contract.lastTradeDateOrContractMonth = str(expiry)
    contract.strike = float(strike)
    contract.right = "C"
    contract.multiplier = str(row.get("multiplier") or "")
    contract.tradingClass = str(row.get("trading_class") or "")
    return contract


def _request_market_snapshot(
    client: _CapabilityClient,
    *,
    req_id: int,
    label: str,
    contract: Contract,
    timeout_seconds: float,
) -> MarketDataCapability:
    client.reqMarketDataType(1)
    event = client.register_market(req_id, label)
    before = len(client.errors)
    client.reqMktData(req_id, contract, "", True, False, [])
    event.wait(timeout_seconds)
    row = client.market_values.get(req_id, {})
    errors = tuple(
        int(item["code"])
        for item in client.errors[before:]
        if int(item.get("request_id", -9999)) in {-1, req_id}
    )
    value = row.get("market_data_type")
    return MarketDataCapability(
        label=label,
        requested_type="REALTIME",
        effective_type=MARKET_DATA_TYPES.get(int(value), "UNKNOWN")
        if value is not None
        else "UNKNOWN",
        has_bid=row.get("bid") not in {None, -1},
        has_ask=row.get("ask") not in {None, -1},
        has_last=row.get("last") not in {None, -1},
        snapshot_complete=bool(row.get("snapshot_complete")),
        error_codes=errors,
    )


def discover_ibkr_capabilities(
    *,
    host: str = "127.0.0.1",
    port: int = 4002,
    client_id: int = 19751,
    timeout_seconds: float = 8.0,
) -> dict[str, object]:
    if host not in {"127.0.0.1", "localhost"} or port != 4002:
        return {
            "schema": CAPABILITY_DISCOVERY_SCHEMA,
            "status": "BLOCK",
            "reason_codes": ["PAPER_ENDPOINT_REQUIRED"],
            "real_order_writes_attempted": 0,
        }

    client = _CapabilityClient()
    thread: threading.Thread | None = None
    reasons: list[str] = []
    contracts: list[ContractCapability] = []
    market_data: list[MarketDataCapability] = []
    option_chains: list[OptionChainCapability] = []

    try:
        client.connect(host, port, client_id)
        if not client.isConnected():
            raise RuntimeError("BROKER_DISCONNECTED")
        thread = threading.Thread(target=client.run, daemon=True)
        thread.start()
        if not client.ready.wait(timeout_seconds):
            raise RuntimeError("BROKER_HANDSHAKE_TIMEOUT")

        client.reqManagedAccts()
        if not client.managed_accounts_event.wait(timeout_seconds):
            raise RuntimeError("MANAGED_ACCOUNT_TIMEOUT")
        if len(client.managed_accounts) != 1:
            raise RuntimeError("MANAGED_ACCOUNT_COUNT_INVALID")
        raw_account = client.managed_accounts[0].strip().upper()
        if not raw_account.startswith("DU"):
            raise RuntimeError("PAPER_ACCOUNT_NAMESPACE_REQUIRED")

        client.reqCurrentTime()
        client.current_time_event.wait(timeout_seconds)

        probes = [
            ("AAPL_STK_SMART", _spec(symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD", primary_exchange="NASDAQ")),
            ("AAPL_STK_OVERNIGHT", _spec(symbol="AAPL", sec_type="STK", exchange="OVERNIGHT", currency="USD", primary_exchange="NASDAQ")),
            ("SPY_STK_OVERNIGHT", _spec(symbol="SPY", sec_type="STK", exchange="OVERNIGHT", currency="USD", primary_exchange="ARCA")),
            ("EURUSD_CASH", _spec(symbol="EUR", sec_type="CASH", exchange="IDEALPRO", currency="USD")),
            ("ES_FUT", _spec(symbol="ES", sec_type="FUT", exchange="CME", currency="USD")),
            ("BTC_CRYPTO", _spec(symbol="BTC", sec_type="CRYPTO", exchange="PAXOS", currency="USD")),
            ("XAUUSD_CMDTY", _spec(symbol="XAUUSD", sec_type="CMDTY", exchange="IBCMDTY", currency="USD")),
        ]

        selected: dict[str, object] = {}
        req_id = 20_000
        for label, contract in probes:
            rows = _request_details(client, req_id=req_id, contract=contract, timeout_seconds=timeout_seconds)
            chosen = select_contract_details(rows, sec_type=contract.secType)
            if chosen is None:
                reasons.append(f"{label}_UNRESOLVED")
            else:
                selected[label] = chosen
                contracts.append(_contract_capability(label, chosen))
            req_id += 1

        aapl_details = selected.get("AAPL_STK_SMART")
        if aapl_details is not None:
            aapl_contract = getattr(aapl_details, "contract")
            option_chains.extend(
                _request_secdef(
                    client,
                    req_id=21_000,
                    label="AAPL_OPT",
                    symbol="AAPL",
                    exchange="SMART",
                    underlying_sec_type="STK",
                    underlying_con_id=int(aapl_contract.conId),
                    timeout_seconds=timeout_seconds,
                )
            )

        es_details = selected.get("ES_FUT")
        if es_details is not None:
            es_contract = getattr(es_details, "contract")
            option_chains.extend(
                _request_secdef(
                    client,
                    req_id=21_001,
                    label="ES_FOP",
                    symbol="ES",
                    exchange="CME",
                    underlying_sec_type="FUT",
                    underlying_con_id=int(es_contract.conId),
                    timeout_seconds=timeout_seconds,
                )
            )

        derivative_specs = [
            (
                "AAPL_OPT_SAMPLE",
                _sample_derivative_spec(
                    client,
                    secdef_req_id=21_000,
                    symbol="AAPL",
                    sec_type="OPT",
                    currency="USD",
                    preferred_exchange="SMART",
                ),
            ),
            (
                "ES_FOP_SAMPLE",
                _sample_derivative_spec(
                    client,
                    secdef_req_id=21_001,
                    symbol="ES",
                    sec_type="FOP",
                    currency="USD",
                    preferred_exchange="CME",
                ),
            ),
        ]
        derivative_req_id = 21_100
        for label, contract in derivative_specs:
            if contract is None:
                reasons.append(f"{label}_UNRESOLVED")
                derivative_req_id += 1
                continue
            rows = _request_details(
                client,
                req_id=derivative_req_id,
                contract=contract,
                timeout_seconds=timeout_seconds,
            )
            chosen = select_contract_details(rows, sec_type=contract.secType)
            if chosen is None:
                reasons.append(f"{label}_UNRESOLVED")
            else:
                selected[label] = chosen
                contracts.append(_contract_capability(label, chosen))
            derivative_req_id += 1

        req_id = 22_000
        for label, details in selected.items():
            market_data.append(
                _request_market_snapshot(
                    client,
                    req_id=req_id,
                    label=label,
                    contract=getattr(details, "contract"),
                    timeout_seconds=timeout_seconds,
                )
            )
            req_id += 1

        if not option_chains:
            reasons.append("OPTION_REFERENCE_DATA_UNAVAILABLE")

        account_hash = expected_identity_hash(raw_account)
        connection_time = client.twsConnectionTime()
        if isinstance(connection_time, bytes):
            connection_time = connection_time.decode("ascii", errors="replace")
        return {
            "schema": CAPABILITY_DISCOVERY_SCHEMA,
            "status": "PASS" if not reasons else "PARTIAL",
            "reason_codes": sorted(set(reasons)),
            "host": host,
            "port": port,
            "gateway_mode": "PAPER",
            "server_version": client.serverVersion(),
            "connection_time": str(connection_time or ""),
            "server_timestamp_utc": client.server_timestamp_utc,
            "account_identity_hash": account_hash,
            "account_fingerprint": account_hash[:16],
            "raw_account_identity_persisted": False,
            "contracts": [asdict(item) for item in contracts],
            "option_chains": [asdict(item) for item in option_chains],
            "market_data": [asdict(item) for item in market_data],
            "account_trade_permission_proven": False,
            "account_trade_permission_note": (
                "TWS read-only reference and market-data calls do not prove per-account "
                "order permission; proving that would require an order-preview/write-path "
                "operation, which this probe intentionally does not perform."
            ),
            "real_order_writes_attempted": 0,
            "outbound_message_ids": list(client.outbound_message_ids),
            "outbound_allowlist_only": all(
                item in CAPABILITY_ALLOWED_MESSAGE_IDS
                for item in client.outbound_message_ids
            ),
            "errors": [
                {
                    "request_id": int(item["request_id"]),
                    "code": int(item["code"]),
                    "message": str(item["message"]),
                }
                for item in client.errors
            ],
        }
    except (OSError, RuntimeError, ReadOnlyTransportViolation) as exc:
        return {
            "schema": CAPABILITY_DISCOVERY_SCHEMA,
            "status": "BLOCK",
            "reason_codes": [str(exc).split(":", 1)[0] or type(exc).__name__],
            "host": host,
            "port": port,
            "real_order_writes_attempted": 0,
            "outbound_message_ids": list(client.outbound_message_ids),
            "outbound_allowlist_only": all(
                item in CAPABILITY_ALLOWED_MESSAGE_IDS
                for item in client.outbound_message_ids
            ),
        }
    finally:
        if client.isConnected():
            client.disconnect()
        if thread is not None:
            thread.join(timeout=2)


def write_capability_discovery(
    report: dict[str, object],
    destination: str | Path,
) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(report)
    temporary = path.with_name(f".{path.name}.{time.monotonic_ns()}.tmp")
    try:
        temporary.write_bytes(payload)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def report_sha256(report: dict[str, object]) -> str:
    return hashlib.sha256(canonical_bytes(report)).hexdigest()
