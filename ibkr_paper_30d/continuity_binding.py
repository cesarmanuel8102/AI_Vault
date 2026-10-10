"""Atomic continuity-to-broker identity binding and crash recovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from .canonical import sha256_json
from .continuity_models import CodexOrderContinuityPlan, OrderBindingType
from .continuity_store import ContinuityStore
from .ibkr_readonly import expected_identity_hash
from .open_order_management import (
    _contract_identity_matches,
    append_order_registry_event,
    canonical_contract_identity,
)
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7


class ContinuityBindingError(RuntimeError):
    pass


@dataclass(frozen=True)
class PendingContinuityBinding:
    plan_id: str
    plan_sha256: str
    order_ref: str
    client_order_id: int
    contract_identity: dict[str, Any]
    account: str
    action: str
    quantity: str
    order_type: str
    routing: str
    execution_client_id: int
    invocation_id: str
    attempt_id: str
    pending_event_sha256: str


@dataclass(frozen=True)
class ActiveContinuityBinding:
    plan_id: str
    plan_sha256: str
    order_ref: str
    client_order_id: int
    perm_id: int
    active_event_sha256: str


@dataclass(frozen=True)
class BindingRecoveryResult:
    status: str
    reason_codes: tuple[str, ...]
    write_authority_frozen: bool
    active_binding: ActiveContinuityBinding | None = None


class ContinuityBindingService:
    def __init__(self, db: Database, store: ContinuityStore) -> None:
        self.db = db
        self.store = store

    @staticmethod
    def _plan_payload(plan: CodexOrderContinuityPlan, bindings: dict[str, Any]) -> dict[str, Any]:
        return {
            "plan": plan.model_dump(mode="json"),
            "plan_sha256": plan.sha256,
            "bindings": bindings,
        }

    def stage_new_order(
        self,
        plan: CodexOrderContinuityPlan,
        *,
        proposal_sha256: str,
        order_ref: str,
        client_order_id: int,
        contract_identity: dict[str, Any],
        account: str,
        action: str,
        quantity: str,
        order_type: str,
        routing: str,
        execution_client_id: int,
        invocation_id: str,
        attempt_id: str,
    ) -> PendingContinuityBinding:
        binding = plan.order_binding
        normalized_action = action.upper()
        normalized_order_type = order_type.upper()
        normalized_routing = routing.upper()
        normalized_quantity = str(Decimal(str(quantity)))
        checks = (
            (
                binding.binding_type == OrderBindingType.NEW_PROPOSAL,
                "NEW_PROPOSAL_PLAN_REQUIRED",
            ),
            (
                binding.account_identity_sha256 == expected_identity_hash(account),
                "ACCOUNT_IDENTITY_MISMATCH",
            ),
            (binding.order_ref == order_ref, "ORDER_REF_MISMATCH"),
            (
                binding.execution_client_id == int(execution_client_id),
                "EXECUTION_CLIENT_ID_MISMATCH",
            ),
            (
                binding.contract_identity_sha256 == sha256_json(contract_identity),
                "CONTRACT_IDENTITY_MISMATCH",
            ),
            (binding.action == normalized_action, "DIRECTION_MISMATCH"),
            (binding.order_type.upper() == normalized_order_type, "ORDER_TYPE_MISMATCH"),
            (
                binding.original_total_quantity == Decimal(normalized_quantity),
                "QUANTITY_MISMATCH",
            ),
            (binding.proposal_sha256 == proposal_sha256, "PROPOSAL_HASH_MISMATCH"),
        )
        for passed, reason in checks:
            if not passed:
                raise ContinuityBindingError(reason)
        if proposal_sha256 != plan.order_binding.original_intent_sha256:
            raise ContinuityBindingError("PROPOSAL_HASH_MISMATCH")
        if invocation_id != plan.invocation_id:
            raise ContinuityBindingError("INVOCATION_ID_MISMATCH")
        if not order_ref or client_order_id <= 0 or not account or not attempt_id:
            raise ContinuityBindingError("PENDING_BINDING_IDENTITY_INCOMPLETE")
        bindings = {
            "proposal_sha256": proposal_sha256,
            "order_ref": order_ref,
            "client_order_id": client_order_id,
            "contract_identity_sha256": sha256_json(contract_identity),
            "invocation_id": invocation_id,
            "attempt_id": attempt_id,
            "account_identity_sha256": binding.account_identity_sha256,
            "execution_client_id": int(execution_client_id),
        }
        if plan.schema == "CODEX_ORDER_CONTINUITY_PLAN_V4":
            bindings.update(
                {
                    "capital_sleeve": plan.capital_sleeve.value,
                    "canonical_contract_sha256": plan.canonical_contract_sha256,
                    "ownership_group_sha256": plan.ownership_group_sha256,
                    "product_family_sha256": plan.product_family_sha256,
                    "position_identity_sha256": plan.position_identity_sha256,
                    "sleeve_authority_sha256": plan.sleeve_authority_sha256,
                    "ownership_projection_sha256": (
                        plan.ownership_projection_sha256
                    ),
                }
            )
        registry_payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
            "lifecycle_event": "ISSUED_PRE_SEND",
            "continuity_state": "CONTINUITY_BIND_PENDING",
            "plan_id": plan.plan_id,
            "plan_sha256": plan.sha256,
            "proposal_sha256": proposal_sha256,
            "invocation_id": invocation_id,
            "attempt_id": attempt_id,
            "order_ref": order_ref,
            "client_order_id": client_order_id,
            "perm_id": 0,
            "ibkr_order_id": client_order_id,
            "contract_id": int(contract_identity.get("conId") or 0),
            "action": normalized_action,
            "quantity": normalized_quantity,
            "execution_client_id": int(execution_client_id),
            "account": account,
            "contract": contract_identity,
            "order_type": normalized_order_type,
            "routing": normalized_routing,
            "created_at_utc": utc_now(),
        }
        event_id = f"continuity-bind-pending:{plan.plan_id}:{attempt_id}"
        with self.db.transaction():
            conflict = self.db.execute(
                "SELECT 1 FROM experiment_order_registry "
                "WHERE order_ref=? AND json_extract(payload_json,'$.continuity_state')="
                "'CONTINUITY_BIND_PENDING' LIMIT 1",
                (order_ref,),
            ).fetchone()
            if conflict is not None:
                raise ContinuityBindingError("PENDING_BINDING_CONFLICT")
            append_order_registry_event(self.db, registry_payload)
            pending_hash = self.store._append(
                table="continuity_plan_events",
                event_id=event_id,
                stream_column="order_ref",
                stream_id=order_ref,
                event_type="BIND_PENDING",
                payload=self._plan_payload(plan, bindings),
                identity_columns={"plan_id": plan.plan_id, "order_ref": order_ref},
            )
        return PendingContinuityBinding(
            plan_id=plan.plan_id,
            plan_sha256=plan.sha256,
            order_ref=order_ref,
            client_order_id=client_order_id,
            contract_identity=contract_identity,
            account=account,
            action=normalized_action,
            quantity=normalized_quantity,
            order_type=normalized_order_type,
            routing=normalized_routing,
            execution_client_id=int(execution_client_id),
            invocation_id=invocation_id,
            attempt_id=attempt_id,
            pending_event_sha256=pending_hash,
        )

    @staticmethod
    def stage_and_send(
        stage: Callable[[], PendingContinuityBinding], send: Callable[[], Any]
    ) -> tuple[PendingContinuityBinding, Any]:
        pending = stage()
        return pending, send()

    def _load_plan(self, plan_id: str) -> CodexOrderContinuityPlan:
        row = self.db.execute(
            "SELECT payload_json FROM continuity_plan_events WHERE plan_id=? "
            "ORDER BY sequence DESC LIMIT 1",
            (plan_id,),
        ).fetchone()
        if row is None:
            raise ContinuityBindingError("PLAN_NOT_FOUND")
        payload = json.loads(str(row[0]))
        plan = CodexOrderContinuityPlan.model_validate(payload["plan"])
        if payload.get("plan_sha256") != plan.sha256:
            raise ContinuityBindingError("PLAN_HASH_MISMATCH")
        return plan

    @staticmethod
    def _validate_snapshot(
        pending: PendingContinuityBinding, snapshot: dict[str, Any]
    ) -> int:
        checks = (
            (str(snapshot.get("account") or "") == pending.account, "ACCOUNT_MISMATCH"),
            (int(snapshot.get("orderId") or 0) == pending.client_order_id, "ORDER_ID_MISMATCH"),
            (str(snapshot.get("orderRef") or "") == pending.order_ref, "ORDER_REF_MISMATCH"),
            (
                int(snapshot.get("clientId") or 0) == pending.execution_client_id,
                "EXECUTION_CLIENT_ID_MISMATCH",
            ),
            (str(snapshot.get("action") or "").upper() == pending.action, "DIRECTION_MISMATCH"),
            (str(snapshot.get("orderType") or "").upper() == pending.order_type, "ORDER_TYPE_MISMATCH"),
            (
                Decimal(str(snapshot.get("totalQuantity") or 0))
                == Decimal(pending.quantity),
                "QUANTITY_MISMATCH",
            ),
            (str((snapshot.get("contract") or {}).get("exchange") or "").upper() == pending.routing, "ROUTING_MISMATCH"),
            (
                _contract_identity_matches(
                    pending.contract_identity,
                    snapshot.get("contract") or {},
                    allow_zero_parent=True,
                ),
                "CONTRACT_MISMATCH",
            ),
        )
        for passed, reason in checks:
            if not passed:
                raise ContinuityBindingError(reason)
        perm_id = int(snapshot.get("permId") or 0)
        if perm_id <= 0:
            raise ContinuityBindingError("PERM_ID_REQUIRED")
        return perm_id

    def activate_broker_binding(
        self,
        pending: PendingContinuityBinding,
        snapshot: dict[str, Any],
        *,
        plan_sha256: str,
    ) -> ActiveContinuityBinding:
        if plan_sha256 != pending.plan_sha256:
            raise ContinuityBindingError("PLAN_HASH_MISMATCH")
        plan = self._load_plan(pending.plan_id)
        if plan.sha256 != plan_sha256:
            raise ContinuityBindingError("PLAN_HASH_MISMATCH")
        perm_id = self._validate_snapshot(pending, snapshot)
        registry_payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
            "lifecycle_event": "BROKER_BOUND",
            "continuity_state": "ACTIVE",
            "plan_id": plan.plan_id,
            "plan_sha256": plan.sha256,
            "attempt_id": pending.attempt_id,
            "order_ref": pending.order_ref,
            "client_order_id": pending.client_order_id,
            "perm_id": perm_id,
            "ibkr_order_id": pending.client_order_id,
            "contract_id": int(pending.contract_identity.get("conId") or 0),
            "action": pending.action,
            "quantity": pending.quantity,
            "execution_client_id": plan.order_binding.execution_client_id,
            "account": pending.account,
            "contract": pending.contract_identity,
            "order_type": pending.order_type,
            "routing": pending.routing,
            "created_at_utc": utc_now(),
        }
        event_id = f"continuity-active:{plan.plan_id}:{pending.attempt_id}"
        with self.db.transaction():
            existing = self.db.execute(
                "SELECT event_sha256 FROM continuity_plan_events WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if existing is not None:
                return ActiveContinuityBinding(
                    plan_id=plan.plan_id,
                    plan_sha256=plan.sha256,
                    order_ref=pending.order_ref,
                    client_order_id=pending.client_order_id,
                    perm_id=perm_id,
                    active_event_sha256=str(existing[0]),
                )
            if self.store.active_plan(pending.order_ref) is not None:
                raise ContinuityBindingError("ACTIVE_PLAN_CONFLICT")
            append_order_registry_event(self.db, registry_payload)
            active_hash = self.store._append(
                table="continuity_plan_events",
                event_id=event_id,
                stream_column="order_ref",
                stream_id=pending.order_ref,
                event_type="ACTIVATED",
                payload=self._plan_payload(
                    plan,
                    {
                        "pending_event_sha256": pending.pending_event_sha256,
                        "perm_id": perm_id,
                        "attempt_id": pending.attempt_id,
                    },
                ),
                identity_columns={"plan_id": plan.plan_id, "order_ref": pending.order_ref},
                expected_previous_event_sha256=pending.pending_event_sha256,
            )
        return ActiveContinuityBinding(
            plan_id=plan.plan_id,
            plan_sha256=plan.sha256,
            order_ref=pending.order_ref,
            client_order_id=pending.client_order_id,
            perm_id=perm_id,
            active_event_sha256=active_hash,
        )

    def terminate_pending_before_send(
        self,
        pending: PendingContinuityBinding,
        *,
        reason_code: str,
    ) -> None:
        """Close a staged binding when placeOrder was provably never invoked."""
        plan = self._load_plan(pending.plan_id)
        evidence = {
            "broker_write_attempted": False,
            "reason_code": str(reason_code),
        }
        payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
            "lifecycle_event": "CONTINUITY_BIND_TERMINAL",
            "continuity_state": "BIND_TERMINAL",
            "plan_id": pending.plan_id,
            "plan_sha256": pending.plan_sha256,
            "attempt_id": pending.attempt_id,
            "order_ref": pending.order_ref,
            "client_order_id": pending.client_order_id,
            "perm_id": 0,
            "ibkr_order_id": pending.client_order_id,
            "contract_id": int(pending.contract_identity.get("conId") or 0),
            "action": pending.action,
            "quantity": pending.quantity,
            "execution_client_id": pending.execution_client_id,
            "account": pending.account,
            "contract": pending.contract_identity,
            "order_type": pending.order_type,
            "routing": pending.routing,
            "status": "PRE_SEND_ABORTED",
            "recovery_evidence": evidence,
            "created_at_utc": utc_now(),
        }
        event_id = (
            f"continuity-bind-terminal:{pending.plan_id}:"
            f"{pending.attempt_id}:PRE_SEND_ABORTED"
        )
        with self.db.transaction():
            append_order_registry_event(self.db, payload)
            self.store._append(
                table="continuity_plan_events",
                event_id=event_id,
                stream_column="order_ref",
                stream_id=pending.order_ref,
                event_type="BIND_TERMINAL",
                payload=self._plan_payload(
                    plan,
                    {
                        "pending_event_sha256": pending.pending_event_sha256,
                        "attempt_id": pending.attempt_id,
                        "status": "PRE_SEND_ABORTED",
                        "evidence_sha256": sha256_json(evidence),
                    },
                ),
                identity_columns={
                    "plan_id": pending.plan_id,
                    "order_ref": pending.order_ref,
                },
                expected_previous_event_sha256=pending.pending_event_sha256,
            )

    def pending_binding(self, plan_id: str) -> PendingContinuityBinding:
        row = self.db.execute(
            "SELECT payload_json,payload_sha256 FROM experiment_order_registry "
            "WHERE json_extract(payload_json,'$.plan_id')=? "
            "ORDER BY sequence DESC LIMIT 1",
            (plan_id,),
        ).fetchone()
        if row is None:
            raise ContinuityBindingError("PENDING_BINDING_NOT_FOUND")
        payload = json.loads(str(row[0]))
        if sha256_json(payload) != str(row[1]):
            raise ContinuityBindingError("REGISTRY_HASH_MISMATCH")
        if payload.get("continuity_state") != "CONTINUITY_BIND_PENDING":
            raise ContinuityBindingError("PENDING_BINDING_NOT_FOUND")
        verified = self.store._verified_rows(
            "continuity_plan_events", "order_ref", str(payload["order_ref"])
        )
        plan_rows = [
            (body, event_sha)
            for event_type, body, event_sha in verified
            if event_type == "BIND_PENDING"
            and body.get("plan", {}).get("plan_id") == plan_id
            and body.get("bindings", {}).get("attempt_id") == payload.get("attempt_id")
        ]
        if len(plan_rows) != 1:
            raise ContinuityBindingError("PENDING_PLAN_EVENT_MISSING_OR_AMBIGUOUS")
        plan_body, pending_event_sha256 = plan_rows[0]
        if (
            plan_body.get("plan_sha256") != payload.get("plan_sha256")
            or plan_body.get("bindings", {}).get("proposal_sha256")
            != payload.get("proposal_sha256")
        ):
            raise ContinuityBindingError("PENDING_BINDING_HASH_MISMATCH")
        return PendingContinuityBinding(
            plan_id=plan_id,
            plan_sha256=str(payload["plan_sha256"]),
            order_ref=str(payload["order_ref"]),
            client_order_id=int(payload["client_order_id"]),
            contract_identity=dict(payload["contract"]),
            account=str(payload["account"]),
            action=str(payload["action"]),
            quantity=str(payload["quantity"]),
            order_type=str(payload["order_type"]),
            routing=str(payload["routing"]),
            execution_client_id=int(payload["execution_client_id"]),
            invocation_id=str(payload["invocation_id"]),
            attempt_id=str(payload["attempt_id"]),
            pending_event_sha256=pending_event_sha256,
        )

    def supersede_existing_order_plan(
        self,
        plan: CodexOrderContinuityPlan,
        *,
        accepted_result_sha256: str,
        expected_prior_sha256: str,
    ) -> str:
        binding = plan.order_binding
        if binding.binding_type != OrderBindingType.EXISTING_ORDER:
            raise ContinuityBindingError("EXISTING_ORDER_PLAN_REQUIRED")
        current = self.store.active_plan(plan.order_binding.order_ref)
        if (
            current is None
            or current.sha256 != expected_prior_sha256
            or plan.predecessor_plan_sha256 != expected_prior_sha256
        ):
            raise ContinuityBindingError("STALE_OR_MISMATCHED_PREDECESSOR")
        if not accepted_result_sha256:
            raise ContinuityBindingError("ACCEPTED_RESULT_REQUIRED")
        anchor_row = self.db.execute(
            "SELECT payload_json,payload_sha256 FROM experiment_order_registry "
            "WHERE order_ref=? AND perm_id>0 ORDER BY sequence DESC LIMIT 1",
            (binding.order_ref,),
        ).fetchone()
        if anchor_row is None:
            raise ContinuityBindingError("BROKER_BOUND_ANCHOR_REQUIRED")
        try:
            anchor = json.loads(str(anchor_row[0]))
        except (TypeError, json.JSONDecodeError) as exc:
            raise ContinuityBindingError("BROKER_BOUND_ANCHOR_INVALID") from exc
        if sha256_json(anchor) != str(anchor_row[1]):
            raise ContinuityBindingError("BROKER_BOUND_ANCHOR_HASH_MISMATCH")
        anchor_account = str(anchor.get("account") or "")
        anchor_account_hash = (
            expected_identity_hash(anchor_account) if anchor_account else ""
        )
        anchor_checks = (
            (str(anchor.get("order_ref") or "") == binding.order_ref, "ORDER_REF"),
            (
                int(anchor.get("ibkr_order_id") or 0) == int(binding.ibkr_order_id or 0),
                "ORDER_ID",
            ),
            (
                int(anchor.get("perm_id") or 0) == int(binding.perm_id or 0),
                "PERM_ID",
            ),
            (
                int(anchor.get("execution_client_id") or -1)
                == binding.execution_client_id,
                "EXECUTION_CLIENT_ID",
            ),
            (
                anchor_account_hash == binding.account_identity_sha256,
                "ACCOUNT_IDENTITY",
            ),
            (
                sha256_json(anchor.get("contract") or {})
                == binding.contract_identity_sha256,
                "CONTRACT_IDENTITY",
            ),
            (str(anchor.get("action") or "").upper() == binding.action, "DIRECTION"),
        )
        for passed, reason in anchor_checks:
            if not passed:
                raise ContinuityBindingError(
                    f"BROKER_BOUND_ANCHOR_{reason}_MISMATCH"
                )
        return self.store.append_plan_event(
            "SUPERSEDED",
            plan,
            bindings={"accepted_result_sha256": accepted_result_sha256},
        )

    def assert_plan_current(self, plan_id: str, plan_sha256: str) -> None:
        rows = self.db.execute(
            "SELECT DISTINCT order_ref FROM continuity_plan_events WHERE plan_id=?",
            (plan_id,),
        ).fetchall()
        if len(rows) != 1:
            raise ContinuityBindingError("STALE_PLAN")
        active = self.store.active_plan(str(rows[0][0]))
        if active is None or active.plan_id != plan_id or active.sha256 != plan_sha256:
            raise ContinuityBindingError("STALE_PLAN")


class PendingBindingReconciler:
    def __init__(self, service: ContinuityBindingService, broker: Any) -> None:
        self.service = service
        self.broker = broker

    @staticmethod
    def _execution_snapshot(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return dict(item)
        execution = getattr(item, "execution", item)
        raw_side = str(getattr(execution, "side", "") or "").upper()
        action = {"BOT": "BUY", "SLD": "SELL"}.get(raw_side, raw_side)
        return {
            "orderRef": str(getattr(execution, "orderRef", "") or ""),
            "orderId": int(getattr(execution, "orderId", 0) or 0),
            "permId": int(getattr(execution, "permId", 0) or 0),
            "clientId": int(getattr(execution, "clientId", 0) or 0),
            "account": str(
                getattr(execution, "acctNumber", "")
                or getattr(execution, "account", "")
                or ""
            ),
            "action": action,
            "shares": str(getattr(execution, "shares", 0) or 0),
            "cumQty": str(getattr(execution, "cumQty", 0) or 0),
            "contract": canonical_contract_identity(getattr(item, "contract", None)),
        }

    @staticmethod
    def _position_snapshot(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return dict(item)
        return {
            "account": str(getattr(item, "account", "") or ""),
            "position": str(getattr(item, "position", 0) or 0),
            "contract": canonical_contract_identity(getattr(item, "contract", None)),
        }

    @staticmethod
    def _execution_matches(
        pending: PendingContinuityBinding, snapshot: dict[str, Any]
    ) -> bool:
        return (
            str(snapshot.get("orderRef") or "") == pending.order_ref
            and int(snapshot.get("orderId") or 0) == pending.client_order_id
            and int(snapshot.get("clientId") or 0) == pending.execution_client_id
            and str(snapshot.get("account") or "") == pending.account
            and str(snapshot.get("action") or "").upper() == pending.action
            and int(snapshot.get("permId") or 0) > 0
            and _contract_identity_matches(
                pending.contract_identity,
                snapshot.get("contract") or {},
                allow_zero_parent=True,
            )
        )

    def _record_terminal(
        self,
        pending: PendingContinuityBinding,
        *,
        status: str,
        perm_id: int,
        evidence: dict[str, Any],
    ) -> BindingRecoveryResult:
        plan = self.service._load_plan(pending.plan_id)
        payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
            "lifecycle_event": "CONTINUITY_BIND_TERMINAL",
            "continuity_state": "BIND_TERMINAL",
            "plan_id": pending.plan_id,
            "plan_sha256": pending.plan_sha256,
            "attempt_id": pending.attempt_id,
            "order_ref": pending.order_ref,
            "client_order_id": pending.client_order_id,
            "perm_id": perm_id,
            "ibkr_order_id": pending.client_order_id,
            "contract_id": int(pending.contract_identity.get("conId") or 0),
            "action": pending.action,
            "quantity": pending.quantity,
            "execution_client_id": pending.execution_client_id,
            "account": pending.account,
            "contract": pending.contract_identity,
            "order_type": pending.order_type,
            "routing": pending.routing,
            "status": status,
            "recovery_evidence": evidence,
            "created_at_utc": utc_now(),
        }
        event_id = (
            f"continuity-bind-terminal:{pending.plan_id}:"
            f"{pending.attempt_id}:{status}"
        )
        with self.service.db.transaction():
            append_order_registry_event(self.service.db, payload)
            self.service.store._append(
                table="continuity_plan_events",
                event_id=event_id,
                stream_column="order_ref",
                stream_id=pending.order_ref,
                event_type="BIND_TERMINAL",
                payload=self.service._plan_payload(
                    plan,
                    {
                        "pending_event_sha256": pending.pending_event_sha256,
                        "attempt_id": pending.attempt_id,
                        "status": status,
                        "evidence_sha256": sha256_json(evidence),
                    },
                ),
                identity_columns={
                    "plan_id": pending.plan_id,
                    "order_ref": pending.order_ref,
                },
                expected_previous_event_sha256=pending.pending_event_sha256,
            )
        return BindingRecoveryResult(
            "TERMINAL", (f"BROKER_ORDER_{status}",), False
        )

    def _critical(
        self, pending: PendingContinuityBinding, reason: str
    ) -> BindingRecoveryResult:
        self.service.store.append_watchdog_event(
            pending.order_ref,
            "BINDING_RECONCILIATION_CRITICAL",
            {
                "plan_id": pending.plan_id,
                "plan_sha256": pending.plan_sha256,
                "attempt_id": pending.attempt_id,
                "reason_code": reason,
            },
        )
        return BindingRecoveryResult("AMBIGUOUS", (reason,), True)

    def reconcile(self, plan_id: str) -> BindingRecoveryResult:
        pending = self.service.pending_binding(plan_id)
        # All broker reads complete before any persistence transaction begins.
        orders = [
            dict(item) if isinstance(item, dict) else canonical_open_order(item)
            for item in list(self.broker.reqAllOpenOrders())
        ]
        executions = [
            self._execution_snapshot(item)
            for item in list(self.broker.reqExecutions())
        ]
        positions = [
            self._position_snapshot(item)
            for item in list(self.broker.positions())
        ]
        exact = [
            item
            for item in orders
            if str(item.get("orderRef") or "") == pending.order_ref
            and int(item.get("orderId") or 0) == pending.client_order_id
            and int(item.get("clientId") or 0)
            == self.service._load_plan(plan_id).order_binding.execution_client_id
        ]
        if len(exact) > 1:
            return self._critical(pending, "ORDER_IDENTITY_AMBIGUOUS")
        if not exact:
            exact_executions = [
                item
                for item in executions
                if self._execution_matches(pending, item)
            ]
            perm_ids = {
                int(item.get("permId") or 0) for item in exact_executions
            }
            if len(perm_ids) > 1:
                return self._critical(pending, "EXECUTION_IDENTITY_AMBIGUOUS")
            filled_quantity = sum(
                (
                    Decimal(str(item.get("shares") or 0))
                    for item in exact_executions
                ),
                Decimal("0"),
            )
            if exact_executions and filled_quantity >= Decimal(pending.quantity):
                matching_positions = [
                    item
                    for item in positions
                    if str(item.get("account") or "") == pending.account
                    and _contract_identity_matches(
                        pending.contract_identity,
                        item.get("contract") or {},
                        allow_zero_parent=True,
                    )
                ]
                return self._record_terminal(
                    pending,
                    status="FILLED",
                    perm_id=next(iter(perm_ids)),
                    evidence={
                        "executions": exact_executions,
                        "matching_positions": matching_positions,
                    },
                )
            return BindingRecoveryResult(
                "EVIDENCE_UNAVAILABLE",
                (
                    "PARTIAL_FILL_WITHOUT_OPEN_ORDER"
                    if exact_executions
                    else "BROKER_ORDER_NOT_OBSERVED"
                ,),
                True,
            )
        snapshot = exact[0]
        status = str(snapshot.get("status") or "").upper().replace(" ", "")
        if status in {"CANCELLED", "APICANCELLED", "REJECTED", "INACTIVE", "FILLED"}:
            try:
                perm_id = self.service._validate_snapshot(pending, snapshot)
            except ContinuityBindingError as exc:
                return self._critical(pending, str(exc))
            return self._record_terminal(
                pending,
                status=status,
                perm_id=perm_id,
                evidence={"open_order": snapshot},
            )
        try:
            active = self.service.activate_broker_binding(
                pending, snapshot, plan_sha256=pending.plan_sha256
            )
        except ContinuityBindingError as exc:
            return self._critical(pending, str(exc))
        return BindingRecoveryResult("ACTIVE", (), False, active)
