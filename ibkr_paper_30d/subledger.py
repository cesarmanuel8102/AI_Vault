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
    quantity: Decimal = Decimal("0")
    price: Decimal = Decimal("0")
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
    quantity: Decimal
    average_cost: Decimal
    mark: Decimal


class Subledger:
    def __init__(self, allocation: Decimal):
        if allocation <= 0:
            raise ValueError("allocation must be positive")
        self.allocation = money(allocation)

    @classmethod
    def start(cls, allocation: Decimal = Decimal("500.00")) -> "Subledger":
        return cls(allocation)

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
                (position.quantity * position.mark for position in positions.values()),
                Decimal("0"),
            )
            unrealized = sum(
                (
                    position.quantity
                    * (position.mark - position.average_cost)
                    for position in positions.values()
                ),
                Decimal("0"),
            )
            equity = cash + market_value
            return money(market_value), money(unrealized), money(equity)

        for event in events:
            if event.event_type == "BUY_FILL":
                if event.quantity <= 0 or event.price <= 0 or not event.symbol:
                    reasons.append("INVALID_BUY_FILL")
                    continue
                cost = event.quantity * event.price
                existing = positions.get(event.symbol)
                if existing is None:
                    positions[event.symbol] = _Position(
                        event.quantity, event.price, event.price
                    )
                else:
                    total_quantity = existing.quantity + event.quantity
                    average = (
                        existing.quantity * existing.average_cost + cost
                    ) / total_quantity
                    positions[event.symbol] = _Position(
                        total_quantity, average, existing.mark
                    )
                cash -= cost
                settled_cash -= cost
            elif event.event_type == "SELL_FILL":
                existing = positions.get(event.symbol)
                if (
                    existing is None
                    or event.quantity <= 0
                    or event.quantity > existing.quantity
                    or event.price <= 0
                ):
                    reasons.append("INVALID_SELL_FILL")
                    continue
                proceeds = event.quantity * event.price
                realized += event.quantity * (event.price - existing.average_cost)
                cash += proceeds
                settled_cash += proceeds
                remaining = existing.quantity - event.quantity
                if remaining == 0:
                    del positions[event.symbol]
                else:
                    positions[event.symbol] = _Position(
                        remaining, existing.average_cost, existing.mark
                    )
            elif event.event_type == "FEE":
                if event.amount < 0:
                    reasons.append("INVALID_FEE")
                    continue
                fees += event.amount
                cash -= event.amount
                settled_cash -= event.amount
            elif event.event_type == "MARK":
                existing = positions.get(event.symbol)
                if existing is None or event.price <= 0:
                    reasons.append("INVALID_MARK")
                    continue
                positions[event.symbol] = _Position(
                    existing.quantity, existing.average_cost, event.price
                )
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
