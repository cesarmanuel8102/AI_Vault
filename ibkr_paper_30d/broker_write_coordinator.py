"""Durable-order command queue for the single authoritative broker writer."""

from __future__ import annotations

import itertools
import queue
import threading
from concurrent.futures import Future
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .canonical import sha256_json
from .coordinated_model_executor import ModelExecutionRequest
from .continuity_liability import MaximumLiabilityRequirement
from .continuity_models import ContinuityAuthorityClass, TimeInForce


class BrokerCommandType(str, Enum):
    RETAIN = "RETAIN"
    CANCEL = "CANCEL"
    MODIFY = "MODIFY"


class AuthorizedBrokerCommand(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1)
    durable_sequence: int = Field(gt=0)
    execution_key: str = Field(min_length=1)
    source: Literal["MODEL", "WATCHDOG"]
    command_type: BrokerCommandType
    evaluation_id: str = Field(min_length=1)
    evaluation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_id: str = Field(min_length=1)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fact_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    order_ref: str = Field(min_length=1)
    order_id: int = Field(gt=0)
    perm_id: int = Field(gt=0)
    execution_client_id: int = Field(ge=0)
    account_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    epoch_id: str = Field(min_length=1)
    definition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_authorization_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_class: ContinuityAuthorityClass
    new_total_quantity: Decimal | None = Field(default=None, gt=0)
    new_limit_price: Decimal | None = Field(default=None, gt=0)
    new_tif: TimeInForce | None = None
    new_good_till_date_utc: datetime | None = None
    resolved_total_quantity: Decimal = Field(gt=0)
    resolved_limit_price: Decimal = Field(gt=0)
    proposed_order_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    maximum_authorized_liability: Decimal = Field(ge=0)
    liability_requirement: MaximumLiabilityRequirement
    created_at_utc: datetime

    @model_validator(mode="after")
    def validate_command(self) -> "AuthorizedBrokerCommand":
        if self.created_at_utc.tzinfo is None:
            raise ValueError("created_at_utc must be timezone-aware")
        mutable = (
            self.new_total_quantity,
            self.new_limit_price,
            self.new_tif,
            self.new_good_till_date_utc,
        )
        if self.command_type == BrokerCommandType.MODIFY:
            if not any(value is not None for value in mutable):
                raise ValueError("MODIFY requires an exact mutable value")
        elif any(value is not None for value in mutable):
            raise ValueError("only MODIFY may contain mutable values")
        if self.new_tif == TimeInForce.GTD:
            if self.new_good_till_date_utc is None:
                raise ValueError("GTD requires new_good_till_date_utc")
        elif self.new_good_till_date_utc is not None:
            raise ValueError("new_good_till_date_utc requires GTD")
        if (
            self.new_good_till_date_utc is not None
            and self.new_good_till_date_utc.tzinfo is None
        ):
            raise ValueError("new_good_till_date_utc must be timezone-aware")
        if not all(
            value.is_finite()
            for value in (
                self.resolved_total_quantity,
                self.resolved_limit_price,
                self.maximum_authorized_liability,
            )
        ):
            raise ValueError("resolved order and liability values must be finite")
        requirement = self.liability_requirement
        if requirement.plan_id != self.plan_id or requirement.plan_sha256 != self.plan_sha256:
            raise ValueError("liability requirement plan mismatch")
        if requirement.maximum_authorized_liability != self.maximum_authorized_liability:
            raise ValueError("liability bound differs from model-authored plan")
        if requirement.account_identity_sha256 != self.account_identity_sha256:
            raise ValueError("liability requirement account mismatch")
        if requirement.contract_identity_sha256 != self.contract_identity_sha256:
            raise ValueError("liability requirement contract mismatch")
        if requirement.proposed_order_sha256 != self.proposed_order_sha256:
            raise ValueError("liability requirement order mismatch")
        return self

    @property
    def sha256(self) -> str:
        return sha256_json(self)


class _WriterCapability:
    pass


class BrokerWriteCoordinator:
    """Only an attached writer capability may consume or complete commands."""

    def __init__(self) -> None:
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._counter = itertools.count()
        self._capability: _WriterCapability | None = None
        self._lock = threading.Lock()
        self._execution_keys: dict[str, tuple[str, Future]] = {}
        self._last_durable_sequence = 0

    def attach_writer(self) -> _WriterCapability:
        with self._lock:
            if self._capability is not None:
                raise RuntimeError("AUTHORITATIVE_WRITER_ALREADY_ATTACHED")
            self._capability = _WriterCapability()
            return self._capability

    @staticmethod
    def _result(*, status: str, reasons: tuple[str, ...]):
        from .autonomous_execution import PaperExecutionResult

        return PaperExecutionResult(
            success=False,
            status=status,
            reason_codes=reasons,
            order={},
            broker_validation={},
        )

    def submit(
        self, command: AuthorizedBrokerCommand | ModelExecutionRequest
    ) -> Future:
        future: Future = Future()
        with self._lock:
            existing = self._execution_keys.get(command.execution_key)
            if existing is not None:
                existing_sha256, existing_future = existing
                if existing_sha256 == command.sha256:
                    return existing_future
                future.set_result(
                    self._result(
                        status="BLOCKED", reasons=("DUPLICATE_EXECUTION_KEY",)
                    )
                )
                return future
            if command.durable_sequence <= self._last_durable_sequence:
                future.set_result(
                    self._result(
                        status="BLOCKED",
                        reasons=("DURABLE_SEQUENCE_NOT_MONOTONIC",),
                    )
                )
                return future
            self._last_durable_sequence = command.durable_sequence
            self._execution_keys[command.execution_key] = (command.sha256, future)
        self._queue.put(
            (command.durable_sequence, next(self._counter), command, future)
        )
        return future

    def claim(self, capability: _WriterCapability, timeout: float = 0.1):
        if capability is not self._capability:
            raise PermissionError("WRITER_CAPABILITY_REQUIRED")
        try:
            _, _, command, future = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        return command, future

    def task_done(self, capability: _WriterCapability) -> None:
        if capability is not self._capability:
            raise PermissionError("WRITER_CAPABILITY_REQUIRED")
        self._queue.task_done()

    def detach_writer(self, capability: _WriterCapability) -> None:
        with self._lock:
            if capability is not self._capability:
                raise PermissionError("WRITER_CAPABILITY_REQUIRED")
            self._capability = None
