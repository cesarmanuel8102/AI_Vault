"""Append-only economic ledgers for isolated autonomous capital sleeves."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .canonical import canonical_bytes, sha256_json
from .experiment_ledger import normalized_decimal, normalized_money
from .multi_universe_models import CapitalSleeve, SHA256_PATTERN
from .multi_universe_schema import verify_multi_universe_schema_v4
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7


class SleeveLedgerError(RuntimeError):
    pass


class _LedgerModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    @property
    def sha256(self) -> str:
        return sha256_json(self)


class CurrencyBalance(_LedgerModel):
    currency: str = Field(min_length=3, max_length=3)
    amount: Decimal

    @field_validator("currency")
    @classmethod
    def _normalize_currency(cls, value: str) -> str:
        return value.upper()


class CarryForwardPosition(_LedgerModel):
    contract_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    quantity: Decimal
    multiplier: Decimal = Field(gt=0)
    average_cost: Decimal = Field(ge=0)
    mark: Decimal = Field(ge=0)
    market_value_usd: Decimal


class RegularCarryForward(_LedgerModel):
    allocation_usd: Decimal
    currency_balances: tuple[CurrencyBalance, ...]
    positions: tuple[CarryForwardPosition, ...]
    open_order_count: int = Field(ge=0)
    fill_count: int = Field(ge=0)
    fees_usd: Decimal = Field(ge=0)
    realized_pnl_usd: Decimal
    unrealized_pnl_usd: Decimal
    historical_event_sha256: tuple[str, ...]
    source_ledger_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def _validate_carry(self) -> "RegularCarryForward":
        if self.allocation_usd != Decimal("500.00"):
            raise ValueError("regular allocation must equal USD 500")
        currencies = [item.currency for item in self.currency_balances]
        if len(currencies) != len(set(currencies)):
            raise ValueError("duplicate carry-forward currency")
        contracts = [item.contract_identity_sha256 for item in self.positions]
        if len(contracts) != len(set(contracts)):
            raise ValueError("duplicate carry-forward contract")
        if len(self.historical_event_sha256) != len(set(self.historical_event_sha256)):
            raise ValueError("duplicate historical event hash")
        if any(
            len(item) != 64 or any(char not in "0123456789abcdef" for char in item)
            for item in self.historical_event_sha256
        ):
            raise ValueError("invalid historical event hash")
        return self


class SleeveLedgerReceipt(_LedgerModel):
    event_id: str = Field(min_length=1)
    event_sha256: str = Field(pattern=SHA256_PATTERN)
    sleeve: CapitalSleeve
    event_type: str = Field(min_length=1)
    duplicate: bool


class SleeveLedgerState(_LedgerModel):
    sleeve: CapitalSleeve
    initialized: bool
    allocation_usd: Decimal
    currency_balances: tuple[CurrencyBalance, ...]
    positions: tuple[CarryForwardPosition, ...]
    open_order_count: int = Field(ge=0)
    fill_count: int = Field(ge=0)
    fees_usd: Decimal
    realized_pnl_usd: Decimal
    unrealized_pnl_usd: Decimal
    reserved_liability_usd: Decimal
    historical_event_sha256: tuple[str, ...]
    source_ledger_sha256: str | None
    event_count: int = Field(ge=0)

    def balance(self, currency: str) -> Decimal:
        normalized = currency.upper()
        return next(
            (item.amount for item in self.currency_balances if item.currency == normalized),
            Decimal("0.00"),
        )


class MultiSleeveLedgerState(_LedgerModel):
    regular: SleeveLedgerState
    extended: SleeveLedgerState
    aggregate_currency_balances: tuple[CurrencyBalance, ...]

    @property
    def continuous(self) -> SleeveLedgerState:
        return self.extended

    def aggregate_balance(self, currency: str) -> Decimal:
        normalized = currency.upper()
        return next(
            (
                item.amount
                for item in self.aggregate_currency_balances
                if item.currency == normalized
            ),
            Decimal("0.00"),
        )


class SleeveLedgerStore:
    SCHEMA = "SLEEVE_LEDGER_EVENT_V1"

    def __init__(self, db: Database):
        verify_multi_universe_schema_v4(db)
        self.db = db

    def _rows(self) -> list[tuple[Any, ...]]:
        return self.db.execute(
            "SELECT event_id,sleeve,currency,event_type,payload_json,"
            "payload_sha256,previous_event_sha256,event_sha256,created_at_utc "
            "FROM sleeve_ledger_events ORDER BY sequence"
        ).fetchall()

    def _events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        previous: str | None = None
        for row in self._rows():
            (
                event_id,
                sleeve,
                currency,
                event_type,
                payload_json,
                payload_sha256,
                stored_previous,
                event_sha256,
                created_at_utc,
            ) = row
            try:
                payload = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError) as exc:
                raise SleeveLedgerError("SLEEVE_LEDGER_JSON_INVALID") from exc
            if payload.get("schema") != self.SCHEMA:
                raise SleeveLedgerError("SLEEVE_LEDGER_SCHEMA_INVALID")
            if sha256_json(payload) != str(payload_sha256):
                raise SleeveLedgerError("SLEEVE_LEDGER_PAYLOAD_HASH_MISMATCH")
            normalized_previous = (
                str(stored_previous) if stored_previous is not None else None
            )
            if normalized_previous != previous:
                raise SleeveLedgerError("SLEEVE_LEDGER_CHAIN_MISMATCH")
            expected = sha256_json(
                {"previous_event_sha256": previous, "payload": payload}
            )
            if expected != str(event_sha256):
                raise SleeveLedgerError("SLEEVE_LEDGER_EVENT_HASH_MISMATCH")
            events.append(
                {
                    **payload,
                    "event_id": str(event_id),
                    "sleeve": str(sleeve),
                    "currency": str(currency),
                    "event_type": str(event_type),
                    "event_sha256": str(event_sha256),
                    "created_at_utc": str(created_at_utc),
                }
            )
            previous = str(event_sha256)
        return events

    def _insert(
        self,
        *,
        sleeve: CapitalSleeve,
        currency: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> SleeveLedgerReceipt:
        body = {
            "schema": self.SCHEMA,
            "sleeve": sleeve.value,
            "currency": currency.upper(),
            "event_type": event_type,
            **payload,
        }
        event_id = str(new_uuid7())
        row = self.db.execute(
            "SELECT event_sha256 FROM sleeve_ledger_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous = str(row[0]) if row is not None else None
        event_sha256 = sha256_json(
            {"previous_event_sha256": previous, "payload": body}
        )
        self.db.execute(
            "INSERT INTO sleeve_ledger_events("
            "event_id,sleeve,currency,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                sleeve.value,
                currency.upper(),
                event_type,
                canonical_bytes(body).decode("utf-8"),
                sha256_json(body),
                previous,
                event_sha256,
                utc_now(),
            ),
        )
        return SleeveLedgerReceipt(
            event_id=event_id,
            event_sha256=event_sha256,
            sleeve=sleeve,
            event_type=event_type,
            duplicate=False,
        )

    def _bootstrap_receipt(
        self,
        sleeve: CapitalSleeve,
        event_type: str,
        authority_sha256: str,
    ) -> SleeveLedgerReceipt | None:
        rows = [
            event
            for event in self._events()
            if CapitalSleeve(event["sleeve"]) is sleeve
        ]
        if not rows:
            return None
        first = rows[0]
        if (
            first["event_type"] != event_type
            or first.get("authority_sha256") != authority_sha256
        ):
            raise SleeveLedgerError("SLEEVE_BOOTSTRAP_CONFLICT")
        return SleeveLedgerReceipt(
            event_id=first["event_id"],
            event_sha256=first["event_sha256"],
            sleeve=sleeve,
            event_type=event_type,
            duplicate=True,
        )

    def bootstrap_regular(self, carry: RegularCarryForward) -> SleeveLedgerReceipt:
        with self.db.transaction():
            return self.bootstrap_regular_in_transaction(carry)

    def bootstrap_regular_in_transaction(
        self, carry: RegularCarryForward
    ) -> SleeveLedgerReceipt:
        if not self.db.connection.in_transaction:
            raise SleeveLedgerError("ATOMIC_BOOTSTRAP_TRANSACTION_REQUIRED")
        existing = self._bootstrap_receipt(
            CapitalSleeve.REGULAR_SLEEVE,
            "REGULAR_BOOTSTRAP",
            carry.sha256,
        )
        if existing is not None:
            return existing
        return self._insert(
            sleeve=CapitalSleeve.REGULAR_SLEEVE,
            currency="USD",
            event_type="REGULAR_BOOTSTRAP",
            payload={
                "authority_sha256": carry.sha256,
                "carry": carry.model_dump(mode="json"),
            },
        )

    @staticmethod
    def _continuous_authority() -> dict[str, Any]:
        return {
            "allocation_usd": "500.00",
            "opening_pnl_usd": "0.00",
            "positions": [],
            "open_order_count": 0,
        }

    def bootstrap_continuous(self) -> SleeveLedgerReceipt:
        with self.db.transaction():
            return self.bootstrap_continuous_in_transaction()

    def bootstrap_continuous_in_transaction(self) -> SleeveLedgerReceipt:
        if not self.db.connection.in_transaction:
            raise SleeveLedgerError("ATOMIC_BOOTSTRAP_TRANSACTION_REQUIRED")
        authority = self._continuous_authority()
        authority_sha256 = sha256_json(authority)
        existing = self._bootstrap_receipt(
            CapitalSleeve.CONTINUOUS_SLEEVE,
            "CONTINUOUS_BOOTSTRAP",
            authority_sha256,
        )
        if existing is not None:
            return existing
        return self._insert(
            sleeve=CapitalSleeve.CONTINUOUS_SLEEVE,
            currency="USD",
            event_type="CONTINUOUS_BOOTSTRAP",
            payload={
                "authority_sha256": authority_sha256,
                "authority": authority,
            },
        )

    def bootstrap_extended(self) -> SleeveLedgerReceipt:
        """Compatibility delegate; new receipts use continuous vocabulary."""

        return self.bootstrap_continuous()

    def bootstrap_extended_in_transaction(self) -> SleeveLedgerReceipt:
        """Compatibility delegate for callers migrating to the canonical API."""

        return self.bootstrap_continuous_in_transaction()

    def append(
        self,
        sleeve: CapitalSleeve,
        event_type: str,
        payload: dict[str, Any],
    ) -> str:
        if not isinstance(sleeve, CapitalSleeve):
            sleeve = CapitalSleeve(sleeve)
        with self.db.transaction():
            state = self.project(sleeve)
            if not state.initialized:
                raise SleeveLedgerError("SLEEVE_NOT_INITIALIZED")
            currency = str(payload.get("currency") or "USD").upper()
            normalized = dict(payload)
            if event_type in {"CURRENCY_CREDIT", "CURRENCY_DEBIT"}:
                amount = normalized_decimal(payload.get("amount"))
                if amount <= 0:
                    raise SleeveLedgerError("INVALID_CURRENCY_AMOUNT")
                if event_type == "CURRENCY_DEBIT" and state.balance(currency) < amount:
                    raise SleeveLedgerError("SLEEVE_CURRENCY_INSUFFICIENT")
                normalized = {"currency": currency, "amount": str(amount)}
            elif event_type == "LIABILITY_RESERVED":
                collateral = str(payload.get("collateral_sleeve") or sleeve.value)
                if collateral != sleeve.value:
                    raise SleeveLedgerError("CROSS_SLEEVE_PLEDGE_FORBIDDEN")
                amount = normalized_decimal(payload.get("amount_usd"))
                if amount < 0:
                    raise SleeveLedgerError("INVALID_RESERVED_LIABILITY")
                normalized = {
                    "amount_usd": str(amount),
                    "collateral_sleeve": collateral,
                }
            elif event_type == "LIABILITY_RELEASED":
                amount = normalized_decimal(payload.get("amount_usd"))
                if amount < 0 or amount > state.reserved_liability_usd:
                    raise SleeveLedgerError("INVALID_RELEASED_LIABILITY")
                normalized = {"amount_usd": str(amount)}
            receipt = self._insert(
                sleeve=sleeve,
                currency=currency,
                event_type=event_type,
                payload=normalized,
            )
        return receipt.event_id

    def reserve_liability_in_transaction(
        self,
        sleeve: CapitalSleeve,
        *,
        amount_usd: Decimal,
        reservation_key: str,
    ) -> SleeveLedgerReceipt:
        """Append one liability reservation inside the caller's transaction."""

        if not self.db.connection.in_transaction:
            raise SleeveLedgerError("ATOMIC_RESERVATION_TRANSACTION_REQUIRED")
        state = self.project(sleeve)
        if not state.initialized:
            raise SleeveLedgerError("SLEEVE_NOT_INITIALIZED")
        amount = normalized_decimal(amount_usd)
        if amount < 0:
            raise SleeveLedgerError("INVALID_RESERVED_LIABILITY")
        if state.reserved_liability_usd + amount > state.allocation_usd:
            raise SleeveLedgerError("SLEEVE_AGGREGATE_LIABILITY_EXCEEDED")
        return self._insert(
            sleeve=sleeve,
            currency="USD",
            event_type="LIABILITY_RESERVED",
            payload={
                "amount_usd": str(amount),
                "collateral_sleeve": sleeve.value,
                "reservation_key": reservation_key,
            },
        )

    def release_liability_in_transaction(
        self,
        sleeve: CapitalSleeve,
        *,
        amount_usd: Decimal,
        reservation_key: str,
        broker_snapshot_sha256: str,
    ) -> SleeveLedgerReceipt:
        """Release one proven-terminal reservation in the caller's transaction."""

        if not self.db.connection.in_transaction:
            raise SleeveLedgerError("ATOMIC_RESERVATION_TRANSACTION_REQUIRED")
        state = self.project(sleeve)
        amount = normalized_decimal(amount_usd)
        if amount < 0 or amount > state.reserved_liability_usd:
            raise SleeveLedgerError("INVALID_RELEASED_LIABILITY")
        return self._insert(
            sleeve=sleeve,
            currency="USD",
            event_type="LIABILITY_RELEASED",
            payload={
                "amount_usd": str(amount),
                "reservation_key": reservation_key,
                "broker_snapshot_sha256": broker_snapshot_sha256,
            },
        )

    def reconcile_broker_snapshot(
        self,
        snapshot: Mapping[str, Any],
        ownership: Any,
    ) -> dict[str, str]:
        """Project one complete broker snapshot into both owned sleeve ledgers."""

        ownership_data = (
            ownership.model_dump(mode="python")
            if hasattr(ownership, "model_dump")
            else dict(ownership)
        )
        owner_by_contract = {
            str(item["contract_identity_sha256"]): CapitalSleeve(item["sleeve"])
            for item in ownership_data.get("active_contracts", ())
        }
        historical_owner_by_contract = dict(owner_by_contract)
        historical_owner_by_contract.update(
            {
                str(item["contract_identity_sha256"]): CapitalSleeve(
                    item["sleeve"]
                )
                for item in ownership_data.get("released_contracts", ())
            }
        )
        per_sleeve: dict[CapitalSleeve, dict[str, Any]] = {
            sleeve: {
                "positions": [],
                "open_order_count": 0,
                "execution_ids": set(),
                "fees_usd": Decimal("0"),
            }
            for sleeve in CapitalSleeve
        }

        def owner(
            raw: Mapping[str, Any], *, allow_released: bool = False
        ) -> CapitalSleeve:
            contract_hash = str(raw.get("contract_identity_sha256") or "")
            sleeve = (
                historical_owner_by_contract.get(contract_hash)
                if allow_released
                else owner_by_contract.get(contract_hash)
            )
            if sleeve is None:
                raise SleeveLedgerError("UNATTRIBUTED_ACCOUNT_EVENT")
            return sleeve

        for raw in snapshot.get("positions", ()) or ():
            quantity = normalized_decimal(raw.get("quantity"))
            if quantity == 0:
                continue
            sleeve = owner(raw)
            per_sleeve[sleeve]["positions"].append(
                CarryForwardPosition(
                    contract_identity_sha256=str(
                        raw["contract_identity_sha256"]
                    ),
                    quantity=quantity,
                    multiplier=normalized_decimal(raw.get("multiplier") or "1"),
                    average_cost=normalized_decimal(
                        raw.get("average_cost") or "0"
                    ),
                    mark=normalized_decimal(raw.get("mark") or "0"),
                    market_value_usd=normalized_decimal(
                        raw.get("market_value_usd") or "0"
                    ),
                )
            )
        for raw in snapshot.get("open_orders", ()) or ():
            per_sleeve[owner(raw)]["open_order_count"] += 1
        for raw in snapshot.get("executions", ()) or ():
            sleeve = owner(raw, allow_released=True)
            execution_id = str(raw.get("execution_id_hash") or "")
            if execution_id:
                per_sleeve[sleeve]["execution_ids"].add(execution_id)
            commission = raw.get("commission")
            if commission not in {None, ""}:
                per_sleeve[sleeve]["fees_usd"] += abs(
                    normalized_decimal(commission)
                )

        snapshot_sha256 = sha256_json(dict(snapshot))
        receipts: dict[str, str] = {}
        with self.db.transaction():
            events = self._events()
            for sleeve in CapitalSleeve:
                state = self.project(sleeve)
                if not state.initialized:
                    raise SleeveLedgerError("SLEEVE_NOT_INITIALIZED")
                prior = next(
                    (
                        event
                        for event in reversed(events)
                        if event["sleeve"] == sleeve.value
                        and event["event_type"] == "BROKER_STATE_RECONCILED"
                        and event.get("broker_snapshot_sha256") == snapshot_sha256
                    ),
                    None,
                )
                if prior is not None:
                    receipts[sleeve.value] = str(prior["event_sha256"])
                    continue
                data = per_sleeve[sleeve]
                receipt = self._insert(
                    sleeve=sleeve,
                    currency="USD",
                    event_type="BROKER_STATE_RECONCILED",
                    payload={
                        "broker_snapshot_sha256": snapshot_sha256,
                        "ownership_projection_sha256": str(
                            ownership_data.get("projection_sha256")
                            or sha256_json(ownership_data)
                        ),
                        "positions": [
                            item.model_dump(mode="json")
                            for item in sorted(
                                data["positions"],
                                key=lambda item: item.contract_identity_sha256,
                            )
                        ],
                        "open_order_count": data["open_order_count"],
                        "fill_count": len(data["execution_ids"]),
                        "fees_usd": str(data["fees_usd"]),
                    },
                )
                receipts[sleeve.value] = receipt.event_sha256
        return receipts

    def project(self, sleeve: CapitalSleeve) -> SleeveLedgerState:
        if not isinstance(sleeve, CapitalSleeve):
            sleeve = CapitalSleeve(sleeve)
        events = [
            event
            for event in self._events()
            if CapitalSleeve(event["sleeve"]) is sleeve
        ]
        balances: dict[str, Decimal] = {}
        positions: tuple[CarryForwardPosition, ...] = ()
        allocation = Decimal("0.00")
        open_orders = 0
        fill_count = 0
        fees = Decimal("0.00")
        realized = Decimal("0.00")
        unrealized = Decimal("0.00")
        reserved = Decimal("0.00")
        historical: tuple[str, ...] = ()
        source_hash: str | None = None
        initialized = False
        for event in events:
            event_type = event["event_type"]
            if event_type == "REGULAR_BOOTSTRAP":
                carry = RegularCarryForward.model_validate(event["carry"])
                initialized = True
                allocation = carry.allocation_usd
                balances = {item.currency: item.amount for item in carry.currency_balances}
                positions = carry.positions
                open_orders = carry.open_order_count
                fill_count = carry.fill_count
                fees = carry.fees_usd
                realized = carry.realized_pnl_usd
                unrealized = carry.unrealized_pnl_usd
                historical = carry.historical_event_sha256
                source_hash = carry.source_ledger_sha256
            elif event_type in {"EXTENDED_BOOTSTRAP", "CONTINUOUS_BOOTSTRAP"}:
                initialized = True
                allocation = Decimal("500.00")
                balances = {"USD": Decimal("500.00")}
            elif event_type == "CURRENCY_CREDIT":
                currency = str(event["currency"])
                balances[currency] = balances.get(currency, Decimal("0")) + normalized_decimal(event["amount"])
            elif event_type == "CURRENCY_DEBIT":
                currency = str(event["currency"])
                balances[currency] = balances.get(currency, Decimal("0")) - normalized_decimal(event["amount"])
            elif event_type == "LIABILITY_RESERVED":
                reserved += normalized_decimal(event.get("amount_usd"))
            elif event_type == "LIABILITY_RELEASED":
                reserved -= normalized_decimal(event.get("amount_usd"))
            elif event_type == "FEE_CHARGED":
                fees += normalized_decimal(event.get("amount_usd"))
            elif event_type == "REALIZED_PNL":
                realized += normalized_decimal(event.get("amount_usd"))
            elif event_type == "UNREALIZED_PNL_SET":
                unrealized = normalized_decimal(event.get("amount_usd"))
            elif event_type == "ORDER_OPENED":
                open_orders += 1
            elif event_type == "ORDER_CLOSED":
                open_orders = max(0, open_orders - 1)
            elif event_type == "FILL_RECORDED":
                fill_count += 1
            elif event_type == "BROKER_STATE_RECONCILED":
                positions = tuple(
                    CarryForwardPosition.model_validate(item)
                    for item in event.get("positions", ())
                )
                open_orders = int(event.get("open_order_count") or 0)
                fill_count = int(event.get("fill_count") or 0)
                fees = normalized_decimal(event.get("fees_usd") or "0")

        currency_balances = tuple(
            CurrencyBalance(currency=currency, amount=normalized_money(amount))
            for currency, amount in balances.items()
        )
        return SleeveLedgerState(
            sleeve=sleeve,
            initialized=initialized,
            allocation_usd=normalized_money(allocation),
            currency_balances=currency_balances,
            positions=positions,
            open_order_count=open_orders,
            fill_count=fill_count,
            fees_usd=normalized_decimal(fees),
            realized_pnl_usd=normalized_decimal(realized),
            unrealized_pnl_usd=normalized_decimal(unrealized),
            reserved_liability_usd=normalized_money(reserved),
            historical_event_sha256=historical,
            source_ledger_sha256=source_hash,
            event_count=len(events),
        )

    def project_all(self) -> MultiSleeveLedgerState:
        regular = self.project(CapitalSleeve.REGULAR_SLEEVE)
        extended = self.project(CapitalSleeve.EXTENDED_SLEEVE)
        aggregate: dict[str, Decimal] = {}
        for state in (regular, extended):
            for balance in state.currency_balances:
                aggregate[balance.currency] = (
                    aggregate.get(balance.currency, Decimal("0")) + balance.amount
                )
        return MultiSleeveLedgerState(
            regular=regular,
            extended=extended,
            aggregate_currency_balances=tuple(
                CurrencyBalance(currency=currency, amount=normalized_money(amount))
                for currency, amount in sorted(aggregate.items())
            ),
        )
