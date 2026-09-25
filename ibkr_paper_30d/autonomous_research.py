from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .canonical import canonical_bytes, sha256_json
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
    reason: str = Field(min_length=1)


class AutonomousTradeProposal(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    thesis: str
    catalyst: str
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
    why_now: str
    alternatives_considered: list[str]
    evidence_used: list[str]
    disconfirming_evidence: list[str]
    confidence: Decimal = Field(ge=0, le=1)

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
            if self.decision == TraderDecision.PROPOSE_TRADE:
                if (
                    self.proposal is None
                    or self.position_action is not None
                    or self.open_order_action is not None
                ):
                    raise ValueError("PROPOSE_TRADE requires proposal only")
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
        self.last_native_tool_events: list[dict[str, Any]] = []
        self.last_model_attestation_mode = "SERVER_REPORTED"

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
            payload = self._prompt_payload(request, bundle, history, toolbox_manifest)
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
                self.last_failure_code = "OUTPUT_INVALID"
                raise RuntimeError("AUTONOMOUS_CODEX_OUTPUT_INVALID") from exc
            self.last_failure_code = None
            return turn

    @staticmethod
    def _prompt_payload(
        request: InvocationRequest,
        bundle: TraderInputBundle,
        history: list[dict[str, Any]],
        toolbox_manifest: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "schema": "CODEX_AUTONOMOUS_RESEARCH_TURN_V1",
            "mandate": {
                "objective": "Maximize terminal experimental equity over the remaining 30-day paper-trading experiment.",
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
                "shallow_research_with_habitual_no_trade_is_not_acceptable": True,
                "avoidable_opportunity_cost_is_failure": True,
                "capital_and_remaining_time_are_scarce": True,
                "destroying_optionality_can_reduce_expected_terminal_equity": True,
                "failing_to_exploit_superior_positive_expectancy_opportunity_can_reduce_expected_terminal_equity": True,
                "instruction": (
                    "You control the research agenda. Request whatever read-only market/broker research you need from the toolbox. "
                    "You may also use native Codex web search when available for public news, macro, filings, catalysts and market context. "
                    "IBKR data and IBKR what-if remain authoritative for broker/account/contract feasibility. "
                    "Do not assume prior candidate lists are exhaustive. Reassess instrument and strategy choices as equity, buying power, "
                    "broker feasibility and remaining time change. When evidence is sufficient, return FINAL.\n"
                    "Objective reasoning: your only objective is expected terminal experimental equity. "
                    "Conduct an active search for superior opportunities every cycle. "
                    "If your current discovery method repeatedly fails, change the search process: broaden or alter instruments, "
                    "asset classes, strategies, horizons, market regions, sessions, research tools and discovery methods, "
                    "limited only by actual broker/account/runtime feasibility. "
                    "Before concluding NO_TRADE, run a counterfactual challenge: state the best feasible alternative found, "
                    "why retaining capital and optionality dominates that alternative, and whether additional research has positive "
                    "expected value. NO_TRADE is valid only when retaining capital and optionality has the higher expected "
                    "contribution to terminal equity after adequate search. "
                    "Repeated NO_TRADE, stagnant equity or repeated inability to find opportunities must make you reconsider the search process, "
                    "never forced trading: the response to stagnation is a different search process, not a trade. Stop additional research only when its marginal expected value "
                    "is below its time/data cost or a sufficiently dominant actionable opportunity has been identified. "
                    "Never manufacture trades to satisfy activity expectations. "
                    "Preserve the experiment's optionality to exploit future opportunities unless risking it is justified by a "
                    "sufficiently compelling expected terminal-equity advantage; this is expected-value reasoning, not a fixed risk limit."
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
                )
            },
        }

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

    @staticmethod
    def _experimental_equity(bundle: TraderInputBundle) -> Decimal:
        raw = bundle.experiment_subledger_snapshot.get("equity")
        if raw is None:
            raise ValueError("experiment subledger equity is required")
        equity = Decimal(str(raw))
        if not equity.is_finite() or equity <= 0:
            raise ValueError("experimental equity must be positive")
        return equity

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
        equity = self._experimental_equity(bundle)

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
                )

            proposal = turn.proposal
            if proposal is None:
                return self._blocked(history, telemetry, round_index, "MISSING_PROPOSAL")
            if not proposal.loss_is_bounded:
                return self._blocked(history, telemetry, round_index, "UNBOUNDED_LIABILITY")
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
            )

        return self._blocked(history, telemetry, self.max_rounds, "RESEARCH_ROUND_LIMIT_REACHED")

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
        )

