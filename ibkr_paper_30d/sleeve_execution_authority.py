"""Fail-closed V4 sleeve authority and atomic execution reservation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .canonical import canonical_bytes, sha256_json
from .coordinated_model_executor import ModelExecutionOperation, ModelExecutionRequest
from .multi_universe_models import (
    CapitalSleeve,
    ContractOwnershipGroup,
    GIT_HEAD_PATTERN,
    SHA256_PATTERN,
    TransitionPhase,
)
from .multi_universe_schema import verify_multi_universe_schema_v4
from .contract_ownership import (
    ContractOwnershipStore,
    OwnershipError,
    ReleaseEvidence,
)
from .multi_universe_models import CanonicalContractIdentity
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7
from .sleeve_ledger import SleeveLedgerStore


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
    writer_binding_sha256: str = Field(pattern=SHA256_PATTERN)
    epoch_id: str = Field(min_length=1)
    approved_head: str = Field(pattern=GIT_HEAD_PATTERN)
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    transition_phase: str = Field(min_length=1)
    supervision_bound: bool
    inherited_position: bool
    entry_authority: Literal["FROZEN", "CANARY_ONLY", "ACTIVE"]
    instrument_management_tradable: bool
    reconciliation_fresh: bool
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
        return SleeveExecutionAuthorityValidator.validate_operation(
            request, broker_evidence, db_snapshot
        )

    @staticmethod
    def validate_operation(
        request: ModelExecutionRequest,
        broker_evidence: Mapping[str, Any],
        db_snapshot: SleeveAuthoritySnapshot,
    ) -> SleeveExecutionAuthorityReceipt:
        reasons: list[str] = []
        management = request.operation in {
            ModelExecutionOperation.OPEN_ORDER_ACTION,
            ModelExecutionOperation.POSITION_ACTION,
        }
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
        try:
            phase = TransitionPhase(db_snapshot.transition_phase)
            phase_index = tuple(TransitionPhase).index(phase)
        except ValueError:
            phase = None
            phase_index = -1
            reasons.append("SUCCESSOR_NOT_ACTIVE")
        supervision_index = tuple(TransitionPhase).index(
            TransitionPhase.SUPERVISION_BOUND
        )
        phase_supervision_bound = phase_index >= supervision_index
        if db_snapshot.supervision_bound != phase_supervision_bound:
            reasons.append("SUPERVISION_AUTHORITY_MISMATCH")
        if management and not phase_supervision_bound:
            reasons.append("SUCCESSOR_NOT_ACTIVE")
        if request.operation is ModelExecutionOperation.NEW_TRADE and (
            phase is not TransitionPhase.ACTIVE
            or db_snapshot.entry_authority != "ACTIVE"
        ):
            reasons.append("SUCCESSOR_NOT_ACTIVE")
        if management and not db_snapshot.instrument_management_tradable:
            reasons.append("INSTRUMENT_NOT_CURRENTLY_MANAGEABLE")
        if (
            management
            and phase is not TransitionPhase.ACTIVE
            and not db_snapshot.inherited_position
        ):
            reasons.append("INHERITED_POSITION_AUTHORITY_REQUIRED")
        if not db_snapshot.paper_only:
            reasons.append("NON_PAPER_AUTHORITY")
        if request.operation is ModelExecutionOperation.NEW_TRADE:
            if not db_snapshot.family_executable:
                reasons.append("PRODUCT_FAMILY_NOT_EXECUTABLE")
            if not db_snapshot.capability_fresh:
                reasons.append("PRODUCT_CAPABILITY_STALE")
        if db_snapshot.ownership_conflict:
            reasons.append("CONTRACT_OWNERSHIP_CONFLICT")
        if db_snapshot.external_capital_offset_detected:
            reasons.append("CROSS_SLEEVE_OR_EXTERNAL_OFFSET_FORBIDDEN")
        if request.operation is ModelExecutionOperation.NEW_TRADE:
            if db_snapshot.unbounded_liability:
                reasons.append("MAXIMUM_LOSS_UNBOUNDED")
            if not db_snapshot.economic_authorization_valid:
                reasons.append("OWNER_ECONOMIC_RISK_AUTHORIZATION_INVALID")

        broker_account = str(broker_evidence.get("account_identity_sha256") or "")
        if broker_evidence.get("possible_live_connection") is not False:
            reasons.append("POSSIBLE_LIVE_CONNECTION")
        if broker_evidence.get("paper_only") is not True:
            reasons.append("BROKER_NOT_PAPER")
        if broker_evidence.get("fresh") is not True:
            reasons.append("BROKER_EVIDENCE_STALE")
        if broker_account != request.account_identity_sha256:
            reasons.append("BROKER_ACCOUNT_MISMATCH")
        if (
            broker_evidence.get("transition_target_sha256")
            != db_snapshot.transition_target_sha256
        ):
            reasons.append("TRANSITION_TARGET_MISMATCH")
        if (
            broker_evidence.get("writer_binding_sha256")
            != db_snapshot.writer_binding_sha256
        ):
            reasons.append("WRITER_BINDING_MISMATCH")
        if (
            broker_evidence.get("reconciliation_status") != "PASS"
            or not db_snapshot.reconciliation_fresh
        ):
            reasons.append("BROKER_RECONCILIATION_STALE")
        if management:
            if (
                broker_evidence.get("owned_contract_sleeve")
                != db_snapshot.capital_sleeve.value
            ):
                reasons.append("CONTRACT_OWNED_BY_OTHER_SLEEVE")
            if broker_evidence.get("management_identity_match") is not True:
                reasons.append("MANAGEMENT_IDENTITY_MISMATCH")

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
        if request.operation is ModelExecutionOperation.NEW_TRADE:
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
            "SELECT event_type,payload_json,payload_sha256,previous_event_sha256,event_sha256 "
            "FROM sleeve_authority_events ORDER BY sequence"
        ).fetchall()
        events: list[dict[str, Any]] = []
        previous: str | None = None
        for event_type, raw, payload_sha, stored_previous, event_sha in rows:
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
            events.append(
                {
                    **payload,
                    "event_type": str(event_type),
                    "event_sha256": str(event_sha),
                }
            )
            previous = str(event_sha)
        return events

    def reserve(
        self,
        request: ModelExecutionRequest,
        broker_evidence: Mapping[str, Any],
        snapshot_reader: Callable[[], SleeveAuthoritySnapshot],
    ) -> SleeveExecutionAuthorityReceipt:
        with self.db.transaction():
            broker_evidence_sha256 = sha256_json(dict(broker_evidence))
            prior = [
                event
                for event in self._events()
                if event.get("execution_key") == request.execution_key
                and event.get("event_type") == "EXECUTION_AUTHORITY_RESERVED"
            ]
            if prior:
                latest = prior[-1]
                exact = (
                    latest.get("request_sha256") == request.sha256
                    and latest.get("broker_evidence_sha256")
                    == broker_evidence_sha256
                )
                if exact:
                    return SleeveExecutionAuthorityReceipt(
                        status="PASS",
                        reason_codes=(),
                        request_sha256=request.sha256,
                        authority_snapshot_sha256=str(
                            latest["authority_snapshot_sha256"]
                        ),
                        broker_evidence_sha256=broker_evidence_sha256,
                        reservation_event_sha256=latest["event_sha256"],
                        idempotent=True,
                    )
                return SleeveExecutionAuthorityReceipt(
                    status="BLOCK",
                    reason_codes=("EXECUTION_RESERVATION_CONFLICT",),
                    request_sha256=request.sha256,
                    authority_snapshot_sha256=str(
                        latest["authority_snapshot_sha256"]
                    ),
                    broker_evidence_sha256=broker_evidence_sha256,
                )
            snapshot = snapshot_reader()
            receipt = SleeveExecutionAuthorityValidator.validate(
                request, broker_evidence, snapshot
            )
            if receipt.status != "PASS":
                return receipt
            ledger = SleeveLedgerStore(self.db)
            ledger_state = ledger.project(snapshot.capital_sleeve)
            if ledger_state.reserved_liability_usd != snapshot.reserved_liability_usd:
                return receipt.model_copy(
                    update={
                        "status": "BLOCK",
                        "reason_codes": ("SLEEVE_LEDGER_RESERVATION_MISMATCH",),
                    }
                )
            if (
                ledger_state.reserved_liability_usd
                + snapshot.proposed_maximum_loss_usd
                > ledger_state.allocation_usd
            ):
                return receipt.model_copy(
                    update={
                        "status": "BLOCK",
                        "reason_codes": ("SLEEVE_AGGREGATE_LIABILITY_EXCEEDED",),
                    }
                )
            raw_contract = broker_evidence.get("canonical_contract")
            try:
                contract = CanonicalContractIdentity.model_validate(raw_contract)
            except Exception:
                return receipt.model_copy(
                    update={
                        "status": "BLOCK",
                        "reason_codes": ("CANONICAL_CONTRACT_EVIDENCE_REQUIRED",),
                    }
                )
            if contract.sha256 != broker_evidence.get("contract_identity_sha256"):
                return receipt.model_copy(
                    update={
                        "status": "BLOCK",
                        "reason_codes": ("CONTRACT_IDENTITY_EVIDENCE_MISMATCH",),
                    }
                )
            ownership = ContractOwnershipStore(self.db)
            if request.operation is ModelExecutionOperation.NEW_TRADE:
                try:
                    if contract.security_type == "BAG":
                        raw_members = broker_evidence.get("ownership_contracts")
                        if not isinstance(raw_members, list):
                            raise OwnershipError(
                                "BAG_OWNERSHIP_EVIDENCE_INCOMPLETE"
                            )
                        members = tuple(
                            CanonicalContractIdentity.model_validate(item)
                            for item in raw_members
                        )
                        member_by_con_id = {
                            item.con_id: item for item in members
                        }
                        required_ids = {
                            contract.con_id,
                            *(leg.con_id for leg in contract.bag_legs),
                        }
                        if (
                            set(member_by_con_id) != required_ids
                            or len(members) != len(required_ids)
                            or member_by_con_id.get(contract.con_id) != contract
                        ):
                            raise OwnershipError(
                                "BAG_OWNERSHIP_EVIDENCE_INCOMPLETE"
                            )
                        ownership.reserve_group_in_transaction(
                            ContractOwnershipGroup(
                                group_id=f"execution:{request.execution_key}",
                                sleeve=snapshot.capital_sleeve,
                                parent_contract=contract,
                                member_contracts=tuple(
                                    member_by_con_id[con_id]
                                    for con_id in sorted(required_ids)
                                ),
                                generation=1,
                            )
                        )
                    else:
                        ownership.claim_in_transaction(
                            snapshot.capital_sleeve,
                            contract,
                            side=str(
                                getattr(request.payload, "action", "") or ""
                            ),
                            group_id=f"execution:{request.execution_key}",
                        )
                except OwnershipError as exc:
                    return receipt.model_copy(
                        update={
                            "status": "BLOCK",
                            "reason_codes": (exc.reason_code,),
                        }
                    )
                ledger.reserve_liability_in_transaction(
                    snapshot.capital_sleeve,
                    amount_usd=snapshot.proposed_maximum_loss_usd,
                    reservation_key=request.execution_key,
                )
            else:
                owner = ownership.projection().owner_of(contract.sha256)
                if owner is None:
                    return receipt.model_copy(
                        update={
                            "status": "BLOCK",
                            "reason_codes": ("CONTRACT_OWNERSHIP_REQUIRED",),
                        }
                    )
                if owner.sleeve is not snapshot.capital_sleeve:
                    return receipt.model_copy(
                        update={
                            "status": "BLOCK",
                            "reason_codes": (
                                "CONTRACT_OWNED_BY_OTHER_SLEEVE",
                            ),
                        }
                    )
            events = self._events()
            previous = events[-1]["event_sha256"] if events else None
            payload = {
                "schema": self.SCHEMA,
                "execution_key": request.execution_key,
                "operation": request.operation.value,
                "order_ref": str(
                    broker_evidence.get("order_ref")
                    or (broker_evidence.get("model_write_context") or {}).get(
                        "order_ref"
                    )
                    or ""
                ),
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

    def _append_terminal_event(
        self,
        *,
        event_type: str,
        reservation: Mapping[str, Any],
        observation_id: str,
        broker_snapshot_sha256: str,
    ) -> str:
        events = self._events()
        previous = events[-1]["event_sha256"] if events else None
        payload = {
            "schema": self.SCHEMA,
            "execution_key": reservation["execution_key"],
            "capital_sleeve": reservation["capital_sleeve"],
            "contract_identity_sha256": reservation[
                "contract_identity_sha256"
            ],
            "reservation_event_sha256": reservation["event_sha256"],
            "observation_id": observation_id,
            "broker_snapshot_sha256": broker_snapshot_sha256,
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
                reservation["capital_sleeve"],
                event_type,
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                previous,
                event_sha,
                utc_now(),
            ),
        )
        return event_sha

    def finalize_terminal_reservations(
        self,
        broker_snapshot: Mapping[str, Any],
        *,
        observation_id: str,
    ) -> dict[str, tuple[str, ...]]:
        """Release flat exposure only after two independent broker observations."""

        if not (
            len(observation_id) == 64
            and all(char in "0123456789abcdef" for char in observation_id)
        ):
            raise ValueError("TERMINAL_OBSERVATION_ID_INVALID")
        if broker_snapshot.get("fresh") is not True:
            raise RuntimeError("BROKER_SNAPSHOT_STALE")
        if broker_snapshot.get("fill_ambiguity") is not False:
            raise RuntimeError("FILL_STATE_AMBIGUOUS")

        def visible_hashes(name: str) -> set[str]:
            result: set[str] = set()
            for raw in broker_snapshot.get(name, ()) or ():
                if not isinstance(raw, Mapping):
                    raise RuntimeError("BROKER_SNAPSHOT_INVALID")
                value = str(raw.get("contract_identity_sha256") or "")
                if len(value) != 64:
                    raise RuntimeError("BROKER_CONTRACT_IDENTITY_REQUIRED")
                if name != "positions" or Decimal(str(raw.get("quantity") or "0")) != 0:
                    result.add(value)
            return result

        visible = visible_hashes("positions") | visible_hashes("open_orders")
        pending = {
            str(value)
            for value in broker_snapshot.get(
                "pending_execution_contract_sha256", ()
            )
        }
        if any(len(value) != 64 for value in pending):
            raise RuntimeError("BROKER_CONTRACT_IDENTITY_REQUIRED")
        broker_snapshot_sha256 = sha256_json(dict(broker_snapshot))
        released: list[str] = []
        awaiting: list[str] = []
        with self.db.transaction():
            events = self._events()
            reservations = [
                event
                for event in events
                if event.get("event_type") == "EXECUTION_AUTHORITY_RESERVED"
                and event.get("operation") == ModelExecutionOperation.NEW_TRADE.value
                and Decimal(str(event.get("reserved_liability_usd") or "0")) > 0
            ]
            ownership = ContractOwnershipStore(self.db)
            ledger = SleeveLedgerStore(self.db)
            projection = ownership.projection()
            all_ownership = (
                *projection.active_contracts,
                *projection.released_contracts,
            )
            ownership_by_contract = {
                item.contract_identity_sha256: item for item in all_ownership
            }
            group_members: dict[str, tuple[str, ...]] = {}
            for item in all_ownership:
                group_members.setdefault(item.group_id, ())
                group_members[item.group_id] = (
                    *group_members[item.group_id],
                    item.contract_identity_sha256,
                )
            active_hashes = {
                item.contract_identity_sha256
                for item in projection.active_contracts
            }
            confirmed: list[tuple[dict[str, Any], str]] = []
            for reservation in reservations:
                key = str(reservation["execution_key"])
                related = [
                    event for event in events if event.get("execution_key") == key
                ]
                if any(
                    event.get("event_type") == "TERMINAL_RESERVATION_RELEASED"
                    for event in related
                ):
                    continue
                contract_sha = str(reservation["contract_identity_sha256"])
                owner = ownership_by_contract.get(contract_sha)
                member_hashes = (
                    group_members.get(owner.group_id, ()) if owner is not None else ()
                )
                group_visible = any(
                    member_sha in visible | pending for member_sha in member_hashes
                )
                terminal = (
                    owner is not None
                    and contract_sha not in visible
                    and contract_sha not in pending
                    and not group_visible
                )
                latest = related[-1]
                if not terminal:
                    if latest.get("event_type") == "TERMINAL_RELEASE_OBSERVED":
                        self._append_terminal_event(
                            event_type="TERMINAL_RELEASE_RESET",
                            reservation=reservation,
                            observation_id=observation_id,
                            broker_snapshot_sha256=broker_snapshot_sha256,
                        )
                    continue
                if latest.get("event_type") != "TERMINAL_RELEASE_OBSERVED":
                    self._append_terminal_event(
                        event_type="TERMINAL_RELEASE_OBSERVED",
                        reservation=reservation,
                        observation_id=observation_id,
                        broker_snapshot_sha256=broker_snapshot_sha256,
                    )
                    awaiting.append(key)
                    continue
                if latest.get("observation_id") == observation_id:
                    awaiting.append(key)
                    continue
                confirmed.append((reservation, owner.group_id))

            evidence = ReleaseEvidence(
                position_quantity=Decimal("0"),
                open_order_count=0,
                pending_execution_count=0,
                child_position_count=0,
                fill_ambiguity=False,
                broker_snapshot_sha256=broker_snapshot_sha256,
                expected_broker_snapshot_sha256=broker_snapshot_sha256,
                broker_snapshot_fresh=True,
            )
            confirmed_groups = {group_id for _, group_id in confirmed}
            for group_id in confirmed_groups:
                for member_sha in group_members.get(group_id, ()):
                    if member_sha not in active_hashes:
                        continue
                    ownership.release_in_transaction(member_sha, evidence)
            for reservation, _group_id in confirmed:
                key = str(reservation["execution_key"])
                ledger.release_liability_in_transaction(
                    CapitalSleeve(str(reservation["capital_sleeve"])),
                    amount_usd=Decimal(
                        str(reservation["reserved_liability_usd"])
                    ),
                    reservation_key=key,
                    broker_snapshot_sha256=broker_snapshot_sha256,
                )
                self._append_terminal_event(
                    event_type="TERMINAL_RESERVATION_RELEASED",
                    reservation=reservation,
                    observation_id=observation_id,
                    broker_snapshot_sha256=broker_snapshot_sha256,
                )
                released.append(key)
        return {
            "released": tuple(released),
            "pending_confirmation": tuple(awaiting),
        }
