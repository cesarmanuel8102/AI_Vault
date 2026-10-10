"""Supervision-first orchestration for one model-selected PAPER canary."""

from __future__ import annotations

from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping

from .canary_candidate import (
    CanaryCandidateProposal,
    CanaryDiscoveryOutcome,
    OwnerPilotAuthorization,
    bind_canary_authorization,
    validate_canary_candidate,
)
from .canary_execution import CanaryExecutionRequest, CanaryExecutionResult
from .autonomous_research import ResearchRequest, ResearchTool
from .canonical import sha256_json


def _contract_arguments(proposal: CanaryCandidateProposal) -> dict[str, Any]:
    identity = proposal.canonical_contract
    return {
        "con_id": identity.con_id,
        "sec_type": identity.security_type,
        "exchange": identity.exchange,
        "currency": identity.currency,
        "primary_exchange": identity.primary_exchange,
        "multiplier": identity.multiplier,
    }


def _positive_finite(value: Any) -> bool:
    try:
        normalized = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return False
    return normalized.is_finite() and normalized > 0


def collect_canary_capability_evidence(
    toolbox: Any,
    bundle: Any,
    proposal: CanaryCandidateProposal,
    *,
    now_utc: datetime,
) -> dict[str, Any]:
    """Recheck the exact proposal using only read-only/what-if broker tools."""

    contract_args = _contract_arguments(proposal)
    resolve = toolbox.execute(
        ResearchRequest(
            request_id=f"canary-resolve-{proposal.candidate_id}",
            tool=ResearchTool.RESOLVE_CONTRACT,
            arguments=contract_args,
            purpose="Requalify the exact model-selected canary contract.",
        ),
        bundle,
    )
    quote = toolbox.execute(
        ResearchRequest(
            request_id=f"canary-quote-{proposal.candidate_id}",
            tool=ResearchTool.QUOTE,
            arguments=contract_args,
            purpose="Refresh market data for the exact canary contract.",
        ),
        bundle,
    )
    feasibility_args = {
        **contract_args,
        "action": proposal.entry_terms.action,
        "order_type": proposal.entry_terms.order_type,
        "quantity": str(proposal.quantity),
        "limit_price": (
            None
            if proposal.entry_terms.limit_price is None
            else str(proposal.entry_terms.limit_price)
        ),
        "time_in_force": proposal.entry_terms.time_in_force,
    }
    feasibility = toolbox.execute(
        ResearchRequest(
            request_id=f"canary-whatif-{proposal.candidate_id}",
            tool=ResearchTool.BROKER_FEASIBILITY,
            arguments=feasibility_args,
            purpose="Verify exact PAPER what-if economics for the canary.",
        ),
        bundle,
    )
    resolved_contracts = (
        resolve.data.get("contracts", []) if resolve.success else []
    )
    contract_qualified = any(
        int(item.get("conId") or 0) == proposal.canonical_contract.con_id
        and str(item.get("secType") or "").upper()
        == proposal.canonical_contract.security_type
        for item in resolved_contracts
        if isinstance(item, Mapping)
    )
    quoted_contract = quote.data.get("contract") if quote.success else None
    quote_identity_exact = bool(
        isinstance(quoted_contract, Mapping)
        and int(quoted_contract.get("conId") or 0)
        == proposal.canonical_contract.con_id
    )
    market_data_verified = bool(
        quote_identity_exact
        and any(
            _positive_finite(quote.data.get(field))
            for field in ("bid", "ask", "last", "marketPrice")
        )
    )
    broker_feasibility_verified = bool(
        feasibility.success
        and feasibility.data.get("paper_only") is True
        and feasibility.data.get("whatIf") is True
        and feasibility.data.get("broker_economics_computed", True) is not False
    )
    expires_at = now_utc + timedelta(minutes=2)
    return {
        "invocation_id": proposal.invocation_id,
        "invocation_sha256": proposal.invocation_sha256,
        "result_sha256": proposal.result_sha256,
        "account_identity_sha256": proposal.account_identity_sha256,
        "successor_definition_sha256": proposal.successor_definition_sha256,
        "approved_head": proposal.approved_head,
        "product_family_sha256": proposal.product_family.sha256,
        "contract_identity_sha256": proposal.canonical_contract.sha256,
        "contract_group_sha256": proposal.contract_group.sha256,
        "entry_terms_sha256": proposal.entry_terms.sha256,
        "flat_return_plan_sha256": proposal.flat_return_plan.sha256,
        "quantity": str(proposal.quantity),
        "maximum_debit_usd": str(proposal.maximum_debit_usd),
        "maximum_loss_usd": str(proposal.maximum_loss_usd),
        "fee_allowance_usd": str(proposal.fee_allowance_usd),
        "paper_only": True,
        "fresh": bool(
            contract_qualified
            and market_data_verified
            and broker_feasibility_verified
        ),
        "broker_write_count": 0,
        "contract_qualified": contract_qualified,
        "market_data_verified": market_data_verified,
        "broker_feasibility_verified": broker_feasibility_verified,
        "observed_at_utc": now_utc,
        "expires_at_utc": expires_at,
        "resolve_result_sha256": sha256_json(resolve),
        "quote_result_sha256": sha256_json(quote),
        "feasibility_result_sha256": sha256_json(feasibility),
    }


class CanaryPilotOrchestrator:
    """Discover read-only first, then submit the exact durable candidate once."""

    def __init__(
        self,
        *,
        discovery_runner: Callable[[Any, Callable[[str, dict[str, Any]], None]], CanaryDiscoveryOutcome],
        capability_evidence_collector: Callable[
            [Any, CanaryCandidateProposal], Mapping[str, Any]
        ],
        store: Any,
        coordinator: Any,
        owner_pilot_authorization: OwnerPilotAuthorization,
        writer_binding_sha256: str,
        durable_sequence_allocator: Callable[[], int],
        now_utc: Callable[[], datetime],
        candidate_finalizer: Callable[[Any, Mapping[str, Any], Any], None]
        | None = None,
        lifecycle_finalizer: Callable[[Any, CanaryExecutionResult], None]
        | None = None,
        result_timeout_seconds: float = 300.0,
    ) -> None:
        if result_timeout_seconds <= 0 or result_timeout_seconds > 300:
            raise ValueError("result_timeout_seconds must be in (0, 300]")
        self.discovery_runner = discovery_runner
        self.capability_evidence_collector = capability_evidence_collector
        self.store = store
        self.coordinator = coordinator
        self.owner_pilot_authorization = owner_pilot_authorization
        self.writer_binding_sha256 = writer_binding_sha256
        self.durable_sequence_allocator = durable_sequence_allocator
        self.now_utc = now_utc
        self.candidate_finalizer = candidate_finalizer or (
            lambda _proposal, _evidence, _validation: None
        )
        self.lifecycle_finalizer = lifecycle_finalizer or (
            lambda _proposal, _result: None
        )
        self.result_timeout_seconds = result_timeout_seconds

    @staticmethod
    def _block(*reason_codes: str) -> dict[str, Any]:
        return {
            "schema": "CANARY_PILOT_ORCHESTRATION_RESULT_V1",
            "status": "BLOCK",
            "decision": "CANARY_BLOCKED",
            "reason_codes": list(dict.fromkeys(reason_codes)),
        }

    def discover(self, bundle: Any) -> dict[str, Any]:
        existing = self.store.load_candidate()
        if existing is not None:
            outcome = existing[0]
            return {
                "schema": "CANARY_PILOT_ORCHESTRATION_RESULT_V1",
                "status": "PASS",
                "decision": "CANDIDATE_READY",
                "candidate_sha256": outcome.proposal.sha256,
                "reason_codes": [],
            }
        outcome = self.discovery_runner(
            bundle, self.store.persist_discovery_event
        )
        if outcome.decision == "NO_CANDIDATE":
            self.store.persist_discovery_event(
                "CANARY_DISCOVERY_NO_CANDIDATE",
                {
                    "outcome_sha256": outcome.sha256,
                    "transcript_sha256": outcome.transcript_sha256,
                },
            )
            return {
                "schema": "CANARY_PILOT_ORCHESTRATION_RESULT_V1",
                "status": "PASS",
                "decision": "NO_CANDIDATE",
                "reason_codes": [],
            }
        proposal = outcome.proposal
        if proposal is None:
            return self._block("CANARY_CANDIDATE_REQUIRED")
        if tuple(proposal.contract_group.member_contracts) != (
            proposal.canonical_contract,
        ):
            return self._block("CANARY_EXECUTION_REPRESENTATION_UNSUPPORTED")
        evidence = dict(self.capability_evidence_collector(bundle, proposal))
        validation = validate_canary_candidate(
            proposal,
            read_only_capability_evidence=evidence,
            now_utc=self.now_utc(),
        )
        if validation.status != "PASS":
            self.store.persist_discovery_event(
                "CANARY_CANDIDATE_VALIDATION_BLOCK",
                {
                    "candidate_sha256": proposal.sha256,
                    "validation_sha256": validation.sha256,
                    "reason_codes": list(validation.reason_codes),
                },
            )
            return self._block(*validation.reason_codes)
        self.store.persist_candidate(outcome, evidence, validation)
        self.candidate_finalizer(proposal, evidence, validation)
        return {
            "schema": "CANARY_PILOT_ORCHESTRATION_RESULT_V1",
            "status": "PASS",
            "decision": "CANDIDATE_READY",
            "candidate_sha256": proposal.sha256,
            "reason_codes": [],
        }

    def execute(self, bundle: Any) -> dict[str, Any]:
        stored = self.store.load_candidate()
        if stored is None:
            return self._block("CANARY_CANDIDATE_REQUIRED")
        outcome = stored[0]
        proposal = outcome.proposal
        if proposal is None:
            return self._block("CANARY_CANDIDATE_REQUIRED")
        prior = self.store.load_result(proposal.sha256)
        if prior is not None:
            return dict(prior)
        evidence = dict(self.capability_evidence_collector(bundle, proposal))
        validation = validate_canary_candidate(
            proposal,
            read_only_capability_evidence=evidence,
            now_utc=self.now_utc(),
        )
        if validation.status != "PASS":
            return self._block(*validation.reason_codes)
        load_authorization = getattr(self.store, "load_authorization", None)
        authorization = (
            load_authorization(proposal.sha256)
            if callable(load_authorization)
            else None
        )
        if authorization is None:
            try:
                authorization = bind_canary_authorization(
                    proposal, self.owner_pilot_authorization, self.now_utc()
                )
            except ValueError as exc:
                reasons = tuple(
                    item for item in str(exc).split(";") if item
                ) or ("CANARY_AUTHORIZATION_BLOCK",)
                return self._block(*reasons)
            self.store.persist_authorization(
                candidate_sha256=proposal.sha256,
                authorization=authorization,
            )
        load_request = getattr(self.store, "load_request", None)
        request = (
            load_request(proposal.sha256) if callable(load_request) else None
        )
        if request is None:
            execution_key = (
                f"canary:{proposal.sha256}:{authorization.sha256}"
            )
            request = CanaryExecutionRequest(
                canary_id=proposal.candidate_id,
                durable_sequence=self.durable_sequence_allocator(),
                execution_key=execution_key,
                candidate_sha256=proposal.sha256,
                authorization_sha256=authorization.sha256,
                account_identity_sha256=proposal.account_identity_sha256,
                successor_definition_sha256=proposal.successor_definition_sha256,
                writer_binding_sha256=self.writer_binding_sha256,
                product_family=proposal.product_family,
                canonical_contract=proposal.canonical_contract,
                entry_terms=proposal.entry_terms,
                quantity=proposal.quantity,
                maximum_debit_usd=proposal.maximum_debit_usd,
                maximum_loss_usd=proposal.maximum_loss_usd,
                fee_allowance_usd=proposal.fee_allowance_usd,
                flat_return_plan=proposal.flat_return_plan,
                created_at_utc=self.now_utc(),
            )
            persist_request = getattr(self.store, "persist_request", None)
            if callable(persist_request):
                persist_request(proposal.sha256, request)
        execution_claimed = getattr(self.store, "execution_claimed", None)
        if callable(execution_claimed) and execution_claimed(
            request.execution_key
        ):
            return self._block("CANARY_RECOVERY_REQUIRED")
        future = self.coordinator.submit(request)
        try:
            result = future.result(timeout=self.result_timeout_seconds)
        except FutureTimeoutError:
            expire = getattr(self.coordinator, "expire_before_write", None)
            if callable(expire) and expire(request.execution_key):
                return self._block("CANARY_WRITER_TIMEOUT_PRE_WRITE")
            return self._block("CANARY_WRITER_TIMEOUT_AFTER_WRITE_START")
        except Exception as exc:
            return self._block(f"CANARY_WRITER_FAILED:{type(exc).__name__}")
        if not isinstance(result, CanaryExecutionResult):
            return self._block("CANARY_EXECUTION_RESULT_INVALID")
        if result.request_sha256 != request.sha256:
            return self._block("CANARY_EXECUTION_RESULT_MISMATCH")
        try:
            self.lifecycle_finalizer(proposal, result)
        except Exception:
            return self._block("CANARY_CERTIFICATION_FINALIZATION_FAILED")
        payload = {
            "schema": "CANARY_PILOT_ORCHESTRATION_RESULT_V1",
            "status": result.status,
            "decision": "CANARY_EXECUTED",
            "reason_codes": list(result.reason_codes),
            "candidate_sha256": proposal.sha256,
            "authorization_sha256": authorization.sha256,
            "request_sha256": request.sha256,
            "broker_write_boundary_crossed": result.broker_write_boundary_crossed,
            "projection": (
                None
                if result.projection is None
                else result.projection.model_dump(mode="json")
            ),
        }
        self.store.persist_result(proposal.sha256, payload)
        return payload
