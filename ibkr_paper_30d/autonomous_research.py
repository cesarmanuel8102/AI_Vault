from __future__ import annotations

import json
import os
import subprocess
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .canonical import canonical_bytes, sha256_json
from .redaction import redact_text
from .trader_invocation import (
    InvocationRequest,
    ProviderResponse,
    TraderInputBundle,
    TraderOutput,
)


class ResearchAction(str, Enum):
    RESEARCH = "RESEARCH"
    FINAL = "FINAL"


class ResearchRequest(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    tool: str
    arguments: dict[str, Any]
    purpose: str


class ResearchTurn(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    action: ResearchAction
    rationale_summary: str
    capital_state_assessment: str
    strategy_space_assessment: str
    research_requests: list[ResearchRequest] = Field(default_factory=list)
    final_output: TraderOutput | None = None

    @model_validator(mode="after")
    def validate_action(self) -> "ResearchTurn":
        if self.action == ResearchAction.RESEARCH:
            if not self.research_requests:
                raise ValueError("RESEARCH requires at least one research request")
            if self.final_output is not None:
                raise ValueError("RESEARCH cannot contain final_output")
        if self.action == ResearchAction.FINAL:
            if self.final_output is None:
                raise ValueError("FINAL requires final_output")
            if self.research_requests:
                raise ValueError("FINAL cannot contain research_requests")
        return self


class ResearchToolbox(Protocol):
    def manifest(self) -> dict[str, Any]: ...

    def execute(self, request: ResearchRequest) -> dict[str, Any]: ...


class AutonomousResearchProvider:
    """
    Multi-round Codex provider.

    Codex chooses what information to request.  Deterministic local code only
    executes the requested read-only market/broker tools and returns evidence.
    No scanner, strategy family, symbol list or timeframe is imposed by this
    provider.
    """

    is_real_codex_provider = True

    def __init__(
        self,
        toolbox: ResearchToolbox,
        *,
        runner: Any = subprocess.run,
        max_rounds: int = 8,
        max_requests_per_round: int = 12,
    ) -> None:
        if max_rounds < 1:
            raise ValueError("max_rounds must be positive")
        if max_requests_per_round < 1:
            raise ValueError("max_requests_per_round must be positive")
        self.toolbox = toolbox
        self.runner = runner
        self.max_rounds = max_rounds
        self.max_requests_per_round = max_requests_per_round
        self.last_event_count = 0
        self.last_tool_activity_detected = False
        self.last_failure_code: str | None = None
        self.last_failure_diagnostic: str | None = None

    def invoke(
        self, request: InvocationRequest, bundle: TraderInputBundle
    ) -> ProviderResponse:
        round_limit = min(self.max_rounds, bundle.research_round_budget)
        evidence: list[dict[str, Any]] = []
        seen_request_ids: set[str] = set()
        total_events = 0

        for round_index in range(1, round_limit + 1):
            turn, event_count = self._invoke_research_turn(
                request=request,
                bundle=bundle,
                evidence=evidence,
                round_index=round_index,
                round_limit=round_limit,
            )
            total_events += event_count

            if turn.action == ResearchAction.FINAL:
                assert turn.final_output is not None
                self.last_event_count = total_events
                return ProviderResponse(
                    actual_model=request.requested_model,
                    fallback_reason=None,
                    structured_output=turn.final_output.model_dump(mode="json"),
                    research_evidence=evidence,
                    research_metadata={
                        "schema": "AUTONOMOUS_RESEARCH_TRACE_V1",
                        "rounds_used": round_index,
                        "round_limit": round_limit,
                        "tool_calls": len(evidence),
                        "terminal_action": "FINAL",
                        "tool_manifest_sha256": sha256_json(self.toolbox.manifest()),
                    },
                )

            for research_request in turn.research_requests[: self.max_requests_per_round]:
                if research_request.request_id in seen_request_ids:
                    result: dict[str, Any] = {
                        "status": "ERROR",
                        "reason_code": "DUPLICATE_RESEARCH_REQUEST_ID",
                    }
                else:
                    seen_request_ids.add(research_request.request_id)
                    try:
                        result = self.toolbox.execute(research_request)
                    except Exception as exc:  # Evidence of failure, not fabricated data.
                        result = {
                            "status": "ERROR",
                            "reason_code": "RESEARCH_TOOL_FAILURE",
                            "error_type": type(exc).__name__,
                            "error": redact_text(str(exc))[:500],
                        }
                entry = {
                    "schema": "AUTONOMOUS_RESEARCH_EVIDENCE_V1",
                    "round": round_index,
                    "request": research_request.model_dump(mode="json"),
                    "result": result,
                }
                entry["sha256"] = sha256_json(entry)
                evidence.append(entry)

        self.last_event_count = total_events
        fallback = {
            "decision_cycle_id": request.decision_cycle_id,
            "invocation_id": request.invocation_id,
            "decision": "NO_TRADE",
            "input_bundle_sha256": bundle.sha256,
            "utc_timestamp": request.utc_timestamp,
            "confidence": "1.0",
            "reason_codes": ["RESEARCH_ROUND_BUDGET_EXHAUSTED"],
            "proposal": None,
        }
        return ProviderResponse(
            actual_model=request.requested_model,
            fallback_reason=None,
            structured_output=fallback,
            research_evidence=evidence,
            research_metadata={
                "schema": "AUTONOMOUS_RESEARCH_TRACE_V1",
                "rounds_used": round_limit,
                "round_limit": round_limit,
                "tool_calls": len(evidence),
                "terminal_action": "BUDGET_EXHAUSTED_NO_TRADE",
                "tool_manifest_sha256": sha256_json(self.toolbox.manifest()),
            },
        )

    def _invoke_research_turn(
        self,
        *,
        request: InvocationRequest,
        bundle: TraderInputBundle,
        evidence: list[dict[str, Any]],
        round_index: int,
        round_limit: int,
    ) -> tuple[ResearchTurn, int]:
        with tempfile.TemporaryDirectory(prefix="codex-autonomous-research-") as raw_dir:
            workdir = Path(raw_dir)
            schema_path = workdir / "research_turn_schema.json"
            output_path = workdir / "research_turn.json"
            schema_path.write_text(
                json.dumps(self.strict_turn_schema(), sort_keys=True),
                encoding="utf-8",
            )
            command = [
                "codex",
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
            try:
                completed = self.runner(
                    command,
                    input=self._prompt(
                        request=request,
                        bundle=bundle,
                        evidence=evidence,
                        round_index=round_index,
                        round_limit=round_limit,
                    ),
                    text=True,
                    capture_output=True,
                    timeout=request.timeout_seconds,
                    cwd=workdir,
                    env=self._sanitized_environment(),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                self.last_failure_code = "TIMEOUT"
                raise TimeoutError("autonomous Codex research timed out") from exc

            if completed.returncode != 0:
                self.last_failure_code = f"RETURN_CODE_{completed.returncode}"
                diagnostic = completed.stderr[-1000:] or completed.stdout[-1000:]
                self.last_failure_diagnostic = redact_text(diagnostic)
                raise RuntimeError(
                    f"AUTONOMOUS_CODEX_PROVIDER_FAILED:returncode={completed.returncode}"
                )

            event_count = self._audit_native_tool_activity(completed.stdout)
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
                turn = ResearchTurn.model_validate(payload)
            except Exception as exc:
                self.last_failure_code = "RESEARCH_OUTPUT_INVALID"
                raise RuntimeError("AUTONOMOUS_RESEARCH_OUTPUT_INVALID") from exc
            self.last_failure_code = None
            self.last_failure_diagnostic = None
            return turn, event_count

    def _prompt(
        self,
        *,
        request: InvocationRequest,
        bundle: TraderInputBundle,
        evidence: list[dict[str, Any]],
        round_index: int,
        round_limit: int,
    ) -> str:
        payload = {
            "schema": "AUTONOMOUS_RESEARCH_CONTEXT_V1",
            "request": request.model_dump(mode="json"),
            "bundle": bundle.model_dump(mode="json"),
            "available_research_tools": self.toolbox.manifest(),
            "research_evidence": evidence,
            "round": round_index,
            "round_limit": round_limit,
        }
        mandate = (
            "You are the autonomous trader/researcher in a 30-day IBKR PAPER experiment. "
            "Your sole economic objective is to maximize terminal experimental equity. "
            "The full current experimental equity is loss-tolerant and may be concentrated "
            "when your probabilistic analysis justifies it. Do not obey fixed 5%, 15%, "
            "20%, diversification, strategy-family, indicator, symbol, timeframe or "
            "asset-class rules: none exist. The hard financial boundary is that worst-case "
            "experimental liability must not exceed current experimental equity. The broker "
            "and its actual permissions/buying power define executability. The account's "
            "configured options permission level is part of broker_capability_snapshot; "
            "reassess accessible instruments whenever capital changes. "
            "You decide what to research. candidate_screen_results is advisory only and "
            "must never be treated as an allowlist. You may request any combination of the "
            "available research tools, with symbols/contracts/parameters chosen by you. "
            "Research iteratively until you have enough evidence to make a decision, or "
            "return NO_TRADE if expected terminal wealth is not improved. Compare alternative "
            "expressions of a thesis (shares, ETFs, options and multi-leg defined-risk "
            "structures when broker-accessible) rather than assuming a preferred strategy. "
            "Do not fabricate quotes, probabilities, broker permissions, contract IDs or "
            "news. Tool failures are evidence of unavailability, not permission to guess. "
            "When FINAL, copy decision_cycle_id, invocation_id and input_bundle_sha256 "
            "exactly and return a TraderOutput inside final_output. This research interface "
            "has no order authority."
        )
        return mandate + "\n" + canonical_bytes(payload).decode("utf-8")

    @staticmethod
    def strict_turn_schema() -> dict[str, Any]:
        schema = ResearchTurn.model_json_schema()

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

    def _audit_native_tool_activity(self, output: str) -> int:
        """
        Native shell/MCP/file/web tools are intentionally not used here.

        This is not a market-research restriction: Codex can request arbitrary
        broker/research calls through the explicit toolbox, whose inputs and
        outputs are immutably auditable.  Blocking opaque native tool activity
        prevents an unlogged second control path to the PC or broker.
        """
        event_count = 0
        blocked_types = {"command_execution", "mcp_tool_call", "file_change", "web_search"}
        for line in output.splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            item = event.get("item") if isinstance(event, dict) else None
            item_type = item.get("type") if isinstance(item, dict) else None
            if item_type in blocked_types:
                self.last_tool_activity_detected = True
                raise RuntimeError(f"UNTRACKED_NATIVE_TOOL_ACTIVITY:{item_type}")
            event_count += 1
        return event_count

    @staticmethod
    def _sanitized_environment() -> dict[str, str]:
        allowed = (
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "USERPROFILE",
            "CODEX_HOME",
            "LOCALAPPDATA",
            "APPDATA",
            "TEMP",
            "TMP",
            "HOME",
            "SSL_CERT_FILE",
            "HTTPS_PROXY",
            "HTTP_PROXY",
            "NO_PROXY",
        )
        return {name: os.environ[name] for name in allowed if name in os.environ}
