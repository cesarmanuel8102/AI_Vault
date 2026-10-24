from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

from .canonical import canonical_bytes, sha256_json


class ContractOrderQuarantineError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContractOrderQuarantineObservation:
    status: str
    reason_codes: tuple[str, ...]
    artifact_sha256: str


def _decimal(value: object) -> str:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ContractOrderQuarantineError("QUARANTINED_ORDER_IDENTITY_INVALID") from exc
    if not parsed.is_finite():
        raise ContractOrderQuarantineError("QUARANTINED_ORDER_IDENTITY_INVALID")
    normalized = parsed.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def _contract(order: Mapping[str, Any]) -> Mapping[str, Any]:
    value = order.get("contract")
    return value if isinstance(value, Mapping) else order


def _con_id(value: Mapping[str, Any]) -> int:
    contract = _contract(value)
    return int(
        contract.get(
            "conId",
            contract.get("con_id", contract.get("contract_id", 0)),
        )
        or 0
    )


def _order_identity(order: Mapping[str, Any]) -> dict[str, object]:
    contract = _contract(order)
    return {
        "order_id": int(order.get("orderId", order.get("order_id", 0)) or 0),
        "perm_id": int(order.get("permId", order.get("perm_id", 0)) or 0),
        "client_id": int(order.get("clientId", order.get("client_id", 0)) or 0),
        "order_ref": str(order.get("orderRef", order.get("order_ref", "")) or ""),
        "con_id": _con_id(order),
        "symbol": str(contract.get("symbol", order.get("symbol", "")) or "").upper(),
        "action": str(order.get("action", "") or "").upper(),
        "total_quantity": _decimal(order.get("totalQuantity", order.get("total_quantity", 0))),
        "status": str(order.get("status", "") or ""),
        "filled": _decimal(order.get("filled", 0)),
        "remaining": _decimal(order.get("remaining", 0)),
    }


def _position_quantity(positions: Sequence[Mapping[str, Any]], con_id: int) -> str | None:
    matches = []
    for position in positions:
        if _con_id(position) == con_id:
            matches.append(_decimal(position.get("position", position.get("quantity", 0))))
    if len(matches) > 1:
        raise ContractOrderQuarantineError("QUARANTINED_POSITION_AMBIGUOUS")
    return None if not matches else matches[0]


class ContractOrderQuarantineStore:
    SCHEMA = "CONTRACT_ORDER_QUARANTINE_V1"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _write(self, body: Mapping[str, Any]) -> dict[str, Any]:
        payload = {**dict(body), "artifact_sha256": sha256_json(dict(body))}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(canonical_bytes(payload))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return payload

    def load(self) -> dict[str, Any] | None:
        if not self.path.is_file():
            return None
        try:
            payload = json.loads(self.path.read_bytes())
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractOrderQuarantineError("CONTRACT_ORDER_QUARANTINE_INVALID") from exc
        if not isinstance(payload, dict) or payload.get("schema") != self.SCHEMA:
            raise ContractOrderQuarantineError("CONTRACT_ORDER_QUARANTINE_INVALID")
        claimed = payload.pop("artifact_sha256", None)
        if claimed != sha256_json(payload):
            raise ContractOrderQuarantineError("CONTRACT_ORDER_QUARANTINE_HASH_MISMATCH")
        return {**payload, "artifact_sha256": claimed}

    def activate(
        self, *, account_identity_sha256: str, approved_head: str,
        order: Mapping[str, Any], position_quantity: object,
        authorized_at_utc: datetime,
    ) -> dict[str, Any]:
        identity = _order_identity(order)
        if (
            len(account_identity_sha256) != 64
            or len(approved_head) != 40
            or identity["status"] != "PendingCancel"
            or identity["filled"] != "0"
            or identity["remaining"] != identity["total_quantity"]
            or identity["con_id"] <= 0
            or identity["order_id"] <= 0
            or identity["perm_id"] <= 0
            or identity["client_id"] <= 0
            or not identity["order_ref"]
        ):
            raise ContractOrderQuarantineError("QUARANTINED_ORDER_IDENTITY_INVALID")
        quantity = _decimal(position_quantity)
        if quantity != identity["remaining"]:
            raise ContractOrderQuarantineError("QUARANTINED_POSITION_CHANGED")
        body = {
            "schema": self.SCHEMA,
            "state": "ACTIVE",
            "account_identity_sha256": account_identity_sha256,
            "approved_head": approved_head.lower(),
            "order": identity,
            "position_quantity": quantity,
            "authorized_at_utc": authorized_at_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "absent_observation_count": 0,
            "last_observed_at_utc": None,
        }
        return self._write(body)

    def artifact_sha256(self) -> str | None:
        payload = self.load()
        if payload is None or payload.get("state") == "RELEASED":
            return None
        return str(payload["artifact_sha256"])

    def write_reasons(self, context: Mapping[str, Any] | None) -> tuple[str, ...]:
        payload = self.load()
        if payload is None or payload.get("state") == "RELEASED":
            return ()
        if str((context or {}).get("order_ref") or "") == str(payload["order"]["order_ref"]):
            return ("QUARANTINED_CONTRACT_WRITE_BLOCKED",)
        contract = (context or {}).get("canonical_contract") or {}
        if not isinstance(contract, Mapping):
            return ("QUARANTINE_WRITE_CONTRACT_IDENTITY_REQUIRED",)
        con_id = int(contract.get("con_id", contract.get("conId", 0)) or 0)
        if con_id == int(payload["order"]["con_id"]):
            return ("QUARANTINED_CONTRACT_WRITE_BLOCKED",)
        return ()

    def verify_recovery_evidence(
        self, open_orders: Sequence[Mapping[str, Any]], positions: Sequence[Mapping[str, Any]]
    ) -> str:
        payload = self.load()
        if payload is None or payload.get("state") == "RELEASED":
            raise ContractOrderQuarantineError("ACTIVE_CONTRACT_ORDER_QUARANTINE_REQUIRED")
        expected = payload["order"]
        same_contract = [
            item for item in open_orders
            if _con_id(item) == int(expected["con_id"])
        ]
        if len(open_orders) != 1 or len(same_contract) != 1:
            raise ContractOrderQuarantineError("UNEXPECTED_QUARANTINED_CONTRACT_ORDER")
        if _order_identity(same_contract[0]) != expected:
            raise ContractOrderQuarantineError("QUARANTINED_ORDER_STATE_CHANGED")
        if _position_quantity(positions, int(expected["con_id"])) != payload["position_quantity"]:
            raise ContractOrderQuarantineError("QUARANTINED_POSITION_CHANGED")
        return str(payload["artifact_sha256"])

    def observe(
        self, *, open_orders: Sequence[Mapping[str, Any]],
        positions: Sequence[Mapping[str, Any]], observed_at_utc: datetime,
    ) -> ContractOrderQuarantineObservation:
        payload = self.load()
        if payload is None:
            return ContractOrderQuarantineObservation("INACTIVE", (), "")
        if payload.get("state") == "RELEASED":
            return ContractOrderQuarantineObservation("RELEASED", (), str(payload["artifact_sha256"]))
        expected = payload["order"]
        con_id = int(expected["con_id"])
        same_contract = [
            item for item in open_orders
            if _con_id(item) == con_id
        ]
        if len(same_contract) > 1:
            raise ContractOrderQuarantineError("UNEXPECTED_QUARANTINED_CONTRACT_ORDER")
        position = _position_quantity(positions, con_id)
        if position != payload["position_quantity"]:
            raise ContractOrderQuarantineError("QUARANTINED_POSITION_CHANGED")
        timestamp = observed_at_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if same_contract:
            if _order_identity(same_contract[0]) != expected:
                raise ContractOrderQuarantineError("QUARANTINED_ORDER_STATE_CHANGED")
            body = {key: value for key, value in payload.items() if key != "artifact_sha256"}
            body.update(absent_observation_count=0, last_observed_at_utc=timestamp)
            written = self._write(body)
            return ContractOrderQuarantineObservation(
                "ACTIVE", ("ORDER_CONTRACT_QUARANTINED",), str(written["artifact_sha256"])
            )
        previous = payload.get("last_observed_at_utc")
        count = int(payload.get("absent_observation_count", 0))
        if previous != timestamp:
            count += 1
        state = "RELEASED" if count >= 2 else "RELEASE_PENDING"
        body = {key: value for key, value in payload.items() if key != "artifact_sha256"}
        body.update(state=state, absent_observation_count=count, last_observed_at_utc=timestamp)
        written = self._write(body)
        reasons = ("QUARANTINED_ORDER_RELEASED",) if state == "RELEASED" else ("QUARANTINED_ORDER_RELEASE_PENDING",)
        return ContractOrderQuarantineObservation(state, reasons, str(written["artifact_sha256"]))
