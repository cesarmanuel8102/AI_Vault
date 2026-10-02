"""Single-threaded owner of the only write-capable IBKR client session."""

from __future__ import annotations

import copy
import threading
from datetime import timezone
from decimal import Decimal
from typing import Any, Callable

from .broker_write_coordinator import (
    AuthorizedBrokerCommand,
    BrokerCommandType,
    BrokerWriteCoordinator,
)
from .canonical import sha256_json
from .ibkr_readonly import expected_identity_hash
from .open_order_management import ACTIONABLE_ORDER_STATUSES, canonical_open_order


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
            [AuthorizedBrokerCommand, Any, dict[str, Any]], None
        ]
        | None = None,
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
        self._capability = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._frozen_order_refs: set[str] = set()

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
        broker = None
        assert self._capability is not None
        try:
            broker = self.broker_factory(self.execution_client_id)
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
            return
        self._ready.set()
        try:
            while not self._stop.is_set():
                claimed = self.coordinator.claim(self._capability, timeout=0.05)
                if claimed is None:
                    continue
                command, future = claimed
                try:
                    result = self._execute(command, broker)
                except BaseException as exc:
                    result = self._result(
                        success=False,
                        status="UNCERTAIN",
                        reasons=(f"WRITER_INTERNAL_FAILURE:{type(exc).__name__}",),
                    )
                if not future.done():
                    future.set_result(result)
                self.coordinator.task_done(self._capability)
        finally:
            if broker is not None:
                try:
                    broker.disconnect()
                except Exception:  # nosec B110
                    pass
            self.coordinator.detach_writer(self._capability)

    def _collect_evidence(self, broker: Any) -> dict[str, Any]:
        if getattr(broker, "all_order_visibility", True) is not True:
            raise PermissionError("ALL_ORDER_VISIBILITY_UNCERTAIN")
        trades = list(broker.reqAllOpenOrders())
        executions = list(broker.reqExecutions())
        positions = list(broker.positions())
        return {
            "trades": trades,
            "open_orders": [canonical_open_order(item) for item in trades],
            "executions_count": len(executions),
            "positions_count": len(positions),
        }

    def _execute(self, command: AuthorizedBrokerCommand, broker: Any):
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
        try:
            evidence = self._collect_evidence(broker)
        except Exception as exc:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=(f"BROKER_EVIDENCE_UNAVAILABLE:{type(exc).__name__}",),
            )
        reasons = tuple(self.authority_validator(command, evidence))
        if reasons:
            return self._result(
                success=False, status="BLOCKED", reasons=reasons, evidence=evidence
            )

        try:
            evidence = self._collect_evidence(broker)
        except Exception as exc:
            return self._result(
                success=False,
                status="BLOCKED",
                reasons=(f"BROKER_EVIDENCE_UNAVAILABLE:{type(exc).__name__}",),
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
            return self._result(
                success=False,
                status="UNCERTAIN",
                reasons=("CONTINUITY_ORDER_STATE_UNCERTAIN",),
                order={"orderRef": command.order_ref},
                evidence=evidence,
            )
        return result
