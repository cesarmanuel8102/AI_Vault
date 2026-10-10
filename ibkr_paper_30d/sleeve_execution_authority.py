"""Fail-closed V4 sleeve authority and atomic execution reservation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .canonical import canonical_bytes, sha256_json
from .coordinated_model_executor import ModelExecutionOperation, ModelExecutionRequest
from .multi_universe_models import CapitalSleeve, GIT_HEAD_PATTERN, SHA256_PATTERN
from .multi_universe_schema import verify_multi_universe_schema_v4
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7


class _AuthorityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @property
    def sha256(self) -> str:
        return sha256_json(self)


class SleeveAuthoritySnapshot(_AuthorityModel):
    capital_sleeve: CapitalSleeve
    sleeve_authority_sha256: str = Field(pattern=SHA256_PATTERN)
    ownership_projection_sha256: str = Field(pattern=SHA256_PATTERN)
    product_family_sha256: str = Field(pattern=SHA256_PATTERN)
    economic_authorization_sha256: str = Field(pattern=SHA256_PATTERN)
    transition_target_sha256: str = Field(pattern=SHA256_PATTERN)
    epoch_id: str = Field(min_length=1)
    approved_head: str = Field(pattern=GIT_HEAD_PATTERN)
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    transition_phase: str = Field(min_length=1)
    paper_only: bool
    family_executable: bool
    capability_fresh: bool
    ownership_conflict: bool
    external_capital_offset_detected: bool = False
    unbounded_liability: bool = False
    economic_authorization_valid: bool = True
    equity_usd: Decimal
    reserved_liability_usd: Decimal
    proposed_maximum_loss_usd: Decimal
    continuity_required: bool
    continuity_plan_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_economics(self) -> "SleeveAuthoritySnapshot":
        values = (
            self.equity_usd,
            self.reserved_liability_usd,
            self.proposed_maximum_loss_usd,
        )
        if not all(value.is_finite() for value in values):
            raise ValueError("sleeve economics must be finite")
        if self.reserved_liability_usd < 0 or self.proposed_maximum_loss_usd < 0:
            raise ValueError("sleeve liabilities cannot be negative")
        return self


class SleeveExecutionAuthorityReceipt(_AuthorityModel):
    status: str
    reason_codes: tuple[str, ...]
    request_sha256: str
    authority_snapshot_sha256: str
    broker_evidence_sha256: str
    reservation_event_sha256: str | None = None
    idempotent: bool = False


class SleeveExecutionAuthorityValidator:
    @staticmethod
    def validate(
        request: ModelExecutionRequest,
        broker_evidence: Mapping[str, Any],
        db_snapshot: SleeveAuthoritySnapshot,
    ) -> SleeveExecutionAuthorityReceipt:
        reasons: list[str] = []
        if not request.input_bundle.multi_sleeve_v4_active:
            reasons.append("V4_AUTHORITY_REQUIRED")
        if request.capital_sleeve != db_snapshot.capital_sleeve:
            reasons.append("CAPITAL_SLEEVE_MISMATCH")
        if request.sleeve_authority_sha256 != db_snapshot.sleeve_authority_sha256:
            reasons.append("SLEEVE_AUTHORITY_MISMATCH")
        if request.ownership_projection_sha256 != db_snapshot.ownership_projection_sha256:
            reasons.append("OWNERSHIP_PROJECTION_MISMATCH")
        if request.product_family_sha256 != db_snapshot.product_family_sha256:
            reasons.append("PRODUCT_FAMILY_MISMATCH")
        if request.epoch_id != db_snapshot.epoch_id:
            reasons.append("EPOCH_MISMATCH")
        if request.approved_head != db_snapshot.approved_head:
            reasons.append("APPROVED_HEAD_MISMATCH")
        if request.account_identity_sha256 != db_snapshot.account_identity_sha256:
            reasons.append("ACCOUNT_AUTHORITY_MISMATCH")
        if db_snapshot.transition_phase not in {"SUCCESSOR_COMMITTED", "RUNTIME_BOUND", "ACTIVE"}:
            reasons.append("SUCCESSOR_NOT_ACTIVE")
        if not db_snapshot.paper_only:
            reasons.append("NON_PAPER_AUTHORITY")
        if not db_snapshot.family_executable:
            reasons.append("PRODUCT_FAMILY_NOT_EXECUTABLE")
        if not db_snapshot.capability_fresh:
            reasons.append("PRODUCT_CAPABILITY_STALE")
        if db_snapshot.ownership_conflict:
            reasons.append("CONTRACT_OWNERSHIP_CONFLICT")
        if db_snapshot.external_capital_offset_detected:
            reasons.append("CROSS_SLEEVE_OR_EXTERNAL_OFFSET_FORBIDDEN")
        if db_snapshot.unbounded_liability:
            reasons.append("MAXIMUM_LOSS_UNBOUNDED")
        if not db_snapshot.economic_authorization_valid:
            reasons.append("OWNER_ECONOMIC_RISK_AUTHORIZATION_INVALID")

        broker_account = str(broker_evidence.get("account_identity_sha256") or "")
        if broker_evidence.get("paper_only") is not True:
            reasons.append("BROKER_NOT_PAPER")
        if broker_evidence.get("fresh") is not True:
            reasons.append("BROKER_EVIDENCE_STALE")
        if broker_account != request.account_identity_sha256:
            reasons.append("BROKER_ACCOUNT_MISMATCH")

        expected_loss = Decimal("0")
        if request.operation is ModelExecutionOperation.NEW_TRADE:
            try:
                expected_loss = Decimal(str(request.payload.maximum_loss))
            except Exception:
                reasons.append("MAXIMUM_LOSS_UNBOUNDED")
        if not expected_loss.is_finite() or expected_loss < 0:
            reasons.append("MAXIMUM_LOSS_UNBOUNDED")
        if db_snapshot.proposed_maximum_loss_usd != expected_loss:
            reasons.append("PROPOSED_MAXIMUM_LOSS_MISMATCH")
        available = max(
            Decimal("0"),
            db_snapshot.equity_usd - db_snapshot.reserved_liability_usd,
        )
        if db_snapshot.proposed_maximum_loss_usd > available:
            reasons.append("SLEEVE_AVAILABLE_CAPITAL_EXCEEDED")
        if (
            db_snapshot.reserved_liability_usd
            + db_snapshot.proposed_maximum_loss_usd
            > db_snapshot.equity_usd
        ):
            reasons.append("SLEEVE_AGGREGATE_LIABILITY_EXCEEDED")
        if db_snapshot.continuity_required and (
            request.continuity_plan_sha256 is None
            or request.continuity_plan_sha256
            != db_snapshot.continuity_plan_sha256
        ):
            reasons.append("CONTINUITY_PLAN_REQUIRED")

        unique = tuple(dict.fromkeys(reasons))
        return SleeveExecutionAuthorityReceipt(
            status="PASS" if not unique else "BLOCK",
            reason_codes=unique,
            request_sha256=request.sha256,
            authority_snapshot_sha256=db_snapshot.sha256,
            broker_evidence_sha256=sha256_json(dict(broker_evidence)),
        )


class SleeveAuthorityReservationStore:
    SCHEMA = "SLEEVE_EXECUTION_RESERVATION_V1"

    def __init__(self, db: Database):
        verify_multi_universe_schema_v4(db)
        self.db = db

    def _events(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT payload_json,payload_sha256,previous_event_sha256,event_sha256 "
            "FROM sleeve_authority_events ORDER BY sequence"
        ).fetchall()
        events: list[dict[str, Any]] = []
        previous: str | None = None
        for raw, payload_sha, stored_previous, event_sha in rows:
            payload = json.loads(str(raw))
            if sha256_json(payload) != str(payload_sha):
                raise RuntimeError("SLEEVE_AUTHORITY_PAYLOAD_HASH_MISMATCH")
            normalized_previous = (
                None if stored_previous is None else str(stored_previous)
            )
            if normalized_previous != previous:
                raise RuntimeError("SLEEVE_AUTHORITY_CHAIN_MISMATCH")
            if sha256_json(
                {"previous_event_sha256": previous, "payload": payload}
            ) != str(event_sha):
                raise RuntimeError("SLEEVE_AUTHORITY_EVENT_HASH_MISMATCH")
            events.append({**payload, "event_sha256": str(event_sha)})
            previous = str(event_sha)
        return events

    def reserve(
        self,
        request: ModelExecutionRequest,
        broker_evidence: Mapping[str, Any],
        snapshot_reader: Callable[[], SleeveAuthoritySnapshot],
    ) -> SleeveExecutionAuthorityReceipt:
        with self.db.transaction():
            snapshot = snapshot_reader()
            receipt = SleeveExecutionAuthorityValidator.validate(
                request, broker_evidence, snapshot
            )
            if receipt.status != "PASS":
                return receipt
            prior = [
                event
                for event in self._events()
                if event.get("execution_key") == request.execution_key
            ]
            if prior:
                latest = prior[-1]
                exact = (
                    latest.get("request_sha256") == request.sha256
                    and latest.get("authority_snapshot_sha256") == snapshot.sha256
                    and latest.get("broker_evidence_sha256")
                    == receipt.broker_evidence_sha256
                )
                if exact:
                    return receipt.model_copy(
                        update={
                            "reservation_event_sha256": latest["event_sha256"],
                            "idempotent": True,
                        }
                    )
                return receipt.model_copy(
                    update={
                        "status": "BLOCK",
                        "reason_codes": ("EXECUTION_RESERVATION_CONFLICT",),
                    }
                )
            events = self._events()
            previous = events[-1]["event_sha256"] if events else None
            payload = {
                "schema": self.SCHEMA,
                "execution_key": request.execution_key,
                "request_sha256": request.sha256,
                "capital_sleeve": snapshot.capital_sleeve.value,
                "reserved_liability_usd": str(
                    snapshot.proposed_maximum_loss_usd
                ),
                "contract_identity_sha256": broker_evidence.get(
                    "contract_identity_sha256"
                ),
                "sleeve_authority_sha256": snapshot.sleeve_authority_sha256,
                "ownership_projection_sha256": snapshot.ownership_projection_sha256,
                "product_family_sha256": snapshot.product_family_sha256,
                "economic_authorization_sha256": snapshot.economic_authorization_sha256,
                "transition_target_sha256": snapshot.transition_target_sha256,
                "authority_snapshot_sha256": snapshot.sha256,
                "broker_evidence_sha256": receipt.broker_evidence_sha256,
            }
            event_sha = sha256_json(
                {"previous_event_sha256": previous, "payload": payload}
            )
            self.db.execute(
                "INSERT INTO sleeve_authority_events("
                "event_id,sleeve,event_type,payload_json,payload_sha256,"
                "previous_event_sha256,event_sha256,created_at_utc) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(new_uuid7()),
                    snapshot.capital_sleeve.value,
                    "EXECUTION_AUTHORITY_RESERVED",
                    canonical_bytes(payload).decode("utf-8"),
                    sha256_json(payload),
                    previous,
                    event_sha,
                    utc_now(),
                ),
            )
            return receipt.model_copy(
                update={"reservation_event_sha256": event_sha}
            )
