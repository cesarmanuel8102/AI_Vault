from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .canonical import canonical_bytes, sha256_json
from .canary_candidate import CanaryCandidateProposal, CanaryDiscoveryOutcome
from .continuity_models import (
    CodexOrderContinuityPlan,
    ContinuityReview,
    OrderBindingType,
    TimeInForce,
)
from .open_order_management import EXPERIMENT_ORDER_PREFIX
from .multi_universe_models import CapitalSleeve, SHA256_PATTERN
from .research_telemetry import (
    ResearchTelemetryAccumulator,
    build_telemetry_summary_from_history,
)
from .trader_invocation import (
    InvocationRequest,
    TraderDecision,
    TraderInputBundle,
    _assert_codex_actual_model,
)


def _resolve_codex_executable() -> str:
    explicit = os.environ.get("CODEX_CLI_EXECUTABLE")
    if explicit and Path(explicit).is_file():
        return explicit
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates = list(
            (Path(local_app_data) / "OpenAI" / "Codex" / "bin").glob(
                "*/codex.exe"
            )
        )
        if candidates:
            return str(max(candidates, key=lambda path: path.stat().st_mtime_ns))
    discovered = shutil.which("codex")
    if discovered:
        return discovered
    raise FileNotFoundError("CODEX_CLI_EXECUTABLE_NOT_FOUND")


class ResearchTool(str, Enum):
    ACCOUNT_STATE = "ACCOUNT_STATE"
    POSITIONS = "POSITIONS"
    OPEN_ORDERS = "OPEN_ORDERS"
    EXECUTIONS = "EXECUTIONS"
    MARKET_SCANNER = "MARKET_SCANNER"
    RESOLVE_CONTRACT = "RESOLVE_CONTRACT"
    QUOTE = "QUOTE"
    HISTORICAL_BARS = "HISTORICAL_BARS"
    OPTION_CHAIN = "OPTION_CHAIN"
    NEWS_SEARCH = "NEWS_SEARCH"
    BROKER_FEASIBILITY = "BROKER_FEASIBILITY"
    WORKSPACE = "WORKSPACE"
    RUN_RESEARCH_SCRIPT = "RUN_RESEARCH_SCRIPT"
    QUANTCONNECT = "QUANTCONNECT"


class ResearchRequest(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    tool: ResearchTool
    arguments: dict[str, Any]
    purpose: str


class ResearchResult(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    tool: ResearchTool
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class AutonomousTurnMode(str, Enum):
    RESEARCH = "RESEARCH"
    FINAL = "FINAL"


class ProposalLeg(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    sec_type: str
    action: str
    ratio: int = Field(gt=0)
    expiry: str | None = None
    strike: Decimal | None = None
    right: str | None = None
    exchange: str = "SMART"
    currency: str = "USD"


class AutonomousPositionAction(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    sec_type: str
    action: str
    quantity: Decimal = Field(gt=0)
    order_type: str
    limit_price: Decimal | None = None
    contract_id: int | None = None
    expiry: str | None = None
    strike: Decimal | None = None
    right: str | None = None
    reason: str
    capital_sleeve: CapitalSleeve | None = None
    product_family_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


class AutonomousOpenOrderAction(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    order_ref: str = Field(min_length=1)
    order_id: int = Field(gt=0)
    perm_id: int | None = Field(default=None, gt=0)
    client_id: int = Field(ge=0)
    contract_id: int = Field(gt=0)
    observed_state_sha256: str = Field(min_length=64, max_length=64)
    new_total_quantity: Decimal | None = Field(default=None, gt=0)
    new_limit_price: Decimal | None = Field(default=None, gt=0)
    new_tif: TimeInForce | None = None
    new_good_till_date_utc: datetime | None = None
    reason: str = Field(min_length=1)
    capital_sleeve: CapitalSleeve | None = None
    product_family_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_time_in_force(self) -> "AutonomousOpenOrderAction":
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


class AutonomousTradeProposal(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    thesis: str
    catalyst: str | None = None
    symbol: str
    sec_type: str
    direction: str
    action: str
    quantity: Decimal = Field(gt=0)
    order_type: str
    limit_price: Decimal | None = None
    expiry: str | None = None
    strike: Decimal | None = None
    right: str | None = None
    legs: list[ProposalLeg] = Field(default_factory=list)
    capital_required: Decimal = Field(ge=0)
    maximum_loss: Decimal = Field(ge=0)
    loss_is_bounded: bool
    probability_profit: Decimal = Field(ge=0, le=1)
    probability_loss: Decimal = Field(ge=0, le=1)
    expected_gain: Decimal = Field(ge=0)
    expected_loss: Decimal = Field(ge=0)
    expected_value: Decimal
    expected_reward_risk: Decimal | None = None
    expected_holding_period: str
    entry_condition: str
    invalidation_condition: str
    exit_plan: str
    why_now: str | None = None
    alternatives_considered: list[str]
    evidence_used: list[str]
    disconfirming_evidence: list[str]
    confidence: Decimal = Field(ge=0, le=1)
    capital_sleeve: CapitalSleeve | None = None
    product_family_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def probability_mass_is_sane(self) -> "AutonomousTradeProposal":
        total = self.probability_profit + self.probability_loss
        if total > Decimal("1.0001"):
            raise ValueError("probability_profit + probability_loss cannot exceed 1")
        return self


class AutonomousTurn(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    mode: AutonomousTurnMode
    research_requests: list[ResearchRequest] = Field(default_factory=list)
    decision: TraderDecision | None = None
    proposal: AutonomousTradeProposal | None = None
    position_action: AutonomousPositionAction | None = None
    open_order_action: AutonomousOpenOrderAction | None = None
    confidence: Decimal = Field(ge=0, le=1)
    reasoning_summary: str
    reason_codes: list[str] = Field(default_factory=list)
    continuity_plan: CodexOrderContinuityPlan | None = None
    continuity_reviews: list[ContinuityReview] = Field(default_factory=list)

    @model_validator(mode="after")
    def mode_consistency(self) -> "AutonomousTurn":
        if self.mode == AutonomousTurnMode.RESEARCH:
            if not self.research_requests:
                raise ValueError("RESEARCH mode requires at least one research request")
            if (
                self.decision is not None
                or self.proposal is not None
                or self.position_action is not None
                or self.open_order_action is not None
            ):
                raise ValueError("RESEARCH mode cannot contain a final decision")
        else:
            if self.research_requests:
                raise ValueError("FINAL mode cannot contain research requests")
            if self.decision is None:
                raise ValueError("FINAL mode requires decision")
            if (
                self.decision == TraderDecision.CANCEL_ORDER
                and self.continuity_plan is not None
            ):
                raise ValueError("CANCEL_ORDER cannot create continuity authority")
            if self.decision == TraderDecision.PROPOSE_TRADE:
                if (
                    self.proposal is None
                    or self.position_action is not None
                    or self.open_order_action is not None
                ):
                    raise ValueError("PROPOSE_TRADE requires proposal only")
                if (
                    self.continuity_plan is not None
                    and self.continuity_plan.order_binding.binding_type
                    == OrderBindingType.NEW_PROPOSAL
                ):
                    proposal_sha256 = sha256_json(self.proposal)
                    binding = self.continuity_plan.order_binding
                    if (
                        binding.proposal_sha256 != proposal_sha256
                        or binding.original_intent_sha256 != proposal_sha256
                    ):
                        raise ValueError(
                            "NEW_PROPOSAL proposal_sha256 and "
                            "original_intent_sha256 must equal canonical proposal "
                            f"SHA-256 {proposal_sha256}"
                        )
            elif self.decision in {TraderDecision.REDUCE_POSITION, TraderDecision.CLOSE_POSITION}:
                if (
                    self.position_action is None
                    or self.proposal is not None
                    or self.open_order_action is not None
                ):
                    raise ValueError("position-management decision requires position_action only")
            elif self.decision == TraderDecision.CANCEL_ORDER:
                if (
                    self.open_order_action is None
                    or self.proposal is not None
                    or self.position_action is not None
                    or self.open_order_action.new_total_quantity is not None
                    or self.open_order_action.new_limit_price is not None
                    or self.open_order_action.new_tif is not None
                    or self.open_order_action.new_good_till_date_utc is not None
                ):
                    raise ValueError("CANCEL_ORDER requires an unmodified open_order_action only")
            elif self.decision == TraderDecision.MODIFY_ORDER:
                if (
                    self.open_order_action is None
                    or self.proposal is not None
                    or self.position_action is not None
                    or (
                        self.open_order_action.new_total_quantity is None
                        and self.open_order_action.new_limit_price is None
                        and self.open_order_action.new_tif is None
                    )
                ):
                    raise ValueError("MODIFY_ORDER requires an effective open_order_action only")
            elif (
                self.proposal is not None
                or self.position_action is not None
                or self.open_order_action is not None
            ):
                raise ValueError("trade payload not allowed for this decision")
        return self


class CanaryDiscoveryTurn(BaseModel, frozen=True):
    """Dedicated read-only turn; it has no broker-execution payload."""

    model_config = ConfigDict(extra="forbid")

    mode: AutonomousTurnMode
    research_requests: list[ResearchRequest] = Field(default_factory=list)
    decision: Literal["CANDIDATE", "NO_CANDIDATE"] | None = None
    proposal: CanaryCandidateProposal | None = None
    reasoning_summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_mode(self) -> "CanaryDiscoveryTurn":
        if self.mode is AutonomousTurnMode.RESEARCH:
            if not self.research_requests or self.decision is not None or self.proposal is not None:
                raise ValueError("canary RESEARCH turn requires only research requests")
            return self
        if self.research_requests or self.decision is None:
            raise ValueError("canary FINAL turn requires a decision and no research requests")
        if (self.decision == "CANDIDATE") != (self.proposal is not None):
            raise ValueError("canary decision/proposal mismatch")
        return self


def validate_multi_sleeve_payload(
    bundle: TraderInputBundle,
    payload: AutonomousTradeProposal | AutonomousPositionAction | AutonomousOpenOrderAction | None,
) -> str | None:
    if not bundle.multi_sleeve_v4_active or payload is None:
        return None
    if payload.capital_sleeve is None:
        return "V4_SLEEVE_BINDING_REQUIRED"
    if payload.product_family_sha256 is None:
        return "V4_PRODUCT_FAMILY_BINDING_REQUIRED"
    portfolio = bundle.multi_sleeve_portfolio or {}
    if isinstance(payload, AutonomousTradeProposal):
        eligibility = (portfolio.get("entry_eligibility") or {}).get(
            payload.capital_sleeve.value
        )
        if not isinstance(eligibility, dict):
            return "V4_ENTRY_ELIGIBILITY_REQUIRED"
        if eligibility.get("status") != "PASS":
            return "SLEEVE_ENTRY_NOT_ELIGIBLE"
        if payload.product_family_sha256 not in set(
            eligibility.get("eligible_family_sha256") or ()
        ):
            return "PRODUCT_FAMILY_NOT_CURRENTLY_ELIGIBLE"
    if isinstance(payload, (AutonomousPositionAction, AutonomousOpenOrderAction)):
        contract_id = payload.contract_id
        ownership = bundle.contract_ownership_snapshot or {}
        durable = (ownership.get("contract_sleeves") or {}).get(str(contract_id))
        if durable is None:
            return "DURABLE_OWNERSHIP_REQUIRED"
        if durable != payload.capital_sleeve.value:
            return "DURABLE_OWNERSHIP_SLEEVE_MISMATCH"
    return None


def capital_equity_for_sleeve(
    bundle: TraderInputBundle,
    sleeve: CapitalSleeve | None,
) -> Decimal:
    """Return the only equity that may authorize the selected payload."""

    if bundle.multi_sleeve_v4_active:
        if sleeve is None:
            raise ValueError("V4_SLEEVE_BINDING_REQUIRED")
        key = {
            CapitalSleeve.REGULAR_SLEEVE: "regular",
            CapitalSleeve.CONTINUOUS_SLEEVE: "continuous",
        }[sleeve]
        portfolio = bundle.multi_sleeve_portfolio or {}
        sleeves = portfolio.get("sleeves") or {}
        sleeve_state = sleeves.get(key) or {}
        if (
            sleeve is CapitalSleeve.CONTINUOUS_SLEEVE
            and not sleeve_state
        ):
            sleeve_state = sleeves.get("extended") or {}
        raw = sleeve_state.get("equity_usd")
        if raw is None:
            raise ValueError("V4_SLEEVE_EQUITY_REQUIRED")
    else:
        raw = bundle.experiment_subledger_snapshot.get("equity")
        if raw is None:
            raise ValueError("experiment subledger equity is required")
    equity = Decimal(str(raw))
    if not equity.is_finite() or equity <= 0:
        raise ValueError("experimental equity must be positive")
    return equity


class ProposalValidation(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    reason_codes: tuple[str, ...]
    broker_evidence: dict[str, Any] = Field(default_factory=dict)


class ResearchToolbox(Protocol):
    def manifest(self) -> list[dict[str, Any]]: ...
    def execute(self, request: ResearchRequest, bundle: TraderInputBundle) -> ResearchResult: ...
    def validate_proposal(
        self, proposal: AutonomousTradeProposal, bundle: TraderInputBundle
    ) -> ProposalValidation: ...
    def validate_position_action(
        self,
        action: AutonomousPositionAction,
        bundle: TraderInputBundle,
        decision: TraderDecision,
    ) -> ProposalValidation: ...
    def validate_open_order_action(
        self,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
        decision: TraderDecision,
    ) -> ProposalValidation: ...


class AutonomousModelProvider(Protocol):
    def next_turn(
        self,
        request: InvocationRequest,
        bundle: TraderInputBundle,
        history: list[dict[str, Any]],
        toolbox_manifest: list[dict[str, Any]],
    ) -> AutonomousTurn: ...


class CanaryCandidateModelProvider(Protocol):
    def next_canary_candidate(
        self,
        request: InvocationRequest,
        bundle: TraderInputBundle,
        history: list[dict[str, Any]],
        toolbox_manifest: list[dict[str, Any]],
    ) -> CanaryDiscoveryTurn: ...


class CodexAutonomousCLIProvider:
    """Codex decision provider for host-mediated autonomous research.

    Codex chooses which research tools to invoke. The host executes only the
    requested read-only tools and feeds the results back on the next turn.
    This keeps broker credentials and execution authority outside the model
    while leaving symbol, instrument, strategy, timeframe and sizing choices
    to Codex.
    """

    is_real_codex_provider = True

    NATIVE_TOOL_TYPES = frozenset({"web_search", "command_execution", "mcp_tool_call", "file_change"})

    def __init__(
        self,
        *,
        runner: Any = subprocess.run,
        codex_executable: str | None = None,
        retry_sleep: Any = time.sleep,
        owner_model_attestation_exception_sha256: str | None = None,
    ):
        if owner_model_attestation_exception_sha256 is not None and (
            len(owner_model_attestation_exception_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in owner_model_attestation_exception_sha256
            )
        ):
            raise ValueError("MODEL_ATTESTATION_EXCEPTION_SHA256_INVALID")
        self.runner = runner
        self.codex_executable = codex_executable
        self.retry_sleep = retry_sleep
        self.owner_model_attestation_exception_sha256 = (
            owner_model_attestation_exception_sha256
        )
        self.last_failure_code: str | None = None
        self.last_failure_detail: str | None = None
        self.last_native_tool_events: list[dict[str, Any]] = []
        self.last_model_attestation_mode = "SERVER_REPORTED"
        self._first_process_bootstrap: dict[str, Any] | None = None

    def install_first_process_bootstrap(self, value: dict[str, Any]) -> None:
        if self._first_process_bootstrap is not None:
            raise RuntimeError("FIRST_PROCESS_BOOTSTRAP_ALREADY_INSTALLED")
        self._first_process_bootstrap = copy.deepcopy(value)

    def _take_first_process_bootstrap(self) -> dict[str, Any] | None:
        value = self._first_process_bootstrap
        self._first_process_bootstrap = None
        return value

    def next_turn(
        self,
        request: InvocationRequest,
        bundle: TraderInputBundle,
        history: list[dict[str, Any]],
        toolbox_manifest: list[dict[str, Any]],
    ) -> AutonomousTurn:
        with tempfile.TemporaryDirectory(prefix="codex-autonomous-trader-") as raw_dir:
            workdir = Path(raw_dir)
            schema_path = workdir / "autonomous_turn_schema.json"
            output_path = workdir / "autonomous_turn.json"
            schema_path.write_text(
                json.dumps(self.strict_output_schema(), sort_keys=True), encoding="utf-8"
            )
            executable = self.codex_executable
            if executable is None:
                executable = (
                    _resolve_codex_executable()
                    if self.runner is subprocess.run
                    else "codex"
                )
            command = [
                executable, "--search", "exec", "--ephemeral", "--ignore-rules",
                "--ignore-user-config", "--skip-git-repo-check",
                "--sandbox", "read-only", "--json",
                "--model", request.requested_model,
                "-c", f'model_reasoning_effort="{request.reasoning_effort.lower()}"',
                "--output-schema", str(schema_path),
                "--output-last-message", str(output_path), "-",
            ]
            base_payload = self._prompt_payload(
                request,
                bundle,
                history,
                toolbox_manifest,
                workspace_context=getattr(self, "workspace_context", None),
                first_process_bootstrap=self._take_first_process_bootstrap(),
            )
            repair_context: dict[str, Any] | None = None
            maximum_repairs = 2
            for semantic_attempt in range(maximum_repairs + 1):
                payload = copy.deepcopy(base_payload)
                if repair_context is not None:
                    payload["semantic_repair"] = repair_context
                completed = None
                retry_delays = (1.0, 3.0)
                for attempt in range(len(retry_delays) + 1):
                    try:
                        completed = self.runner(
                            command,
                            input=canonical_bytes(payload).decode("utf-8"),
                            text=True,
                            capture_output=True,
                            timeout=request.timeout_seconds,
                            cwd=workdir,
                            env=self._sanitized_environment(),
                            check=False,
                        )
                    except subprocess.TimeoutExpired as exc:
                        self.last_failure_code = "TIMEOUT"
                        raise TimeoutError("autonomous Codex provider timed out") from exc
                    if completed.returncode == 0:
                        try:
                            if self.owner_model_attestation_exception_sha256 is None:
                                self._assert_effective_model(
                                    completed.stdout, request.requested_model
                                )
                                self.last_model_attestation_mode = "SERVER_REPORTED"
                            else:
                                self._assert_effective_model_with_owner_exception(
                                    completed.stdout, request.requested_model
                                )
                                self.last_model_attestation_mode = (
                                    "OWNER_EXCEPTION_REQUEST_PIN"
                                )
                        except RuntimeError as exc:
                            transient_jsonl = (
                                self.owner_model_attestation_exception_sha256 is not None
                                and str(exc).endswith(":invalid_jsonl")
                            )
                            if not transient_jsonl:
                                raise
                            self.last_failure_code = "ATTESTATION_INVALID_JSONL"
                            if attempt == len(retry_delays):
                                raise
                            self.retry_sleep(retry_delays[attempt])
                            continue
                        break
                    self.last_failure_code = f"RETURN_CODE_{completed.returncode}"
                    if completed.returncode != 1 or attempt == len(retry_delays):
                        raise RuntimeError("AUTONOMOUS_CODEX_PROVIDER_FAILED")
                    self.retry_sleep(retry_delays[attempt])
                assert completed is not None
                self.last_native_tool_events = self._native_tool_events(completed.stdout)
                raw: Any = None
                try:
                    raw = json.loads(output_path.read_text(encoding="utf-8"))
                    for item in raw.get("research_requests", []):
                        if isinstance(item, dict) and isinstance(
                            item.get("arguments"), str
                        ):
                            decoded_arguments = json.loads(item["arguments"])
                            if not isinstance(decoded_arguments, dict):
                                raise ValueError(
                                    "research request arguments must decode to an object"
                                )
                            item["arguments"] = decoded_arguments
                    turn = AutonomousTurn.model_validate(raw)
                except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
                    errors = self._semantic_validation_errors(exc)
                    self.last_failure_code = "OUTPUT_INVALID"
                    self.last_failure_detail = "; ".join(
                        error["message"] for error in errors
                    )[:2000]
                    if semantic_attempt == maximum_repairs:
                        raise RuntimeError("AUTONOMOUS_CODEX_OUTPUT_INVALID") from exc
                    repair_context = {
                        "attempt": semantic_attempt + 1,
                        "maximum_attempts": maximum_repairs,
                        "instruction": (
                            "Correct only the structural or semantic validation errors below. "
                            "Preserve your independent research and trading judgment. Return a "
                            "complete replacement object that satisfies the output contract."
                        ),
                        "invalid_output": raw,
                        "validation_errors": errors,
                    }
                    continue
                continuity_error = AutonomousResearchLoop._validate_continuity_turn(
                    turn,
                    request=request,
                    bundle=bundle,
                )
                if continuity_error is not None and semantic_attempt < maximum_repairs:
                    self.last_failure_code = "CONTINUITY_OUTPUT_INVALID"
                    self.last_failure_detail = continuity_error
                    repair_context = {
                        "attempt": semantic_attempt + 1,
                        "maximum_attempts": maximum_repairs,
                        "instruction": (
                            "Correct only the continuity contract error below. Preserve your "
                            "independent research, proposal, and trading judgment. Copy all "
                            "host provenance bindings exactly from continuity_contract and "
                            "return a complete replacement object."
                        ),
                        "invalid_output": raw,
                        "validation_errors": [
                            {
                                "location": ["continuity_plan"],
                                "message": continuity_error,
                                "type": "continuity_contract",
                            }
                        ],
                    }
                    continue
                self.last_failure_code = None
                self.last_failure_detail = None
                return turn
            raise AssertionError("semantic repair loop exhausted unexpectedly")

    def next_canary_candidate(
        self,
        request: InvocationRequest,
        bundle: TraderInputBundle,
        history: list[dict[str, Any]],
        toolbox_manifest: list[dict[str, Any]],
    ) -> CanaryDiscoveryTurn:
        """Run the same attested Codex provider in discovery-only mode."""

        with tempfile.TemporaryDirectory(prefix="codex-canary-discovery-") as raw_dir:
            workdir = Path(raw_dir)
            schema_path = workdir / "canary_discovery_schema.json"
            output_path = workdir / "canary_discovery_turn.json"
            schema_path.write_text(
                json.dumps(self.canary_strict_output_schema(), sort_keys=True),
                encoding="utf-8",
            )
            executable = self.codex_executable
            if executable is None:
                executable = (
                    _resolve_codex_executable()
                    if self.runner is subprocess.run
                    else "codex"
                )
            command = [
                executable,
                "--search",
                "exec",
                "--ephemeral",
                "--ignore-rules",
                "--ignore-user-config",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--json",
                "--model",
                request.requested_model,
                "-c",
                f'model_reasoning_effort="{request.reasoning_effort.lower()}"',
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            ]
            payload = self._canary_prompt_payload(
                request, bundle, history, toolbox_manifest
            )
            try:
                completed = self.runner(
                    command,
                    input=canonical_bytes(payload).decode("utf-8"),
                    text=True,
                    capture_output=True,
                    timeout=request.timeout_seconds,
                    cwd=workdir,
                    env=self._sanitized_environment(),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                self.last_failure_code = "TIMEOUT"
                raise TimeoutError("canary discovery Codex provider timed out") from exc
            if completed.returncode != 0:
                self.last_failure_code = f"RETURN_CODE_{completed.returncode}"
                raise RuntimeError("CANARY_DISCOVERY_CODEX_PROVIDER_FAILED")
            if self.owner_model_attestation_exception_sha256 is None:
                self._assert_effective_model(completed.stdout, request.requested_model)
                self.last_model_attestation_mode = "SERVER_REPORTED"
            else:
                self._assert_effective_model_with_owner_exception(
                    completed.stdout, request.requested_model
                )
                self.last_model_attestation_mode = "OWNER_EXCEPTION_REQUEST_PIN"
            self.last_native_tool_events = self._native_tool_events(completed.stdout)
            try:
                raw = json.loads(output_path.read_text(encoding="utf-8"))
                for item in raw.get("research_requests", []):
                    if isinstance(item, dict) and isinstance(item.get("arguments"), str):
                        decoded = json.loads(item["arguments"])
                        if not isinstance(decoded, dict):
                            raise ValueError(
                                "research request arguments must decode to an object"
                            )
                        item["arguments"] = decoded
                turn = CanaryDiscoveryTurn.model_validate(raw)
            except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
                self.last_failure_code = "OUTPUT_INVALID"
                raise RuntimeError("CANARY_DISCOVERY_CODEX_OUTPUT_INVALID") from exc
            self.last_failure_code = None
            self.last_failure_detail = None
            return turn

    @staticmethod
    def _canary_prompt_payload(
        request: InvocationRequest,
        bundle: TraderInputBundle,
        history: list[dict[str, Any]],
        toolbox_manifest: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "schema": "CODEX_CANARY_CANDIDATE_DISCOVERY_V1",
            "mandate": {
                "objective": (
                    "Select an exact PAPER continuous-market canary candidate only "
                    "when its expected information value and bounded economics justify it."
                ),
                "predefined_symbol_universe": False,
                "predefined_security_type": False,
                "fallback_candidate": False,
                "no_candidate_is_valid": True,
                "read_only_discovery": True,
                "broker_writes_prohibited": True,
                "instruction": (
                    "Independently investigate any technically available continuous-market "
                    "family and contract. Return NO_CANDIDATE when no exact candidate is "
                    "justified. For CANDIDATE, author the exact family, canonical contract "
                    "group, entry economics, expiry, and exact flat-return plan. Do not "
                    "substitute a host suggestion or assume that read-only evidence certifies "
                    "the family for ordinary execution."
                ),
            },
            "request": request.model_dump(mode="json"),
            "request_sha256": sha256_json(request),
            "bundle": bundle.model_dump(mode="json"),
            "toolbox": toolbox_manifest,
            "research_history": history,
            "output_contract": {
                "research_request_arguments": (
                    "Encode each research_requests[].arguments value as a JSON object string."
                ),
                "candidate_binding": (
                    "Copy all account, successor, approved-HEAD, invocation, family, contract, "
                    "economics, expiry, and flat-return bindings exactly from authenticated "
                    "evidence. The host validates every field and may reject the proposal."
                ),
            },
        }

    @staticmethod
    def _semantic_validation_errors(exc: Exception) -> list[dict[str, Any]]:
        if isinstance(exc, ValidationError):
            return [
                {
                    "location": [str(value) for value in error.get("loc", ())],
                    "message": str(error.get("msg", "validation failed")),
                    "type": str(error.get("type", "value_error")),
                }
                for error in exc.errors()
            ]
        return [
            {
                "location": [],
                "message": str(exc) or type(exc).__name__,
                "type": type(exc).__name__,
            }
        ]

    @staticmethod
    def _prompt_payload(
        request: InvocationRequest,
        bundle: TraderInputBundle,
        history: list[dict[str, Any]],
        toolbox_manifest: list[dict[str, Any]],
        workspace_context: dict[str, Any] | None = None,
        first_process_bootstrap: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = bundle.continuity_context
        host_provenance_bindings = {
            "created_by_model": request.actual_model,
            "model_attestation_sha256": sha256_json(
                {"actual_model": request.actual_model}
            ),
            "decision_cycle_id": request.decision_cycle_id,
            "invocation_id": request.invocation_id,
            "input_bundle_sha256": bundle.sha256,
            "epoch_id": context.get("epoch_id"),
            "definition_sha256": context.get("definition_sha256"),
            "clock_event_sha256": context.get("clock_event_sha256"),
            "owner_authorization_sha256": context.get(
                "owner_authorization_sha256"
            ),
        }
        host_new_proposal_bindings = {
            "order_ref": (
                f"{EXPERIMENT_ORDER_PREFIX}-a-"
                f"{request.decision_cycle_id[-12:]}"
            ),
        }
        payload: dict[str, Any] = {
            "schema": "CODEX_AUTONOMOUS_RESEARCH_TURN_V1",
            "mandate": {
                "objective": "Maximize terminal experimental PAPER equity over the remaining experiment horizon.",
                "capital_can_be_fully_lost": True,
                "fixed_percent_risk_limits": False,
                "predefined_symbol_universe": False,
                "predefined_strategy_family": False,
                "predefined_timeframe": False,
                "broker_and_account_permissions_are_authoritative": True,
                "only_external_capital_boundary": "maximum experiment liability must not exceed current experimental equity",
                "no_trade_is_allowed": True,
                "no_trade_remains_valid": True,
                "capital_adaptive": True,
                "trading_frequency_is_not_success": True,
                "inactivity_is_not_success": True,
                "cash_preservation_is_not_success_by_itself": True,
                "risk_taking_is_not_success_by_itself": True,
                "avoidable_opportunity_cost_is_failure": True,
                "capital_and_remaining_time_are_scarce": True,
                "destroying_optionality_can_reduce_expected_terminal_equity": True,
                "failing_to_exploit_superior_positive_expectancy_opportunity_can_reduce_expected_terminal_equity": True,
                "immutable_environmental_constraints": [
                    "PAPER account only",
                    "LIVE execution prohibited",
                    "experimental capital boundary",
                    "account identity",
                    "execution authorization",
                    "kill switch",
                    "broker-write authority",
                    "execution idempotency",
                    "stale-data protections",
                    "audit integrity",
                    "no falsification or concealment of state",
                ],
                "may_not_modify_boundaries_to_improve_objective": True,
                "instruction": (
                    "You decide how to pursue the objective. You may decide what markets to investigate, what instruments "
                    "to consider, what strategies to formulate, what time horizons to use, what evidence matters, how much "
                    "research has marginal value, when to trade, when not to trade, when to change methodology, what tools "
                    "to build, what hypotheses to test, what information to retain, and how to learn from previous "
                    "observations and outcomes. There is no prescribed trading strategy, predefined universe, required "
                    "setup type, required research sequence, or required asset class.\n"
                    "NO_TRADE is a valid local decision whenever it is preferable to the available alternatives. Do not "
                    "trade merely to demonstrate activity. However, if your current process is not producing useful "
                    "progress toward the objective, you are expected to diagnose the cause, reconsider assumptions, "
                    "explore alternatives, acquire better information, develop useful capabilities, or replace an "
                    "ineffective methodology when doing so has positive expected value. Persist toward the objective "
                    "with adaptive methodology; neither a losing trade nor a failed strategy ends the pursuit.\n"
                    "You may use any legally permissible and technically authorized research resource available to the "
                    "environment when you judge that its expected value justifies its use, including public web "
                    "information, market data, news, IBKR read-only data, historical data, local Python, statistical "
                    "computation, local databases, QuantConnect, existing connected research services, public "
                    "documentation, and research tools you build yourself. You must not create paid subscriptions, "
                    "incur external financial costs, accept new contractual terms, expose credentials, create "
                    "financial accounts, circumvent access controls, violate licenses or terms, scrape illegally, or "
                    "evade paywalls. IBKR data and IBKR what-if remain authoritative for broker/account/contract "
                    "feasibility.\n"
                    "QuantConnect is available as an optional research laboratory for backtesting, historical "
                    "experiments, simulation, strategy validation, or other research if you decide it is useful. You "
                    "are not required to use QuantConnect.\n"
                    "You may build your own research tools and maintain persistent research artifacts when useful. "
                    "Use the WORKSPACE tool to inspect, create and manage your persistent research workspace, and "
                    "run your own research scripts with the RUN_RESEARCH_SCRIPT tool. Artifacts you create persist "
                    "across cycles.\n"
                    "If a useful investigation cannot fit within the current cycle, you may persist the research "
                    "objective and artifacts in your workspace and resume in a later cycle. This capability is "
                    "optional, not required.\n"
                    "The immutable environmental constraints listed in this mandate are properties of the "
                    "environment, not strategy suggestions. You may not improve the measured objective by modifying, "
                    "bypassing, disabling, or redefining them.\n"
                    "When continuity authority is required by the frozen bundle, you author its activation, expiry "
                    "mode, finite evidence conditions, exact executable actions, unavailable-evidence behavior, and "
                    "terminal disposition. The host validates and executes only what you state; it does not complete "
                    "missing economic intent."
                ),
            },
            "request": request.model_dump(mode="json"),
            "bundle": bundle.model_dump(mode="json"),
            "toolbox": toolbox_manifest,
            "research_history": history,
            "output_contract": {
                "research_request_arguments": (
                    "Encode each research_requests[].arguments value as a JSON "
                    "object string. The host decodes and validates it before use."
                ),
                "continuity_instruction": (
                    "When continuity authority is required, every final PROPOSE_TRADE or "
                    "MODIFY_ORDER must include a complete continuity_plan. Author its "
                    "activation, expiry, finite conditions, exact actions, unavailable-evidence "
                    "behavior, and terminal disposition. Copy host_provenance_bindings exactly; "
                    "do not calculate, infer, or invent those values. The host independently "
                    "verifies every binding. For a NEW_PROPOSAL, set order_binding."
                    "proposal_sha256 and order_binding.original_intent_sha256 to the "
                    "same canonical sha256_json of the complete proposal; do not hash "
                    "an order subset or use different values. For a NEW_PROPOSAL, copy "
                    "host_new_proposal_bindings exactly and copy account_identity_sha256, "
                    "contract_identity_sha256, and execution_client_id exactly from the "
                    "continuity_host_bindings returned by the successful BROKER_FEASIBILITY "
                    "for that exact proposal; do not infer or invent infrastructure identity."
                ),
            },
            "continuity_authority": bundle.continuity_context,
            "continuity_contract": {
                "authority_contract_required": bool(
                    context.get("authority_contract_required", False)
                ),
                "plan_required_for": ["PROPOSE_TRADE", "MODIFY_ORDER"],
                "host_provenance_bindings": host_provenance_bindings,
                "host_new_proposal_bindings": host_new_proposal_bindings,
                "host_verifies_bindings": True,
            },
        }
        if workspace_context:
            payload["workspace_context"] = workspace_context
        if first_process_bootstrap:
            payload["first_process_bootstrap"] = first_process_bootstrap
        return payload

    @staticmethod
    def strict_output_schema() -> dict[str, Any]:
        schema = AutonomousTurn.model_json_schema()

        def normalize(node: object) -> None:
            if isinstance(node, dict):
                node.pop("pattern", None)
                properties = node.get("properties")
                if isinstance(properties, dict):
                    node["required"] = list(properties)
                    node["additionalProperties"] = False
                for value in node.values():
                    normalize(value)
            elif isinstance(node, list):
                for value in node:
                    normalize(value)

        normalize(schema)
        state_actions = schema["$defs"]["ContinuityContingency"]["properties"][
            "state_actions"
        ]
        action_schema = state_actions["additionalProperties"]
        action_states = [
            value
            for value in schema["$defs"]["ContinuityOrderState"]["enum"]
            if value != "EVIDENCE_UNAVAILABLE"
        ]
        state_actions.pop("propertyNames", None)
        state_actions["properties"] = {
            value: copy.deepcopy(action_schema) for value in action_states
        }
        state_actions["required"] = action_states
        state_actions["additionalProperties"] = False
        arguments_schema = schema["$defs"]["ResearchRequest"]["properties"][
            "arguments"
        ]
        arguments_schema.clear()
        arguments_schema.update(
            {
                "type": "string",
                "description": (
                    "JSON object string containing the selected research tool arguments"
                ),
            }
        )
        return schema

    @staticmethod
    def canary_strict_output_schema() -> dict[str, Any]:
        schema = CanaryDiscoveryTurn.model_json_schema()

        def normalize(node: object) -> None:
            if isinstance(node, dict):
                node.pop("pattern", None)
                properties = node.get("properties")
                if isinstance(properties, dict):
                    node["required"] = list(properties)
                    node["additionalProperties"] = False
                for value in node.values():
                    normalize(value)
            elif isinstance(node, list):
                for value in node:
                    normalize(value)

        normalize(schema)
        arguments_schema = schema["$defs"]["ResearchRequest"]["properties"][
            "arguments"
        ]
        arguments_schema.clear()
        arguments_schema.update(
            {
                "type": "string",
                "description": "JSON object string containing read-only tool arguments",
            }
        )
        return schema

    @staticmethod
    def _assert_effective_model(output: object, requested_model: str) -> None:
        _assert_codex_actual_model(
            output,
            requested_model,
            error_prefix="AUTONOMOUS_CODEX_MODEL_SUBSTITUTION_DETECTED",
        )

    @staticmethod
    def _assert_effective_model_with_owner_exception(
        output: object, requested_model: str
    ) -> None:
        _assert_codex_actual_model(
            output,
            requested_model,
            error_prefix="AUTONOMOUS_CODEX_MODEL_SUBSTITUTION_DETECTED",
            allow_missing_actual_model=True,
        )

    @classmethod
    def _native_tool_events(cls, output: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item") if isinstance(event, dict) else None
            item_type = item.get("type") if isinstance(item, dict) else None
            if item_type in cls.NATIVE_TOOL_TYPES:
                events.append({
                    "type": item_type,
                    "status": item.get("status"),
                    "id": item.get("id"),
                })
        return events

    @staticmethod
    def _sanitized_environment() -> dict[str, str]:
        allowed = (
            "SYSTEMROOT", "WINDIR", "PATH", "USERPROFILE", "CODEX_HOME",
            "LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "HOME", "SSL_CERT_FILE",
            "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY",
        )
        return {name: os.environ[name] for name in allowed if name in os.environ}


class AutonomousResearchOutcome(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    validation: str
    decision: TraderDecision
    proposal: AutonomousTradeProposal | None
    position_action: AutonomousPositionAction | None
    open_order_action: AutonomousOpenOrderAction | None
    reason_codes: tuple[str, ...]
    rounds: int
    transcript: list[dict[str, Any]]
    transcript_sha256: str
    broker_validation: dict[str, Any] = Field(default_factory=dict)
    continuity_plan: CodexOrderContinuityPlan | None = None
    continuity_reviews: tuple[ContinuityReview, ...] = ()


class CanaryCandidateDiscoveryLoop:
    """Read-only model-directed discovery for an exact continuous canary."""

    def __init__(
        self,
        provider: CanaryCandidateModelProvider,
        toolbox: ResearchToolbox,
        *,
        event_persister: Callable[[str, dict[str, Any]], None] | None = None,
        max_rounds: int = 24,
        max_requests_per_round: int = 16,
    ) -> None:
        if max_rounds <= 0 or max_requests_per_round <= 0:
            raise ValueError("research loop limits must be positive")
        self.provider = provider
        self.toolbox = toolbox
        self.event_persister = event_persister or (lambda _kind, _payload: None)
        self.max_rounds = max_rounds
        self.max_requests_per_round = max_requests_per_round

    def run(
        self, request: InvocationRequest, bundle: TraderInputBundle
    ) -> CanaryDiscoveryOutcome:
        if request.decision_cycle_id != bundle.decision_cycle_id:
            raise ValueError("CYCLE_MISMATCH")
        if request.input_bundle_sha256 != bundle.sha256:
            raise ValueError("INPUT_HASH_MISMATCH")
        if bundle.reconciliation_receipt.get("status") != "PASS":
            raise ValueError("BROKER_RECONCILIATION_REQUIRED")
        if bundle.kill_switch_state != "KILL_SWITCH_CLEAR":
            raise ValueError("KILL_SWITCH_TRIGGERED")

        history: list[dict[str, Any]] = []
        manifest = self.toolbox.manifest()
        for round_index in range(1, self.max_rounds + 1):
            turn = self.provider.next_canary_candidate(
                request, bundle, history, manifest
            )
            history.append(
                {
                    "round": round_index,
                    "type": "model_turn",
                    "payload": turn.model_dump(mode="json"),
                }
            )
            if turn.mode is AutonomousTurnMode.RESEARCH:
                if len(turn.research_requests) > self.max_requests_per_round:
                    raise ValueError("RESEARCH_REQUEST_BATCH_TOO_LARGE")
                for research_request in turn.research_requests:
                    result = self.toolbox.execute(research_request, bundle)
                    event = {
                        "round": round_index,
                        "request": research_request.model_dump(mode="json"),
                        "result": result.model_dump(mode="json"),
                    }
                    history.append(
                        {
                            "round": round_index,
                            "type": "research_result",
                            "payload": event,
                        }
                    )
                    self.event_persister(
                        "CANARY_DISCOVERY_RESEARCH_EVENT", event
                    )
                continue

            transcript_sha256 = sha256_json(history)
            if turn.decision == "NO_CANDIDATE":
                outcome = CanaryDiscoveryOutcome(
                    decision="NO_CANDIDATE",
                    invocation_sha256=sha256_json(request),
                    result_sha256=sha256_json(turn),
                    transcript_sha256=transcript_sha256,
                )
                self.event_persister(
                    "CANARY_DISCOVERY_NO_CANDIDATE",
                    {
                        "outcome_sha256": outcome.sha256,
                        "transcript_sha256": transcript_sha256,
                    },
                )
                return outcome

            if turn.proposal is None:
                raise ValueError("CANARY_CANDIDATE_REQUIRED")
            outcome = CanaryDiscoveryOutcome(
                decision="CANDIDATE",
                invocation_sha256=turn.proposal.invocation_sha256,
                result_sha256=turn.proposal.result_sha256,
                transcript_sha256=transcript_sha256,
                proposal=turn.proposal,
            )
            self.event_persister(
                "CANARY_CANDIDATE_ACCEPTED",
                {
                    "candidate_id": turn.proposal.candidate_id,
                    "candidate_sha256": turn.proposal.sha256,
                    "outcome_sha256": outcome.sha256,
                    "transcript_sha256": transcript_sha256,
                },
            )
            return outcome
        raise RuntimeError("CANARY_DISCOVERY_MAX_ROUNDS_EXCEEDED")


class AutonomousResearchLoop:
    def __init__(
        self,
        provider: AutonomousModelProvider,
        toolbox: ResearchToolbox,
        *,
        max_rounds: int = 24,
        max_requests_per_round: int = 16,
    ) -> None:
        if max_rounds <= 0 or max_requests_per_round <= 0:
            raise ValueError("research loop limits must be positive")
        self.provider = provider
        self.toolbox = toolbox
        self.max_rounds = max_rounds
        self.max_requests_per_round = max_requests_per_round

    def run(
        self, request: InvocationRequest, bundle: TraderInputBundle
    ) -> AutonomousResearchOutcome:
        history: list[dict[str, Any]] = []
        telemetry = ResearchTelemetryAccumulator()
        if request.decision_cycle_id != bundle.decision_cycle_id:
            return self._blocked(history, telemetry, 0, "CYCLE_MISMATCH")
        if request.input_bundle_sha256 != bundle.sha256:
            return self._blocked(history, telemetry, 0, "INPUT_HASH_MISMATCH")
        if bundle.reconciliation_receipt.get("status") != "PASS":
            return self._blocked(history, telemetry, 0, "BROKER_RECONCILIATION_REQUIRED")
        if bundle.kill_switch_state != "KILL_SWITCH_CLEAR":
            return self._blocked(history, telemetry, 0, "KILL_SWITCH_TRIGGERED")
        if bundle.market_data_snapshot.get("gate_status") != "PASS":
            return self._blocked(history, telemetry, 0, "MARKET_DATA_GATE_BLOCK")

        manifest = self.toolbox.manifest()
        for round_index in range(1, self.max_rounds + 1):
            turn = self.provider.next_turn(request, bundle, history, manifest)
            history.append({
                "round": round_index,
                "type": "model_turn",
                "payload": turn.model_dump(mode="json"),
            })
            native_events = getattr(self.provider, "last_native_tool_events", None)
            if native_events:
                history.append({
                    "round": round_index,
                    "type": "native_tool_activity",
                    "payload": {"events": list(native_events)},
                })
            if turn.mode == AutonomousTurnMode.RESEARCH:
                if len(turn.research_requests) > self.max_requests_per_round:
                    return self._blocked(history, telemetry, round_index, "RESEARCH_REQUEST_BATCH_TOO_LARGE"
                    )
                for research_request in turn.research_requests:
                    telemetry.observe_request(research_request)
                    result = self.toolbox.execute(research_request, bundle)
                    telemetry.observe_result(result)
                    history.append({
                        "round": round_index,
                        "type": "research_result",
                        "payload": result.model_dump(mode="json"),
                    })
                continue

            continuity_error = self._validate_continuity_turn(
                turn, request=request, bundle=bundle
            )
            if continuity_error is not None:
                return self._blocked(
                    history, telemetry, round_index, continuity_error
                )

            selected_payload = (
                turn.proposal or turn.position_action or turn.open_order_action
            )
            sleeve_error = validate_multi_sleeve_payload(bundle, selected_payload)
            if sleeve_error is not None:
                return self._blocked(history, telemetry, round_index, sleeve_error)

            decision = turn.decision or TraderDecision.NO_TRADE
            if decision in {TraderDecision.CANCEL_ORDER, TraderDecision.MODIFY_ORDER}:
                action = turn.open_order_action
                if action is None:
                    return self._blocked(history, telemetry, round_index, "MISSING_OPEN_ORDER_ACTION")
                validation = self.toolbox.validate_open_order_action(
                    action, bundle, decision
                )
                history.append({
                    "round": round_index,
                    "type": "open_order_action_validation",
                    "payload": validation.model_dump(mode="json"),
                })
                if not validation.passed:
                    return self._finish(
                    telemetry=telemetry,
                    history=history,
                        rounds=round_index,
                        decision=TraderDecision.NO_TRADE,
                        proposal=None,
                        position_action=None,
                        open_order_action=None,
                        accepted=False,
                        validation="BLOCK",
                        reason_codes=validation.reason_codes,
                        broker_validation=validation.broker_evidence,
                    )
                return self._finish(
                    telemetry=telemetry,
                    history=history,
                    rounds=round_index,
                    decision=decision,
                    proposal=None,
                    position_action=None,
                    open_order_action=action,
                    accepted=True,
                    validation="PASS",
                    reason_codes=tuple(turn.reason_codes),
                    broker_validation=validation.broker_evidence,
                    continuity_plan=turn.continuity_plan,
                    continuity_reviews=tuple(turn.continuity_reviews),
                )

            if decision in {TraderDecision.REDUCE_POSITION, TraderDecision.CLOSE_POSITION}:
                action = turn.position_action
                if action is None:
                    return self._blocked(history, telemetry, round_index, "MISSING_POSITION_ACTION")
                validation = self.toolbox.validate_position_action(
                    action, bundle, decision
                )
                history.append({
                    "round": round_index,
                    "type": "position_action_validation",
                    "payload": validation.model_dump(mode="json"),
                })
                if not validation.passed:
                    return self._finish(
                    telemetry=telemetry,
                    history=history,
                        rounds=round_index,
                        decision=TraderDecision.MONITOR_POSITION,
                        proposal=None,
                        position_action=None,
                        accepted=False,
                        validation="BLOCK",
                        reason_codes=validation.reason_codes,
                        broker_validation=validation.broker_evidence,
                    )
                return self._finish(
                    telemetry=telemetry,
                    history=history,
                    rounds=round_index,
                    decision=decision,
                    proposal=None,
                    position_action=action,
                    accepted=True,
                    validation="PASS",
                    reason_codes=tuple(turn.reason_codes),
                    broker_validation=validation.broker_evidence,
                    continuity_plan=turn.continuity_plan,
                    continuity_reviews=tuple(turn.continuity_reviews),
                )

            if decision != TraderDecision.PROPOSE_TRADE:
                return self._finish(
                    telemetry=telemetry,
                    history=history,
                    rounds=round_index,
                    decision=decision,
                    proposal=None,
                    position_action=None,
                    accepted=True,
                    validation="PASS",
                    reason_codes=tuple(turn.reason_codes),
                    continuity_plan=turn.continuity_plan,
                    continuity_reviews=tuple(turn.continuity_reviews),
                )

            proposal = turn.proposal
            if proposal is None:
                return self._blocked(history, telemetry, round_index, "MISSING_PROPOSAL")
            if not proposal.loss_is_bounded:
                return self._blocked(history, telemetry, round_index, "UNBOUNDED_LIABILITY")
            equity = capital_equity_for_sleeve(bundle, proposal.capital_sleeve)
            if proposal.maximum_loss > equity:
                return self._blocked(history, telemetry, round_index, "EXPERIMENT_CAPITAL_BOUNDARY")
            # capital_required is a model estimate, not an authority boundary.
            # IBKR what-if margin/commission is authoritative for executability.
            validation = self.toolbox.validate_proposal(proposal, bundle)
            history.append({
                "round": round_index,
                "type": "proposal_validation",
                "payload": validation.model_dump(mode="json"),
            })
            if not validation.passed:
                return self._finish(
                    telemetry=telemetry,
                    history=history,
                    rounds=round_index,
                    decision=TraderDecision.NO_TRADE,
                    proposal=None,
                    position_action=None,
                    accepted=False,
                    validation="BLOCK",
                    reason_codes=validation.reason_codes,
                    broker_validation=validation.broker_evidence,
                )
            continuity_binding_error = self._validate_new_proposal_host_bindings(
                turn.continuity_plan,
                request=request,
                broker_evidence=validation.broker_evidence,
            )
            if continuity_binding_error is not None:
                return self._finish(
                    telemetry=telemetry,
                    history=history,
                    rounds=round_index,
                    decision=TraderDecision.NO_TRADE,
                    proposal=None,
                    position_action=None,
                    accepted=False,
                    validation="BLOCK",
                    reason_codes=(continuity_binding_error,),
                    broker_validation=validation.broker_evidence,
                )
            return self._finish(
                    telemetry=telemetry,
                    history=history,
                rounds=round_index,
                decision=decision,
                proposal=proposal,
                position_action=None,
                accepted=True,
                validation="PASS",
                reason_codes=tuple(turn.reason_codes),
                broker_validation=validation.broker_evidence,
                continuity_plan=turn.continuity_plan,
                continuity_reviews=tuple(turn.continuity_reviews),
            )

        return self._blocked(history, telemetry, self.max_rounds, "RESEARCH_ROUND_LIMIT_REACHED")

    @staticmethod
    def _validate_new_proposal_host_bindings(
        plan: CodexOrderContinuityPlan | None,
        *,
        request: InvocationRequest,
        broker_evidence: dict[str, Any],
    ) -> str | None:
        if plan is None:
            return None
        what_if = broker_evidence.get("what_if")
        host = (
            what_if.get("continuity_host_bindings")
            if isinstance(what_if, dict)
            else None
        )
        if not isinstance(host, dict):
            return "CONTINUITY_PLAN_HOST_BINDING_EVIDENCE_MISSING"
        binding = plan.order_binding
        expected_order_ref = (
            f"{EXPERIMENT_ORDER_PREFIX}-a-{request.decision_cycle_id[-12:]}"
        )
        if any(
            (
                binding.order_ref != expected_order_ref,
                binding.account_identity_sha256
                != host.get("account_identity_sha256"),
                binding.contract_identity_sha256
                != host.get("contract_identity_sha256"),
                binding.execution_client_id
                != host.get("execution_client_id"),
            )
        ):
            return "CONTINUITY_PLAN_HOST_BINDING_MISMATCH"
        return None

    @staticmethod
    def _validate_continuity_turn(
        turn: AutonomousTurn,
        *,
        request: InvocationRequest,
        bundle: TraderInputBundle,
    ) -> str | None:
        plan = turn.continuity_plan
        required = bool(
            bundle.continuity_context.get("authority_contract_required", False)
        )
        decision = turn.decision or TraderDecision.NO_TRADE
        if decision == TraderDecision.CANCEL_ORDER and plan is not None:
            return "CONTINUITY_PLAN_FORBIDDEN_FOR_CANCEL"
        if required and decision in {
            TraderDecision.PROPOSE_TRADE,
            TraderDecision.MODIFY_ORDER,
        } and plan is None:
            return "CONTINUITY_PLAN_REQUIRED"
        if plan is None:
            return None
        if decision not in {
            TraderDecision.PROPOSE_TRADE,
            TraderDecision.MODIFY_ORDER,
            TraderDecision.NO_TRADE,
        }:
            return "CONTINUITY_PLAN_DECISION_MISMATCH"
        if (
            plan.decision_cycle_id != request.decision_cycle_id
            or plan.invocation_id != request.invocation_id
            or plan.input_bundle_sha256 != bundle.sha256
            or plan.created_by_model != request.actual_model
        ):
            return "CONTINUITY_PLAN_PROVENANCE_MISMATCH"
        if plan.model_attestation_sha256 != sha256_json(
            {"actual_model": request.actual_model}
        ):
            return "CONTINUITY_PLAN_MODEL_ATTESTATION_MISMATCH"
        context = bundle.continuity_context
        for field in (
            "epoch_id",
            "definition_sha256",
            "clock_event_sha256",
            "owner_authorization_sha256",
        ):
            expected = context.get(field)
            if expected is not None and getattr(plan, field) != expected:
                return "CONTINUITY_PLAN_AUTHORITY_BINDING_MISMATCH"
        if decision == TraderDecision.PROPOSE_TRADE:
            if turn.proposal is None:
                return "CONTINUITY_PLAN_PROPOSAL_MISSING"
            proposal_hash = sha256_json(turn.proposal)
            if (
                plan.order_binding.binding_type != OrderBindingType.NEW_PROPOSAL
                or plan.order_binding.proposal_sha256 != proposal_hash
                or plan.order_binding.original_intent_sha256 != proposal_hash
            ):
                return "CONTINUITY_PLAN_PROPOSAL_MISMATCH"
            return None
        if plan.order_binding.binding_type != OrderBindingType.EXISTING_ORDER:
            return "CONTINUITY_PLAN_ORDER_BINDING_MISMATCH"
        action = turn.open_order_action
        if decision == TraderDecision.MODIFY_ORDER:
            if action is None or (
                plan.order_binding.order_ref != action.order_ref
                or plan.order_binding.ibkr_order_id != action.order_id
                or plan.order_binding.perm_id != action.perm_id
                or plan.order_binding.execution_client_id != action.client_id
                or plan.order_binding.contract_identity_sha256
                != sha256_json({"conId": action.contract_id})
            ):
                return "CONTINUITY_PLAN_ORDER_BINDING_MISMATCH"
            if plan.order_binding.original_intent_sha256 != sha256_json(action):
                return "CONTINUITY_PLAN_ACTION_MISMATCH"
            return None
        matches = [
            item
            for item in bundle.open_orders_snapshot
            if str(item.get("orderRef") or "") == plan.order_binding.order_ref
            and int(item.get("orderId") or 0)
            == int(plan.order_binding.ibkr_order_id or 0)
            and int(item.get("permId") or 0)
            == int(plan.order_binding.perm_id or 0)
            and int(item.get("clientId") or -1)
            == plan.order_binding.execution_client_id
        ]
        if len(matches) != 1:
            return "CONTINUITY_PLAN_ORDER_BINDING_MISMATCH"
        return None

    def _blocked(
        self,
        history: list[dict[str, Any]],
        telemetry: ResearchTelemetryAccumulator,
        rounds: int,
        reason: str,
    ) -> AutonomousResearchOutcome:
        return self._finish(
            telemetry=telemetry,
            history=history,
            rounds=rounds,
            decision=TraderDecision.NO_TRADE,
            proposal=None,
            position_action=None,
            accepted=False,
            validation="BLOCK",
            reason_codes=(reason,),
        )

    @staticmethod
    def _finish(
        *,
        telemetry: ResearchTelemetryAccumulator,
        history: list[dict[str, Any]],
        rounds: int,
        decision: TraderDecision,
        proposal: AutonomousTradeProposal | None,
        position_action: AutonomousPositionAction | None,
        accepted: bool,
        validation: str,
        reason_codes: tuple[str, ...],
        broker_validation: dict[str, Any] | None = None,
        open_order_action: AutonomousOpenOrderAction | None = None,
        continuity_plan: CodexOrderContinuityPlan | None = None,
        continuity_reviews: tuple[ContinuityReview, ...] = (),
    ) -> AutonomousResearchOutcome:
        history.append({
            "round": rounds,
            "type": "research_telemetry_summary",
            "payload": telemetry.summary(),
        })
        transcript_hash = sha256_json(history)
        return AutonomousResearchOutcome(
            accepted=accepted,
            validation=validation,
            decision=decision,
            proposal=proposal,
            position_action=position_action,
            open_order_action=open_order_action,
            reason_codes=reason_codes,
            rounds=rounds,
            transcript=history,
            transcript_sha256=transcript_hash,
            broker_validation=broker_validation or {},
            continuity_plan=continuity_plan,
            continuity_reviews=continuity_reviews,
        )

