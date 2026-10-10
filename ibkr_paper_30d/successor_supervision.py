"""Pure planning and atomic binding for inherited Day1 supervision."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .canonical import sha256_json
from .contract_ownership import (
    ContractOwnershipStore,
    OwnershipError,
    canonical_contract_identity,
)
from .multi_universe_models import (
    CapitalSleeve,
    CanonicalContractIdentity,
    ContractOwnershipGroup,
    SHA256_PATTERN,
    TransitionPhase,
    TransitionTarget,
)
from .multi_universe_transition import (
    MultiUniverseTransitionCoordinator,
    MultiUniverseTransitionError,
)
from .persistence import Database
from .sleeve_ledger import (
    CarryForwardPosition,
    CurrencyBalance,
    RegularCarryForward,
    SleeveLedgerError,
    SleeveLedgerStore,
)


class SupervisionBindingError(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class _BindingModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    @property
    def sha256(self) -> str:
        return sha256_json(self)


class InheritedPositionBinding(_BindingModel):
    group_id: str = Field(min_length=1)
    contract: CanonicalContractIdentity
    ownership_members: tuple[CanonicalContractIdentity, ...]
    quantity: Decimal
    multiplier: Decimal = Field(gt=0)
    average_cost: Decimal = Field(ge=0)
    mark: Decimal = Field(ge=0)
    market_value_usd: Decimal
    historical_fill_sha256: tuple[str, ...]
    lineage_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def _validate_members_and_lineage(self) -> "InheritedPositionBinding":
        member_hashes = [item.sha256 for item in self.ownership_members]
        if self.contract.sha256 not in member_hashes:
            raise ValueError("parent contract must be an ownership member")
        if len(member_hashes) != len(set(member_hashes)):
            raise ValueError("duplicate inherited ownership member")
        if len(self.historical_fill_sha256) != len(
            set(self.historical_fill_sha256)
        ):
            raise ValueError("duplicate inherited fill hash")
        if any(not _is_sha256(item) for item in self.historical_fill_sha256):
            raise ValueError("invalid inherited fill hash")
        return self


class SupervisionBindingPlan(_BindingModel):
    transition_id: str = Field(min_length=1)
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    broker_observation_sha256: str = Field(pattern=SHA256_PATTERN)
    day1_projection_sha256: str = Field(pattern=SHA256_PATTERN)
    day1_lineage_sha256: str = Field(pattern=SHA256_PATTERN)
    inherited_position_projection_sha256: str = Field(pattern=SHA256_PATTERN)
    regular_sleeve_authority_sha256: str = Field(pattern=SHA256_PATTERN)
    transition_target_sha256: str = Field(pattern=SHA256_PATTERN)
    execution_lock_generation: int = Field(gt=0)
    writer_binding_sha256: str = Field(pattern=SHA256_PATTERN)
    inherited_positions: tuple[InheritedPositionBinding, ...]
    regular_carry: RegularCarryForward


class SupervisionBindingReceipt(_BindingModel):
    status: Literal["PASS"] = "PASS"
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    broker_observation_sha256: str = Field(pattern=SHA256_PATTERN)
    day1_lineage_sha256: str = Field(pattern=SHA256_PATTERN)
    inherited_position_projection_sha256: str = Field(pattern=SHA256_PATTERN)
    regular_sleeve_authority_sha256: str = Field(pattern=SHA256_PATTERN)
    transition_target_sha256: str = Field(pattern=SHA256_PATTERN)
    execution_lock_generation: int = Field(gt=0)
    writer_binding_sha256: str = Field(pattern=SHA256_PATTERN)
    binding_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    regular_ledger_event_sha256: str = Field(pattern=SHA256_PATTERN)
    continuous_ledger_event_sha256: str = Field(pattern=SHA256_PATTERN)
    ownership_projection_sha256: str = Field(pattern=SHA256_PATTERN)
    transition_event_sha256: str = Field(pattern=SHA256_PATTERN)
    idempotent: bool = False


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _decimal(value: Any, reason: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SupervisionBindingError(reason) from exc
    if not result.is_finite():
        raise SupervisionBindingError(reason)
    return result


def _mapping_rows(source: Mapping[str, Any], name: str) -> tuple[Mapping[str, Any], ...]:
    raw = source.get(name, ()) or ()
    if not isinstance(raw, (list, tuple)) or not all(
        isinstance(item, Mapping) for item in raw
    ):
        raise SupervisionBindingError("SUPERVISION_BINDING_INPUT_INVALID")
    return tuple(raw)


def build_supervision_binding_plan(
    *,
    broker_snapshot: Mapping[str, Any],
    day1_projection: Mapping[str, Any],
    account_identity_sha256: str,
    transition_target_sha256: str,
) -> SupervisionBindingPlan:
    """Build a deterministic plan without touching a database or broker."""

    if not _is_sha256(account_identity_sha256) or not _is_sha256(
        transition_target_sha256
    ):
        raise SupervisionBindingError("SUPERVISION_BINDING_INPUT_INVALID")
    if (
        broker_snapshot.get("account_identity_sha256") != account_identity_sha256
        or day1_projection.get("account_identity_sha256")
        != account_identity_sha256
    ):
        raise SupervisionBindingError("PAPER_ACCOUNT_IDENTITY_MISMATCH")
    if broker_snapshot.get("open_orders"):
        raise SupervisionBindingError("OPEN_ORDER_BLOCKS_SUPERVISION_BINDING")
    if int(day1_projection.get("open_order_count") or 0) != 0:
        raise SupervisionBindingError("OPEN_ORDER_BLOCKS_SUPERVISION_BINDING")
    if broker_snapshot.get("execution_ambiguity") is not False:
        raise SupervisionBindingError("EXECUTION_STATE_AMBIGUOUS")

    writer_binding = str(day1_projection.get("writer_binding_sha256") or "")
    regular_authority = str(
        day1_projection.get("regular_sleeve_authority_sha256") or ""
    )
    day1_lineage = str(day1_projection.get("day1_lineage_sha256") or "")
    if not all(
        _is_sha256(item)
        for item in (writer_binding, regular_authority, day1_lineage)
    ):
        raise SupervisionBindingError("SUPERVISION_BINDING_INPUT_INVALID")
    if broker_snapshot.get("writer_binding_sha256") != writer_binding:
        raise SupervisionBindingError("WRITER_BINDING_MISMATCH")
    try:
        lock_generation = int(day1_projection.get("execution_lock_generation"))
        broker_generation = int(broker_snapshot.get("execution_lock_generation"))
    except (TypeError, ValueError) as exc:
        raise SupervisionBindingError("EXECUTION_LOCK_BINDING_MISMATCH") from exc
    if lock_generation <= 0 or broker_generation != lock_generation:
        raise SupervisionBindingError("EXECUTION_LOCK_BINDING_MISMATCH")

    day1_rows = _mapping_rows(day1_projection, "positions")
    broker_rows = _mapping_rows(broker_snapshot, "positions")
    if day1_lineage != sha256_json(list(day1_rows)):
        raise SupervisionBindingError("INHERITED_LINEAGE_MISMATCH")
    day1_by_contract: dict[str, Mapping[str, Any]] = {}
    for row in day1_rows:
        identity = str(row.get("contract_identity_sha256") or "")
        if not _is_sha256(identity) or identity in day1_by_contract:
            raise SupervisionBindingError("UNATTRIBUTED_POSITION")
        day1_by_contract[identity] = row

    bindings: list[InheritedPositionBinding] = []
    seen_contracts: set[str] = set()
    owned_members: set[str] = set()
    for broker_row in broker_rows:
        raw_contract = broker_row.get("contract")
        if not isinstance(raw_contract, Mapping):
            raise SupervisionBindingError("UNATTRIBUTED_POSITION")
        try:
            contract = canonical_contract_identity(raw_contract)
        except (TypeError, ValueError) as exc:
            raise SupervisionBindingError("UNATTRIBUTED_POSITION") from exc
        if contract.sha256 in seen_contracts:
            raise SupervisionBindingError("UNATTRIBUTED_POSITION")
        seen_contracts.add(contract.sha256)
        day1_row = day1_by_contract.get(contract.sha256)
        if day1_row is None:
            raise SupervisionBindingError("UNATTRIBUTED_POSITION")
        quantity = _decimal(broker_row.get("quantity"), "INHERITED_POSITION_MISMATCH")
        average_cost = _decimal(
            broker_row.get("average_cost"), "INHERITED_POSITION_MISMATCH"
        )
        if (
            quantity != _decimal(
                day1_row.get("quantity"), "INHERITED_POSITION_MISMATCH"
            )
            or average_cost
            != _decimal(
                day1_row.get("average_cost"), "INHERITED_POSITION_MISMATCH"
            )
            or str(broker_row.get("group_id") or "")
            != str(day1_row.get("group_id") or "")
        ):
            raise SupervisionBindingError("INHERITED_POSITION_MISMATCH")
        raw_members = broker_row.get("ownership_members") or (raw_contract,)
        if not isinstance(raw_members, (list, tuple)):
            raise SupervisionBindingError("UNATTRIBUTED_POSITION")
        try:
            members = tuple(canonical_contract_identity(item) for item in raw_members)
        except (TypeError, ValueError) as exc:
            raise SupervisionBindingError("UNATTRIBUTED_POSITION") from exc
        member_hashes = {item.sha256 for item in members}
        if contract.sha256 not in member_hashes or owned_members & member_hashes:
            raise SupervisionBindingError("DUPLICATE_CONTRACT_ACROSS_SLEEVES")
        owned_members.update(member_hashes)
        fills = tuple(str(item) for item in day1_row.get("historical_fill_sha256", ()))
        try:
            binding = InheritedPositionBinding(
                group_id=str(day1_row.get("group_id") or ""),
                contract=contract,
                ownership_members=members,
                quantity=quantity,
                multiplier=_decimal(
                    broker_row.get("multiplier") or "1",
                    "INHERITED_POSITION_MISMATCH",
                ),
                average_cost=average_cost,
                mark=_decimal(broker_row.get("mark") or "0", "INHERITED_POSITION_MISMATCH"),
                market_value_usd=_decimal(
                    broker_row.get("market_value_usd") or "0",
                    "INHERITED_POSITION_MISMATCH",
                ),
                historical_fill_sha256=fills,
                lineage_sha256=str(day1_row.get("lineage_sha256") or ""),
            )
        except ValueError as exc:
            raise SupervisionBindingError("INHERITED_POSITION_MISMATCH") from exc
        bindings.append(binding)
    if seen_contracts != set(day1_by_contract):
        raise SupervisionBindingError("UNATTRIBUTED_POSITION")

    execution_ids = [
        str(item.get("execution_id_hash") or "")
        for item in _mapping_rows(broker_snapshot, "executions")
    ]
    if (
        any(not _is_sha256(item) for item in execution_ids)
        or len(execution_ids) != len(set(execution_ids))
    ):
        raise SupervisionBindingError("EXECUTION_STATE_AMBIGUOUS")
    historical_events = tuple(
        str(item) for item in day1_projection.get("historical_event_sha256", ())
    )
    if (
        int(day1_projection.get("fill_count") or 0) != len(execution_ids)
        or not set(execution_ids) <= set(historical_events)
    ):
        raise SupervisionBindingError("INHERITED_LINEAGE_MISMATCH")
    for field in ("fees_usd", "realized_pnl_usd", "unrealized_pnl_usd"):
        if field in broker_snapshot and _decimal(
            broker_snapshot.get(field), "INHERITED_ECONOMICS_INVALID"
        ) != _decimal(
            day1_projection.get(field), "INHERITED_ECONOMICS_INVALID"
        ):
            raise SupervisionBindingError("INHERITED_ECONOMICS_MISMATCH")

    currency_rows = _mapping_rows(day1_projection, "currency_balances")
    try:
        carry = RegularCarryForward(
            allocation_usd=_decimal(
                day1_projection.get("allocation_usd"),
                "INHERITED_ECONOMICS_INVALID",
            ),
            currency_balances=tuple(
                CurrencyBalance(
                    currency=str(item.get("currency") or ""),
                    amount=_decimal(
                        item.get("amount"), "INHERITED_ECONOMICS_INVALID"
                    ),
                )
                for item in currency_rows
            ),
            positions=tuple(
                CarryForwardPosition(
                    contract_identity_sha256=item.contract.sha256,
                    quantity=item.quantity,
                    multiplier=item.multiplier,
                    average_cost=item.average_cost,
                    mark=item.mark,
                    market_value_usd=item.market_value_usd,
                )
                for item in sorted(bindings, key=lambda item: item.contract.sha256)
            ),
            open_order_count=0,
            fill_count=int(day1_projection.get("fill_count") or 0),
            fees_usd=_decimal(
                day1_projection.get("fees_usd") or "0",
                "INHERITED_ECONOMICS_INVALID",
            ),
            realized_pnl_usd=_decimal(
                day1_projection.get("realized_pnl_usd") or "0",
                "INHERITED_ECONOMICS_INVALID",
            ),
            unrealized_pnl_usd=_decimal(
                day1_projection.get("unrealized_pnl_usd") or "0",
                "INHERITED_ECONOMICS_INVALID",
            ),
            historical_event_sha256=historical_events,
            source_ledger_sha256=str(
                day1_projection.get("source_ledger_sha256") or ""
            ),
        )
    except (TypeError, ValueError) as exc:
        raise SupervisionBindingError("INHERITED_ECONOMICS_INVALID") from exc

    bindings_tuple = tuple(sorted(bindings, key=lambda item: item.contract.sha256))
    return SupervisionBindingPlan(
        transition_id=str(day1_projection.get("transition_id") or ""),
        account_identity_sha256=account_identity_sha256,
        broker_observation_sha256=sha256_json(dict(broker_snapshot)),
        day1_projection_sha256=sha256_json(dict(day1_projection)),
        day1_lineage_sha256=day1_lineage,
        inherited_position_projection_sha256=sha256_json(
            [item.model_dump(mode="json") for item in bindings_tuple]
        ),
        regular_sleeve_authority_sha256=regular_authority,
        transition_target_sha256=transition_target_sha256,
        execution_lock_generation=lock_generation,
        writer_binding_sha256=writer_binding,
        inherited_positions=bindings_tuple,
        regular_carry=carry,
    )


class SuccessorSupervisionBinder:
    def __init__(self, db: Database):
        self.db = db

    def _transition_target(self, plan: SupervisionBindingPlan) -> TransitionTarget:
        row = self.db.execute(
            "SELECT payload_json FROM successor_transition_events "
            "WHERE transition_id=? ORDER BY sequence DESC LIMIT 1",
            (plan.transition_id,),
        ).fetchone()
        if row is None:
            raise SupervisionBindingError("SUCCESSOR_COMMIT_NOT_FOUND")
        try:
            payload = json.loads(str(row[0]))
            target = TransitionTarget.model_validate(payload.get("target"))
        except Exception as exc:
            raise SupervisionBindingError("TRANSITION_PROJECTION_AMBIGUOUS") from exc
        if (
            target.sha256 != plan.transition_target_sha256
            or target.account_identity_sha256 != plan.account_identity_sha256
            or target.regular_sleeve_authority_sha256
            != plan.regular_sleeve_authority_sha256
            or target.writer_binding_sha256 != plan.writer_binding_sha256
        ):
            raise SupervisionBindingError("SUPERVISION_AUTHORITY_MISMATCH")
        return target

    def bind(
        self,
        plan: SupervisionBindingPlan,
        fresh_snapshot: Mapping[str, Any],
    ) -> SupervisionBindingReceipt:
        if sha256_json(dict(fresh_snapshot)) != plan.broker_observation_sha256:
            raise SupervisionBindingError("SUPERVISION_BINDING_STALE")
        target = self._transition_target(plan)
        ledger = SleeveLedgerStore(self.db)
        ownership = ContractOwnershipStore(self.db)
        coordinator = MultiUniverseTransitionCoordinator(self.db)
        try:
            with self.db.transaction():
                target = self._transition_target(plan)
                regular_receipt = ledger.bootstrap_regular_in_transaction(
                    plan.regular_carry
                )
                continuous_receipt = ledger.bootstrap_continuous_in_transaction()
                for inherited in plan.inherited_positions:
                    ownership.reserve_group_in_transaction(
                        ContractOwnershipGroup(
                            group_id=inherited.group_id,
                            sleeve=CapitalSleeve.REGULAR_SLEEVE,
                            parent_contract=inherited.contract,
                            member_contracts=inherited.ownership_members,
                            generation=1,
                        )
                    )
                projection = ownership.projection()
                evidence = {
                    "phase_evidence_sha256": plan.sha256,
                    "reconciliation_status": "PASS",
                    "broker_observation_sha256": plan.broker_observation_sha256,
                    "supervision_binding_plan_sha256": plan.sha256,
                    "day1_lineage_sha256": plan.day1_lineage_sha256,
                    "inherited_position_projection_sha256": (
                        plan.inherited_position_projection_sha256
                    ),
                    "ownership_projection_sha256": projection.projection_sha256,
                    "writer_binding_sha256": plan.writer_binding_sha256,
                    "execution_lock_generation": plan.execution_lock_generation,
                    "regular_ledger_event_sha256": regular_receipt.event_sha256,
                    "continuous_ledger_event_sha256": (
                        continuous_receipt.event_sha256
                    ),
                    "new_entry_authority": False,
                }
                transition = coordinator.advance_in_transaction(
                    target,
                    TransitionPhase.SUPERVISION_BOUND,
                    evidence,
                )
        except SupervisionBindingError:
            raise
        except (OwnershipError, SleeveLedgerError, MultiUniverseTransitionError) as exc:
            raise SupervisionBindingError(str(exc)) from exc
        return SupervisionBindingReceipt(
            account_identity_sha256=plan.account_identity_sha256,
            broker_observation_sha256=plan.broker_observation_sha256,
            day1_lineage_sha256=plan.day1_lineage_sha256,
            inherited_position_projection_sha256=(
                plan.inherited_position_projection_sha256
            ),
            regular_sleeve_authority_sha256=(
                plan.regular_sleeve_authority_sha256
            ),
            transition_target_sha256=plan.transition_target_sha256,
            execution_lock_generation=plan.execution_lock_generation,
            writer_binding_sha256=plan.writer_binding_sha256,
            binding_plan_sha256=plan.sha256,
            regular_ledger_event_sha256=regular_receipt.event_sha256,
            continuous_ledger_event_sha256=continuous_receipt.event_sha256,
            ownership_projection_sha256=projection.projection_sha256,
            transition_event_sha256=transition.phase_event_sha256,
            idempotent=transition.idempotent,
        )
