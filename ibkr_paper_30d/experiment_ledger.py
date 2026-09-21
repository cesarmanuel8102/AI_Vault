from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .canonical import canonical_bytes, sha256_json
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7


MONEY = Decimal("0.01")


def _d(value: Any, default: str = "0") -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception:
        return Decimal(default)
    return result if result.is_finite() else Decimal(default)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY)


@dataclass(frozen=True)
class ExperimentPosition:
    contract_id: int
    symbol: str
    sec_type: str
    multiplier: Decimal
    quantity: Decimal
    mark: Decimal
    market_value: Decimal


@dataclass(frozen=True)
class ExperimentLedgerState:
    allocation: Decimal
    cash: Decimal
    market_value: Decimal
    equity: Decimal
    high_water_mark: Decimal
    drawdown: Decimal
    fees: Decimal
    positions: tuple[ExperimentPosition, ...]
    event_count: int
    valid: bool
    reason_codes: tuple[str, ...]


class AutonomousExperimentLedger:
    """Append-only isolated ledger for the Codex paper experiment.

    Cash flow is reconstructed from actual broker fills, contract multipliers
    and commissions. Open positions are marked separately, so the equity used
    by Codex is independent from any unrelated buying power in the IBKR paper
    account.
    """

    SCHEMA = "AUTONOMOUS_EXPERIMENT_LEDGER_EVENT_V1"

    def __init__(self, db: Database, *, allocation: Decimal = Decimal("500.00")):
        if allocation <= 0:
            raise ValueError("allocation must be positive")
        self.db = db
        self.allocation = _money(allocation)

    def _events(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT event_type,payload_json FROM subledger_events ORDER BY sequence"
        ).fetchall()
        events: list[dict[str, Any]] = []
        for event_type, payload_json in rows:
            try:
                payload = json.loads(payload_json)
            except (TypeError, json.JSONDecodeError):
                continue
            if payload.get("schema") != self.SCHEMA:
                continue
            payload["event_type"] = event_type
            events.append(payload)
        return events

    def append(self, event_type: str, payload: dict[str, Any]) -> str:
        body = {
            "schema": self.SCHEMA,
            "event_type": event_type,
            **payload,
        }
        event_id = str(new_uuid7())
        self.db.execute(
            "INSERT INTO subledger_events(event_id,event_type,payload_json,payload_sha256,created_at_utc) "
            "VALUES(?,?,?,?,?)",
            (
                event_id,
                event_type,
                canonical_bytes(body).decode("utf-8"),
                sha256_json(body),
                utc_now(),
            ),
        )
        return event_id

    def record_fill(self, fill: dict[str, Any]) -> str:
        side = str(fill.get("side") or fill.get("action") or "").upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("fill side must be BUY or SELL")
        contract = fill.get("contract") or {}
        contract_id = int(contract.get("conId") or fill.get("contract_id") or 0)
        if contract_id <= 0:
            raise ValueError("fill contract id is required")
        quantity = abs(_d(fill.get("quantity") or fill.get("shares")))
        price = _d(fill.get("price"))
        if quantity <= 0 or price <= 0:
            raise ValueError("fill quantity and price must be positive")
        multiplier = _d(contract.get("multiplier") or fill.get("multiplier") or "1", "1")
        if multiplier <= 0:
            multiplier = Decimal("1")
        commission = max(_d(fill.get("commission")), Decimal("0"))
        return self.append(
            "BROKER_FILL",
            {
                "contract_id": contract_id,
                "symbol": str(contract.get("symbol") or fill.get("symbol") or ""),
                "sec_type": str(contract.get("secType") or fill.get("sec_type") or ""),
                "multiplier": str(multiplier),
                "side": side,
                "quantity": str(quantity),
                "price": str(price),
                "commission": str(commission),
                "execution_id_hash": fill.get("execution_id_hash"),
            },
        )

    def record_mark(
        self,
        *,
        contract_id: int,
        price: Decimal,
        symbol: str = "",
    ) -> str:
        if contract_id <= 0 or price <= 0:
            raise ValueError("valid contract_id and positive mark required")
        return self.append(
            "MARK",
            {
                "contract_id": int(contract_id),
                "symbol": symbol,
                "price": str(price),
            },
        )

    def record_execution_result(self, result: Any) -> list[str]:
        order = getattr(result, "order", None)
        if order is None and isinstance(result, dict):
            order = result.get("order")
        order = order or {}
        ids: list[str] = []
        for fill in order.get("fills", []) or []:
            ids.append(self.record_fill(fill))
        return ids

    def project(self) -> ExperimentLedgerState:
        cash = self.allocation
        fees = Decimal("0")
        positions: dict[int, dict[str, Any]] = {}
        marks: dict[int, Decimal] = {}
        reasons: list[str] = []
        high_water = self.allocation

        def equity_now() -> Decimal:
            market = Decimal("0")
            for contract_id, position in positions.items():
                mark = marks.get(contract_id, position.get("last_fill_price", Decimal("0")))
                market += position["quantity"] * mark * position["multiplier"]
            return cash + market

        events = self._events()
        for event in events:
            event_type = event.get("event_type")
            if event_type == "BROKER_FILL":
                contract_id = int(event.get("contract_id") or 0)
                side = str(event.get("side") or "").upper()
                quantity = _d(event.get("quantity"))
                price = _d(event.get("price"))
                multiplier = _d(event.get("multiplier"), "1")
                commission = max(_d(event.get("commission")), Decimal("0"))
                if (
                    contract_id <= 0
                    or side not in {"BUY", "SELL"}
                    or quantity <= 0
                    or price <= 0
                    or multiplier <= 0
                ):
                    reasons.append("INVALID_BROKER_FILL")
                    continue
                signed_quantity = quantity if side == "BUY" else -quantity
                cash -= signed_quantity * price * multiplier
                cash -= commission
                fees += commission
                slot = positions.setdefault(
                    contract_id,
                    {
                        "symbol": str(event.get("symbol") or ""),
                        "sec_type": str(event.get("sec_type") or ""),
                        "multiplier": multiplier,
                        "quantity": Decimal("0"),
                        "last_fill_price": price,
                    },
                )
                if slot["multiplier"] != multiplier:
                    reasons.append("MULTIPLIER_MISMATCH")
                slot["quantity"] += signed_quantity
                slot["last_fill_price"] = price
                marks[contract_id] = price
                if slot["quantity"] == 0:
                    positions.pop(contract_id, None)
                    marks.pop(contract_id, None)
            elif event_type == "MARK":
                contract_id = int(event.get("contract_id") or 0)
                price = _d(event.get("price"))
                if contract_id <= 0 or price <= 0:
                    reasons.append("INVALID_MARK")
                    continue
                if contract_id in positions:
                    marks[contract_id] = price
            else:
                reasons.append("UNKNOWN_AUTONOMOUS_LEDGER_EVENT")
            high_water = max(high_water, equity_now())

        position_rows: list[ExperimentPosition] = []
        market_value = Decimal("0")
        for contract_id, position in sorted(positions.items()):
            mark = marks.get(contract_id, position["last_fill_price"])
            value = position["quantity"] * mark * position["multiplier"]
            market_value += value
            position_rows.append(
                ExperimentPosition(
                    contract_id=contract_id,
                    symbol=position["symbol"],
                    sec_type=position["sec_type"],
                    multiplier=position["multiplier"],
                    quantity=position["quantity"],
                    mark=mark,
                    market_value=_money(value),
                )
            )
        equity = cash + market_value
        high_water = max(high_water, equity)
        unique_reasons = tuple(dict.fromkeys(reasons))
        return ExperimentLedgerState(
            allocation=self.allocation,
            cash=_money(cash),
            market_value=_money(market_value),
            equity=_money(equity),
            high_water_mark=_money(high_water),
            drawdown=_money(max(high_water - equity, Decimal("0"))),
            fees=_money(fees),
            positions=tuple(position_rows),
            event_count=len(events),
            valid=not unique_reasons,
            reason_codes=unique_reasons,
        )
