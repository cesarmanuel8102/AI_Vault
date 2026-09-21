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
    average_cost: Decimal
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

    def _events(self) -> tuple[list[dict[str, Any]], list[str]]:
        rows = self.db.execute(
            "SELECT event_type,payload_json,payload_sha256,previous_event_sha256,event_sha256 "
            "FROM autonomous_ledger_events ORDER BY sequence"
        ).fetchall()
        events: list[dict[str, Any]] = []
        reasons: list[str] = []
        previous: str | None = None
        for event_type, payload_json, payload_sha, stored_previous, event_sha in rows:
            try:
                payload = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError):
                reasons.append("LEDGER_EVENT_JSON_INVALID")
                break
            if payload.get("schema") != self.SCHEMA:
                reasons.append("LEDGER_EVENT_SCHEMA_INVALID")
                break
            if sha256_json(payload) != str(payload_sha):
                reasons.append("LEDGER_PAYLOAD_HASH_MISMATCH")
                break
            normalized_previous = str(stored_previous) if stored_previous is not None else None
            if normalized_previous != previous:
                reasons.append("LEDGER_CHAIN_PREDECESSOR_MISMATCH")
                break
            expected_event_sha = sha256_json(
                {"previous_event_sha256": previous, "payload": payload}
            )
            if expected_event_sha != str(event_sha):
                reasons.append("LEDGER_EVENT_HASH_MISMATCH")
                break
            payload["event_type"] = str(event_type)
            events.append(payload)
            previous = str(event_sha)
        return events, reasons

    def append(self, event_type: str, payload: dict[str, Any]) -> str:
        body = {
            "schema": self.SCHEMA,
            "event_type": event_type,
            **payload,
        }
        event_id = str(new_uuid7())
        payload_json = canonical_bytes(body).decode("utf-8")
        payload_sha = sha256_json(body)
        with self.db.transaction() as tx:
            row = tx.execute(
                "SELECT event_sha256 FROM autonomous_ledger_events "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous = str(row[0]) if row is not None else None
            event_sha = sha256_json(
                {"previous_event_sha256": previous, "payload": body}
            )
            tx.execute(
                "INSERT INTO autonomous_ledger_events("
                "event_id,event_type,payload_json,payload_sha256,"
                "previous_event_sha256,event_sha256,created_at_utc"
                ") VALUES(?,?,?,?,?,?,?)",
                (
                    event_id,
                    event_type,
                    payload_json,
                    payload_sha,
                    previous,
                    event_sha,
                    utc_now(),
                ),
            )
        return event_id

    def _recorded_execution_hashes(self) -> set[str]:
        events, _ = self._events()
        return {
            str(event.get("execution_id_hash"))
            for event in events
            if event.get("event_type") == "BROKER_FILL"
            and event.get("execution_id_hash")
        }

    def _effective_commission_for_execution(self, execution_hash: str) -> Decimal | None:
        events, _ = self._events()
        found = False
        total = Decimal("0")
        for event in events:
            if str(event.get("execution_id_hash") or "") != execution_hash:
                continue
            if event.get("event_type") == "BROKER_FILL":
                found = True
                total += max(_d(event.get("commission")), Decimal("0"))
            elif event.get("event_type") == "BROKER_COMMISSION_ADJUSTMENT":
                total += _d(event.get("commission_delta"))
        return total if found else None

    @staticmethod
    def _execution_hash(fill: dict[str, Any]) -> str:
        supplied = str(fill.get("execution_id_hash") or "").strip()
        if supplied:
            return supplied
        contract = fill.get("contract") or {}
        fallback = {
            "schema": "SYNTHETIC_EXECUTION_ID_V1",
            "contract_id": int(contract.get("conId") or fill.get("contract_id") or 0),
            "side": str(fill.get("side") or fill.get("action") or "").upper(),
            "quantity": str(fill.get("quantity") or fill.get("shares") or ""),
            "price": str(fill.get("price") or ""),
            "multiplier": str(contract.get("multiplier") or fill.get("multiplier") or "1"),
            "order_ref": str(fill.get("orderRef") or ""),
            "perm_id": int(fill.get("permId") or 0),
            "order_id": int(fill.get("orderId") or 0),
            "client_id": int(fill.get("clientId") or 0),
            "execution_time": str(fill.get("execution_time") or ""),
            "cum_qty": str(fill.get("cumQty") or ""),
            "avg_price": str(fill.get("avgPrice") or ""),
        }
        return sha256_json(fallback)

    def record_fill(self, fill: dict[str, Any]) -> str:
        execution_hash = self._execution_hash(fill)
        incoming_commission = max(_d(fill.get("commission")), Decimal("0"))
        existing_commission = self._effective_commission_for_execution(execution_hash)
        if existing_commission is not None:
            if incoming_commission != existing_commission:
                delta = incoming_commission - existing_commission
                return self.append(
                    "BROKER_COMMISSION_ADJUSTMENT",
                    {
                        "execution_id_hash": execution_hash,
                        "commission_delta": str(delta),
                        "effective_commission": str(incoming_commission),
                    },
                )
            return f"duplicate:{execution_hash}"
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
        commission = incoming_commission
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
                "execution_id_hash": execution_hash,
                "orderRef": str(fill.get("orderRef") or ""),
                "permId": int(fill.get("permId") or 0),
                "orderId": int(fill.get("orderId") or 0),
                "clientId": int(fill.get("clientId") or 0),
                "execution_time": str(fill.get("execution_time") or ""),
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
                mark = marks.get(contract_id, position.get("average_cost", Decimal("0")))
                market += position["quantity"] * mark * position["multiplier"]
            return cash + market

        events, integrity_reasons = self._events()
        reasons.extend(integrity_reasons)
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
                        "average_cost": price,
                        "last_fill_price": price,
                    },
                )
                if slot["multiplier"] != multiplier:
                    reasons.append("MULTIPLIER_MISMATCH")
                old_quantity = slot["quantity"]
                old_average = slot["average_cost"]
                new_quantity = old_quantity + signed_quantity
                if old_quantity == 0 or old_quantity * signed_quantity > 0:
                    total_units = abs(old_quantity) + abs(signed_quantity)
                    slot["average_cost"] = (
                        (abs(old_quantity) * old_average + abs(signed_quantity) * price)
                        / total_units
                    )
                elif abs(signed_quantity) > abs(old_quantity):
                    # Position crossed through zero. The excess opens a new
                    # position on the opposite side at the current fill price.
                    slot["average_cost"] = price
                # Partial closes preserve the cost basis of the remaining units.
                slot["quantity"] = new_quantity
                slot["last_fill_price"] = price
                marks[contract_id] = price
                if slot["quantity"] == 0:
                    positions.pop(contract_id, None)
                    marks.pop(contract_id, None)
            elif event_type == "BROKER_COMMISSION_ADJUSTMENT":
                delta = _d(event.get("commission_delta"))
                cash -= delta
                fees += delta
                if fees < 0:
                    reasons.append("INVALID_COMMISSION_ADJUSTMENT")
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
            mark = marks.get(contract_id, position["average_cost"])
            value = position["quantity"] * mark * position["multiplier"]
            market_value += value
            position_rows.append(
                ExperimentPosition(
                    contract_id=contract_id,
                    symbol=position["symbol"],
                    sec_type=position["sec_type"],
                    multiplier=position["multiplier"],
                    quantity=position["quantity"],
                    average_cost=_money(position["average_cost"]),
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
