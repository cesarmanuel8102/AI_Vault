"""PAPER product-family capability evidence and lifecycle certification."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .canonical import canonical_bytes, sha256_json
from .canary_authority import CanaryLifecycleProjection
from .multi_universe_models import ProductFamilyKey, SHA256_PATTERN
from .multi_universe_schema import verify_multi_universe_schema_v4
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7


CERTIFICATION_SEQUENCE = (
    "CONTRACT_QUALIFIED",
    "PERMISSIONS_VERIFIED",
    "MARKET_DATA_VERIFIED",
    "ORDER_SEMANTICS_VERIFIED",
    "BOUNDED_ECONOMICS_VERIFIED",
    "ORDER_TRANSMIT_VERIFIED",
    "ENTRY_FILL_VERIFIED",
    "POSITION_VISIBLE",
    "MANAGEMENT_OBSERVED",
    "CLOSING_FILL_VERIFIED",
    "FLAT_STATE_VERIFIED",
    "ECONOMICS_RECONCILED",
)


class ProductCapabilityError(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class ProductFamilyCertificationStatus(str, Enum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    ORDER_TRANSMIT_VERIFIED = "ORDER_TRANSMIT_VERIFIED"
    FULL_LIFECYCLE_VERIFIED = "FULL_LIFECYCLE_VERIFIED"
    REVOKED = "REVOKED"


class _CapabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @property
    def sha256(self) -> str:
        return sha256_json(self)


def _utc(value: datetime, field_name: str) -> datetime:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
        or value.utcoffset().total_seconds() != 0
    ):
        raise ValueError(f"{field_name} must use UTC")
    return value


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value, "certification_time")
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc(parsed, "certification_time")


class ProductCapabilityEvidence(_CapabilityModel):
    candidate: dict[str, Any]
    paper_account_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_qualified: bool
    permissions_verified: bool
    market_data_verified: bool
    order_semantics_verified: bool
    quantity_semantics_verified: bool
    bounded_economics_verified: bool
    paper_limitations: tuple[str, ...] = Field(min_length=1)
    observed_at_utc: datetime
    expires_at_utc: datetime

    @model_validator(mode="after")
    def _validate_window(self) -> "ProductCapabilityEvidence":
        _utc(self.observed_at_utc, "observed_at_utc")
        _utc(self.expires_at_utc, "expires_at_utc")
        if self.expires_at_utc <= self.observed_at_utc:
            raise ValueError("capability evidence must expire after observation")
        return self

    @property
    def research_visible(self) -> bool:
        return bool(self.candidate)

    @property
    def execution_ready(self) -> bool:
        return all(
            (
                self.contract_qualified,
                self.permissions_verified,
                self.market_data_verified,
                self.order_semantics_verified,
                self.quantity_semantics_verified,
                self.bounded_economics_verified,
            )
        )


class ProductExecutionCapability(_CapabilityModel):
    family: ProductFamilyKey
    family_sha256: str = Field(pattern=SHA256_PATTERN)
    status: ProductFamilyCertificationStatus
    completed_steps: tuple[str, ...]
    account_sha256: str | None
    adapter_sha256: str | None
    observed_at_utc: datetime | None
    expires_at_utc: datetime | None
    paper_limitations: tuple[str, ...]
    paper_only: bool = True
    executable: bool = False
    revoked_reason: str | None = None


class AvailabilityDecision(_CapabilityModel):
    status: str
    reason_codes: tuple[str, ...]
    eligible_family_sha256: tuple[str, ...] = ()
    reconciliation_enabled: bool
    watchdog_enabled: bool
    position_supervision_enabled: bool
    open_order_supervision_enabled: bool
    extended_entries_enabled: bool
    regular_decisions_enabled: bool
    exits_enabled: bool
    continuity_actions_enabled: bool


class ProductFamilyCertificationStore:
    SCHEMA = "PRODUCT_FAMILY_CERTIFICATION_EVENT_V1"

    def __init__(self, db: Database, *, current_adapter_sha256: str):
        verify_multi_universe_schema_v4(db)
        if len(current_adapter_sha256) != 64:
            raise ValueError("adapter sha256 is required")
        self.db = db
        self.current_adapter_sha256 = current_adapter_sha256

    def _events(self, family: ProductFamilyKey) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT product_family_sha256,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256 FROM "
            "product_family_certification_events ORDER BY sequence"
        ).fetchall()
        events: list[dict[str, Any]] = []
        prior: str | None = None
        for family_sha, event_type, raw, payload_sha, previous, event_sha in rows:
            try:
                payload = json.loads(str(raw))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ProductCapabilityError("CERTIFICATION_JSON_INVALID") from exc
            if payload.get("schema") != self.SCHEMA:
                raise ProductCapabilityError("CERTIFICATION_SCHEMA_INVALID")
            if sha256_json(payload) != str(payload_sha):
                raise ProductCapabilityError("CERTIFICATION_PAYLOAD_HASH_MISMATCH")
            normalized_previous = str(previous) if previous is not None else None
            if normalized_previous != prior:
                raise ProductCapabilityError("CERTIFICATION_CHAIN_MISMATCH")
            if sha256_json(
                {
                    "previous_event_sha256": normalized_previous,
                    "payload": payload,
                }
            ) != str(event_sha):
                raise ProductCapabilityError("CERTIFICATION_EVENT_HASH_MISMATCH")
            if str(family_sha) == family.sha256:
                events.append({**payload, "event_type": str(event_type)})
            prior = str(event_sha)
        return events

    def _append(
        self,
        family: ProductFamilyKey,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> str:
        body = {
            "schema": self.SCHEMA,
            "family": family.model_dump(mode="json"),
            "family_sha256": family.sha256,
            "event_type": event_type,
            **dict(payload),
        }
        row = self.db.execute(
            "SELECT event_sha256 FROM product_family_certification_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous = str(row[0]) if row is not None else None
        event_sha = sha256_json(
            {"previous_event_sha256": previous, "payload": body}
        )
        self.db.execute(
            "INSERT INTO product_family_certification_events("
            "event_id,product_family_sha256,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                str(new_uuid7()),
                family.sha256,
                event_type,
                canonical_bytes(body).decode("utf-8"),
                sha256_json(body),
                previous,
                event_sha,
                utc_now(),
            ),
        )
        return event_sha

    def record_step(
        self,
        family: ProductFamilyKey,
        step: str,
        evidence_sha256: str,
        *,
        account_sha256: str,
        adapter_sha256: str,
        observed_at_utc: datetime,
        expires_at_utc: datetime,
        paper_limitations: tuple[str, ...],
    ) -> str:
        if step in CERTIFICATION_SEQUENCE[6:]:
            raise ProductCapabilityError("AUTHORIZED_CANARY_FINALIZER_REQUIRED")
        return self._record_step(
            family,
            step,
            evidence_sha256,
            account_sha256=account_sha256,
            adapter_sha256=adapter_sha256,
            observed_at_utc=observed_at_utc,
            expires_at_utc=expires_at_utc,
            paper_limitations=paper_limitations,
        )

    def _record_step(
        self,
        family: ProductFamilyKey,
        step: str,
        evidence_sha256: str,
        *,
        account_sha256: str,
        adapter_sha256: str,
        observed_at_utc: datetime,
        expires_at_utc: datetime,
        paper_limitations: tuple[str, ...],
    ) -> str:
        if len(evidence_sha256) != 64 or any(c not in "0123456789abcdef" for c in evidence_sha256):
            raise ProductCapabilityError("INVALID_EVIDENCE_SHA256")
        if not paper_limitations:
            raise ProductCapabilityError("PAPER_LIMITATIONS_REQUIRED")
        _utc(observed_at_utc, "observed_at_utc")
        _utc(expires_at_utc, "expires_at_utc")
        if expires_at_utc <= observed_at_utc:
            raise ProductCapabilityError("INVALID_EVIDENCE_WINDOW")
        with self.db.transaction():
            projection = self.projection(family)
            if projection.status is ProductFamilyCertificationStatus.REVOKED:
                raise ProductCapabilityError("FAMILY_REVOKED")
            completed = list(projection.completed_steps)
            if projection.account_sha256 not in {None, account_sha256}:
                raise ProductCapabilityError("CERTIFICATION_ACCOUNT_DRIFT")
            if projection.adapter_sha256 not in {None, adapter_sha256}:
                raise ProductCapabilityError("CERTIFICATION_ADAPTER_DRIFT")
            if step == "ORDER_TERMINAL_NO_FILL":
                if "ORDER_TRANSMIT_VERIFIED" not in completed:
                    raise ProductCapabilityError("CERTIFICATION_STEP_OUT_OF_ORDER")
            elif step in CERTIFICATION_SEQUENCE:
                expected_index = len(completed)
                if step in completed:
                    return projection.sha256
                if expected_index >= len(CERTIFICATION_SEQUENCE) or CERTIFICATION_SEQUENCE[expected_index] != step:
                    raise ProductCapabilityError("CERTIFICATION_STEP_OUT_OF_ORDER")
            else:
                raise ProductCapabilityError("UNKNOWN_CERTIFICATION_STEP")
            return self._append(
                family,
                step,
                {
                    "evidence_sha256": evidence_sha256,
                    "account_sha256": account_sha256,
                    "adapter_sha256": adapter_sha256,
                    "observed_at_utc": observed_at_utc,
                    "expires_at_utc": expires_at_utc,
                    "paper_limitations": list(paper_limitations),
                    "endpoint": "PAPER",
                },
            )

    def record_canary_lifecycle(
        self,
        family: ProductFamilyKey,
        lifecycle: CanaryLifecycleProjection,
        *,
        account_sha256: str,
        adapter_sha256: str,
        observed_at_utc: datetime,
        expires_at_utc: datetime,
        paper_limitations: tuple[str, ...],
    ) -> ProductExecutionCapability:
        if (
            lifecycle.product_family_sha256 != family.sha256
            or lifecycle.account_identity_sha256 != account_sha256
            or lifecycle.status != "PASS"
            or lifecycle.full_lifecycle_verified is not True
            or lifecycle.flat is not True
        ):
            raise ProductCapabilityError("CANARY_FULL_LIFECYCLE_REQUIRED")
        for step in CERTIFICATION_SEQUENCE[6:]:
            self._record_step(
                family,
                step,
                lifecycle.sha256,
                account_sha256=account_sha256,
                adapter_sha256=adapter_sha256,
                observed_at_utc=observed_at_utc,
                expires_at_utc=expires_at_utc,
                paper_limitations=paper_limitations,
            )
        return self.projection(family)

    def revoke(self, family: ProductFamilyKey, *, reason: str) -> str:
        with self.db.transaction():
            return self._append(family, "REVOKED", {"reason": reason})

    def projection(self, family: ProductFamilyKey) -> ProductExecutionCapability:
        events = self._events(family)
        completed: list[str] = []
        latest: dict[str, Any] = {}
        account_hashes: set[str] = set()
        adapter_hashes: set[str] = set()
        observed_values: list[datetime] = []
        expiry_values: list[datetime] = []
        limitations: set[str] = set()
        revoked_reason: str | None = None
        for event in events:
            step = event["event_type"]
            if step in CERTIFICATION_SEQUENCE and step not in completed:
                completed.append(step)
            if step == "REVOKED":
                revoked_reason = str(event.get("reason") or "REVOKED")
            if step != "REVOKED":
                latest = event
                if event.get("account_sha256"):
                    account_hashes.add(str(event["account_sha256"]))
                if event.get("adapter_sha256"):
                    adapter_hashes.add(str(event["adapter_sha256"]))
                observed = _parse_utc(event.get("observed_at_utc"))
                expires = _parse_utc(event.get("expires_at_utc"))
                if observed is not None:
                    observed_values.append(observed)
                if expires is not None:
                    expiry_values.append(expires)
                limitations.update(event.get("paper_limitations") or ())
        if len(account_hashes) > 1:
            raise ProductCapabilityError("CERTIFICATION_ACCOUNT_DRIFT")
        if len(adapter_hashes) > 1:
            raise ProductCapabilityError("CERTIFICATION_ADAPTER_DRIFT")
        if revoked_reason is not None:
            status = ProductFamilyCertificationStatus.REVOKED
        elif tuple(completed) == CERTIFICATION_SEQUENCE:
            status = ProductFamilyCertificationStatus.FULL_LIFECYCLE_VERIFIED
        elif "ORDER_TRANSMIT_VERIFIED" in completed:
            status = ProductFamilyCertificationStatus.ORDER_TRANSMIT_VERIFIED
        else:
            status = ProductFamilyCertificationStatus.RESEARCH_ONLY
        return ProductExecutionCapability(
            family=family,
            family_sha256=family.sha256,
            status=status,
            completed_steps=tuple(completed),
            account_sha256=next(iter(account_hashes), None),
            adapter_sha256=next(iter(adapter_hashes), None),
            observed_at_utc=max(observed_values) if observed_values else None,
            expires_at_utc=min(expiry_values) if expiry_values else None,
            paper_limitations=tuple(sorted(limitations)),
            executable=status is ProductFamilyCertificationStatus.FULL_LIFECYCLE_VERIFIED,
            revoked_reason=revoked_reason,
        )

    def projections(self) -> tuple[ProductExecutionCapability, ...]:
        rows = self.db.execute(
            "SELECT payload_json FROM product_family_certification_events "
            "ORDER BY sequence"
        ).fetchall()
        families: dict[str, ProductFamilyKey] = {}
        for (payload_json,) in rows:
            try:
                payload = json.loads(str(payload_json))
                family = ProductFamilyKey.model_validate(payload.get("family"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            families[family.sha256] = family
        return tuple(
            self.projection(families[key]) for key in sorted(families)
        )

    def assert_executable(
        self,
        family: ProductFamilyKey,
        now_utc: datetime,
        account_sha256: str,
    ) -> ProductExecutionCapability:
        _utc(now_utc, "now_utc")
        result = self.projection(family)
        if result.status is ProductFamilyCertificationStatus.REVOKED:
            raise ProductCapabilityError("FAMILY_REVOKED")
        if result.status is not ProductFamilyCertificationStatus.FULL_LIFECYCLE_VERIFIED:
            reason = (
                "FULL_LIFECYCLE_REQUIRED"
                if result.status is ProductFamilyCertificationStatus.ORDER_TRANSMIT_VERIFIED
                else "FAMILY_NOT_CERTIFIED"
            )
            raise ProductCapabilityError(reason)
        if result.account_sha256 != account_sha256:
            raise ProductCapabilityError("ACCOUNT_MISMATCH")
        if result.adapter_sha256 != self.current_adapter_sha256:
            raise ProductCapabilityError("ADAPTER_MISMATCH")
        if result.expires_at_utc is None or result.expires_at_utc <= now_utc:
            raise ProductCapabilityError("CERTIFICATION_STALE")
        return result.model_copy(update={"executable": True})


class ExtendedAvailabilityGate:
    @staticmethod
    def _available(
        certifications: list[ProductExecutionCapability],
        session_evidence: Mapping[str, Mapping[str, Any]],
        now_utc: datetime,
        *,
        horizon: timedelta | None,
    ) -> tuple[str, ...]:
        eligible: list[str] = []
        for certification in certifications:
            if certification.status is not ProductFamilyCertificationStatus.FULL_LIFECYCLE_VERIFIED:
                continue
            if certification.expires_at_utc is None or certification.expires_at_utc <= now_utc:
                continue
            session = session_evidence.get(certification.family_sha256, {})
            if session.get("authenticated") is not True:
                continue
            if session.get("tradable_now") is True:
                eligible.append(certification.family_sha256)
                continue
            next_open = session.get("next_open_utc")
            if horizon is not None and isinstance(next_open, datetime):
                _utc(next_open, "next_open_utc")
                if now_utc <= next_open <= now_utc + horizon:
                    eligible.append(certification.family_sha256)
        return tuple(sorted(eligible))

    @classmethod
    def evaluate_initial_activation(
        cls,
        certifications: list[ProductExecutionCapability],
        session_evidence: Mapping[str, Mapping[str, Any]],
        now_utc: datetime,
    ) -> AvailabilityDecision:
        eligible = cls._available(
            certifications, session_evidence, now_utc, horizon=timedelta(hours=24)
        )
        passed = bool(eligible)
        return AvailabilityDecision(
            status="PASS" if passed else "BLOCK",
            reason_codes=() if passed else ("NO_EXTENDED_FAMILY_AVAILABLE_WITHIN_24H",),
            eligible_family_sha256=eligible,
            reconciliation_enabled=True,
            watchdog_enabled=True,
            position_supervision_enabled=True,
            open_order_supervision_enabled=True,
            extended_entries_enabled=passed,
            regular_decisions_enabled=True,
            exits_enabled=True,
            continuity_actions_enabled=True,
        )

    @classmethod
    def evaluate_runtime_session(
        cls,
        certifications: list[ProductExecutionCapability],
        session_evidence: Mapping[str, Mapping[str, Any]],
        continuity_state: Mapping[str, Any],
        now_utc: datetime,
    ) -> AvailabilityDecision:
        eligible = cls._available(
            certifications, session_evidence, now_utc, horizon=None
        )
        due = continuity_state.get("exact_continuity_action_due") is True
        status = "CONTINUITY_ACTION_DUE" if due else ("PASS" if eligible else "MARKET_CLOSED_IDLE")
        return AvailabilityDecision(
            status=status,
            reason_codes=(),
            eligible_family_sha256=eligible,
            reconciliation_enabled=True,
            watchdog_enabled=True,
            position_supervision_enabled=True,
            open_order_supervision_enabled=True,
            extended_entries_enabled=bool(eligible),
            regular_decisions_enabled=True,
            exits_enabled=True,
            continuity_actions_enabled=True,
        )
