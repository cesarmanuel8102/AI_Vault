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
    authority_class: ContinuityAuthorityClass
    new_total_quantity: Decimal | None = Field(default=None, gt=0)
    new_limit_price: Decimal | None = Field(default=None, gt=0)
    new_tif: TimeInForce | None = None
    new_good_till_date_utc: datetime | None = None
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
        self._execution_keys: set[str] = set()

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

    def submit(self, command: AuthorizedBrokerCommand) -> Future:
        future: Future = Future()
        with self._lock:
            if command.execution_key in self._execution_keys:
                future.set_result(
                    self._result(
                        status="BLOCKED", reasons=("DUPLICATE_EXECUTION_KEY",)
                    )
                )
                return future
            self._execution_keys.add(command.execution_key)
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
