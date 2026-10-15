"""Single-threaded owner of the only write-capable IBKR client session."""

from __future__ import annotations

import asyncio
import copy
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Iterator

from .broker_write_coordinator import (
    AuthorizedBrokerCommand,
    BrokerCommandType,
    BrokerWriteCoordinator,
)
from .canonical import sha256_json
from .canary_execution import (
    CanaryExecutionAdapter, CanaryExecutionRequest, CanaryExecutionResult,
    CanaryPreWriteBlocked,
    CanaryRecoveryRequest,
)
from .coordinated_model_executor import ModelExecutionRequest
from .continuity_liability import MaximumLiabilityEvidence
from .contract_ownership import canonical_contract_identity as v4_contract_identity
from .ibkr_readonly import expected_identity_hash
from .model_execution_engine import (
    ModelExecutionAuthorityContext,
    ModelExecutionEngine,
)
from .open_order_management import (
    ACTIONABLE_ORDER_STATUSES,
    canonical_open_order,
)
from .production_authority import (
    ProductionAuthorityDecision,
    ProductionAuthoritySnapshot,
    ProductionAuthorityValidator,
    ProductionBrokerEvidence,
)
from .sleeve_execution_authority import SleeveAuthorityReservationStore


class BrokerEvidenceTimeout(TimeoutError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


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
        liability_evidence_collector: Callable[
            [Any, AuthorizedBrokerCommand, dict[str, Any]],
            MaximumLiabilityEvidence,
        ]
        | None = None,
        now_utc: Callable[[], datetime] | None = None,
        resource_closer: Callable[[], None] | None = None,
        uncertainty_reporter: Callable[[str], None] | None = None,
        broker_request_timeout_seconds: float = 15.0,
        sleeve_authority_reservation_store: SleeveAuthorityReservationStore | None = None,
        sleeve_authority_snapshot_reader: Callable[[ModelExecutionRequest], Any]
        | None = None,
        sleeve_broker_evidence_collector: Callable[
            [Any, ModelExecutionRequest, dict[str, Any]], dict[str, Any]
        ]
        | None = None,
        canary_execution_adapter: CanaryExecutionAdapter | Any | None = None,
        canary_evidence_collector: Callable[
            [Any, CanaryExecutionRequest, dict[str, Any]], dict[str, Any]
        ]
        | None = None,
        canary_recovery_claim: Callable[[CanaryRecoveryRequest, dict[str, Any]], bool] | None = None,
        canary_recovery_result_persister: Callable[[CanaryRecoveryRequest, Any], None] | None = None,
        canary_broker_accounting: Callable[[CanaryExecutionRequest, dict[str, Any]], bool] | None = None,
        canary_recovery_bound_order_reader: Callable[[CanaryRecoveryRequest], dict[str, Any] | None] | None = None,
        startup_connect_attempts: int = 3,
        startup_retry_delay_seconds: float = 1.0,
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
        self.liability_evidence_collector = liability_evidence_collector
        self.now_utc = now_utc or (lambda: datetime.now(timezone.utc))
        self.resource_closer = resource_closer or (lambda: None)
        self.uncertainty_reporter = uncertainty_reporter or (lambda code: None)
        self.sleeve_authority_reservation_store = (
            sleeve_authority_reservation_store
        )
        self.sleeve_authority_snapshot_reader = sleeve_authority_snapshot_reader
        self.sleeve_broker_evidence_collector = sleeve_broker_evidence_collector
        self.canary_execution_adapter = canary_execution_adapter
        self.canary_evidence_collector = canary_evidence_collector
        self.canary_recovery_claim = canary_recovery_claim
        self.canary_recovery_result_persister = canary_recovery_result_persister
        self.canary_broker_accounting = canary_broker_accounting
        self.canary_recovery_bound_order_reader = canary_recovery_bound_order_reader
        self.canary_supervision_verifier: Callable[[], bool] | None = None
        if (
            isinstance(self.canary_execution_adapter, CanaryExecutionAdapter)
            and self.canary_execution_adapter.writer_executor is None
        ):
            self.canary_execution_adapter.writer_executor = (
                self._execute_canary_lifecycle_through_writer
            )
        if broker_request_timeout_seconds <= 0 or broker_request_timeout_seconds > 60:
            raise ValueError("broker_request_timeout_seconds must be in (0, 60]")
        self.broker_request_timeout_seconds = float(broker_request_timeout_seconds)
        if not 1 <= startup_connect_attempts <= 5:
            raise ValueError("startup_connect_attempts must be in [1, 5]")
        if not 0 <= startup_retry_delay_seconds <= 10:
            raise ValueError("startup_retry_delay_seconds must be in [0, 10]")
        self.startup_connect_attempts = int(startup_connect_attempts)
        self.startup_retry_delay_seconds = float(startup_retry_delay_seconds)
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
        self._startup_error = None
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
            for attempt in range(1, self.startup_connect_attempts + 1):
                try:
                    broker = self.broker_factory(self.execution_client_id)
                    if hasattr(broker, "RequestTimeout"):
                        broker.RequestTimeout = self.broker_request_timeout_seconds
                    break
                except BaseException as exc:
                    retryable = not isinstance(exc, PermissionError) and isinstance(
                        exc, (ConnectionError, TimeoutError, OSError)
                    )
                    if not retryable or attempt == self.startup_connect_attempts:
                        self._startup_error = exc
                        self._ready.set()
                        return
                    if self._stop.wait(self.startup_retry_delay_seconds):
                        self._startup_error = RuntimeError(
                            "AUTHORITATIVE_WRITER_STARTUP_STOPPED"
                        )
                        self._ready.set()
                        return
            self._ready.set()
            while not self._stop.is_set():
                claimed = self.coordinator.claim(self._capability, timeout=0.05)
                if claimed is None:
                    if hasattr(broker, "sleep"):
                        broker.sleep(0.01)
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
                self.coordinator.complete(
                    self._capability,
                    command,
                    future,
                    result,
                )
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

    @staticmethod
    def _broker_list_read(stage: str, call: Callable[[], Any]) -> list[Any]:
        try:
            return list(call())
        except TimeoutError as exc:
            raise BrokerEvidenceTimeout(
                f"BROKER_EVIDENCE_{stage}_TIMEOUT"
            ) from exc

    def _collect_evidence(self, broker: Any) -> dict[str, Any]:
        if getattr(broker, "all_order_visibility", True) is not True:
            raise PermissionError("ALL_ORDER_VISIBILITY_UNCERTAIN")
        trades = self._broker_list_read("OPEN_ORDERS", broker.reqAllOpenOrders)
        executions = self._broker_list_read("EXECUTIONS", broker.reqExecutions)
        positions = self._broker_list_read("POSITIONS", broker.positions)
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
        command: AuthorizedBrokerCommand | ModelExecutionRequest | CanaryExecutionRequest,
        broker: Any,
    ):
        if isinstance(command, CanaryRecoveryRequest):
            return self._execute_canary_recovery(command, broker)
        if isinstance(command, CanaryExecutionRequest):
            return self._execute_canary(command, broker)
        if isinstance(command, ModelExecutionRequest):
            return self._execute_model(command, broker)
        if isinstance(command, AuthorizedBrokerCommand):
            return self._execute_continuity(command, broker)
        return self._result(
            success=False,
            status="BLOCKED",
            reasons=("WRITER_REQUEST_TYPE_UNSUPPORTED",),
        )

    def _execute_canary_recovery(self, request: CanaryRecoveryRequest, broker: Any):
        """One separately authorized reduction; never reuse entry authority."""
        from ib_insync import Contract, Order

        original = request.original_request
        if (self.canary_recovery_claim is None
                or self.canary_recovery_result_persister is None
                or self.execution_lock_verifier() is not True
                or not request.created_at_utc <= self.now_utc() < request.expires_at_utc):
            return self._result(success=False, status="BLOCKED",
                                reasons=("CANARY_RECOVERY_AUTHORITY_REQUIRED",))
        if self.canary_recovery_bound_order_reader is not None:
            bound = self.canary_recovery_bound_order_reader(request)
            if bound is not None:
                return self._manage_bound_canary_recovery(request, broker, bound)

        def exact_evidence():
            evidence = self._collect_evidence(broker)
            matching_orders = [t for t in evidence["trades"]
                               if int(getattr(t.contract, "conId", 0) or 0)
                               == original.canonical_contract.con_id]
            positions = [p for p in evidence["positions"]
                         if int(getattr(p.contract, "conId", 0) or 0)
                         == original.canonical_contract.con_id]
            entry_ref = f"codex-ibkr-paper-30d-canary-entry-{original.sha256[:12]}"
            fills = [f for f in evidence["executions"]
                     if str(getattr(f.execution, "orderRef", "")) == entry_ref]
            expected_side = "BOT" if original.entry_terms.action == "BUY" else "SLD"
            if matching_orders or len(positions) != 1 or len(fills) != 1:
                raise ValueError("CANARY_RECOVERY_IDENTITY_AMBIGUOUS")
            position, fill = positions[0], fills[0]
            signed = Decimal(str(position.position))
            expected_signed = original.quantity if expected_side == "BOT" else -original.quantity
            if (signed != expected_signed
                    or expected_identity_hash(position.account) != original.account_identity_sha256
                    or expected_identity_hash(fill.execution.acctNumber) != original.account_identity_sha256
                    or int(fill.contract.conId) != original.canonical_contract.con_id
                    or int(fill.execution.clientId) != self.execution_client_id
                    or int(fill.execution.permId) <= 0
                    or sha256_json(fill.execution.execId) != request.entry_execution_id_sha256
                    or Decimal(str(fill.execution.shares)) != original.quantity
                    or fill.execution.side != expected_side):
                raise ValueError("CANARY_RECOVERY_IDENTITY_MISMATCH")
            return position, fill, evidence

        try:
            position, entry_fill, _ = exact_evidence()
            identity = original.canonical_contract
            qualified = list(broker.qualifyContracts(Contract(
                conId=identity.con_id, secType=identity.security_type,
                exchange=identity.exchange, currency=identity.currency,
                localSymbol=identity.local_symbol, tradingClass=identity.trading_class,
                multiplier=identity.multiplier)))
            if (len(qualified) != 1 or int(qualified[0].conId) != identity.con_id
                    or not qualified[0].exchange):
                raise ValueError("CANARY_RECOVERY_CONTRACT_QUALIFICATION_MISMATCH")
            resolved_contract = qualified[0]
            price = self._canary_flat_return_limit_price(original, broker)
            if price is None:
                raise ValueError("CANARY_FLAT_RETURN_PRICE_UNRESOLVED")
            position, entry_fill, evidence = exact_evidence()
            if (self.execution_lock_verifier() is not True
                    or not request.created_at_utc <= self.now_utc() < request.expires_at_utc):
                raise ValueError("CANARY_RECOVERY_AUTHORITY_REQUIRED")
            facts = {
                "request_sha256": request.sha256,
                "original_request_sha256": original.sha256,
                "entry_execution_id_sha256": request.entry_execution_id_sha256,
                "position_quantity": str(position.position),
                "account_identity_sha256": original.account_identity_sha256,
                "contract_identity_sha256": original.canonical_contract.sha256,
                "entry_order_id": int(entry_fill.execution.orderId),
                "entry_perm_id": int(entry_fill.execution.permId),
                "entry_price": str(entry_fill.execution.price),
                "exit_limit_price": str(price),
                "observed_at_utc": self.now_utc().isoformat(),
            }
            if self.canary_recovery_claim(request, facts) is not True:
                raise ValueError("CANARY_RECOVERY_ALREADY_CLAIMED")
        except Exception as exc:
            return self._result(success=False, status="BLOCKED", reasons=(str(exc),))

        ref = f"codex-ibkr-paper-30d-canary-recovery-{request.sha256[:12]}"
        order = Order(action=original.flat_return_plan.action, orderType="LMT",
                      tif="GTC", totalQuantity=float(original.quantity),
                      lmtPrice=float(price), transmit=True, whatIf=False,
                      account=position.account, orderRef=ref,
                      outsideRth=original.entry_terms.outside_regular_hours,
                      orderId=int(broker.client.getReqId()))
        try:
            trade = broker.placeOrder(resolved_contract, order)
            deadline = time.monotonic() + self.broker_request_timeout_seconds
            while not int(getattr(trade.order, "permId", 0) or 0):
                if str(trade.orderStatus.status) in {"Cancelled", "ApiCancelled", "Inactive"}:
                    errors = [int(getattr(item, "errorCode", 0)) for item in getattr(trade, "log", ())]
                    if 321 in errors:
                        result = self._result(success=False, status="REJECTED_PRE_BROKER",
                            reasons=("IBKR_VALIDATION_REJECTED:321",),
                            order={"orderRef": ref, "orderId": order.orderId, "permId": 0}, evidence=facts)
                        self.canary_recovery_result_persister(request, result)
                        return result
                    raise RuntimeError("CANARY_RECOVERY_BINDING_REJECTED")
                if time.monotonic() >= deadline:
                    raise RuntimeError("CANARY_RECOVERY_BINDING_TIMEOUT")
                broker.sleep(0.05)
            while (str(trade.orderStatus.status) not in {"Filled", "Cancelled", "ApiCancelled", "Inactive"}
                   and time.monotonic() < deadline):
                broker.sleep(0.05)
            status = str(trade.orderStatus.status)
            if status in {"Cancelled", "ApiCancelled", "Inactive"}:
                raise RuntimeError("CANARY_RECOVERY_EXIT_NOT_FILLED")
            if status == "Filled":
                post = self._collect_evidence(broker)
                exit_fills = [f for f in post["executions"]
                              if f.execution.orderRef == ref
                              and int(f.execution.orderId) == order.orderId
                              and int(f.execution.permId) == int(trade.order.permId)
                              and int(f.execution.clientId) == self.execution_client_id
                              and expected_identity_hash(f.execution.acctNumber) == original.account_identity_sha256
                              and int(f.contract.conId) == original.canonical_contract.con_id
                              and f.execution.side == ("SLD" if order.action == "SELL" else "BOT")]
                post_quantity = sum((Decimal(str(p.position)) for p in post["positions"]
                                     if int(p.contract.conId) == original.canonical_contract.con_id), Decimal("0"))
                if (not exit_fills or sum((Decimal(str(f.execution.shares)) for f in exit_fills), Decimal("0")) != original.quantity
                        or post_quantity != 0
                        or any(int(t.contract.conId) == original.canonical_contract.con_id for t in post["trades"])):
                    raise RuntimeError("CANARY_RECOVERY_FLAT_NOT_PROVEN")
                facts["exit_execution_ids_sha256"] = [sha256_json(f.execution.execId) for f in exit_fills]
                facts["post_position_quantity"] = "0"
                if self.canary_broker_accounting is not None:
                    facts["economics_reconciled"] = self.canary_broker_accounting(
                        original, self._canary_broker_facts(original, broker, recovery_ref=ref))
            result = self._result(
                success=True, status="FILLED" if status == "Filled" else "BROKER_BOUND",
                order={"orderRef": ref, "orderId": int(trade.order.orderId),
                       "permId": int(trade.order.permId), "clientId": self.execution_client_id,
                       "status": status}, evidence=facts,
            )
            self.canary_recovery_result_persister(request, result)
            return result
        except Exception as exc:
            result = self._result(success=False, status="UNCERTAIN",
                                 reasons=("CANARY_RECOVERY_STATE_UNCERTAIN", type(exc).__name__),
                                 order={"orderRef": ref, "orderId": order.orderId}, evidence=facts)
            self._report_uncertainty("CANARY_RECOVERY_STATE_UNCERTAIN")
            self.canary_recovery_result_persister(request, result)
            return result

    def _manage_bound_canary_recovery(self, request, broker, bound):
        """Refresh the model-authorized limit on the same proven broker order."""
        from ib_insync import Contract
        original = request.original_request
        identity = original.canonical_contract
        ref = f"codex-ibkr-paper-30d-canary-recovery-{request.sha256[:12]}"
        if (bound.get("orderRef") != ref or int(bound.get("permId") or 0) <= 0
                or int(bound.get("clientId", -1)) != self.execution_client_id):
            return self._result(success=False, status="BLOCKED", reasons=("CANARY_RECOVERY_BINDING_MISMATCH",))
        qualified = list(broker.qualifyContracts(Contract(
            conId=identity.con_id, secType=identity.security_type,
            exchange=identity.exchange, currency=identity.currency)))
        if len(qualified) != 1 or int(qualified[0].conId) != identity.con_id or not qualified[0].exchange:
            return self._result(success=False, status="BLOCKED", reasons=("CANARY_RECOVERY_CONTRACT_QUALIFICATION_MISMATCH",))
        deadline = time.monotonic() + self.broker_request_timeout_seconds
        next_refresh = 0.0
        while True:
            evidence = self._collect_evidence(broker)
            facts = self._canary_broker_facts(original, broker, recovery_ref=ref)
            matches = [t for t in evidence["trades"]
                       if int(t.contract.conId) == identity.con_id]
            if not matches and Decimal(facts["position_quantity"]) == 0:
                exit_fills = [f for f in facts["fills"] if f.get("order_ref") == ref
                              and f.get("order_id") == bound["orderId"]
                              and f.get("perm_id") == bound["permId"]]
                if sum((Decimal(f["quantity"]) for f in exit_fills), Decimal("0")) != original.quantity:
                    return self._result(success=False, status="UNCERTAIN", reasons=("CANARY_RECOVERY_FLAT_NOT_PROVEN",))
                reconciled = self.canary_broker_accounting(original, facts) if self.canary_broker_accounting is not None else False
                result = self._result(success=True, status="FILLED",
                    order={**bound, "status": "Filled"},
                    evidence={"broker_facts": facts, "economics_reconciled": reconciled,
                              "post_position_quantity": "0", "new_order_created": False})
                self.canary_recovery_result_persister(request, result)
                return result
            if len(matches) != 1:
                return self._result(success=False, status="BLOCKED", reasons=("CANARY_RECOVERY_ORDER_IDENTITY_AMBIGUOUS",))
            trade = matches[0]
            order = trade.order
            if (order.orderId != bound["orderId"] or order.permId != bound["permId"]
                    or order.clientId != self.execution_client_id or order.orderRef != ref
                    or order.action != original.flat_return_plan.action
                    or order.orderType != "LMT" or Decimal(str(order.totalQuantity)) != original.quantity
                    or self.execution_lock_verifier() is not True):
                return self._result(success=False, status="BLOCKED", reasons=("CANARY_RECOVERY_BINDING_MISMATCH",))
            if not 0 < abs(Decimal(facts["position_quantity"])) <= original.quantity:
                return self._result(success=False, status="BLOCKED", reasons=("CANARY_RECOVERY_POSITION_SIZE_MISMATCH",))
            if time.monotonic() >= deadline or self.now_utc() >= request.expires_at_utc:
                result = self._result(success=True, status="BROKER_BOUND",
                    order={**bound, "status": str(trade.orderStatus.status)}, evidence={"broker_facts": facts})
                self.canary_recovery_result_persister(request, result)
                return result
            if time.monotonic() >= next_refresh:
                price = self._canary_flat_return_limit_price(original, broker)
                if price is None:
                    return self._result(success=False, status="BLOCKED", reasons=("CANARY_FLAT_RETURN_PRICE_UNRESOLVED",))
                fresh = self._collect_evidence(broker)
                if not any(t.order.orderId == bound["orderId"] and t.order.permId == bound["permId"] for t in fresh["trades"]):
                    continue
                if Decimal(str(order.lmtPrice)) != price:
                    result = self._result(success=True, status="REFRESH_AUTHORIZED",
                        order=dict(bound), evidence={"limit_price": str(price), "new_order_created": False})
                    self.canary_recovery_result_persister(request, result)
                    order.lmtPrice = float(price)
                    broker.placeOrder(qualified[0], order)
                next_refresh = time.monotonic() + 5
            broker.sleep(0.1)

    def _canary_supervision_ready(self) -> bool:
        if self.canary_supervision_verifier is None:
            return True
        deadline = time.monotonic() + 5.0
        while True:
            if self.canary_supervision_verifier() is True:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def _execute_canary(self, request: CanaryExecutionRequest, broker: Any):
        if not self._canary_supervision_ready():
            return CanaryExecutionResult(
                status="BLOCKED", request_sha256=request.sha256,
                reason_codes=("CONTINUITY_WATCHDOG_UNHEALTHY",),
            )
        if self.execution_lock_verifier() is not True:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("EXECUTION_LOCK_REQUIRED",),
            )
        if self.canary_execution_adapter is None:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("CANARY_EXECUTION_ADAPTER_REQUIRED",),
            )
        if self.canary_evidence_collector is None:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("CANARY_EVIDENCE_COLLECTOR_REQUIRED",),
            )
        try:
            base_evidence = self._collect_evidence(broker)
            authority_evidence = self.canary_evidence_collector(
                broker, request, base_evidence
            )
            flat_return_limit_price = dict(authority_evidence).get(
                "flat_return_limit_price"
            )
            if flat_return_limit_price is None:
                flat_return_limit_price = self._canary_flat_return_limit_price(
                    request, broker
                )
            evidence = {
                **base_evidence,
                **dict(authority_evidence),
                "flat_return_limit_price": flat_return_limit_price,
                "writer_thread_id": threading.get_ident(),
                "execution_client_id": self.execution_client_id,
            }
        except BrokerEvidenceTimeout as exc:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=(exc.reason_code,),
            )
        except Exception as exc:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=(f"CANARY_EVIDENCE_UNAVAILABLE:{type(exc).__name__}",),
            )
        capture = getattr(self.canary_broker_accounting, 'capture_baseline', None)
        if callable(capture):
            try:
                capture(request, broker)
            except Exception as exc:
                return self._result(success=False, status='BLOCKED',
                                    reasons=(f'CANARY_NET_BASELINE_UNAVAILABLE:{type(exc).__name__}',))
        result = self.canary_execution_adapter.execute(request, broker, evidence)
        if getattr(result, "status", None) == "UNCERTAIN":
            self._report_uncertainty("CANARY_STATE_UNCERTAIN")
        return result

    def _canary_flat_return_limit_price(
        self, request: CanaryExecutionRequest, broker: Any
    ) -> Decimal | None:
        if request.flat_return_plan.order_type != "LMT":
            return None
        from ib_insync import Contract

        identity = request.canonical_contract
        contract = Contract(
            conId=identity.con_id,
            secType=identity.security_type,
            exchange=identity.exchange,
            currency=identity.currency,
            localSymbol=identity.local_symbol,
            tradingClass=identity.trading_class,
            multiplier=identity.multiplier,
        )
        qualified = list(broker.qualifyContracts(contract))
        if len(qualified) != 1 or int(qualified[0].conId or 0) != identity.con_id:
            return None
        ticker = broker.reqMktData(qualified[0], snapshot=False)
        field = (
            "bid" if request.flat_return_plan.action == "SELL" else "ask"
        )
        deadline = time.monotonic() + min(15.0, self.broker_request_timeout_seconds)
        try:
            while True:
                try:
                    price = Decimal(str(getattr(ticker, field, None)))
                except Exception:
                    price = Decimal("NaN")
                if price.is_finite() and price > 0:
                    return price
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                if hasattr(broker, "sleep"):
                    broker.sleep(min(0.05, remaining))
                else:
                    time.sleep(min(0.05, remaining))
        finally:
            if hasattr(broker, "cancelMktData"):
                broker.cancelMktData(qualified[0])

    def _execute_canary_lifecycle_through_writer(
        self,
        request: CanaryExecutionRequest,
        broker: Any,
        evidence: dict[str, Any],
    ) -> Iterator[tuple[str, int, int, bool]]:
        """Perform the bounded round trip on this writer's existing IB session."""

        from ib_insync import Contract, Order

        identity = request.canonical_contract
        contract = Contract(
            conId=identity.con_id,
            secType=identity.security_type,
            exchange=identity.exchange,
            currency=identity.currency,
            localSymbol=identity.local_symbol,
            tradingClass=identity.trading_class,
            multiplier=identity.multiplier,
        )
        if hasattr(broker, "qualifyContracts"):
            qualified = list(broker.qualifyContracts(contract))
            if len(qualified) != 1 or int(qualified[0].conId or 0) != identity.con_id:
                raise RuntimeError("CANARY_CONTRACT_QUALIFICATION_MISMATCH")
            contract = qualified[0]

        entry_ref = f"codex-ibkr-paper-30d-canary-entry-{request.sha256[:12]}"
        exit_ref = f"codex-ibkr-paper-30d-canary-exit-{request.sha256[:12]}"
        existing_refs = {
            str(getattr(item.order, "orderRef", "") or "")
            for item in evidence.get("trades", ())
        }
        if entry_ref in existing_refs or exit_ref in existing_refs:
            raise RuntimeError("CANARY_DUPLICATE_ORDER_PRESENT")

        def make_order(*, action: str, order_type: str, order_ref: str, quantity=None) -> Any:
            order = Order(
                action=action,
                orderType=order_type,
                tif=(request.entry_terms.time_in_force if order_ref == entry_ref
                     else "GTC" if order_type == "LMT" else "IOC"),
                totalQuantity=float(request.quantity if quantity is None else quantity),
                transmit=True,
                whatIf=False,
                orderRef=order_ref,
                outsideRth=request.entry_terms.outside_regular_hours,
            )
            if order_type == "LMT":
                price = (
                    request.entry_terms.limit_price
                    if order_ref == entry_ref
                    else evidence.get("flat_return_limit_price")
                )
                if price is None or Decimal(str(price)) <= 0:
                    raise RuntimeError("CANARY_LIMIT_PRICE_REQUIRED")
                order.lmtPrice = float(Decimal(str(price)))
            if hasattr(broker, "client") and hasattr(broker.client, "getReqId"):
                order.orderId = int(broker.client.getReqId())
            return order

        def wait_terminal(trade: Any) -> tuple[str, Decimal, Decimal]:
            deadline = time.monotonic() + self.broker_request_timeout_seconds
            while True:
                status = str(getattr(trade.orderStatus, "status", "") or "")
                filled = Decimal(str(getattr(trade.orderStatus, "filled", 0) or 0))
                remaining = Decimal(
                    str(getattr(trade.orderStatus, "remaining", 0) or 0)
                )
                if status in {"Filled", "Cancelled", "ApiCancelled", "Inactive"}:
                    return status, filled, remaining
                if time.monotonic() >= deadline:
                    try:
                        broker.cancelOrder(trade.order)
                    except Exception as exc:
                        raise RuntimeError("CANARY_CANCEL_STATE_UNCERTAIN") from exc
                    status = str(getattr(trade.orderStatus, "status", "") or "")
                    filled = Decimal(
                        str(getattr(trade.orderStatus, "filled", 0) or 0)
                    )
                    remaining = Decimal(
                        str(getattr(trade.orderStatus, "remaining", 0) or 0)
                    )
                    if status in {"Cancelled", "ApiCancelled", "Inactive"} and filled == 0:
                        return status, filled, remaining
                    raise RuntimeError("CANARY_ORDER_STATE_UNCERTAIN")
                if hasattr(broker, "sleep"):
                    broker.sleep(0.05)
                else:
                    time.sleep(0.05)

        entry_order = make_order(
            action=request.entry_terms.action,
            order_type=request.entry_terms.order_type,
            order_ref=entry_ref,
        )
        # Qualification/quotes may outlive a previously valid operator state.
        if self.execution_lock_verifier() is not True:
            raise CanaryPreWriteBlocked(("EXECUTION_LOCK_REQUIRED",))
        if not self._canary_supervision_ready():
            raise CanaryPreWriteBlocked(("CONTINUITY_WATCHDOG_UNHEALTHY",))
        if self.execution_lock_verifier() is not True:
            raise CanaryPreWriteBlocked(("EXECUTION_LOCK_REQUIRED",))
        current_controls = self.canary_evidence_collector(broker, request, evidence)
        reasons = self.canary_execution_adapter._authority_reasons(
            request, {**evidence, **dict(current_controls)}
        )
        if reasons:
            raise CanaryPreWriteBlocked(reasons)
        entry_trade = broker.placeOrder(contract, entry_order)
        yield ("BROKER_BOUND", 1, 0, False)
        status, filled, _remaining = wait_terminal(entry_trade)
        actual_quantity = request.quantity
        partial_entry = status != "Filled" or filled != request.quantity
        if partial_entry:
            # Terminal callbacks can precede execution/position updates.
            deadline = time.monotonic() + 2.0
            while True:
                entry_facts = self._canary_broker_facts(request, broker)
                entry_fills = entry_facts["fills"]
                actual_quantity = sum((Decimal(str(f["quantity"])) for f in entry_fills), Decimal(0))
                if actual_quantity or time.monotonic() >= deadline:
                    break
                broker.sleep(.1) if hasattr(broker, "sleep") else time.sleep(.1)
            signed = actual_quantity if request.entry_terms.action == "BUY" else -actual_quantity
            if (entry_facts["open_order_count"] != 0
                    or not 0 <= actual_quantity <= request.quantity
                    or Decimal(entry_facts["position_quantity"]) != signed
                    or (filled != 0 and filled != actual_quantity)
                    or any(f["action"] != request.entry_terms.action or f["order_ref"] != entry_ref
                           or f["order_id"] != int(entry_order.orderId)
                           or f["perm_id"] != int(entry_trade.order.permId)
                           for f in entry_fills)):
                raise RuntimeError("CANARY_PARTIAL_FILL_UNCERTAIN")
            if actual_quantity == 0:
                yield ("TERMINAL_NO_FILL", 0, 0, False)
                return
        if self.canary_broker_accounting is not None:
            self.canary_broker_accounting(request, self._canary_broker_facts(request, broker))
        yield ("ENTRY_FILL", 0, 1, False)
        yield ("POSITION_VISIBLE", 0, 1, False)
        yield ("MANAGEMENT_OBSERVED", 0, 1, False)

        refreshed_exit_price = self._canary_flat_return_limit_price(
            request, broker
        )
        if request.flat_return_plan.order_type == "LMT":
            if refreshed_exit_price is None:
                raise RuntimeError("CANARY_FLAT_RETURN_PRICE_UNRESOLVED")
            evidence["flat_return_limit_price"] = refreshed_exit_price

        exit_order = make_order(
            action=request.flat_return_plan.action,
            order_type=request.flat_return_plan.order_type,
            order_ref=exit_ref,
            quantity=actual_quantity,
        )
        if partial_entry:
            fresh = self._canary_broker_facts(request, broker)
            signed = actual_quantity if request.entry_terms.action == "BUY" else -actual_quantity
            def execution_signature(items):
                return sha256_json(sorted(
                    ({k: v for k, v in f.items() if k not in {"commission", "commission_currency"}}
                     for f in items), key=lambda f: f["execution_id_sha256"]))
            if (fresh["open_order_count"] != 0 or Decimal(fresh["position_quantity"]) != signed
                    or execution_signature(fresh["fills"]) != execution_signature(entry_facts["fills"])
                    or self.execution_lock_verifier() is not True):
                raise RuntimeError("CANARY_PARTIAL_FILL_UNCERTAIN")
        exit_trade = broker.placeOrder(contract, exit_order)
        exit_status, exit_filled, _exit_remaining = wait_terminal(exit_trade)
        if exit_status != "Filled" or exit_filled != actual_quantity:
            raise RuntimeError("CANARY_EXIT_NOT_FILLED")

        open_refs = {
            str(getattr(item.order, "orderRef", "") or "")
            for item in self._broker_list_read(
                "CANARY_OPEN_ORDERS", broker.reqAllOpenOrders
            )
        }
        positions = self._broker_list_read("CANARY_POSITIONS", getattr(broker, "reqPositions", broker.positions))
        canary_positions = [
            item
            for item in positions
            if int(getattr(item.contract, "conId", 0) or 0) == identity.con_id
            and Decimal(str(getattr(item, "position", 0) or 0)) != 0
        ]
        if entry_ref in open_refs or exit_ref in open_refs or canary_positions:
            raise RuntimeError("CANARY_FLAT_STATE_NOT_PROVEN")
        yield ("EXIT_FILL", 0, 0, False)
        yield ("FLAT_STATE", 0, 0, False)
        if self.canary_broker_accounting is not None:
            facts = self._canary_broker_facts(request, broker)
            reconciled = self.canary_broker_accounting(
                request, facts)
            reconcile_net = getattr(self.canary_broker_accounting, 'reconcile_with_broker', None)
            if not reconciled and callable(reconcile_net):
                reconciled = reconcile_net(request, broker, facts)
            if not reconciled:
                return
        yield ("ECONOMICS_RECONCILED", 0, 0, True)

    def _canary_broker_facts(self, request, broker, *, recovery_ref=None):
        evidence = self._collect_evidence(broker)
        if hasattr(broker, "reqPositions"):
            evidence["positions"] = self._broker_list_read("CANARY_POSITIONS", broker.reqPositions)
        identity = request.canonical_contract
        refs = {f"codex-ibkr-paper-30d-canary-entry-{request.sha256[:12]}",
                f"codex-ibkr-paper-30d-canary-exit-{request.sha256[:12]}"}
        if recovery_ref is not None:
            refs.add(recovery_ref)
        fills = []
        for fill in evidence["executions"]:
            execution = fill.execution
            if int(fill.contract.conId) != identity.con_id:
                continue
            if execution.orderRef not in refs:
                recognizes = getattr(self.canary_broker_accounting, 'recognizes_broker_fill', None)
                if callable(recognizes) and recognizes(fill):
                    continue
            if (execution.orderRef not in refs
                    or expected_identity_hash(execution.acctNumber) != request.account_identity_sha256
                    or int(execution.clientId) != self.execution_client_id
                    or int(execution.permId) <= 0):
                raise ValueError("CANARY_BROKER_FILL_IDENTITY_MISMATCH")
            commission = getattr(fill, "commissionReport", None)
            fee = None
            currency = ""
            if commission is not None and commission.execId == execution.execId:
                raw = Decimal(str(commission.commission))
                if raw.is_finite() and abs(raw) < Decimal("1000000"):
                    fee = str(raw)
                    currency = commission.currency
            fills.append({"execution_id_sha256": sha256_json(execution.execId),
                          "action": "BUY" if execution.side == "BOT" else "SELL" if execution.side == "SLD" else "UNKNOWN",
                          "quantity": str(execution.shares), "price": str(execution.price),
                          "order_ref": execution.orderRef, "order_id": int(execution.orderId),
                          "perm_id": int(execution.permId), "client_id": int(execution.clientId),
                          "commission": fee, "commission_currency": currency})
        matching_positions = [p for p in evidence["positions"] if int(p.contract.conId) == identity.con_id]
        if any(expected_identity_hash(p.account) != request.account_identity_sha256 for p in matching_positions):
            raise ValueError("CANARY_BROKER_POSITION_IDENTITY_MISMATCH")
        if len(matching_positions) > 1:
            raise ValueError("CANARY_BROKER_POSITION_IDENTITY_AMBIGUOUS")
        return {"account_identity_sha256": request.account_identity_sha256,
                "contract_identity_sha256": identity.sha256, "request_sha256": request.sha256,
                "complete": True, "observed_at_utc": self.now_utc().isoformat(),
                "position_quantity": str(sum((Decimal(str(p.position)) for p in matching_positions), Decimal("0"))),
                "average_cost": str(matching_positions[0].avgCost) if matching_positions else "0",
                "open_order_count": sum(int(t.contract.conId) == identity.con_id for t in evidence["trades"]),
                "fills": fills}

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
        """Collect broker evidence, then re-read DB authority, without a write tx."""

        try:
            evidence = self._collect_evidence(broker)
        except BrokerEvidenceTimeout as exc:
            return None, {}, (exc.reason_code,)
        except Exception as exc:
            return (
                None,
                {},
                (f"BROKER_EVIDENCE_UNAVAILABLE:{type(exc).__name__}",),
            )
        if self.production_authority_validator is None:
            return None, evidence, ()
        if self.production_broker_evidence_collector is None:
            return None, evidence, ("PRODUCTION_BROKER_EVIDENCE_COLLECTOR_REQUIRED",)
        try:
            broker_evidence = self.production_broker_evidence_collector(
                broker, request, evidence
            )
            if not isinstance(broker_evidence, ProductionBrokerEvidence):
                raise TypeError("ProductionBrokerEvidence required")
            liability_evidence = None
            if (
                isinstance(request, AuthorizedBrokerCommand)
                and request.command_type == BrokerCommandType.MODIFY
            ):
                if self.liability_evidence_collector is None:
                    return None, evidence, ("LIABILITY_EVIDENCE_COLLECTOR_REQUIRED",)
                liability_evidence = self.liability_evidence_collector(
                    broker, request, evidence
                )
                if not isinstance(liability_evidence, MaximumLiabilityEvidence):
                    raise TypeError("MaximumLiabilityEvidence required")
            decision = self.production_authority_validator.validate_before_write(
                request=request,
                broker_evidence=broker_evidence,
                liability_evidence=liability_evidence,
                now_utc=self.now_utc(),
                prior_authority_snapshot=prior_authority_snapshot,
            )
        except Exception as exc:
            return (
                None,
                evidence,
                (f"PRODUCTION_AUTHORITY_VALIDATION_FAILED:{type(exc).__name__}",),
            )
        enriched = {
            **evidence,
            "production_authority": {
                "authority_snapshot_sha256": decision.authority_snapshot_sha256,
                "broker_evidence_sha256": decision.broker_evidence_sha256,
                "liability_evidence_sha256": (
                    None
                    if decision.liability_result is None
                    else decision.liability_result.evidence_sha256
                ),
            },
        }
        return decision, enriched, decision.reason_codes

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

        def final_write_authority_check(
            write_context: dict[str, Any] | None = None,
        ) -> tuple[str, ...]:
            nonlocal decision, evidence, final_gate_invoked
            final_gate_invoked = True
            if self.coordinator.is_execution_expired(request.execution_key):
                return ("MODEL_EXECUTION_REQUEST_EXPIRED",)
            final_decision, final_evidence, final_reasons = (
                self._production_authority_read(
                    request=request,
                    broker=broker,
                    prior_authority_snapshot=(
                        None if decision is None else decision.authority_snapshot
                    ),
                )
            )
            if self.coordinator.is_execution_expired(request.execution_key):
                return ("MODEL_EXECUTION_REQUEST_EXPIRED",)
            decision = final_decision
            evidence = {
                **final_evidence,
                "request_sha256": request.sha256,
                "writer_thread_id": threading.get_ident(),
                "execution_client_id": self.execution_client_id,
                "model_write_context": dict(write_context or {}),
            }
            if final_reasons:
                return final_reasons
            legacy_reasons = tuple(self.authority_validator(request, evidence))
            if legacy_reasons:
                return legacy_reasons
            if request.input_bundle.multi_sleeve_v4_active:
                if (
                    self.sleeve_authority_reservation_store is None
                    or self.sleeve_authority_snapshot_reader is None
                    or self.sleeve_broker_evidence_collector is None
                ):
                    return ("SLEEVE_EXECUTION_AUTHORITY_REQUIRED",)
                try:
                    sleeve_broker_evidence = self.sleeve_broker_evidence_collector(
                        broker, request, evidence
                    )
                    reservation = self.sleeve_authority_reservation_store.reserve(
                        request,
                        sleeve_broker_evidence,
                        lambda: self.sleeve_authority_snapshot_reader(request),
                    )
                except Exception as exc:
                    return (
                        f"SLEEVE_EXECUTION_AUTHORITY_FAILED:{type(exc).__name__}",
                    )
                if reservation.status != "PASS":
                    return reservation.reason_codes
                evidence = {
                    **evidence,
                    "sleeve_execution_authority": reservation.model_dump(
                        mode="json"
                    ),
                }
            if self.coordinator.is_execution_expired(request.execution_key):
                return ("MODEL_EXECUTION_REQUEST_EXPIRED",)
            try:
                self.attempt_persister(request, evidence)
            except Exception:
                return ("MODEL_ATTEMPT_PERSISTENCE_FAILED",)
            if not self.coordinator.begin_write(request.execution_key):
                return ("MODEL_EXECUTION_REQUEST_EXPIRED",)
            return ()

        if (
            self.production_authority_validator is None
            and not request.input_bundle.multi_sleeve_v4_active
        ):
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
                or request.input_bundle.multi_sleeve_v4_active
                else None
            ),
        )
        if (
            (
                self.production_authority_validator is not None
                or request.input_bundle.multi_sleeve_v4_active
            )
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

        if command.command_type in {
            BrokerCommandType.REDUCE_POSITION,
            BrokerCommandType.CLOSE_POSITION,
        }:
            return self._execute_position_continuity(command, broker, evidence)

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

    @staticmethod
    def _position_identity(
        *, account_identity_sha256: str, contract_sha256: str, quantity: Decimal
    ) -> str:
        normalized = quantity.normalize()
        quantity_text = (
            str(normalized.quantize(Decimal("1")))
            if normalized == normalized.to_integral()
            else format(normalized, "f")
        )
        return sha256_json(
            {
                "account_identity_sha256": account_identity_sha256,
                "canonical_contract_sha256": contract_sha256,
                "signed_quantity": quantity_text,
            }
        )

    @staticmethod
    def _v4_contract_sha256(contract: Any) -> str:
        return v4_contract_identity(
            {
                "conId": int(getattr(contract, "conId", 0) or 0),
                "secType": str(getattr(contract, "secType", "") or ""),
                "currency": str(getattr(contract, "currency", "") or ""),
                "exchange": str(getattr(contract, "exchange", "") or ""),
                "primaryExchange": str(
                    getattr(contract, "primaryExchange", "") or ""
                )
                or None,
                "localSymbol": str(
                    getattr(contract, "localSymbol", "") or ""
                )
                or None,
                "tradingClass": str(
                    getattr(contract, "tradingClass", "") or ""
                )
                or None,
                "multiplier": str(getattr(contract, "multiplier", "") or "")
                or None,
                "comboLegs": [
                    {
                        "conId": int(getattr(leg, "conId", 0) or 0),
                        "ratio": int(getattr(leg, "ratio", 0) or 0),
                        "action": str(getattr(leg, "action", "") or ""),
                        "exchange": str(getattr(leg, "exchange", "") or ""),
                    }
                    for leg in list(getattr(contract, "comboLegs", None) or [])
                ],
            }
        ).sha256

    def _confirm_immediate_position_fill(
        self,
        *,
        broker: Any,
        command: AuthorizedBrokerCommand,
        order_ref: str,
        order_id: int,
        before_quantity: Decimal,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        executions = list(broker.reqExecutions())
        matches: list[Any] = []
        for fill in executions:
            execution = getattr(fill, "execution", fill)
            contract = getattr(fill, "contract", None)
            raw_side = str(getattr(execution, "side", "") or "").upper()
            side = "BUY" if raw_side in {"BUY", "BOT"} else "SELL" if raw_side in {"SELL", "SLD"} else raw_side
            if (
                str(getattr(execution, "orderRef", "") or "") == order_ref
                and int(getattr(execution, "orderId", 0) or 0) == order_id
                and int(getattr(execution, "clientId", -1) or -1)
                == self.execution_client_id
                and int(getattr(execution, "permId", 0) or 0) > 0
                and expected_identity_hash(
                    str(getattr(execution, "acctNumber", "") or "")
                )
                == command.account_identity_sha256
                and contract is not None
                and self._v4_contract_sha256(contract)
                == command.canonical_contract_sha256
                and side == command.position_action
            ):
                matches.append(fill)
        if not matches:
            raise RuntimeError("POST_WRITE_POSITION_EXECUTION_UNCONFIRMED")
        filled = sum(
            Decimal(
                str(
                    getattr(getattr(fill, "execution", fill), "shares", 0)
                    or 0
                )
            )
            for fill in matches
        )
        if filled != command.position_quantity:
            raise RuntimeError("POST_WRITE_POSITION_FILL_QUANTITY_UNCONFIRMED")
        perm_ids = {
            int(
                getattr(getattr(fill, "execution", fill), "permId", 0) or 0
            )
            for fill in matches
        }
        if len(perm_ids) != 1:
            raise RuntimeError("POST_WRITE_POSITION_PERM_ID_AMBIGUOUS")

        post_quantities: list[Decimal] = []
        for position in list(broker.positions()):
            contract = getattr(position, "contract", None)
            if (
                expected_identity_hash(
                    str(getattr(position, "account", "") or "")
                )
                == command.account_identity_sha256
                and contract is not None
                and self._v4_contract_sha256(contract)
                == command.canonical_contract_sha256
            ):
                post_quantities.append(
                    Decimal(str(getattr(position, "position", 0) or 0))
                )
        if len(post_quantities) > 1:
            raise RuntimeError("POST_WRITE_POSITION_IDENTITY_AMBIGUOUS")
        post_quantity = post_quantities[0] if post_quantities else Decimal("0")
        signed_delta = (
            command.position_quantity
            if command.position_action == "BUY"
            else -command.position_quantity
        )
        if post_quantity != before_quantity + signed_delta:
            raise RuntimeError("POST_WRITE_POSITION_QUANTITY_UNCONFIRMED")
        return (
            {
                "orderRef": order_ref,
                "orderId": order_id,
                "permId": next(iter(perm_ids)),
                "status": "Filled",
            },
            {
                "execution_count": len(matches),
                "filled_quantity": str(filled),
                "post_write_position_quantity": str(post_quantity),
            },
        )

    def _execute_position_continuity(
        self,
        command: AuthorizedBrokerCommand,
        broker: Any,
        evidence: dict[str, Any],
    ):
        from ib_insync import Order

        candidates: list[tuple[Any, str, Decimal]] = []
        for position in evidence.get("positions", ()):  # fresh, writer-owned read
            account_hash = expected_identity_hash(
                str(getattr(position, "account", "") or "")
            )
            contract = getattr(position, "contract", None)
            contract_hash = self._v4_contract_sha256(contract)
            if (
                account_hash == command.account_identity_sha256
                and contract_hash == command.canonical_contract_sha256
            ):
                candidates.append(
                    (
                        position,
                        contract_hash,
                        Decimal(str(getattr(position, "position", 0) or 0)),
                    )
                )
        if len(candidates) != 1:
            reason = (
                "CONTINUITY_POSITION_IDENTITY_AMBIGUOUS"
                if len(candidates) > 1
                else "CONTINUITY_POSITION_NOT_FOUND"
            )
            return self._result(
                success=False, status="BLOCKED", reasons=(reason,), evidence=evidence
            )
        position, contract_hash, signed_quantity = candidates[0]
        current_identity = self._position_identity(
            account_identity_sha256=command.account_identity_sha256,
            contract_sha256=contract_hash,
            quantity=signed_quantity,
        )
        if current_identity != command.position_identity_sha256:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("CONTINUITY_POSITION_IDENTITY_CHANGED",),
                evidence=evidence,
            )
        if signed_quantity == 0:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("CONTINUITY_POSITION_NOT_FOUND",),
                evidence=evidence,
            )
        required_action = "SELL" if signed_quantity > 0 else "BUY"
        assert command.position_action is not None
        assert command.position_quantity is not None
        if command.position_action != required_action:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("POSITION_ACTION_WOULD_INCREASE_EXPOSURE",),
                evidence=evidence,
            )
        current_size = abs(signed_quantity)
        if command.command_type == BrokerCommandType.REDUCE_POSITION:
            quantity_valid = command.position_quantity < current_size
            size_reason = "REDUCE_POSITION_SIZE_CHANGED_BEFORE_SEND"
        else:
            quantity_valid = command.position_quantity == current_size
            size_reason = "CLOSE_POSITION_SIZE_CHANGED_BEFORE_SEND"
        if not quantity_valid:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=(size_reason,),
                evidence=evidence,
            )

        order_ref = f"codex-ibkr-paper-30d-c-{command.sha256[:16]}"
        try:
            self.attempt_persister(command, evidence)
        except Exception:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=("CONTINUITY_ATTEMPT_PERSISTENCE_FAILED",),
                evidence=evidence,
            )
        try:
            order = Order(
                action=command.position_action,
                orderType=command.position_order_type,
                totalQuantity=float(command.position_quantity),
                transmit=True,
                whatIf=False,
                orderRef=order_ref,
                account=str(getattr(position, "account", "") or ""),
            )
            if command.position_limit_price is not None:
                order.lmtPrice = float(command.position_limit_price)
            order.orderId = int(broker.client.getReqId())
            trade = broker.placeOrder(position.contract, order)
            post_trades = list(broker.reqAllOpenOrders())
            post_matches = [
                item
                for item in post_trades
                if str(getattr(item.order, "orderRef", "") or "") == order_ref
                and int(getattr(item.order, "orderId", 0) or 0) == order.orderId
                and int(getattr(item.order, "permId", 0) or 0) > 0
                and int(getattr(item.order, "clientId", 0) or 0)
                == self.execution_client_id
            ]
            fill_evidence: dict[str, Any] = {}
            if len(post_matches) == 1:
                bound = post_matches[0]
                order_result = {
                    "orderRef": order_ref,
                    "orderId": int(getattr(bound.order, "orderId", 0) or 0),
                    "permId": int(getattr(bound.order, "permId", 0) or 0),
                    "status": str(
                        getattr(bound.orderStatus, "status", "UNKNOWN")
                        or "UNKNOWN"
                    ),
                }
                post_write_order = canonical_open_order(bound)
                status = "BROKER_BOUND"
            elif not post_matches:
                order_result, fill_evidence = self._confirm_immediate_position_fill(
                    broker=broker,
                    command=command,
                    order_ref=order_ref,
                    order_id=order.orderId,
                    before_quantity=signed_quantity,
                )
                post_write_order = order_result
                status = "FILLED"
            else:
                raise RuntimeError("POST_WRITE_POSITION_ORDER_IDENTITY_AMBIGUOUS")
            result = self._result(
                success=True,
                status=status,
                order=order_result,
                evidence={
                    **evidence,
                    "post_write_order": post_write_order,
                    **fill_evidence,
                },
            )
        except Exception:
            self._frozen_order_refs.add(order_ref)
            self._report_uncertainty("CONTINUITY_POSITION_ORDER_STATE_UNCERTAIN")
            return self._result(
                success=False,
                status="UNCERTAIN",
                reasons=("CONTINUITY_POSITION_ORDER_STATE_UNCERTAIN",),
                order={"orderRef": order_ref},
                evidence=evidence,
            )
        try:
            self.result_persister(command, result, result.broker_validation)
        except Exception:
            self._frozen_order_refs.add(order_ref)
            self._report_uncertainty("CONTINUITY_POSITION_ORDER_STATE_UNCERTAIN")
            return self._result(
                success=False,
                status="UNCERTAIN",
                reasons=("CONTINUITY_POSITION_ORDER_STATE_UNCERTAIN",),
                order={"orderRef": order_ref},
                evidence=result.broker_validation,
            )
        return result
