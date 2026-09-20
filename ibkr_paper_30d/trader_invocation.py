from __future__ import annotations

import json
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .canonical import canonical_bytes, sha256_json
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7


class TraderDecision(str, Enum):
    NO_TRADE = "NO_TRADE"
    PROPOSE_TRADE = "PROPOSE_TRADE"
    MONITOR_POSITION = "MONITOR_POSITION"
    REDUCE_POSITION = "REDUCE_POSITION"
    CLOSE_POSITION = "CLOSE_POSITION"
    PAUSE_FOR_REVIEW = "PAUSE_FOR_REVIEW"


class TraderInputBundle(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    decision_cycle_id: str
    utc_timestamp: str
    market_session_state: str
    reconciliation_receipt: dict[str, Any]
    experiment_subledger_snapshot: dict[str, Any]
    broker_account_snapshot: dict[str, Any]
    positions_snapshot: list[dict[str, Any]]
    open_orders_snapshot: list[dict[str, Any]]
    risk_snapshot: dict[str, Any]
    kill_switch_state: str
    market_data_snapshot: dict[str, Any]
    candidate_screen_results: list[dict[str, Any]]
    relevant_previous_immutable_decisions: list[dict[str, Any]]
    process_policy_version: str
    execution_realism_version: str
    benchmark_state: dict[str, Any]

    @property
    def sha256(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


class InvocationRequest(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    decision_cycle_id: str
    invocation_id: str
    utc_timestamp: str
    requested_model: str
    actual_model: str
    model_configuration: dict[str, Any]
    reasoning_effort: str
    input_bundle_sha256: str
    risk_policy_version: str
    experiment_id: str
    invocation_trigger: str
    timeout_seconds: int = Field(gt=0, le=600)
    fallback_reason: str | None = None


class TradeProposal(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    thesis: str
    mechanism: str
    catalyst: str
    symbol: str
    instrument: str
    direction: str
    entry_condition: str
    invalidation_condition: str
    profit_taking_rule: str
    expected_holding_period: str
    expected_reward: Decimal
    expected_risk: Decimal
    expected_reward_risk: Decimal
    why_now: str
    why_this_beats_cash: str
    best_reasonable_alternative: str
    disconfirming_evidence: list[str]
    confidence: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_risk_math(self) -> "TradeProposal":
        if self.expected_risk <= 0 or self.expected_reward <= 0:
            raise ValueError("expected reward and risk must be positive")
        return self


class TraderOutput(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    decision_cycle_id: str
    invocation_id: str
    decision: TraderDecision
    input_bundle_sha256: str
    utc_timestamp: str
    confidence: Decimal = Field(ge=0, le=1)
    reason_codes: list[str]
    proposal: TradeProposal | None = None

    @model_validator(mode="after")
    def proposal_matches_decision(self) -> "TraderOutput":
        if self.decision == TraderDecision.PROPOSE_TRADE and self.proposal is None:
            raise ValueError("PROPOSE_TRADE requires proposal")
        if self.decision != TraderDecision.PROPOSE_TRADE and self.proposal is not None:
            raise ValueError("proposal only allowed for PROPOSE_TRADE")
        return self


class ProviderResponse(BaseModel, frozen=True):
    actual_model: str
    fallback_reason: str | None = None
    structured_output: Any


class TraderProvider(Protocol):
    def invoke(
        self, request: InvocationRequest, bundle: TraderInputBundle
    ) -> ProviderResponse: ...


class ValidatedTraderResult(BaseModel, frozen=True):
    accepted: bool
    validation: str
    effective_decision: str
    reason_codes: tuple[str, ...]
    final_decision_hash: str
    order_authority: bool = False


class TraderInvocationAdapter:
    MAX_OUTPUT_BYTES = 131_072

    def __init__(self, db: Database, provider: TraderProvider):
        self.db = db
        self.provider = provider
        self.last_result: ValidatedTraderResult | None = None
        self.local_gate_status = "NOT_TESTED"
        self.real_codex_gate_status = "NOT_TESTED"

    def _persist_bundle(self, bundle: TraderInputBundle) -> str:
        bundle_id = f"bundle-{bundle.decision_cycle_id}"
        payload = bundle.model_dump(mode="json")
        encoded = canonical_bytes(payload).decode("utf-8")
        existing = self.db.execute(
            "SELECT payload_sha256 FROM trader_input_bundles WHERE bundle_id=?",
            (bundle_id,),
        ).fetchone()
        if existing is not None and str(existing[0]) != bundle.sha256:
            raise ValueError("decision cycle already bound to different input")
        self.db.execute(
            "INSERT OR IGNORE INTO trader_input_bundles(bundle_id,decision_cycle_id,payload_json,payload_sha256,created_at_utc) "
            "VALUES(?,?,?,?,?)",
            (bundle_id, bundle.decision_cycle_id, encoded, bundle.sha256, utc_now()),
        )
        return bundle_id

    def _persist_invocation(self, request: InvocationRequest, bundle_id: str) -> None:
        payload = request.model_dump(mode="json")
        encoded = canonical_bytes(payload).decode("utf-8")
        self.db.execute(
            "INSERT INTO trader_invocations(invocation_id,decision_cycle_id,bundle_id,payload_json,payload_sha256,created_at_utc) "
            "VALUES(?,?,?,?,?,?)",
            (
                request.invocation_id,
                request.decision_cycle_id,
                bundle_id,
                encoded,
                sha256_json(payload),
                utc_now(),
            ),
        )

    def _accepted_cycle_exists(self, cycle_id: str) -> bool:
        return (
            self.db.execute(
                "SELECT 1 FROM trader_results WHERE decision_cycle_id=? AND accepted=1",
                (cycle_id,),
            ).fetchone()
            is not None
        )

    def _finish(
        self,
        request: InvocationRequest,
        *,
        accepted: bool,
        validation: str,
        decision: str,
        reasons: tuple[str, ...],
        raw: Any,
        provider_metadata: dict[str, Any] | None = None,
    ) -> ValidatedTraderResult:
        evidence = {
            "invocation_id": request.invocation_id,
            "decision_cycle_id": request.decision_cycle_id,
            "accepted": accepted,
            "validation": validation,
            "effective_decision": decision,
            "reason_codes": reasons,
            "raw_structured_output": raw,
            "provider_metadata": provider_metadata or {},
        }
        digest = sha256_json(evidence)
        self.db.execute(
            "INSERT INTO trader_results(result_id,invocation_id,decision_cycle_id,accepted,accepted_cycle_key,"
            "payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
            (
                str(new_uuid7()),
                request.invocation_id,
                request.decision_cycle_id,
                1 if accepted else 0,
                request.decision_cycle_id if accepted else None,
                canonical_bytes(evidence).decode("utf-8"),
                digest,
                utc_now(),
            ),
        )
        result = ValidatedTraderResult(
            accepted=accepted,
            validation=validation,
            effective_decision=decision,
            reason_codes=reasons,
            final_decision_hash=digest,
            order_authority=False,
        )
        self.last_result = result
        if accepted:
            self.local_gate_status = "PASS"
        return result

    def _invalid(
        self,
        request: InvocationRequest,
        reason: str,
        raw: Any = None,
        provider_metadata: dict[str, Any] | None = None,
    ) -> ValidatedTraderResult:
        return self._finish(
            request,
            accepted=False,
            validation="INVALID",
            decision=TraderDecision.NO_TRADE.value,
            reasons=(reason,),
            raw=raw,
            provider_metadata=provider_metadata,
        )

    def invoke(
        self, request: InvocationRequest, bundle: TraderInputBundle
    ) -> ValidatedTraderResult:
        bundle_id = self._persist_bundle(bundle)
        self._persist_invocation(request, bundle_id)
        if self._accepted_cycle_exists(request.decision_cycle_id):
            return self._invalid(request, "DUPLICATE_ACCEPTED_CYCLE")
        if request.decision_cycle_id != bundle.decision_cycle_id:
            return self._invalid(request, "CYCLE_MISMATCH")
        if request.input_bundle_sha256 != bundle.sha256:
            return self._invalid(request, "INPUT_HASH_MISMATCH")
        if bundle.market_data_snapshot.get("gate_status") != "PASS":
            return self._invalid(request, "MARKET_DATA_GATE_BLOCK")
        try:
            response = self.provider.invoke(request, bundle)
        except TimeoutError:
            return self._invalid(request, "PROVIDER_TIMEOUT")
        except Exception as exc:
            return self._invalid(request, "PROVIDER_FAILURE", raw={"type": type(exc).__name__})

        metadata = {
            "requested_model": request.requested_model,
            "actual_model": response.actual_model,
            "fallback_reason": response.fallback_reason,
        }
        if response.actual_model != request.requested_model and not response.fallback_reason:
            return self._invalid(
                request,
                "SILENT_MODEL_SUBSTITUTION",
                raw=response.structured_output,
                provider_metadata=metadata,
            )
        if response.actual_model != request.actual_model:
            return self._invalid(
                request,
                "ACTUAL_MODEL_MISMATCH",
                raw=response.structured_output,
                provider_metadata=metadata,
            )
        try:
            if len(canonical_bytes(response.structured_output)) > self.MAX_OUTPUT_BYTES:
                return self._invalid(request, "OUTPUT_TOO_LARGE")
            parsed = TraderOutput.model_validate(response.structured_output)
        except (ValidationError, TypeError, ValueError):
            return self._invalid(
                request,
                "MALFORMED_OUTPUT",
                raw=response.structured_output,
                provider_metadata=metadata,
            )
        if parsed.decision_cycle_id != request.decision_cycle_id:
            return self._invalid(request, "CYCLE_MISMATCH", raw=parsed.model_dump(mode="json"))
        if parsed.invocation_id != request.invocation_id:
            return self._invalid(
                request, "INVOCATION_MISMATCH", raw=parsed.model_dump(mode="json")
            )
        if parsed.input_bundle_sha256 != bundle.sha256:
            return self._invalid(
                request, "INPUT_HASH_MISMATCH", raw=parsed.model_dump(mode="json")
            )
        if parsed.proposal is not None:
            candidates = {
                str(item.get("symbol", ""))
                for item in bundle.candidate_screen_results
            }
            if parsed.proposal.symbol not in candidates:
                return self._invalid(
                    request,
                    "SYMBOL_NOT_IN_FROZEN_CANDIDATES",
                    raw=parsed.model_dump(mode="json"),
                )
        return self._finish(
            request,
            accepted=True,
            validation="PASS",
            decision=parsed.decision.value,
            reasons=tuple(parsed.reason_codes),
            raw=parsed.model_dump(mode="json"),
            provider_metadata=metadata,
        )
