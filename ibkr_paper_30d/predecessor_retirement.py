"""Pure predecessor launch-surface retirement validation."""

from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

from .canonical import sha256_json
from .multi_universe_models import SHA256_PATTERN


class _RetirementModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def sha256(self) -> str:
        return sha256_json(self)


class PredecessorLaunchPath(_RetirementModel):
    path_id: str = Field(min_length=1)
    kind: Literal[
        "SCHEDULED_TASK",
        "AT_LOGON",
        "SERVICE",
        "STARTUP_ENTRY",
        "DIRECT_INVOCATION",
    ]
    enabled: bool
    can_reach_paper_port: bool
    launch_binding_sha256: str = Field(pattern=SHA256_PATTERN)


class PredecessorLaunchInventory(_RetirementModel):
    predecessor_epoch_id: str = Field(min_length=1)
    complete: bool
    scheduled_tasks: tuple[PredecessorLaunchPath, ...]
    at_logon_triggers: tuple[PredecessorLaunchPath, ...]
    services: tuple[PredecessorLaunchPath, ...]
    startup_entries: tuple[PredecessorLaunchPath, ...]
    managed_direct_invocations: tuple[PredecessorLaunchPath, ...]
    active_launch_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    historical_launch_receipt_sha256: tuple[str, ...] = Field(min_length=1)

    @property
    def paths(self) -> tuple[PredecessorLaunchPath, ...]:
        return (
            self.scheduled_tasks
            + self.at_logon_triggers
            + self.services
            + self.startup_entries
            + self.managed_direct_invocations
        )


class RetirementDecision(_RetirementModel):
    status: Literal["PASS", "BLOCK"]
    reason_codes: tuple[str, ...]
    inventory_sha256: str = Field(pattern=SHA256_PATTERN)
    observation_sha256: str = Field(pattern=SHA256_PATTERN)


class PredecessorRetirementReceipt(_RetirementModel):
    predecessor_epoch_id: str
    inventory_sha256: str = Field(pattern=SHA256_PATTERN)
    decision_sha256: str = Field(pattern=SHA256_PATTERN)
    target_successor_transition_sha256: str = Field(pattern=SHA256_PATTERN)


class PredecessorRetirementTombstone(PredecessorRetirementReceipt):
    active_launch_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    historical_launch_receipt_sha256: tuple[str, ...]
    retirement_evidence_sha256: str = Field(pattern=SHA256_PATTERN)

    @classmethod
    def create(
        cls,
        *,
        inventory: PredecessorLaunchInventory,
        decision: RetirementDecision,
        target_successor_transition_sha256: str,
    ) -> "PredecessorRetirementTombstone":
        if decision.status != "PASS" or decision.inventory_sha256 != inventory.sha256:
            raise ValueError("PREDECESSOR_RETIREMENT_NOT_PROVEN")
        return cls(
            predecessor_epoch_id=inventory.predecessor_epoch_id,
            inventory_sha256=inventory.sha256,
            decision_sha256=decision.sha256,
            target_successor_transition_sha256=target_successor_transition_sha256,
            active_launch_receipt_sha256=inventory.active_launch_receipt_sha256,
            historical_launch_receipt_sha256=(
                inventory.historical_launch_receipt_sha256
            ),
            retirement_evidence_sha256=decision.observation_sha256,
        )


class LaunchAfterRetirementDecision(_RetirementModel):
    status: Literal["PASS", "BLOCK"]
    reason_codes: tuple[str, ...]
    execution_lock_permitted: bool
    broker_connection_permitted: bool


def authorize_launch_after_retirement(
    tombstone: PredecessorRetirementTombstone,
    *,
    launch_binding_sha256: str,
    successor_transition_sha256: str,
    supervision_launch: bool,
) -> LaunchAfterRetirementDecision:
    retired = {
        tombstone.active_launch_receipt_sha256,
        *tombstone.historical_launch_receipt_sha256,
    }
    if launch_binding_sha256 in retired:
        reasons = ("PREDECESSOR_REACTIVATION_ATTEMPT",)
    elif (
        supervision_launch is not True
        or successor_transition_sha256
        != tombstone.target_successor_transition_sha256
    ):
        reasons = ("SUCCESSOR_SUPERVISION_BINDING_REQUIRED",)
    else:
        reasons = ()
    return LaunchAfterRetirementDecision(
        status="BLOCK" if reasons else "PASS",
        reason_codes=reasons,
        execution_lock_permitted=not reasons,
        broker_connection_permitted=not reasons,
    )


def validate_retirement(
    inventory: PredecessorLaunchInventory,
    observations: Mapping[str, Mapping[str, Any]],
) -> RetirementDecision:
    reasons: set[str] = set()
    if not inventory.complete:
        reasons.add("INVENTORY_INCOMPLETE")
    path_ids = [path.path_id for path in inventory.paths]
    if len(path_ids) != len(set(path_ids)):
        reasons.add("INVENTORY_PATH_AMBIGUOUS")
    for path in inventory.paths:
        if path.enabled:
            reasons.add("PREDECESSOR_LAUNCH_PATH_ENABLED")
        if path.can_reach_paper_port:
            reasons.add("PREDECESSOR_PATH_CAN_REACH_4002")
        observed = observations.get(path.path_id)
        if observed is None:
            reasons.add("LEGACY_REJECTION_EVIDENCE_MISSING")
            continue
        if observed.get("rejected_before_execution_lock") is not True:
            reasons.add("LEGACY_LAUNCH_REACHED_EXECUTION_LOCK")
        if observed.get("broker_connection_constructed") is not False:
            reasons.add("LEGACY_LAUNCH_REACHED_BROKER")
        if int(observed.get("broker_write_count", -1)) != 0:
            reasons.add("LEGACY_BROKER_WRITE_DETECTED")
        if observed.get("fallback_path_detected") is not False:
            reasons.add("LEGACY_FALLBACK_PATH_DETECTED")
    return RetirementDecision(
        status="BLOCK" if reasons else "PASS",
        reason_codes=tuple(sorted(reasons)),
        inventory_sha256=inventory.sha256,
        observation_sha256=sha256_json(dict(observations)),
    )
