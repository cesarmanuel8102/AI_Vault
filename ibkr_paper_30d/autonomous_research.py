from __future__ import annotations

import json
import os
import subprocess
import tempfile
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .canonical import canonical_bytes, sha256_json
from .trader_invocation import InvocationRequest, TraderDecision, TraderInputBundle


class ResearchTool(str, Enum):
    ACCOUNT_STATE = "ACCOUNT_STATE"
    POSITIONS = "POSITIONS"
    OPEN_ORDERS = "OPEN_ORDERS"
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
    confidence: Decimal = Field(ge=0, le=1)
    reasoning_summary: str
    reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def mode_consistency(self) -> "AutonomousTurn":
        if self.mode == AutonomousTurnMode.RESEARCH:
            if not self.research_requests:
                raise ValueError("RESEARCH mode requires at least one research request")
            if self.decision is not None or self.proposal is not None:
                raise ValueError("RESEARCH mode cannot contain a final decision")
        else:
            if self.research_requests:
                raise ValueError("FINAL mode cannot contain research requests")
            if self.decision is None:
                raise ValueError("FINAL mode requires decision")
            if self.decision == TraderDecision.PROPOSE_TRADE and self.proposal is None:
                raise ValueError("PROPOSE_TRADE requires proposal")
            if self.decision != TraderDecision.PROPOSE_TRADE and self.proposal is not None:
                raise ValueError("proposal only allowed for PROPOSE_TRADE")
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

    def __init__(self, *, runner: Any = subprocess.run):
        self.runner = runner
        self.last_failure_code: str | None = None

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
            command = [
                "codex", "exec", "--ephemeral", "--ignore-rules",
                "--ignore-user-config", "--skip-git-repo-check",
                "--sandbox", "read-only", "--json",
                "--model", request.requested_model,
                "-c", f'model_reasoning_effort="{request.reasoning_effort.lower()}"',
                "--output-schema", str(schema_path),
                "--output-last-message", str(output_path), "-",
            ]
            payload = self._prompt_payload(request, bundle, history, toolbox_manifest)
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
            if completed.returncode != 0:
                self.last_failure_code = f"RETURN_CODE_{completed.returncode}"
                raise RuntimeError("AUTONOMOUS_CODEX_PROVIDER_FAILED")
            try:
                raw = json.loads(output_path.read_text(encoding="utf-8"))
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
                "trader_style": "aggressive_ambitious_probability_driven",
                "capital_can_be_fully_lost": True,
                "fixed_percent_risk_limits": False,
                "predefined_symbol_universe": False,
                "predefined_strategy_family": False,
                "predefined_timeframe": False,
                "broker_and_account_permissions_are_authoritative": True,
                "only_external_capital_boundary": "maximum experiment liability must not exceed current experimental equity",
                "no_trade_is_allowed": True,
                "capital_adaptive": True,
                "instruction": (
                    "You control the research agenda. Request whatever read-only market/broker research you need from the toolbox. "
                    "Do not assume prior candidate lists are exhaustive. Reassess instrument and strategy choices as equity, buying power, "
                    "broker feasibility and remaining time change. When evidence is sufficient, return FINAL."
                ),
            },
            "request": request.model_dump(mode="json"),
            "bundle": bundle.model_dump(mode="json"),
            "toolbox": toolbox_manifest,
            "research_history": history,
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
        return schema

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
        manifest = self.toolbox.manifest()
        equity = self._experimental_equity(bundle)

        for round_index in range(1, self.max_rounds + 1):
            turn = self.provider.next_turn(request, bundle, history, manifest)
            history.append({
                "round": round_index,
                "type": "model_turn",
                "payload": turn.model_dump(mode="json"),
            })
            if turn.mode == AutonomousTurnMode.RESEARCH:
                if len(turn.research_requests) > self.max_requests_per_round:
                    return self._blocked(
                        history, round_index, "RESEARCH_REQUEST_BATCH_TOO_LARGE"
                    )
                for research_request in turn.research_requests:
                    result = self.toolbox.execute(research_request, bundle)
                    history.append({
                        "round": round_index,
                        "type": "research_result",
                        "payload": result.model_dump(mode="json"),
                    })
                continue

            decision = turn.decision or TraderDecision.NO_TRADE
            if decision != TraderDecision.PROPOSE_TRADE:
                return self._finish(
                    history=history,
                    rounds=round_index,
                    decision=decision,
                    proposal=None,
                    accepted=True,
                    validation="PASS",
                    reason_codes=tuple(turn.reason_codes),
                )

            proposal = turn.proposal
            if proposal is None:
                return self._blocked(history, round_index, "MISSING_PROPOSAL")
            if not proposal.loss_is_bounded:
                return self._blocked(history, round_index, "UNBOUNDED_LIABILITY")
            if proposal.maximum_loss > equity:
                return self._blocked(history, round_index, "EXPERIMENT_CAPITAL_BOUNDARY")
            if proposal.capital_required > equity:
                return self._blocked(history, round_index, "CAPITAL_REQUIRED_EXCEEDS_EQUITY")

            validation = self.toolbox.validate_proposal(proposal, bundle)
            history.append({
                "round": round_index,
                "type": "proposal_validation",
                "payload": validation.model_dump(mode="json"),
            })
            if not validation.passed:
                return self._finish(
                    history=history,
                    rounds=round_index,
                    decision=TraderDecision.NO_TRADE,
                    proposal=None,
                    accepted=False,
                    validation="BLOCK",
                    reason_codes=validation.reason_codes,
                    broker_validation=validation.broker_evidence,
                )
            return self._finish(
                history=history,
                rounds=round_index,
                decision=decision,
                proposal=proposal,
                accepted=True,
                validation="PASS",
                reason_codes=tuple(turn.reason_codes),
                broker_validation=validation.broker_evidence,
            )

        return self._blocked(history, self.max_rounds, "RESEARCH_ROUND_LIMIT_REACHED")

    def _blocked(
        self, history: list[dict[str, Any]], rounds: int, reason: str
    ) -> AutonomousResearchOutcome:
        return self._finish(
            history=history,
            rounds=rounds,
            decision=TraderDecision.NO_TRADE,
            proposal=None,
            accepted=False,
            validation="BLOCK",
            reason_codes=(reason,),
        )

    @staticmethod
    def _finish(
        *,
        history: list[dict[str, Any]],
        rounds: int,
        decision: TraderDecision,
        proposal: AutonomousTradeProposal | None,
        accepted: bool,
        validation: str,
        reason_codes: tuple[str, ...],
        broker_validation: dict[str, Any] | None = None,
    ) -> AutonomousResearchOutcome:
        transcript_hash = sha256_json(history)
        return AutonomousResearchOutcome(
            accepted=accepted,
            validation=validation,
            decision=decision,
            proposal=proposal,
            reason_codes=reason_codes,
            rounds=rounds,
            transcript=history,
            transcript_sha256=transcript_hash,
            broker_validation=broker_validation or {},
        )
