from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from .canonical import sha256_json


class DecisionClass(str, Enum):
    NEW_TRADE = "NEW_TRADE"
    OPEN_POSITION_MANAGEMENT = "OPEN_POSITION_MANAGEMENT"


class QuoteSnapshot(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    contract_id: int
    source: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    last_size: Decimal | None = None
    quote_timestamp: datetime | None = None
    local_receipt_timestamp: datetime | None = None
    market_session: str
    realtime_or_delayed: str
    data_entitlement_status: str
    declared_quote_age_ms: int | None = None
    source_health: str

    @property
    def mid(self) -> Decimal | None:
        if not _valid_price(self.bid) or not _valid_price(self.ask):
            return None
        assert self.bid is not None and self.ask is not None
        if self.bid > self.ask:
            return None
        return (self.bid + self.ask) / Decimal("2")


class MarketDataPolicy(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    version: str
    max_new_trade_age_ms: int = Field(ge=0)
    max_position_management_age_ms: int = Field(ge=0)
    max_clock_skew_ms: int = Field(ge=0)
    require_realtime_for_new_trade: bool = True
    require_bid_ask_for_spread: bool = True


class MarketDataSnapshot(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    sha256: str
    created_at_utc: datetime
    quotes: tuple[QuoteSnapshot, ...]

    @classmethod
    def freeze(
        cls,
        quotes: Iterable[QuoteSnapshot],
        *,
        created_at_utc: datetime,
    ) -> "MarketDataSnapshot":
        frozen_quotes = tuple(quotes)
        if not frozen_quotes:
            raise ValueError("at least one quote is required")
        payload = {
            "schema": "MARKET_DATA_SNAPSHOT_V1",
            "created_at_utc": created_at_utc,
            "quotes": [quote.model_dump(mode="python") for quote in frozen_quotes],
        }
        digest = sha256_json(payload)
        return cls(
            snapshot_id=f"md-{digest[:24]}",
            sha256=digest,
            created_at_utc=created_at_utc,
            quotes=frozen_quotes,
        )


class MarketDataGateResult(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    status: str
    reason_codes: tuple[str, ...]
    market_data_snapshot_id: str
    market_data_snapshot_sha256: str
    quote_timestamp: datetime | None
    quote_age_at_decision_ms: int | None
    market_data_policy_version: str


def _valid_price(value: Decimal | None) -> bool:
    return value is not None and value.is_finite() and value > 0


def _valid_optional_size(value: Decimal | None) -> bool:
    return value is None or (value.is_finite() and value >= 0)


def _utc_age_ms(now: datetime, timestamp: datetime) -> int | None:
    if now.tzinfo is None or timestamp.tzinfo is None:
        return None
    return int((now - timestamp).total_seconds() * 1_000)


class MarketDataGate:
    def __init__(self, policy: MarketDataPolicy):
        self.policy = policy

    def evaluate(
        self,
        snapshot: MarketDataSnapshot,
        decision_class: DecisionClass,
        *,
        now: datetime,
    ) -> MarketDataGateResult:
        reasons: list[str] = []
        ages: list[int] = []
        timestamps: list[datetime] = []
        max_age = (
            self.policy.max_new_trade_age_ms
            if decision_class is DecisionClass.NEW_TRADE
            else self.policy.max_position_management_age_ms
        )

        for quote in snapshot.quotes:
            if (
                decision_class is DecisionClass.NEW_TRADE
                and self.policy.require_realtime_for_new_trade
                and quote.realtime_or_delayed != "REALTIME"
            ):
                _add_reason(reasons, "DELAYED_DATA")
            if (
                self.policy.require_bid_ask_for_spread
                and (quote.bid is None or quote.ask is None)
            ):
                _add_reason(reasons, "MISSING_BID_ASK")
            if _valid_price(quote.bid) and _valid_price(quote.ask):
                assert quote.bid is not None and quote.ask is not None
                if quote.bid > quote.ask:
                    _add_reason(reasons, "CROSSED_MARKET")
            if quote.data_entitlement_status != "AVAILABLE":
                _add_reason(reasons, "ENTITLEMENT_UNAVAILABLE")
            if quote.source_health != "HEALTHY":
                _add_reason(reasons, "SOURCE_UNHEALTHY")
            if (
                decision_class is DecisionClass.NEW_TRADE
                and quote.market_session != "REGULAR"
            ):
                _add_reason(
                    reasons,
                    (
                        "MARKET_SESSION_CLOSED"
                        if quote.market_session == "CLOSED"
                        else "MARKET_SESSION_NOT_REGULAR"
                    ),
                )

            prices = (quote.bid, quote.ask, quote.last)
            if any(value is not None and not _valid_price(value) for value in prices):
                _add_reason(reasons, "INVALID_PRICE")
            sizes = (quote.bid_size, quote.ask_size, quote.last_size)
            if any(not _valid_optional_size(value) for value in sizes):
                _add_reason(reasons, "INVALID_SIZE")

            if quote.quote_timestamp is None or quote.local_receipt_timestamp is None:
                _add_reason(reasons, "TIMESTAMP_PROVENANCE_UNCERTAIN")
                continue
            age = _utc_age_ms(now, quote.quote_timestamp)
            receipt_age = _utc_age_ms(now, quote.local_receipt_timestamp)
            if age is None or receipt_age is None:
                _add_reason(reasons, "TIMESTAMP_PROVENANCE_UNCERTAIN")
                continue
            timestamps.append(quote.quote_timestamp)
            ages.append(age)
            if age < -self.policy.max_clock_skew_ms:
                _add_reason(reasons, "CLOCK_SKEW")
            if age > max_age:
                _add_reason(reasons, "STALE_QUOTE")
            if (
                quote.declared_quote_age_ms is None
                or abs(age - quote.declared_quote_age_ms)
                > self.policy.max_clock_skew_ms
            ):
                _add_reason(reasons, "TIMESTAMP_MISMATCH")

        oldest_index = ages.index(max(ages)) if ages else None
        return MarketDataGateResult(
            status="BLOCK" if reasons else "PASS",
            reason_codes=tuple(reasons),
            market_data_snapshot_id=snapshot.snapshot_id,
            market_data_snapshot_sha256=snapshot.sha256,
            quote_timestamp=(
                timestamps[oldest_index] if oldest_index is not None else None
            ),
            quote_age_at_decision_ms=(
                ages[oldest_index] if oldest_index is not None else None
            ),
            market_data_policy_version=self.policy.version,
        )


def _add_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)
