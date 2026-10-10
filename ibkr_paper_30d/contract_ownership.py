"""Exclusive sleeve ownership for canonical IBKR contract identities."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from .canonical import canonical_bytes, sha256_json
from .multi_universe_models import (
    CapitalSleeve,
    CanonicalBagLeg,
    CanonicalContractIdentity,
    ContractOwnershipGroup,
    SHA256_PATTERN,
)
from .multi_universe_schema import verify_multi_universe_schema_v4
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7


LINEAGE_EVENTS = frozenset(
    {
        "OPTION_EXERCISE",
        "OPTION_ASSIGNMENT",
        "EXPIRATION_SETTLEMENT",
        "FUTURES_SETTLEMENT",
        "SPLIT",
        "MERGER",
        "SPIN_OFF",
        "CONTRACT_REPLACEMENT",
        "BROKER_CORRECTION",
        "BAG_LEG_MATERIALIZATION",
        "SETTLEMENT",
    }
)


class OwnershipError(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class _OwnershipModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @property
    def sha256(self) -> str:
        return sha256_json(self)


class ReleaseEvidence(_OwnershipModel):
    position_quantity: Decimal
    open_order_count: int = Field(ge=0)
    pending_execution_count: int = Field(ge=0)
    child_position_count: int = Field(ge=0)
    fill_ambiguity: bool
    broker_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_broker_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    broker_snapshot_fresh: bool


class BrokerLineageEvidence(_OwnershipModel):
    source_contract_sha256: str = Field(pattern=SHA256_PATTERN)
    descendant_contract_sha256: str = Field(pattern=SHA256_PATTERN)
    lineage_event: str = Field(min_length=1)
    broker_event_id: str = Field(min_length=1)
    broker_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    observed_at_utc: datetime

    def model_post_init(self, __context: Any) -> None:
        if self.lineage_event not in LINEAGE_EVENTS:
            raise ValueError("unsupported broker lineage event")
        if (
            self.observed_at_utc.tzinfo is None
            or self.observed_at_utc.utcoffset() is None
        ):
            raise ValueError("lineage observation must be timezone-aware")


class OwnershipReceipt(_OwnershipModel):
    status: str
    reason_codes: tuple[str, ...] = ()
    sleeve: CapitalSleeve | None = None
    group_id: str | None = None
    contract_identity_sha256: str | None = None
    member_contract_sha256: tuple[str, ...] = ()
    event_id: str | None = None
    event_sha256: str | None = None
    idempotent: bool = False


class OwnershipRecord(_OwnershipModel):
    contract_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    contract: CanonicalContractIdentity
    sleeve: CapitalSleeve
    group_id: str
    group_sha256: str | None = None
    side: str | None = None
    source_contract_sha256: str | None = None
    lineage_event: str | None = None


class OwnershipProjection(_OwnershipModel):
    active_contracts: tuple[OwnershipRecord, ...]
    released_contracts: tuple[OwnershipRecord, ...] = ()
    event_count: int
    projection_sha256: str

    def owner_of(self, contract_identity_sha256: str) -> OwnershipRecord | None:
        return next(
            (
                item
                for item in self.active_contracts
                if item.contract_identity_sha256 == contract_identity_sha256
            ),
            None,
        )


def _value(source: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in source:
            return source[name]
    return default


def canonical_contract_identity(
    contract: Mapping[str, Any],
    legs: Sequence[Mapping[str, Any]] = (),
) -> CanonicalContractIdentity:
    raw_legs = legs or tuple(_value(contract, "comboLegs", "bag_legs", default=()) or ())
    canonical_legs = tuple(
        CanonicalBagLeg(
            con_id=int(_value(leg, "conId", "con_id", default=0) or 0),
            ratio=int(_value(leg, "ratio", default=0) or 0),
            action=str(_value(leg, "action", default="") or "").upper(),
            exchange=str(_value(leg, "exchange", default="") or ""),
        )
        for leg in raw_legs
    )
    multiplier = _value(contract, "multiplier")
    return CanonicalContractIdentity(
        con_id=int(_value(contract, "conId", "con_id", default=0) or 0),
        security_type=str(_value(contract, "secType", "security_type", default="") or ""),
        currency=str(_value(contract, "currency", default="") or ""),
        exchange=str(_value(contract, "exchange", default="") or ""),
        primary_exchange=_value(contract, "primaryExchange", "primary_exchange"),
        local_symbol=_value(contract, "localSymbol", "local_symbol"),
        trading_class=_value(contract, "tradingClass", "trading_class"),
        multiplier=(None if multiplier in (None, "") else Decimal(str(multiplier))),
        bag_legs=canonical_legs,
    )


class ContractOwnershipStore:
    SCHEMA = "CONTRACT_OWNERSHIP_EVENT_V1"

    def __init__(self, db: Database):
        verify_multi_universe_schema_v4(db)
        self.db = db

    def _events(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT event_id,ownership_group_id,contract_identity_sha256,sleeve,"
            "event_type,payload_json,payload_sha256,previous_event_sha256,"
            "event_sha256,created_at_utc FROM contract_ownership_events "
            "ORDER BY sequence"
        ).fetchall()
        events: list[dict[str, Any]] = []
        previous: str | None = None
        for row in rows:
            payload = json.loads(str(row[5]))
            if payload.get("schema") != self.SCHEMA:
                raise OwnershipError("OWNERSHIP_EVENT_SCHEMA_INVALID")
            if sha256_json(payload) != str(row[6]):
                raise OwnershipError("OWNERSHIP_PAYLOAD_HASH_MISMATCH")
            stored_previous = str(row[7]) if row[7] is not None else None
            if stored_previous != previous:
                raise OwnershipError("OWNERSHIP_CHAIN_MISMATCH")
            expected = sha256_json(
                {"previous_event_sha256": previous, "payload": payload}
            )
            if expected != str(row[8]):
                raise OwnershipError("OWNERSHIP_EVENT_HASH_MISMATCH")
            events.append(
                {
                    **payload,
                    "event_id": str(row[0]),
                    "group_id": str(row[1]),
                    "contract_identity_sha256": str(row[2]),
                    "sleeve": str(row[3]),
                    "event_type": str(row[4]),
                    "event_sha256": str(row[8]),
                }
            )
            previous = str(row[8])
        return events

    def _append(
        self,
        *,
        group_id: str,
        contract: CanonicalContractIdentity,
        sleeve: CapitalSleeve,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> OwnershipReceipt:
        body = {
            "schema": self.SCHEMA,
            "group_id": group_id,
            "contract_identity_sha256": contract.sha256,
            "sleeve": sleeve.value,
            "event_type": event_type,
            "contract": contract.model_dump(mode="json"),
            **dict(payload),
        }
        last = self.db.execute(
            "SELECT event_sha256 FROM contract_ownership_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous = str(last[0]) if last is not None else None
        event_sha256 = sha256_json(
            {"previous_event_sha256": previous, "payload": body}
        )
        event_id = str(new_uuid7())
        self.db.execute(
            "INSERT INTO contract_ownership_events("
            "event_id,ownership_group_id,contract_identity_sha256,sleeve,"
            "event_type,payload_json,payload_sha256,previous_event_sha256,"
            "event_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                group_id,
                contract.sha256,
                sleeve.value,
                event_type,
                canonical_bytes(body).decode("utf-8"),
                sha256_json(body),
                previous,
                event_sha256,
                utc_now(),
            ),
        )
        return OwnershipReceipt(
            status=event_type,
            sleeve=sleeve,
            group_id=group_id,
            contract_identity_sha256=contract.sha256,
            event_id=event_id,
            event_sha256=event_sha256,
        )

    def projection(self) -> OwnershipProjection:
        active: dict[str, OwnershipRecord] = {}
        released: dict[str, OwnershipRecord] = {}
        events = self._events()
        for event in events:
            identity_hash = event["contract_identity_sha256"]
            if event["event_type"] in {
                "CLAIMED",
                "GROUP_MEMBER_RESERVED",
                "DESCENDANT_CLAIMED",
            }:
                record = OwnershipRecord(
                    contract_identity_sha256=identity_hash,
                    contract=CanonicalContractIdentity.model_validate(event["contract"]),
                    sleeve=CapitalSleeve(event["sleeve"]),
                    group_id=event["group_id"],
                    group_sha256=event.get("group_sha256"),
                    side=event.get("side"),
                    source_contract_sha256=event.get("source_contract_sha256"),
                    lineage_event=event.get("lineage_event"),
                )
                active[identity_hash] = record
                released.pop(identity_hash, None)
            elif event["event_type"] == "RELEASED":
                record = active.pop(identity_hash, None)
                if record is not None:
                    released[identity_hash] = record
        records = tuple(sorted(active.values(), key=lambda item: item.contract_identity_sha256))
        released_records = tuple(
            sorted(released.values(), key=lambda item: item.contract_identity_sha256)
        )
        projection_body = {
            "active_contracts": [item.model_dump(mode="json") for item in records],
            "released_contracts": [
                item.model_dump(mode="json") for item in released_records
            ],
        }
        return OwnershipProjection(
            active_contracts=records,
            released_contracts=released_records,
            event_count=len(events),
            projection_sha256=sha256_json(projection_body),
        )

    def claim(
        self,
        sleeve: CapitalSleeve,
        contract: CanonicalContractIdentity | str,
        *,
        side: str | None = None,
        group_id: str | None = None,
    ) -> OwnershipReceipt:
        if isinstance(contract, str):
            currency = contract.upper()
            if len(currency) != 3 or not currency.isalpha():
                raise OwnershipError("INVALID_CURRENCY_BALANCE")
            return OwnershipReceipt(
                status="NON_EXCLUSIVE_CURRENCY_BALANCE",
                sleeve=sleeve,
                group_id=f"currency:{currency}",
            )
        normalized_side = None if side is None else side.upper()
        if normalized_side not in {None, "BUY", "SELL"}:
            raise OwnershipError("INVALID_OWNERSHIP_SIDE")
        with self.db.transaction():
            existing = self.projection().owner_of(contract.sha256)
            if existing is not None:
                if existing.sleeve is not sleeve:
                    raise OwnershipError("CONTRACT_OWNED_BY_OTHER_SLEEVE")
                return OwnershipReceipt(
                    status="CLAIMED",
                    sleeve=sleeve,
                    group_id=existing.group_id,
                    contract_identity_sha256=contract.sha256,
                    idempotent=True,
                )
            receipt = self._append(
                group_id=group_id or f"contract:{contract.sha256}",
                contract=contract,
                sleeve=sleeve,
                event_type="CLAIMED",
                payload={"side": normalized_side},
            )
        return receipt

    def claim_in_transaction(
        self,
        sleeve: CapitalSleeve,
        contract: CanonicalContractIdentity,
        *,
        side: str | None = None,
        group_id: str | None = None,
    ) -> OwnershipReceipt:
        """Claim a canonical contract without opening a nested transaction."""

        if not self.db.connection.in_transaction:
            raise OwnershipError("ATOMIC_OWNERSHIP_TRANSACTION_REQUIRED")
        normalized_side = None if side is None else side.upper()
        if normalized_side not in {None, "BUY", "SELL"}:
            raise OwnershipError("INVALID_OWNERSHIP_SIDE")
        existing = self.projection().owner_of(contract.sha256)
        if existing is not None:
            if existing.sleeve is not sleeve:
                raise OwnershipError("CONTRACT_OWNED_BY_OTHER_SLEEVE")
            return OwnershipReceipt(
                status="CLAIMED",
                sleeve=sleeve,
                group_id=existing.group_id,
                contract_identity_sha256=contract.sha256,
                idempotent=True,
            )
        return self._append(
            group_id=group_id or f"contract:{contract.sha256}",
            contract=contract,
            sleeve=sleeve,
            event_type="CLAIMED",
            payload={"side": normalized_side},
        )

    def reserve_group(self, group: ContractOwnershipGroup) -> OwnershipReceipt:
        with self.db.transaction():
            return self.reserve_group_in_transaction(group)

    def reserve_group_in_transaction(
        self, group: ContractOwnershipGroup
    ) -> OwnershipReceipt:
        """Reserve one parent/leg ownership group in the caller's transaction."""

        if not self.db.connection.in_transaction:
            raise OwnershipError("ATOMIC_OWNERSHIP_TRANSACTION_REQUIRED")
        members = (*group.member_contracts, *group.contingent_contracts)
        projection = self.projection()
        existing = [projection.owner_of(member.sha256) for member in members]
        if any(
            record is not None and record.sleeve is not group.sleeve
            for record in existing
        ):
            raise OwnershipError("CONTRACT_OWNED_BY_OTHER_SLEEVE")
        if all(
            record is not None
            and record.group_id == group.group_id
            and record.group_sha256 == group.sha256
            for record in existing
        ):
            return OwnershipReceipt(
                status="GROUP_RESERVED",
                sleeve=group.sleeve,
                group_id=group.group_id,
                member_contract_sha256=tuple(member.sha256 for member in members),
                idempotent=True,
            )
        if any(record is not None for record in existing):
            raise OwnershipError("CONTRACT_GROUP_CONFLICT")
        last: OwnershipReceipt | None = None
        for member in members:
            last = self._append(
                group_id=group.group_id,
                contract=member,
                sleeve=group.sleeve,
                event_type="GROUP_MEMBER_RESERVED",
                payload={"group_sha256": group.sha256},
            )
        assert last is not None
        return OwnershipReceipt(
            status="GROUP_RESERVED",
            sleeve=group.sleeve,
            group_id=group.group_id,
            member_contract_sha256=tuple(member.sha256 for member in members),
            event_id=last.event_id,
            event_sha256=last.event_sha256,
        )

    def record_descendant(
        self,
        *,
        descendant: CanonicalContractIdentity,
        evidence: BrokerLineageEvidence,
    ) -> OwnershipReceipt:
        if evidence.descendant_contract_sha256 != descendant.sha256:
            return OwnershipReceipt(
                status="BLOCK",
                reason_codes=("LINEAGE_EVIDENCE_MISMATCH",),
                contract_identity_sha256=descendant.sha256,
            )
        with self.db.transaction():
            projection = self.projection()
            source = projection.owner_of(evidence.source_contract_sha256)
            if source is None:
                return OwnershipReceipt(
                    status="BLOCK",
                    reason_codes=("UNATTRIBUTED_ACCOUNT_EVENT",),
                    contract_identity_sha256=descendant.sha256,
                )
            existing = projection.owner_of(descendant.sha256)
            if existing is not None:
                if existing.sleeve is not source.sleeve:
                    raise OwnershipError("CONTRACT_OWNED_BY_OTHER_SLEEVE")
                return OwnershipReceipt(
                    status="DESCENDANT_CLAIMED",
                    sleeve=source.sleeve,
                    group_id=source.group_id,
                    contract_identity_sha256=descendant.sha256,
                    idempotent=True,
                )
            receipt = self._append(
                group_id=source.group_id,
                contract=descendant,
                sleeve=source.sleeve,
                event_type="DESCENDANT_CLAIMED",
                payload={
                    "source_contract_sha256": evidence.source_contract_sha256,
                    "lineage_event": evidence.lineage_event,
                    "lineage_evidence_sha256": evidence.sha256,
                    "broker_event_id": evidence.broker_event_id,
                    "broker_snapshot_sha256": evidence.broker_snapshot_sha256,
                    "observed_at_utc": evidence.observed_at_utc,
                },
            )
        return receipt

    @staticmethod
    def _release_reasons(evidence: ReleaseEvidence) -> tuple[str, ...]:
        reasons: list[str] = []
        if evidence.position_quantity != 0:
            reasons.append("POSITION_REMAINS")
        if evidence.open_order_count:
            reasons.append("OPEN_ORDER_REMAINS")
        if evidence.pending_execution_count:
            reasons.append("PENDING_EXECUTION_REMAINS")
        if evidence.child_position_count:
            reasons.append("CHILD_POSITION_REMAINS")
        if evidence.fill_ambiguity:
            reasons.append("FILL_STATE_AMBIGUOUS")
        if not evidence.broker_snapshot_fresh:
            reasons.append("BROKER_SNAPSHOT_STALE")
        if evidence.broker_snapshot_sha256 != evidence.expected_broker_snapshot_sha256:
            reasons.append("BROKER_RECONCILIATION_MISMATCH")
        return tuple(reasons)

    def release(
        self,
        contract_identity_sha256: str,
        evidence: ReleaseEvidence,
    ) -> OwnershipReceipt:
        reasons = self._release_reasons(evidence)
        if reasons:
            raise OwnershipError(reasons[0])
        with self.db.transaction():
            return self.release_in_transaction(contract_identity_sha256, evidence)

    def release_in_transaction(
        self,
        contract_identity_sha256: str,
        evidence: ReleaseEvidence,
    ) -> OwnershipReceipt:
        """Release exact terminal ownership inside the caller's transaction."""

        if not self.db.connection.in_transaction:
            raise OwnershipError("ATOMIC_OWNERSHIP_TRANSACTION_REQUIRED")
        reasons = self._release_reasons(evidence)
        if reasons:
            raise OwnershipError(reasons[0])
        projection = self.projection()
        existing = projection.owner_of(contract_identity_sha256)
        if existing is None:
            releases = [
                event
                for event in self._events()
                if event["event_type"] == "RELEASED"
                and event["contract_identity_sha256"] == contract_identity_sha256
            ]
            if (
                not releases
                or releases[-1].get("release_evidence_sha256") != evidence.sha256
            ):
                raise OwnershipError("OWNERSHIP_NOT_ACTIVE")
            latest = releases[-1]
            return OwnershipReceipt(
                status="RELEASED",
                sleeve=CapitalSleeve(latest["sleeve"]),
                group_id=latest["group_id"],
                contract_identity_sha256=contract_identity_sha256,
                event_id=latest["event_id"],
                event_sha256=latest["event_sha256"],
                idempotent=True,
            )
        return self._append(
            group_id=existing.group_id,
            contract=existing.contract,
            sleeve=existing.sleeve,
            event_type="RELEASED",
            payload={"release_evidence_sha256": evidence.sha256},
        )
