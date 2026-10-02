"""Writer-thread dispatch for accepted model-authored broker actions."""

from __future__ import annotations

import threading
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from .autonomous_execution import (
    PaperExecutionResult,
    WriterOwnedModelExecutionMechanics,
)
from .continuity_models import SHA256_PATTERN
from .coordinated_model_executor import (
    ModelExecutionOperation,
    ModelExecutionRequest,
)


class ModelExecutionAuthorityContext(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    request_sha256: str = Field(pattern=SHA256_PATTERN)
    writer_thread_id: int = Field(ge=-1)
    execution_client_id: int = Field(ge=0)
    production_validation_sha256: str = Field(pattern=SHA256_PATTERN)


class ModelExecutionEngine:
    def __init__(
        self,
        *,
        mechanics: WriterOwnedModelExecutionMechanics,
        execution_client_id: int = 19761,
    ) -> None:
        self.mechanics = mechanics
        self.execution_client_id = execution_client_id

    @staticmethod
    def _blocked(reason: str) -> PaperExecutionResult:
        return PaperExecutionResult(False, "BLOCKED", (reason,), {}, {})

    def execute(
        self,
        broker: Any,
        request: ModelExecutionRequest,
        authority_context: ModelExecutionAuthorityContext,
        final_write_authority_check: Callable[[], tuple[str, ...]] | None = None,
    ) -> PaperExecutionResult:
        if not isinstance(request, ModelExecutionRequest):
            raise TypeError("MODEL_EXECUTION_REQUEST_REQUIRED")
        if not isinstance(authority_context, ModelExecutionAuthorityContext):
            raise TypeError("MODEL_EXECUTION_AUTHORITY_CONTEXT_REQUIRED")
        if authority_context.request_sha256 != request.sha256:
            return self._blocked("MODEL_REQUEST_AUTHORITY_MISMATCH")
        if authority_context.writer_thread_id != threading.get_ident():
            return self._blocked("MODEL_WRITER_THREAD_MISMATCH")
        if authority_context.execution_client_id != self.execution_client_id:
            return self._blocked("MODEL_EXECUTION_CLIENT_MISMATCH")

        if request.operation == ModelExecutionOperation.NEW_TRADE:
            return self.mechanics.execute_with_broker(
                broker,
                request.payload,
                request.input_bundle,
                continuity_plan=request.continuity_plan,
                invocation_id=request.invocation_id,
                final_write_authority_check=final_write_authority_check,
            )
        if request.operation == ModelExecutionOperation.OPEN_ORDER_ACTION:
            return self.mechanics.execute_open_order_action_with_broker(
                broker,
                request.payload,
                request.input_bundle,
                request.accepted_decision,
                invocation_id=request.invocation_id,
                final_write_authority_check=final_write_authority_check,
            )
        if request.operation == ModelExecutionOperation.POSITION_ACTION:
            return self.mechanics.execute_position_action_with_broker(
                broker,
                request.payload,
                request.input_bundle,
                request.accepted_decision,
                final_write_authority_check=final_write_authority_check,
            )
        return self._blocked("MODEL_EXECUTION_OPERATION_UNSUPPORTED")
