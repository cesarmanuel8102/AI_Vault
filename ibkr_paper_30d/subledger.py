from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT)


@dataclass(frozen=True)
class SubledgerEvent:
    event_type: str
    symbol: str = ""
    contract_id: int = 0
    security_type: str = "STK"
    quantity: Decimal = Decimal("0")
    price: Decimal = Decimal("0")
    multiplier: Decimal = Decimal("1")
    amount: Decimal = Decimal("0")


@dataclass(frozen=True)
class BrokerAccountSnapshot:
    cash: Decimal
    settled_cash: Decimal
    buying_power: Decimal
    net_liquidation: Decimal
    market_value: Decimal


@dataclass(frozen=True)
class SubledgerState:
    allocation: Decimal
    cash: Decimal
    settled_cash: Decimal
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    equity: Decimal
    high_water_mark: Decimal
    drawdown: Decimal
    valid: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ReconciliationReceipt:
    status: str
    reason_codes: tuple[str, ...]
    maximum_allocated_capital: Decimal
    broker_buying_power: Decimal


@dataclass
class _Position:
    symbol: str
    contract_id: int
    security_type: str
    quantity: Decimal  # signed: long > 0, short < 0
    average_cost: Decimal
    mark: Decimal
    multiplier: Decimal


class Subledger:
    """
    Virtual experiment ledger.

    STK and premium-based derivative fills use signed quantities, so defined-risk
    option structures can contain both long and short legs without confusing a
    short leg with an invalid sale.  A contract multiplier is part of every
    cash/P&L calculation.

    Futures variation-margin accounting is intentionally not synthesized from
    notional fills here; a FUT fill must be reconciled from authoritative broker
    cash/P&L events before it can be represented as experimental equity.
    """

    def __init__(self, allocation: Decimal):
        if allocation <= 0:
            raise ValueError("allocation must be positive")
        self.allocation = money(allocation)

    @classmethod
    def start(cls, allocation: Decimal = Decimal("500.00")) -> "Subledger":
        return cls(allocation)

    @staticmethod
    def _key(event: SubledgerEvent) -> str:
        return (
            f"conid:{event.contract_id}"
            if int(event.contract_id or 0) > 0
            else f"symbol:{event.symbol.upper()}"
        )

    @staticmethod
    def _valid_fill(event: SubledgerEvent) -> bool:
        return bool(
            event.symbol
            and event.quantity > 0
            and event.price > 0
            and event.multiplier > 0
            and event.quantity.is_finite()
            and event.price.is_finite()
            and event.multiplier.is_finite()
        )

    def project(self, events: list[SubledgerEvent]) -> SubledgerState:
        cash = self.allocation
        settled_cash = self.allocation
        realized = Decimal("0")
        fees = Decimal("0")
        high_water = self.allocation
        positions: dict[str, _Position] = {}
        reasons: list[str] = []

        def totals() -> tuple[Decimal, Decimal, Decimal]:
            market_value = sum(
                (
                    position.quantity
                    * (
                        position.mark - position.average_cost
                        if position.security_type == "FUT"
                        else position.mark
                    )
                    * position.multiplier
                    for position in positions.values()
                ),
                Decimal("0"),
            )
            unrealized = sum(
                (
                    position.quantity
                    * (position.mark - position.average_cost)
                    * position.multiplier
                    for position in positions.values()
                ),
                Decimal("0"),
            )
            equity = cash + market_value
            return money(market_value), money(unrealized), money(equity)

        def apply_fill(event: SubledgerEvent, signed_fill: Decimal) -> None:
            nonlocal cash, settled_cash, realized
            if not self._valid_fill(event):
                reasons.append(
                    "INVALID_BUY_FILL"
                    if signed_fill > 0
                    else "INVALID_SELL_FILL"
                )
                return
            security_type = str(event.security_type or "STK").upper()
            key = self._key(event)
            multiplier = event.multiplier
            if security_type == "FUT":
                # Futures do not exchange the full notional on entry. Equity is
                # marked through variation P&L; realized variation is moved to
                # cash when quantity is closed below.
                cash_delta = Decimal("0")
            else:
                cash_delta = -(signed_fill * event.price * multiplier)
                cash += cash_delta
                settled_cash += cash_delta

            existing = positions.get(key)
            if existing is None:
                positions[key] = _Position(
                    symbol=event.symbol,
                    contract_id=int(event.contract_id or 0),
                    security_type=security_type,
                    quantity=signed_fill,
                    average_cost=event.price,
                    mark=event.price,
                    multiplier=multiplier,
                )
                return

            if existing.multiplier != multiplier:
                reasons.append("CONTRACT_MULTIPLIER_MISMATCH")
                return
            if existing.symbol.upper() != event.symbol.upper():
                reasons.append("CONTRACT_SYMBOL_MISMATCH")
                return

            old_q = existing.quantity
            if old_q == 0 or (old_q > 0) == (signed_fill > 0):
                total_abs = abs(old_q) + abs(signed_fill)
                average = (
                    abs(old_q) * existing.average_cost
                    + abs(signed_fill) * event.price
                ) / total_abs
                existing.quantity = old_q + signed_fill
                existing.average_cost = average
                existing.mark = event.price
                return

            closing = min(abs(old_q), abs(signed_fill))
            # q * (exit - entry) works for long q; reverse for a short.
            if old_q > 0:
                realized_delta = (
                    closing * (event.price - existing.average_cost) * multiplier
                )
            else:
                realized_delta = (
                    closing * (existing.average_cost - event.price) * multiplier
                )
            realized += realized_delta
            if existing.security_type == "FUT":
                cash += realized_delta
                settled_cash += realized_delta

            new_q = old_q + signed_fill
            if new_q == 0:
                del positions[key]
                return
            if (new_q > 0) == (old_q > 0):
                # Partial close: original basis survives.
                existing.quantity = new_q
                existing.mark = event.price
                return

            # Fill crossed through zero and opened a position in the opposite
            # direction. The excess quantity begins at the current fill price.
            existing.quantity = new_q
            existing.average_cost = event.price
            existing.mark = event.price

        for event in events:
            if event.event_type == "BUY_FILL":
                apply_fill(event, abs(event.quantity))
            elif event.event_type == "SELL_FILL":
                apply_fill(event, -abs(event.quantity))
            elif event.event_type == "FEE":
                if event.amount < 0 or not event.amount.is_finite():
                    reasons.append("INVALID_FEE")
                    continue
                fees += event.amount
                cash -= event.amount
                settled_cash -= event.amount
            elif event.event_type == "MARK":
                if event.price <= 0 or not event.price.is_finite():
                    reasons.append("INVALID_MARK")
                    continue
                key = self._key(event)
                existing = positions.get(key)
                if existing is None and int(event.contract_id or 0) <= 0:
                    matches = [
                        item
                        for item in positions.values()
                        if item.symbol.upper() == event.symbol.upper()
                    ]
                    existing = matches[0] if len(matches) == 1 else None
                if existing is None:
                    reasons.append("INVALID_MARK")
                    continue
                existing.mark = event.price
            elif event.event_type == "SETTLED_CASH":
                settled_cash = event.amount
            else:
                reasons.append("UNKNOWN_EVENT_TYPE")

            _, _, event_equity = totals()
            high_water = max(high_water, event_equity)

        market_value, unrealized, equity = totals()
        if cash < 0:
            reasons.append("NEGATIVE_CASH")
        if settled_cash < 0:
            reasons.append("NEGATIVE_SETTLED_CASH")
        unique_reasons = tuple(dict.fromkeys(reasons))
        return SubledgerState(
            allocation=self.allocation,
            cash=money(cash),
            settled_cash=money(settled_cash),
            market_value=market_value,
            realized_pnl=money(realized),
            unrealized_pnl=unrealized,
            fees=money(fees),
            equity=equity,
            high_water_mark=money(high_water),
            drawdown=money(max(high_water - equity, Decimal("0"))),
            valid=not unique_reasons,
            reason_codes=unique_reasons,
        )

    def reconcile(
        self, broker: BrokerAccountSnapshot, projection: SubledgerState
    ) -> ReconciliationReceipt:
        reasons: list[str] = []
        if not projection.valid:
            reasons.append("INVALID_SUBLEDGER")
        if money(broker.market_value) != projection.market_value:
            reasons.append("POSITION_VALUE_MISMATCH")
        if broker.net_liquidation < projection.equity:
            reasons.append("BROKER_EQUITY_BELOW_SUBLEDGER")
        maximum = max(projection.equity, Decimal("0"))
        return ReconciliationReceipt(
            status="PASS" if not reasons else "BLOCK",
            reason_codes=tuple(reasons),
            maximum_allocated_capital=money(maximum),
            broker_buying_power=money(broker.buying_power),
        )
