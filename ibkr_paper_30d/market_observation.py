from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MarketSession(str, Enum):
    PREMARKET = "PREMARKET"
    REGULAR = "REGULAR"
    AFTER_HOURS = "AFTER_HOURS"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class ClockSample(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    local_send_utc: datetime
    broker_time_utc: datetime
    local_receive_utc: datetime
    round_trip_ms: int = Field(ge=0)
    clock_skew_ms: int

    @classmethod
    def from_round_trip(
        cls,
        local_send_utc: datetime,
        broker_time_utc: datetime,
        local_receive_utc: datetime,
    ) -> "ClockSample":
        for value in (local_send_utc, broker_time_utc, local_receive_utc):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("clock timestamps must be timezone-aware")
        if local_receive_utc < local_send_utc:
            raise ValueError("clock response precedes request")
        round_trip = local_receive_utc - local_send_utc
        midpoint = local_send_utc + round_trip / 2
        return cls(
            local_send_utc=local_send_utc,
            broker_time_utc=broker_time_utc,
            local_receive_utc=local_receive_utc,
            round_trip_ms=round(round_trip.total_seconds() * 1_000),
            clock_skew_ms=round(
                (midpoint - broker_time_utc).total_seconds() * 1_000
            ),
        )

    @field_validator(
        "local_send_utc", "broker_time_utc", "local_receive_utc"
    )
    @classmethod
    def timestamps_are_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock timestamps must be timezone-aware")
        return value


class MarketObservation(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    observation_id: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    symbol: str = Field(min_length=1)
    contract_id: int = Field(gt=0)
    source: Literal["IBKR"]
    market_session: MarketSession
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
    raw_quote_age_ms: int | None = None
    corrected_quote_age_ms: int | None = None
    clock_skew_ms: int | None = None
    round_trip_ms: int | None = Field(default=None, ge=0)
    source_health: str
    identity_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reconciliation_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted: bool
    reason_codes: tuple[str, ...]
    metadata: dict[str, Any] = Field(default_factory=dict)
    record_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("broker_quote_timestamp", "local_receipt_timestamp")
    @classmethod
    def quote_timestamps_are_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("quote timestamps must be timezone-aware")
        return value

    @field_validator("bid", "ask", "last")
    @classmethod
    def prices_are_finite_and_positive(
        cls, value: Decimal | None
    ) -> Decimal | None:
        if value is not None and (not value.is_finite() or value <= 0):
            raise ValueError("prices must be finite and positive")
        return value

    @field_validator("bid_size", "ask_size", "last_size")
    @classmethod
    def sizes_are_finite_and_nonnegative(
        cls, value: Decimal | None
    ) -> Decimal | None:
        if value is not None and (not value.is_finite() or value < 0):
            raise ValueError("sizes must be finite and nonnegative")
        return value

    @model_validator(mode="after")
    def sanitized_and_consistent(self) -> "MarketObservation":
        _reject_forbidden_metadata(self.metadata)
        if self.accepted and self.reason_codes:
            raise ValueError("accepted observations cannot contain rejection reasons")
        if not self.accepted and not self.reason_codes:
            raise ValueError("rejected observations require reason codes")
        return self

    @property
    def bid_present(self) -> bool:
        return self.bid is not None

    @property
    def ask_present(self) -> bool:
        return self.ask is not None

    @property
    def last_present(self) -> bool:
        return self.last is not None

    @property
    def spread_present(self) -> bool:
        return self.bid is not None and self.ask is not None and self.bid <= self.ask


class ObservationWindow(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    window_id: str = Field(min_length=1)
    started_at_utc: datetime
    ended_at_utc: datetime
    observations: tuple[MarketObservation, ...]
    identity_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reconciliation_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: str
    reason_codes: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_window(self) -> "ObservationWindow":
        for value in (self.started_at_utc, self.ended_at_utc):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("window timestamps must be timezone-aware")
        if self.ended_at_utc < self.started_at_utc:
            raise ValueError("window end precedes start")
        _reject_forbidden_metadata(self.metadata)
        return self


def classify_session(
    now_utc: datetime,
    liquid_hours: str,
    timezone_id: str,
) -> MarketSession:
    if now_utc.tzinfo is None or now_utc.utcoffset() is None or not liquid_hours:
        return MarketSession.UNKNOWN
    try:
        local_now = now_utc.astimezone(ZoneInfo(timezone_id))
    except (ZoneInfoNotFoundError, ValueError):
        return MarketSession.UNKNOWN

    date_key = local_now.strftime("%Y%m%d")
    matching = [
        item.strip()
        for item in liquid_hours.split(";")
        if item.strip().startswith(f"{date_key}:")
    ]
    if len(matching) != 1:
        return MarketSession.UNKNOWN
    entry = matching[0]
    if entry == f"{date_key}:CLOSED":
        return MarketSession.CLOSED

    ranges = entry.split(",")
    parsed: list[tuple[datetime, datetime]] = []
    for value in ranges:
        match = re.fullmatch(r"(\d{8}):(\d{4})-(\d{8}):(\d{4})", value)
        if not match:
            return MarketSession.UNKNOWN
        try:
            start = datetime.strptime(
                f"{match.group(1)}{match.group(2)}", "%Y%m%d%H%M"
            ).replace(tzinfo=ZoneInfo(timezone_id))
            end = datetime.strptime(
                f"{match.group(3)}{match.group(4)}", "%Y%m%d%H%M"
            ).replace(tzinfo=ZoneInfo(timezone_id))
        except (ValueError, ZoneInfoNotFoundError):
            return MarketSession.UNKNOWN
        if end <= start:
            return MarketSession.UNKNOWN
        parsed.append((start, end))

    if any(start <= local_now <= end for start, end in parsed):
        return MarketSession.REGULAR
    if local_now < min(start for start, _ in parsed):
        return MarketSession.PREMARKET
    if local_now > max(end for _, end in parsed):
        return MarketSession.AFTER_HOURS
    return MarketSession.UNKNOWN


def corrected_quote_age_ms(
    broker_quote_timestamp: datetime,
    local_receipt_timestamp: datetime,
    clock_sample: ClockSample,
) -> int | None:
    if any(
        value.tzinfo is None or value.utcoffset() is None
        for value in (broker_quote_timestamp, local_receipt_timestamp)
    ):
        return None
    raw_age = round(
        (local_receipt_timestamp - broker_quote_timestamp).total_seconds() * 1_000
    )
    corrected = raw_age - clock_sample.clock_skew_ms
    uncertainty = max(1, clock_sample.round_trip_ms // 2)
    if corrected < -uncertainty:
        return None
    return corrected


def _reject_forbidden_metadata(value: Any) -> None:
    forbidden_keys = {
        "account",
        "account_id",
        "ibkr_account",
        "password",
        "smtp_password",
        "secret",
        "token",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in forbidden_keys or any(
                marker in normalized for marker in ("password", "secret", "token")
            ):
                raise ValueError("forbidden evidence metadata key")
            _reject_forbidden_metadata(nested)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _reject_forbidden_metadata(nested)
        return
    if isinstance(value, str) and re.search(r"\bDU\d{4,}\b", value, re.IGNORECASE):
        raise ValueError("raw account identity is forbidden")
