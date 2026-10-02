"""Typed model requests for the single authoritative broker writer."""

from __future__ import annotations

from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .autonomous_execution import PaperExecutionResult
from .autonomous_research import (
    AutonomousOpenOrderAction,
    AutonomousPositionAction,
    AutonomousTradeProposal,
)
from .canonical import sha256_json
from .continuity_models import CodexOrderContinuityPlan, SHA256_PATTERN
from .trader_invocation import TraderDecision, TraderInputBundle


class ModelExecutionOperation(str, Enum):
    NEW_TRADE = "NEW_TRADE"
    OPEN_ORDER_ACTION = "OPEN_ORDER_ACTION"
    POSITION_ACTION = "POSITION_ACTION"


ModelExecutionPayload = (
    AutonomousTradeProposal | AutonomousOpenOrderAction | AutonomousPositionAction
)


class ModelExecutionRequest(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    durable_sequence: int = Field(gt=0)
    execution_key: str = Field(min_length=1)
    source: Literal["MODEL"]
    operation: ModelExecutionOperation
    launch_attempt_id: str = Field(min_length=1)
    epoch_id: str = Field(min_length=1)
    approved_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    invocation_id: str = Field(min_length=1)
    decision_cycle_id: str = Field(min_length=1)
    accepted_decision: TraderDecision
    accepted_result_sha256: str = Field(pattern=SHA256_PATTERN)
    payload: ModelExecutionPayload
    payload_sha256: str = Field(pattern=SHA256_PATTERN)
    input_bundle: TraderInputBundle
    input_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    continuity_plan: CodexOrderContinuityPlan | None = None
    continuity_plan_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    created_at_utc: datetime

    @model_validator(mode="after")
    def validate_bindings(self) -> "ModelExecutionRequest":
        if self.created_at_utc.tzinfo is None or self.created_at_utc.utcoffset() is None:
            raise ValueError("created_at_utc must be timezone-aware")
        expected_types = {
            ModelExecutionOperation.NEW_TRADE: AutonomousTradeProposal,
            ModelExecutionOperation.OPEN_ORDER_ACTION: AutonomousOpenOrderAction,
            ModelExecutionOperation.POSITION_ACTION: AutonomousPositionAction,
        }
        if not isinstance(self.payload, expected_types[self.operation]):
            raise ValueError("model execution payload does not match operation")
        allowed_decisions = {
            ModelExecutionOperation.NEW_TRADE: {TraderDecision.PROPOSE_TRADE},
            ModelExecutionOperation.OPEN_ORDER_ACTION: {
                TraderDecision.CANCEL_ORDER,
                TraderDecision.MODIFY_ORDER,
            },
            ModelExecutionOperation.POSITION_ACTION: {
                TraderDecision.REDUCE_POSITION,
                TraderDecision.CLOSE_POSITION,
            },
        }
        if self.accepted_decision not in allowed_decisions[self.operation]:
            raise ValueError("accepted decision does not match operation")
        if self.payload_sha256 != sha256_json(self.payload):
            raise ValueError("model execution payload hash mismatch")
        if self.input_bundle_sha256 != self.input_bundle.sha256:
            raise ValueError("model execution input bundle hash mismatch")
        if self.input_bundle.decision_cycle_id != self.decision_cycle_id:
            raise ValueError("decision cycle binding mismatch")
        if self.continuity_plan is None:
            if self.continuity_plan_sha256 is not None:
                raise ValueError("continuity plan hash requires a plan")
        elif self.continuity_plan_sha256 != self.continuity_plan.sha256:
            raise ValueError("continuity plan hash mismatch")
        return self

    @property
    def sha256(self) -> str:
        return sha256_json(self)


class CoordinatedModelExecutor:
    """Broker-free proxy that submits accepted model actions to one coordinator."""

    is_coordinated_model_executor = True

    def __init__(
        self,
        *,
        coordinator: Any,
        launch_attempt_id: str,
        epoch_id: str,
        approved_head: str,
        account_identity_sha256: str,
        accepted_result_sha256_reader: Callable[[str], str],
        invocation_id_reader: Callable[[TraderInputBundle], str],
        durable_sequence_allocator: Callable[[], int],
        now_utc: Callable[[], datetime],
        result_timeout_seconds: float,
        production_validation_sha256: str | None,
    ) -> None:
        if result_timeout_seconds <= 0 or result_timeout_seconds > 300:
            raise ValueError("result_timeout_seconds must be in (0, 300]")
        if production_validation_sha256 is not None and (
            len(production_validation_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in production_validation_sha256
            )
        ):
            raise ValueError("production_validation_sha256 must be sha256")
        self._coordinator = coordinator
        self._launch_attempt_id = launch_attempt_id
        self._epoch_id = epoch_id
        self._approved_head = approved_head
        self._account_identity_sha256 = account_identity_sha256
        self._accepted_result_sha256_reader = accepted_result_sha256_reader
        self._invocation_id_reader = invocation_id_reader
        self._durable_sequence_allocator = durable_sequence_allocator
        self._now_utc = now_utc
        self._result_timeout_seconds = result_timeout_seconds
        self.production_validation_sha256 = production_validation_sha256
        self.armed = production_validation_sha256 is not None

    @staticmethod
    def _blocked(reason: str) -> PaperExecutionResult:
        return PaperExecutionResult(
            success=False,
            status="BLOCKED",
            reason_codes=(reason,),
            order={},
            broker_validation={},
        )

    def _request(
        self,
        *,
        operation: ModelExecutionOperation,
        decision: TraderDecision,
        payload: ModelExecutionPayload,
        bundle: TraderInputBundle,
        invocation_id: str | None,
        continuity_plan: CodexOrderContinuityPlan | None = None,
    ) -> ModelExecutionRequest:
        resolved_invocation_id = invocation_id or self._invocation_id_reader(bundle)
        payload_sha256 = sha256_json(payload)
        execution_key = (
            f"model:{self._launch_attempt_id}:{resolved_invocation_id}:"
            f"{operation.value}:{payload_sha256}"
        )
        return ModelExecutionRequest(
            request_id=execution_key,
            durable_sequence=self._durable_sequence_allocator(),
            execution_key=execution_key,
            source="MODEL",
            operation=operation,
            launch_attempt_id=self._launch_attempt_id,
            epoch_id=self._epoch_id,
            approved_head=self._approved_head,
            account_identity_sha256=self._account_identity_sha256,
            invocation_id=resolved_invocation_id,
            decision_cycle_id=bundle.decision_cycle_id,
            accepted_decision=decision,
            accepted_result_sha256=self._accepted_result_sha256_reader(
                resolved_invocation_id
            ),
            payload=payload,
            payload_sha256=payload_sha256,
            input_bundle=bundle,
            input_bundle_sha256=bundle.sha256,
            continuity_plan=continuity_plan,
            continuity_plan_sha256=(
                None if continuity_plan is None else continuity_plan.sha256
            ),
            created_at_utc=self._now_utc(),
        )

    def _submit(self, request: ModelExecutionRequest) -> PaperExecutionResult:
        if not self.armed:
            return self._blocked("COORDINATED_MODEL_EXECUTOR_NOT_ARMED")
        future = self._coordinator.submit(request)
        try:
            result = future.result(timeout=self._result_timeout_seconds)
        except FutureTimeoutError:
            return self._blocked("MODEL_EXECUTION_WRITER_TIMEOUT")
        except Exception as exc:
            return self._blocked(f"MODEL_EXECUTION_WRITER_FAILED:{type(exc).__name__}")
        if not isinstance(result, PaperExecutionResult):
            return self._blocked("MODEL_EXECUTION_RESULT_INVALID")
        return result

    def execute(
        self,
        proposal: AutonomousTradeProposal,
        bundle: TraderInputBundle,
        *,
        continuity_plan: CodexOrderContinuityPlan | None = None,
        invocation_id: str | None = None,
    ) -> PaperExecutionResult:
        return self._submit(
            self._request(
                operation=ModelExecutionOperation.NEW_TRADE,
                decision=TraderDecision.PROPOSE_TRADE,
                payload=proposal,
                bundle=bundle,
                invocation_id=invocation_id,
                continuity_plan=continuity_plan,
            )
        )

    def execute_open_order_action(
        self,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
        decision: TraderDecision,
        *,
        invocation_id: str | None = None,
    ) -> PaperExecutionResult:
        return self._submit(
            self._request(
                operation=ModelExecutionOperation.OPEN_ORDER_ACTION,
                decision=decision,
                payload=action,
                bundle=bundle,
                invocation_id=invocation_id,
            )
        )

    def execute_position_action(
        self,
        action: AutonomousPositionAction,
        bundle: TraderInputBundle,
        decision: TraderDecision,
    ) -> PaperExecutionResult:
        return self._submit(
            self._request(
                operation=ModelExecutionOperation.POSITION_ACTION,
                decision=decision,
                payload=action,
                bundle=bundle,
                invocation_id=None,
            )
        )
