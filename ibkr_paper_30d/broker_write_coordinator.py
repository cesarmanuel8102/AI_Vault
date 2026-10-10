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
from .canary_execution import CanaryExecutionRequest
from .continuity_liability import MaximumLiabilityRequirement
from .continuity_models import ContinuityAuthorityClass, TimeInForce


class BrokerCommandType(str, Enum):
    RETAIN = "RETAIN"
    CANCEL = "CANCEL"
    MODIFY = "MODIFY"
    REDUCE_POSITION = "REDUCE_POSITION"
    CLOSE_POSITION = "CLOSE_POSITION"


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
    position_action: Literal["BUY", "SELL"] | None = None
    position_quantity: Decimal | None = Field(default=None, gt=0)
    position_order_type: Literal["MKT", "LMT"] | None = None
    position_limit_price: Decimal | None = Field(default=None, gt=0)
    position_identity_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    canonical_contract_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    resolved_total_quantity: Decimal = Field(gt=0)
    resolved_limit_price: Decimal = Field(ge=0)
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
        position_terms = (
            self.position_action,
            self.position_quantity,
            self.position_order_type,
            self.position_identity_sha256,
            self.canonical_contract_sha256,
        )
        if self.command_type == BrokerCommandType.MODIFY:
            if not any(value is not None for value in mutable):
                raise ValueError("MODIFY requires an exact mutable value")
        elif any(value is not None for value in mutable):
            raise ValueError("only MODIFY may contain mutable values")
        if self.command_type in {
            BrokerCommandType.REDUCE_POSITION,
            BrokerCommandType.CLOSE_POSITION,
        }:
            if any(value is None for value in position_terms):
                raise ValueError("position command requires exact identity and terms")
            if self.position_order_type == "LMT" and self.position_limit_price is None:
                raise ValueError("LMT position command requires position_limit_price")
            if self.position_order_type == "MKT" and self.position_limit_price is not None:
                raise ValueError("MKT position command cannot contain position_limit_price")
            expected_authority = (
                ContinuityAuthorityClass.REDUCE_POSITION
                if self.command_type == BrokerCommandType.REDUCE_POSITION
                else ContinuityAuthorityClass.CLOSE_POSITION
            )
            if self.authority_class != expected_authority:
                raise ValueError("position command authority class mismatch")
        elif any(value is not None for value in position_terms) or self.position_limit_price is not None:
            raise ValueError("only position commands may contain position terms")
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
        self._expired_execution_keys: set[str] = set()
        self._write_started_execution_keys: set[str] = set()

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
        self,
        command: AuthorizedBrokerCommand | ModelExecutionRequest | CanaryExecutionRequest,
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
            if (
                isinstance(command, ModelExecutionRequest)
                and command.input_bundle.multi_sleeve_v4_active
                and (
                    command.sleeve_authority_sha256 is None
                    or command.ownership_projection_sha256 is None
                    or command.product_family_sha256 is None
                )
            ):
                future.set_result(
                    self._result(
                        status="BLOCKED",
                        reasons=("SLEEVE_EXECUTION_BINDINGS_REQUIRED",),
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

    def expire_before_write(self, execution_key: str) -> bool:
        """Expire a request atomically only while no broker write may start."""
        with self._lock:
            if execution_key in self._write_started_execution_keys:
                return False
            self._expired_execution_keys.add(execution_key)
            return True

    def is_execution_expired(self, execution_key: str) -> bool:
        with self._lock:
            return execution_key in self._expired_execution_keys

    def begin_write(self, execution_key: str) -> bool:
        """Cross the pre-write boundary unless the caller already expired it."""
        with self._lock:
            if execution_key in self._expired_execution_keys:
                return False
            self._write_started_execution_keys.add(execution_key)
            return True

    def task_done(self, capability: _WriterCapability) -> None:
        if capability is not self._capability:
            raise PermissionError("WRITER_CAPABILITY_REQUIRED")
        self._queue.task_done()

    def fail_pending(self, capability: _WriterCapability, result: object) -> int:
        if capability is not self._capability:
            raise PermissionError("WRITER_CAPABILITY_REQUIRED")
        count = 0
        while True:
            try:
                _, _, _command, future = self._queue.get_nowait()
            except queue.Empty:
                return count
            if not future.done():
                future.set_result(result)
            self._queue.task_done()
            count += 1

    def detach_writer(self, capability: _WriterCapability) -> None:
        with self._lock:
            if capability is not self._capability:
                raise PermissionError("WRITER_CAPABILITY_REQUIRED")
            self._capability = None
