"""Single-threaded owner of the only write-capable IBKR client session."""

from __future__ import annotations

import asyncio
import copy
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from .broker_write_coordinator import (
    AuthorizedBrokerCommand,
    BrokerCommandType,
    BrokerWriteCoordinator,
)
from .canonical import sha256_json
from .coordinated_model_executor import ModelExecutionRequest
from .continuity_liability import MaximumLiabilityEvidence
from .ibkr_readonly import expected_identity_hash
from .model_execution_engine import (
    ModelExecutionAuthorityContext,
    ModelExecutionEngine,
)
from .open_order_management import ACTIONABLE_ORDER_STATUSES, canonical_open_order
from .production_authority import (
    ProductionAuthorityDecision,
    ProductionAuthoritySnapshot,
    ProductionAuthorityValidator,
    ProductionBrokerEvidence,
)


class AuthoritativeBrokerWriter:
    def __init__(
        self,
        coordinator: BrokerWriteCoordinator,
        *,
        broker_factory: Callable[[int], Any],
        execution_client_id: int,
        execution_lock_verifier: Callable[[], bool],
        authority_validator: Callable[
            [AuthorizedBrokerCommand, dict[str, Any]], tuple[str, ...]
        ],
        attempt_persister: Callable[[AuthorizedBrokerCommand, dict[str, Any]], None]
        | None = None,
        result_persister: Callable[
            [AuthorizedBrokerCommand | ModelExecutionRequest, Any, dict[str, Any]], None
        ]
        | None = None,
        model_execution_engine: ModelExecutionEngine | None = None,
        production_validation_sha256: str | None = None,
        production_authority_validator: ProductionAuthorityValidator | None = None,
        production_broker_evidence_collector: Callable[
            [Any, AuthorizedBrokerCommand | ModelExecutionRequest, dict[str, Any]],
            ProductionBrokerEvidence,
        ]
        | None = None,
        authority_broker_factory: Callable[[], Any] | None = None,
        liability_evidence_collector: Callable[
            [Any, AuthorizedBrokerCommand, dict[str, Any]],
            MaximumLiabilityEvidence,
        ]
        | None = None,
        now_utc: Callable[[], datetime] | None = None,
        resource_closer: Callable[[], None] | None = None,
        uncertainty_reporter: Callable[[str], None] | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.broker_factory = broker_factory
        self.execution_client_id = execution_client_id
        self.execution_lock_verifier = execution_lock_verifier
        self.authority_validator = authority_validator
        self.attempt_persister = attempt_persister or (lambda command, evidence: None)
        self.result_persister = result_persister or (
            lambda command, result, evidence: None
        )
        self.model_execution_engine = model_execution_engine
        self.production_validation_sha256 = production_validation_sha256
        self.production_authority_validator = production_authority_validator
        self.production_broker_evidence_collector = (
            production_broker_evidence_collector
        )
        self.authority_broker_factory = authority_broker_factory
        self.liability_evidence_collector = liability_evidence_collector
        self.now_utc = now_utc or (lambda: datetime.now(timezone.utc))
        self.resource_closer = resource_closer or (lambda: None)
        self.uncertainty_reporter = uncertainty_reporter or (lambda code: None)
        self._capability = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._frozen_order_refs: set[str] = set()
        self._model_write_authority_frozen = False

    def _report_uncertainty(self, reason_code: str) -> None:
        try:
            self.uncertainty_reporter(reason_code)
        except Exception:
            pass

    @staticmethod
    def _result(
        *,
        success: bool,
        status: str,
        reasons: tuple[str, ...] = (),
        order: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
    ):
        from .autonomous_execution import PaperExecutionResult

        return PaperExecutionResult(
            success=success,
            status=status,
            reason_codes=reasons,
            order=order or {},
            broker_validation=evidence or {},
        )

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("AUTHORITATIVE_WRITER_ALREADY_RUNNING")
        self._capability = self.coordinator.attach_writer()
        self._stop.clear()
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="ibkr-authoritative-broker-writer",
            daemon=True,
        )
        self._thread.start()

    def wait_until_ready(self, timeout_seconds: float) -> bool:
        return self._ready.wait(timeout_seconds) and self._startup_error is None

    def stop(self, timeout_seconds: float) -> bool:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout_seconds)
        return self._thread is None or not self._thread.is_alive()

    def _run(self) -> None:
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
        broker = None
        assert self._capability is not None
        try:
            try:
                broker = self.broker_factory(self.execution_client_id)
            except BaseException as exc:
                self._startup_error = exc
                self._ready.set()
                return
            self._ready.set()
            while not self._stop.is_set():
                claimed = self.coordinator.claim(self._capability, timeout=0.05)
                if claimed is None:
                    continue
                command, future = claimed
                try:
                    result = self._execute(command, broker)
                except BaseException as exc:
                    if isinstance(command, ModelExecutionRequest):
                        self._model_write_authority_frozen = True
                    self._report_uncertainty("BROKER_STATE_UNCERTAIN")
                    result = self._result(
                        success=False,
                        status="UNCERTAIN",
                        reasons=(f"WRITER_INTERNAL_FAILURE:{type(exc).__name__}",),
                    )
                if not future.done():
                    future.set_result(result)
                self.coordinator.task_done(self._capability)
        finally:
            pending = self._result(
                success=False,
                status="UNCERTAIN",
                reasons=("WRITER_STOPPED_WITH_PENDING_COMMAND",),
            )
            self.coordinator.fail_pending(self._capability, pending)
            if broker is not None:
                try:
                    broker.disconnect()
                except Exception:  # nosec B110
                    pass
            try:
                self.resource_closer()
            except Exception:
                pass
            self.coordinator.detach_writer(self._capability)
            asyncio.set_event_loop(None)
            event_loop.close()

    def _collect_evidence(self, broker: Any) -> dict[str, Any]:
        if getattr(broker, "all_order_visibility", True) is not True:
            raise PermissionError("ALL_ORDER_VISIBILITY_UNCERTAIN")
        trades = list(broker.reqAllOpenOrders())
        execution_client_id = getattr(
            broker, "evidence_execution_client_id", None
        )
        if execution_client_id is None:
            executions = list(broker.reqExecutions())
        else:
            from ib_insync import ExecutionFilter

            executions = list(
                broker.reqExecutions(
                    ExecutionFilter(clientId=int(execution_client_id))
                )
            )
        positions = list(broker.positions())
        return {
            "trades": trades,
            "open_orders": [canonical_open_order(item) for item in trades],
            "executions": executions,
            "positions": positions,
            "executions_count": len(executions),
            "positions_count": len(positions),
        }

    def _execute(
        self,
        command: AuthorizedBrokerCommand | ModelExecutionRequest,
        broker: Any,
    ):
        if isinstance(command, ModelExecutionRequest):
            return self._execute_model(command, broker)
        if isinstance(command, AuthorizedBrokerCommand):
            return self._execute_continuity(command, broker)
        return self._result(
            success=False,
            status="BLOCKED",
            reasons=("WRITER_REQUEST_TYPE_UNSUPPORTED",),
        )

    def _production_authority_read(
        self,
        *,
        request: AuthorizedBrokerCommand | ModelExecutionRequest,
        broker: Any,
        prior_authority_snapshot: ProductionAuthoritySnapshot | None = None,
    ) -> tuple[
        ProductionAuthorityDecision | None,
        dict[str, Any],
        tuple[str, ...],
    ]:
        """Collect fresh authority evidence outside the write-capable session."""

        authority_broker = broker
        owns_authority_broker = False
        if self.authority_broker_factory is not None:
            try:
                authority_broker = self.authority_broker_factory()
                owns_authority_broker = True
            except Exception as exc:
                return (
                    None,
                    {},
                    (f"AUTHORITY_BROKER_UNAVAILABLE:{type(exc).__name__}",),
                )
        try:
            try:
                evidence = self._collect_evidence(authority_broker)
            except Exception as exc:
                return (
                    None,
                    {},
                    (f"BROKER_EVIDENCE_UNAVAILABLE:{type(exc).__name__}",),
                )
            if self.production_authority_validator is None:
                return None, evidence, ()
            if self.production_broker_evidence_collector is None:
                return (
                    None,
                    evidence,
                    ("PRODUCTION_BROKER_EVIDENCE_COLLECTOR_REQUIRED",),
                )
            try:
                broker_evidence = self.production_broker_evidence_collector(
                    authority_broker, request, evidence
                )
                if not isinstance(broker_evidence, ProductionBrokerEvidence):
                    raise TypeError("ProductionBrokerEvidence required")
                liability_evidence = None
                if (
                    isinstance(request, AuthorizedBrokerCommand)
                    and request.command_type == BrokerCommandType.MODIFY
                ):
                    if self.liability_evidence_collector is None:
                        return (
                            None,
                            evidence,
                            ("LIABILITY_EVIDENCE_COLLECTOR_REQUIRED",),
                        )
                    liability_evidence = self.liability_evidence_collector(
                        authority_broker, request, evidence
                    )
                    if not isinstance(
                        liability_evidence, MaximumLiabilityEvidence
                    ):
                        raise TypeError("MaximumLiabilityEvidence required")
                decision = (
                    self.production_authority_validator.validate_before_write(
                        request=request,
                        broker_evidence=broker_evidence,
                        liability_evidence=liability_evidence,
                        now_utc=self.now_utc(),
                        prior_authority_snapshot=prior_authority_snapshot,
                    )
                )
            except Exception as exc:
                return (
                    None,
                    evidence,
                    (
                        "PRODUCTION_AUTHORITY_VALIDATION_FAILED:"
                        f"{type(exc).__name__}"
                    ,),
                )
            enriched = {
                **evidence,
                "production_authority": {
                    "authority_snapshot_sha256": (
                        decision.authority_snapshot_sha256
                    ),
                    "broker_evidence_sha256": decision.broker_evidence_sha256,
                    "liability_evidence_sha256": (
                        None
                        if decision.liability_result is None
                        else decision.liability_result.evidence_sha256
                    ),
                },
            }
            return decision, enriched, decision.reason_codes
        finally:
            if owns_authority_broker:
                try:
                    authority_broker.disconnect()
                except Exception:  # nosec B110
                    pass

    def _execute_model(self, request: ModelExecutionRequest, broker: Any):
        if self._model_write_authority_frozen:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("MODEL_WRITE_AUTHORITY_FROZEN",),
            )
        if self.model_execution_engine is None:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("MODEL_EXECUTION_ENGINE_REQUIRED",),
            )
        if self.production_validation_sha256 is None:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("PRODUCTION_VALIDATION_REQUIRED",),
            )
        if self.execution_lock_verifier() is not True:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("EXECUTION_LOCK_REQUIRED",),
            )
        decision, evidence, production_reasons = self._production_authority_read(
            request=request,
            broker=broker,
        )
        if production_reasons:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=production_reasons,
                evidence=evidence,
            )
        evidence = {
            **evidence,
            "request_sha256": request.sha256,
            "writer_thread_id": threading.get_ident(),
            "execution_client_id": self.execution_client_id,
        }
        reasons = tuple(self.authority_validator(request, evidence))
        if reasons:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=reasons,
                evidence=evidence,
            )
        final_gate_invoked = False

        def final_write_authority_check() -> tuple[str, ...]:
            nonlocal decision, evidence, final_gate_invoked
            final_gate_invoked = True
            final_decision, final_evidence, final_reasons = (
                self._production_authority_read(
                    request=request,
                    broker=broker,
                    prior_authority_snapshot=(
                        None if decision is None else decision.authority_snapshot
                    ),
                )
            )
            decision = final_decision
            evidence = {
                **final_evidence,
                "request_sha256": request.sha256,
                "writer_thread_id": threading.get_ident(),
                "execution_client_id": self.execution_client_id,
            }
            if final_reasons:
                return final_reasons
            legacy_reasons = tuple(self.authority_validator(request, evidence))
            if legacy_reasons:
                return legacy_reasons
            try:
                self.attempt_persister(request, evidence)
            except Exception:
                return ("MODEL_ATTEMPT_PERSISTENCE_FAILED",)
            return ()

        if self.production_authority_validator is None:
            try:
                self.attempt_persister(request, evidence)
            except Exception:
                return self._result(
                    success=False,
                    status="BLOCKED",
                    reasons=("MODEL_ATTEMPT_PERSISTENCE_FAILED",),
                    evidence=evidence,
                )
        context = ModelExecutionAuthorityContext(
            request_sha256=request.sha256,
            writer_thread_id=threading.get_ident(),
            execution_client_id=self.execution_client_id,
            production_validation_sha256=self.production_validation_sha256,
        )
        result = self.model_execution_engine.execute(
            broker,
            request,
            context,
            final_write_authority_check=(
                final_write_authority_check
                if self.production_authority_validator is not None
                else None
            ),
        )
        if (
            self.production_authority_validator is not None
            and result.success
            and not final_gate_invoked
        ):
            self._model_write_authority_frozen = True
            return self._result(
                success=False,
                status="UNCERTAIN",
                reasons=("MODEL_FINAL_WRITE_AUTHORITY_NOT_INVOKED",),
                evidence=evidence,
            )
        if result.status == "UNCERTAIN":
            self._model_write_authority_frozen = True
            self._report_uncertainty("MODEL_EXECUTION_RESULT_UNCERTAIN")
        try:
            self.result_persister(request, result, evidence)
        except Exception:
            self._model_write_authority_frozen = True
            self._report_uncertainty("MODEL_EXECUTION_RESULT_UNCERTAIN")
            return self._result(
                success=False,
                status="UNCERTAIN",
                reasons=("MODEL_EXECUTION_RESULT_PERSISTENCE_FAILED",),
                evidence=evidence,
            )
        return result

    def _execute_continuity(self, command: AuthorizedBrokerCommand, broker: Any):
        if command.order_ref in self._frozen_order_refs:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("ORDER_WRITE_AUTHORITY_FROZEN",),
            )
        if command.execution_client_id != self.execution_client_id:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("NON_OWNER_EXECUTION_CLIENT",),
            )
        if self.execution_lock_verifier() is not True:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("EXECUTION_LOCK_REQUIRED",),
            )
        decision, evidence, production_reasons = self._production_authority_read(
            request=command,
            broker=broker,
        )
        if production_reasons:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=production_reasons,
                evidence=evidence,
            )
        reasons = tuple(self.authority_validator(command, evidence))
        if reasons:
            return self._result(
                success=False, status="BLOCKED", reasons=reasons, evidence=evidence
            )

        decision, evidence, production_reasons = self._production_authority_read(
            request=command,
            broker=broker,
            prior_authority_snapshot=(
                None if decision is None else decision.authority_snapshot
            ),
        )
        if production_reasons:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=production_reasons,
                evidence=evidence,
            )
        reasons = tuple(self.authority_validator(command, evidence))
        if reasons:
            return self._result(
                success=False, status="BLOCKED", reasons=reasons, evidence=evidence
            )

        matches = [
            (trade, snapshot)
            for trade, snapshot in zip(evidence["trades"], evidence["open_orders"])
            if snapshot["orderRef"] == command.order_ref
            and snapshot["orderId"] == command.order_id
            and snapshot["permId"] == command.perm_id
        ]
        if len(matches) != 1:
            reason = (
                "OPEN_ORDER_IDENTITY_AMBIGUOUS"
                if len(matches) > 1
                else "OPEN_ORDER_NOT_FOUND"
            )
            return self._result(
                success=False, status="BLOCKED", reasons=(reason,), evidence=evidence
            )
        trade, snapshot = matches[0]
        identity_reasons = []
        if snapshot["clientId"] != self.execution_client_id:
            identity_reasons.append("NON_OWNER_EXECUTION_CLIENT")
        if expected_identity_hash(snapshot["account"]) != command.account_identity_sha256:
            identity_reasons.append("OPEN_ORDER_ACCOUNT_MISMATCH")
        if sha256_json(snapshot["contract"]) != command.contract_identity_sha256:
            identity_reasons.append("OPEN_ORDER_CONTRACT_MISMATCH")
        if snapshot["state_sha256"] != command.observed_state_sha256:
            identity_reasons.append("OPEN_ORDER_STATE_CHANGED")
        if snapshot["status"].upper() not in ACTIONABLE_ORDER_STATUSES:
            identity_reasons.append("OPEN_ORDER_NOT_ACTIONABLE")
        if identity_reasons:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=tuple(identity_reasons),
                evidence=evidence,
            )

        try:
            self.attempt_persister(command, evidence)
        except Exception:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("CONTINUITY_ATTEMPT_PERSISTENCE_FAILED",),
                evidence=evidence,
            )

        if command.command_type == BrokerCommandType.RETAIN:
            result = self._result(
                success=True,
                status="RETAINED",
                order={"orderRef": command.order_ref},
                evidence=evidence,
            )
        else:
            try:
                if command.command_type == BrokerCommandType.CANCEL:
                    broker.cancelOrder(trade.order)
                    status = "CANCEL_CONFIRMED"
                else:
                    modified = copy.deepcopy(trade.order)
                    if command.new_total_quantity is not None:
                        if command.new_total_quantity <= Decimal(snapshot["filled"]):
                            return self._result(
                                success=False,
                                status="BLOCKED",
                                reasons=("ORDER_WOULD_HAVE_NO_REMAINING_QUANTITY",),
                                evidence=evidence,
                            )
                        modified.totalQuantity = float(command.new_total_quantity)
                    if command.new_limit_price is not None:
                        modified.lmtPrice = float(command.new_limit_price)
                    if command.new_tif is not None:
                        modified.tif = command.new_tif.value
                        modified.goodTillDate = ""
                        if command.new_good_till_date_utc is not None:
                            timestamp = command.new_good_till_date_utc.astimezone(
                                timezone.utc
                            )
                            modified.goodTillDate = timestamp.strftime(
                                "%Y%m%d %H:%M:%S UTC"
                            )
                    broker.placeOrder(trade.contract, modified)
                    status = "MODIFY_CONFIRMED"
                post_trades = list(broker.reqAllOpenOrders())
                post_matches = [
                    canonical_open_order(item)
                    for item in post_trades
                    if str(getattr(item.order, "orderRef", "") or "")
                    == command.order_ref
                    and int(getattr(item.order, "orderId", 0) or 0)
                    == command.order_id
                    and int(getattr(item.order, "permId", 0) or 0)
                    == command.perm_id
                    and int(getattr(item.order, "clientId", 0) or 0)
                    == self.execution_client_id
                ]
                if len(post_matches) != 1:
                    raise RuntimeError("POST_WRITE_ORDER_IDENTITY_UNCONFIRMED")
                post = post_matches[0]
                if command.command_type == BrokerCommandType.CANCEL:
                    confirmed = post["status"].upper().replace(" ", "") in {
                        "PENDINGCANCEL",
                        "CANCELLED",
                        "APICANCELLED",
                    }
                else:
                    expected_total = (
                        command.new_total_quantity
                        if command.new_total_quantity is not None
                        else Decimal(snapshot["totalQuantity"])
                    )
                    expected_limit = (
                        command.new_limit_price
                        if command.new_limit_price is not None
                        else Decimal(snapshot["limitPrice"])
                    )
                    expected_tif = (
                        command.new_tif.value
                        if command.new_tif is not None
                        else snapshot["tif"]
                    )
                    expected_good_till = (
                        command.new_good_till_date_utc.astimezone(
                            timezone.utc
                        ).strftime("%Y%m%d %H:%M:%S UTC")
                        if command.new_good_till_date_utc is not None
                        else str(
                            (snapshot.get("orderAttributes") or {}).get(
                                "goodTillDate"
                            )
                            or ""
                        )
                    )
                    confirmed = (
                        Decimal(post["totalQuantity"]) == expected_total
                        and Decimal(post["limitPrice"]) == expected_limit
                        and post["tif"] == expected_tif
                        and str(
                            (post.get("orderAttributes") or {}).get(
                                "goodTillDate"
                            )
                            or ""
                        )
                        == expected_good_till
                    )
                if not confirmed:
                    raise RuntimeError("POST_WRITE_STATE_UNCONFIRMED")
                evidence = {**evidence, "post_write_order": post}
                result = self._result(
                    success=True,
                    status=status,
                    order={"orderRef": command.order_ref},
                    evidence=evidence,
                )
            except Exception:
                self._frozen_order_refs.add(command.order_ref)
                self._report_uncertainty("CONTINUITY_ORDER_STATE_UNCERTAIN")
                return self._result(
                    success=False,
                    status="UNCERTAIN",
                    reasons=("CONTINUITY_ORDER_STATE_UNCERTAIN",),
                    order={"orderRef": command.order_ref},
                    evidence=evidence,
                )
        try:
            self.result_persister(command, result, evidence)
        except Exception:
            self._frozen_order_refs.add(command.order_ref)
            self._report_uncertainty("CONTINUITY_ORDER_STATE_UNCERTAIN")
            return self._result(
                success=False,
                status="UNCERTAIN",
                reasons=("CONTINUITY_ORDER_STATE_UNCERTAIN",),
                order={"orderRef": command.order_ref},
                evidence=evidence,
            )
        return result
