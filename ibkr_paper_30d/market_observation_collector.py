from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Protocol

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .ibkr_readonly import expected_identity_hash
from .ibkr_readonly_session import ReadOnlyMessageGuard
from .market_observation import (
    ClockSample,
    MarketObservation,
    MarketSession,
    ObservationWindow,
    classify_session,
    corrected_quote_age_ms,
)


class ObservationAborted(RuntimeError):
    pass


class ObservationConfig(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    symbols: tuple[str, ...]
    cadence_seconds: float = Field(gt=0)
    window_seconds: float = Field(ge=0)

    @field_validator("symbols")
    @classmethod
    def symbols_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(symbol.strip().upper() for symbol in value)
        if not normalized or len(set(normalized)) != len(normalized):
            raise ValueError("symbols must be nonempty and unique")
        return normalized


class ObservationPrerequisites(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    identity_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reconciliation_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    paper_identity_proven: bool
    broker_reconciliation_gate: str


class RawQuote(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    contract_id: int = Field(gt=0)
    liquid_hours: str
    timezone_id: str
    realtime_or_delayed: str
    entitlement_state: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    last_size: Decimal | None = None
    broker_quote_timestamp: datetime | None = None
    local_receipt_timestamp: datetime
    monotonic_receipt_ns: int = Field(ge=0)
    clock_skew_ms: int | None = None
    round_trip_ms: int | None = Field(default=None, ge=0)
    source_health: str

    @field_validator("broker_quote_timestamp", "local_receipt_timestamp")
    @classmethod
    def timestamps_are_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("quote timestamps must be timezone-aware")
        return value


class MarketDataSource(Protocol):
    def start(self, symbols: tuple[str, ...]) -> None: ...

    def identity_receipt_sha256(self) -> str: ...

    def heartbeat_ok(self) -> bool: ...

    def source_health(self) -> str: ...

    def snapshot(self, symbol: str) -> RawQuote: ...

    def stop(self) -> None: ...


class MarketObservationCollector:
    def __init__(
        self,
        source: MarketDataSource,
        *,
        now_utc: Callable[[], datetime] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.source = source
        self.now_utc = now_utc or (lambda: datetime.now(timezone.utc))
        self.monotonic_ns = monotonic_ns or time.monotonic_ns
        self.sleep = sleep or time.sleep

    def collect_window(
        self,
        config: ObservationConfig,
        prerequisites: ObservationPrerequisites,
    ) -> ObservationWindow:
        if not prerequisites.paper_identity_proven:
            raise ObservationAborted("PAPER_IDENTITY_UNCERTAIN")
        if prerequisites.broker_reconciliation_gate != "PASS":
            raise ObservationAborted("BROKER_RECONCILIATION_REQUIRED")

        started = self.now_utc()
        observations: list[MarketObservation] = []
        sample_count = int(config.window_seconds // config.cadence_seconds) + 1
        try:
            self.source.start(config.symbols)
            for sample_index in range(sample_count):
                identity = self.source.identity_receipt_sha256()
                if identity != prerequisites.identity_receipt_sha256:
                    raise ObservationAborted("PAPER_IDENTITY_UNCERTAIN")
                if not self.source.heartbeat_ok():
                    raise ObservationAborted("BROKER_HEARTBEAT_TIMEOUT")
                for symbol in config.symbols:
                    observations.append(
                        self._observation(
                            self.source.snapshot(symbol),
                            sequence=len(observations),
                            prerequisites=prerequisites,
                        )
                    )
                if sample_index + 1 < sample_count:
                    self.sleep(config.cadence_seconds)
            ended = self.now_utc()
        finally:
            self.source.stop()

        window_digest = hashlib.sha256(
            f"{started.isoformat()}|{ended.isoformat()}|{len(observations)}".encode(
                "ascii"
            )
        ).hexdigest()
        return ObservationWindow(
            window_id=f"market-window-{window_digest[:24]}",
            started_at_utc=started,
            ended_at_utc=ended,
            observations=tuple(observations),
            identity_receipt_sha256=prerequisites.identity_receipt_sha256,
            reconciliation_receipt_sha256=(
                prerequisites.reconciliation_receipt_sha256
            ),
            status="COMPLETE",
        )

    def _observation(
        self,
        raw: RawQuote,
        *,
        sequence: int,
        prerequisites: ObservationPrerequisites,
    ) -> MarketObservation:
        reasons: list[str] = []
        session = classify_session(
            raw.local_receipt_timestamp, raw.liquid_hours, raw.timezone_id
        )
        if session is not MarketSession.REGULAR:
            reasons.append(f"MARKET_SESSION_{session.value}")
        if raw.realtime_or_delayed != "REALTIME":
            reasons.append("DELAYED_DATA")
        if raw.entitlement_state != "AVAILABLE":
            reasons.append("ENTITLEMENT_UNAVAILABLE")
        if raw.bid is None or raw.ask is None:
            reasons.append("MISSING_BID_ASK")
        elif raw.bid > raw.ask:
            reasons.append("CROSSED_MARKET")
        if raw.source_health != "HEALTHY" or self.source.source_health() != "HEALTHY":
            reasons.append("SOURCE_UNHEALTHY")

        raw_age: int | None = None
        corrected_age: int | None = None
        if (
            raw.broker_quote_timestamp is None
            or raw.clock_skew_ms is None
            or raw.round_trip_ms is None
        ):
            reasons.append("TIMESTAMP_PROVENANCE_UNCERTAIN")
        else:
            raw_age = round(
                (
                    raw.local_receipt_timestamp - raw.broker_quote_timestamp
                ).total_seconds()
                * 1_000
            )
            clock = ClockSample(
                local_send_utc=raw.local_receipt_timestamp,
                broker_time_utc=raw.local_receipt_timestamp,
                local_receive_utc=raw.local_receipt_timestamp,
                round_trip_ms=raw.round_trip_ms,
                clock_skew_ms=raw.clock_skew_ms,
            )
            corrected_age = corrected_quote_age_ms(
                raw.broker_quote_timestamp,
                raw.local_receipt_timestamp,
                clock,
            )
            if corrected_age is None:
                reasons.append("CLOCK_SKEW_UNCERTAIN")

        unique_reasons = tuple(dict.fromkeys(reasons))
        digest = hashlib.sha256(
            f"{sequence}|{raw.symbol}|{raw.local_receipt_timestamp.isoformat()}".encode(
                "ascii"
            )
        ).hexdigest()
        return MarketObservation(
            observation_id=f"obs-{digest[:24]}",
            sequence=sequence,
            symbol=raw.symbol,
            contract_id=raw.contract_id,
            source="IBKR",
            market_session=session,
            realtime_or_delayed=raw.realtime_or_delayed,
            entitlement_state=raw.entitlement_state,
            bid=raw.bid,
            ask=raw.ask,
            last=raw.last,
            bid_size=raw.bid_size,
            ask_size=raw.ask_size,
            last_size=raw.last_size,
            broker_quote_timestamp=raw.broker_quote_timestamp,
            local_receipt_timestamp=raw.local_receipt_timestamp,
            monotonic_receipt_ns=raw.monotonic_receipt_ns,
            raw_quote_age_ms=raw_age,
            corrected_quote_age_ms=corrected_age,
            clock_skew_ms=raw.clock_skew_ms,
            round_trip_ms=raw.round_trip_ms,
            source_health=raw.source_health,
            identity_receipt_sha256=prerequisites.identity_receipt_sha256,
            reconciliation_receipt_sha256=(
                prerequisites.reconciliation_receipt_sha256
            ),
            accepted=not unique_reasons,
            reason_codes=unique_reasons,
        )


class _IBKRMarketDataClient(EWrapper, EClient):
    def __init__(
        self,
        *,
        now_utc: Callable[[], datetime] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
    ) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        self.now_utc = now_utc or (lambda: datetime.now(timezone.utc))
        self.monotonic_ns = monotonic_ns or time.monotonic_ns
        self.ready = threading.Event()
        self.managed_accounts_event = threading.Event()
        self.current_time_event = threading.Event()
        self.managed_accounts_value: tuple[str, ...] = ()
        self.server_timestamp: int | None = None
        self.clock_sample: ClockSample | None = None
        self._clock_send_utc: datetime | None = None
        self.request_symbols: dict[int, str] = {}
        self.contract_request_symbols: dict[int, str] = {}
        self.contract_details_events: dict[int, threading.Event] = {}
        self.contract_details_values: dict[int, tuple[str, int, str, str]] = {}
        self.quotes: dict[str, dict[str, object]] = {}
        self.outbound_message_ids: list[int] = []
        self.error_values: list[dict[str, object]] = []

    def sendMsg(self, msg: str) -> None:
        message_id = ReadOnlyMessageGuard.validate(msg)
        self.outbound_message_ids.append(message_id)
        super().sendMsg(msg)

    def nextValidId(self, orderId: int) -> None:
        self.ready.set()

    def managedAccounts(self, accountsList: str) -> None:
        self.managed_accounts_value = tuple(
            account.strip() for account in accountsList.split(",") if account.strip()
        )
        self.managed_accounts_event.set()

    def currentTime(self, time_value: int) -> None:
        self.server_timestamp = time_value
        local_receive = self.now_utc()
        if self._clock_send_utc is not None:
            self.clock_sample = ClockSample.from_round_trip(
                self._clock_send_utc,
                datetime.fromtimestamp(time_value, timezone.utc),
                local_receive,
            )
        self.current_time_event.set()

    def begin_clock_sample(self) -> None:
        self.current_time_event.clear()
        self.clock_sample = None
        self._clock_send_utc = self.now_utc()

    def register_contract_request(self, request_id: int, symbol: str) -> None:
        self.contract_request_symbols[request_id] = symbol
        self.contract_details_events[request_id] = threading.Event()

    def contractDetails(self, reqId: int, contractDetails: object) -> None:
        symbol = self.contract_request_symbols.get(reqId)
        contract = getattr(contractDetails, "contract", None)
        contract_id = getattr(contract, "conId", 0)
        liquid_hours = getattr(contractDetails, "liquidHours", "")
        timezone_id = getattr(contractDetails, "timeZoneId", "")
        if symbol and contract_id and liquid_hours and timezone_id:
            self.contract_details_values[reqId] = (
                symbol,
                int(contract_id),
                str(liquid_hours),
                str(timezone_id),
            )

    def contractDetailsEnd(self, reqId: int) -> None:
        event = self.contract_details_events.get(reqId)
        if event is not None:
            event.set()

    def resolved_contract(self, request_id: int) -> tuple[str, int, str, str]:
        try:
            return self.contract_details_values[request_id]
        except KeyError as exc:
            raise ObservationAborted("CONTRACT_DETAILS_UNRESOLVED") from exc

    def register_request(
        self,
        request_id: int,
        symbol: str,
        contract_id: int,
        liquid_hours: str,
        timezone_id: str,
    ) -> None:
        self.request_symbols[request_id] = symbol
        self.quotes.setdefault(symbol, {}).update(
            {
                "symbol": symbol,
                "contract_id": contract_id,
                "liquid_hours": liquid_hours,
                "timezone_id": timezone_id,
            }
        )

    def marketDataType(self, reqId: int, marketDataType: int) -> None:
        symbol = self.request_symbols.get(reqId)
        if symbol:
            classifications = {
                1: "REALTIME",
                2: "FROZEN",
                3: "DELAYED",
                4: "DELAYED_FROZEN",
            }
            self.quotes[symbol]["realtime_or_delayed"] = classifications.get(
                marketDataType, "UNKNOWN"
            )

    def tickByTickBidAsk(
        self,
        reqId: int,
        time_value: int,
        bidPrice: float,
        askPrice: float,
        bidSize: object,
        askSize: object,
        tickAttribBidAsk: object,
    ) -> None:
        symbol = self.request_symbols.get(reqId)
        if not symbol:
            return
        quote = self.quotes[symbol]
        quote.update(
            {
                "bid": Decimal(str(bidPrice)),
                "ask": Decimal(str(askPrice)),
                "bid_size": Decimal(str(bidSize)),
                "ask_size": Decimal(str(askSize)),
            }
        )
        self._stamp(quote, time_value)

    def tickByTickAllLast(
        self,
        reqId: int,
        tickType: int,
        time_value: int,
        price: float,
        size: object,
        tickAttribLast: object,
        exchange: str,
        specialConditions: str,
    ) -> None:
        symbol = self.request_symbols.get(reqId)
        if not symbol:
            return
        quote = self.quotes[symbol]
        quote.update({"last": Decimal(str(price)), "last_size": Decimal(str(size))})
        self._stamp(quote, time_value)

    def _stamp(self, quote: dict[str, object], time_value: int) -> None:
        broker_timestamp = datetime.fromtimestamp(time_value, timezone.utc)
        previous = quote.get("broker_quote_timestamp")
        if not isinstance(previous, datetime) or broker_timestamp < previous:
            quote["broker_quote_timestamp"] = broker_timestamp
        quote["local_receipt_timestamp"] = self.now_utc()
        quote["monotonic_receipt_ns"] = self.monotonic_ns()

    def raw_quote(self, symbol: str) -> RawQuote:
        quote = dict(self.quotes[symbol])
        local_receipt = quote.get("local_receipt_timestamp")
        if not isinstance(local_receipt, datetime):
            local_receipt = self.now_utc()
        if self.clock_sample is None:
            skew = None
            round_trip = None
        else:
            skew = self.clock_sample.clock_skew_ms
            round_trip = self.clock_sample.round_trip_ms
        has_data = any(quote.get(name) is not None for name in ("bid", "ask", "last"))
        return RawQuote(
            symbol=symbol,
            contract_id=int(quote["contract_id"]),
            liquid_hours=str(quote["liquid_hours"]),
            timezone_id=str(quote["timezone_id"]),
            realtime_or_delayed=str(quote.get("realtime_or_delayed", "UNKNOWN")),
            entitlement_state="AVAILABLE" if has_data else "UNKNOWN",
            bid=quote.get("bid"),
            ask=quote.get("ask"),
            last=quote.get("last"),
            bid_size=quote.get("bid_size"),
            ask_size=quote.get("ask_size"),
            last_size=quote.get("last_size"),
            broker_quote_timestamp=quote.get("broker_quote_timestamp"),
            local_receipt_timestamp=local_receipt,
            monotonic_receipt_ns=int(quote.get("monotonic_receipt_ns", 0)),
            clock_skew_ms=skew,
            round_trip_ms=round_trip,
            source_health="HEALTHY",
        )

    def error(
        self,
        reqId: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        self.error_values.append(
            {"request_id": reqId, "code": errorCode, "message": errorString[:300]}
        )


PRIMARY_EXCHANGE_BY_SYMBOL = {
    "SPY": "ARCA",
    "QQQ": "NASDAQ",
    "IEF": "NASDAQ",
}


class IBKRMarketDataSource:
    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 19741,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.timeout_seconds = timeout_seconds
        self.client = _IBKRMarketDataClient()
        self.thread: threading.Thread | None = None
        self.request_ids: list[int] = []

    def start(self, symbols: tuple[str, ...]) -> None:
        if self.port != 4002 or self.host not in {"127.0.0.1", "localhost"}:
            raise ObservationAborted("PAPER_ENDPOINT_REQUIRED")
        self.client.connect(self.host, self.port, self.client_id)
        if not self.client.isConnected():
            raise ObservationAborted("BROKER_DISCONNECTED")
        self.thread = threading.Thread(target=self.client.run, daemon=True)
        self.thread.start()
        if not self.client.ready.wait(self.timeout_seconds):
            raise ObservationAborted("BROKER_HANDSHAKE_TIMEOUT")
        self.client.reqManagedAccts()
        if not self.client.managed_accounts_event.wait(self.timeout_seconds):
            raise ObservationAborted("MANAGED_ACCOUNT_TIMEOUT")
        if len(self.client.managed_accounts_value) != 1:
            raise ObservationAborted("MANAGED_ACCOUNT_COUNT_INVALID")

        resolved: list[tuple[Contract, tuple[str, int, str, str]]] = []
        for offset, symbol in enumerate(symbols):
            contract = Contract()
            contract.symbol = symbol
            contract.secType = "STK"
            contract.exchange = "SMART"
            contract.currency = "USD"
            primary_exchange = PRIMARY_EXCHANGE_BY_SYMBOL.get(symbol.upper())
            if primary_exchange:
                contract.primaryExchange = primary_exchange
            contract_request_id = 9_000 + offset
            self.client.register_contract_request(contract_request_id, symbol)
            self.client.reqContractDetails(contract_request_id, contract)
            event = self.client.contract_details_events[contract_request_id]
            if not event.wait(self.timeout_seconds):
                raise ObservationAborted("CONTRACT_DETAILS_TIMEOUT")
            resolved.append(
                (contract, self.client.resolved_contract(contract_request_id))
            )

        for offset, (contract, details) in enumerate(resolved):
            symbol, contract_id, liquid_hours, timezone_id = details
            contract.conId = contract_id
            request_base = 10_000 + offset * 10
            self.client.register_request(
                request_base,
                symbol,
                contract_id,
                liquid_hours,
                timezone_id,
            )
            self.client.reqMktData(request_base, contract, "", False, False, [])
            self.client.reqTickByTickData(request_base + 1, contract, "BidAsk", 0, False)
            self.client.reqTickByTickData(request_base + 2, contract, "Last", 0, False)
            self.client.request_symbols[request_base + 1] = symbol
            self.client.request_symbols[request_base + 2] = symbol
            self.request_ids.extend((request_base, request_base + 1, request_base + 2))
        self.client.begin_clock_sample()
        self.client.reqCurrentTime()
        if not self.client.current_time_event.wait(self.timeout_seconds):
            raise ObservationAborted("BROKER_CLOCK_TIMEOUT")

    def identity_receipt_sha256(self) -> str:
        accounts = self.client.managed_accounts_value
        return expected_identity_hash(accounts[0]) if len(accounts) == 1 else ""

    def heartbeat_ok(self) -> bool:
        return self.client.isConnected() and self.client.current_time_event.is_set()

    def source_health(self) -> str:
        unhealthy_codes = {502, 503, 504, 1100, 1300, 2103, 2105}
        return (
            "DEGRADED"
            if any(int(item["code"]) in unhealthy_codes for item in self.client.error_values)
            else "HEALTHY"
        )

    def snapshot(self, symbol: str) -> RawQuote:
        return self.client.raw_quote(symbol)

    def stop(self) -> None:
        for request_id in self.request_ids:
            if request_id % 10 == 0:
                self.client.cancelMktData(request_id)
            else:
                self.client.cancelTickByTickData(request_id)
        if self.client.isConnected():
            self.client.disconnect()
        if self.thread is not None:
            self.thread.join(timeout=2)


def reconciliation_receipt_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
