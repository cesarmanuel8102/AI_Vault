from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from .autonomous_research import AutonomousResearchProvider
from .canonical import sha256_json
from .ibkr_research import IBKRResearchToolbox
from .liability import assess_proposal_liability
from .persistence import Database
from .repositories import utc_now
from .risk import RiskEngine, RiskInputs, RiskResult
from .trader_invocation import (
    InvocationRequest,
    TraderInputBundle,
    TraderInvocationAdapter,
)


class AutonomousCycleResult(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    decision_cycle_id: str
    invocation_id: str
    accepted: bool
    decision: str
    validation: str
    proposal: dict[str, Any] | None
    research_evidence_count: int
    research_evidence_sha256: str
    risk_gate: str
    risk_reason_codes: tuple[str, ...]
    liability_gate: str
    liability_reason_codes: tuple[str, ...]
    broker_what_if_seen: bool
    capital_feasibility_seen: bool
    execution_ready: bool
    order_authority: bool
    reason_codes: tuple[str, ...]


class AutonomousDecisionRuntime:
    """
    Operational decision path for the 30-day paper experiment.

    The runtime does not supply a strategy or tradable-symbol universe.  Codex
    owns discovery and research.  Deterministic code validates only the paper
    broker state, experimental-capital boundary, and exact broker what-if
    evidence before a proposal can be considered execution-ready.

    This class intentionally does not submit an order.  Submission remains a
    separate gated side effect so decision research can be tested independently.
    """

    def __init__(
        self,
        *,
        db: Database,
        toolbox: IBKRResearchToolbox,
        model: str,
        reasoning_effort: str = "HIGH",
        timeout_seconds: int = 180,
        max_research_rounds: int = 8,
    ) -> None:
        self.db = db
        self.toolbox = toolbox
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds
        self.max_research_rounds = max_research_rounds

    def run_cycle(
        self,
        *,
        readonly_report: dict[str, Any],
        experiment_equity: Decimal,
        market_data_gate: str,
        market_session_state: str,
        kill_switch_state: str = "KILL_SWITCH_CLEAR",
        current_open_risk: Decimal = Decimal("0"),
        candidate_screen_results: Sequence[dict[str, Any]] = (),
        benchmark_state: dict[str, Any] | None = None,
        invocation_trigger: str = "SCHEDULED_SCAN",
    ) -> AutonomousCycleResult:
        if experiment_equity <= 0:
            raise ValueError("experimental equity must be positive")
        if readonly_report.get("paper_account_identity_gate") != "PASS":
            raise RuntimeError("PAPER_ACCOUNT_IDENTITY_GATE_BLOCK")
        if readonly_report.get("broker_reconciliation_gate") != "PASS":
            raise RuntimeError("BROKER_RECONCILIATION_GATE_BLOCK")
        if market_data_gate != "PASS":
            raise RuntimeError("MARKET_DATA_GATE_BLOCK")

        run_id = uuid4().hex
        cycle_id = f"autonomous-cycle-{run_id}"
        invocation_id = f"autonomous-invocation-{run_id}"
        now = utc_now()
        buying_power = readonly_report.get("buying_power")
        capability_snapshot = {
            "schema": "BROKER_CAPABILITY_SNAPSHOT_V1",
            "paper_only": True,
            "options_permission_level": self.toolbox.options_permission_level,
            "buying_power": buying_power,
            "net_liquidation": readonly_report.get("net_liquidation"),
            "market_data_behavior": readonly_report.get("market_data_behavior"),
            "dynamic_contract_discovery": True,
            "dynamic_option_chain_discovery": True,
            "broker_what_if_available": True,
            "fixed_symbol_allowlist": False,
            "fixed_strategy_allowlist": False,
            "fixed_timeframe_allowlist": False,
        }
        bundle = TraderInputBundle(
            decision_cycle_id=cycle_id,
            utc_timestamp=now,
            market_session_state=market_session_state,
            reconciliation_receipt={
                "status": readonly_report.get("broker_reconciliation_gate"),
                "sha256": sha256_json(readonly_report),
            },
            experiment_subledger_snapshot={
                "equity": str(experiment_equity),
                "current_open_risk": str(current_open_risk),
            },
            broker_account_snapshot={
                "cash": readonly_report.get("cash"),
                "settled_cash": readonly_report.get("settled_cash"),
                "buying_power": buying_power,
                "net_liquidation": readonly_report.get("net_liquidation"),
            },
            positions_snapshot=list(readonly_report.get("positions") or []),
            open_orders_snapshot=list(readonly_report.get("open_orders") or []),
            risk_snapshot={
                "policy_version": "CAPITAL_BOUNDARY_V2",
                "maximum_experiment_liability": str(experiment_equity),
                "fixed_percentage_limits": False,
            },
            kill_switch_state=kill_switch_state,
            market_data_snapshot={
                "gate_status": market_data_gate,
                "source": "IBKR",
                "dynamic_research": True,
            },
            candidate_screen_results=list(candidate_screen_results),
            relevant_previous_immutable_decisions=[],
            process_policy_version="AUTONOMOUS_RESEARCH_V1",
            execution_realism_version="IBKR_PAPER_WHAT_IF_REQUIRED_V1",
            benchmark_state=benchmark_state or {},
            broker_capability_snapshot=capability_snapshot,
            research_policy_version="AUTONOMOUS_RESEARCH_V1",
            research_round_budget=self.max_research_rounds,
        )
        request = InvocationRequest(
            decision_cycle_id=cycle_id,
            invocation_id=invocation_id,
            utc_timestamp=now,
            requested_model=self.model,
            actual_model=self.model,
            model_configuration={
                "provider": "codex-cli-autonomous-research",
                "paper_only": True,
                "candidate_screens_are_advisory": True,
            },
            reasoning_effort=self.reasoning_effort,
            input_bundle_sha256=bundle.sha256,
            risk_policy_version="CAPITAL_BOUNDARY_V2",
            experiment_id="codex-ibkr-paper-30d",
            invocation_trigger=invocation_trigger,
            timeout_seconds=self.timeout_seconds,
        )

        provider = AutonomousResearchProvider(
            self.toolbox,
            max_rounds=self.max_research_rounds,
        )
        adapter = TraderInvocationAdapter(self.db, provider)
        validated = adapter.invoke(request, bundle)
        response = provider.last_response
        evidence = response.research_evidence if response is not None else []
        structured = response.structured_output if response is not None else {}
        proposal = structured.get("proposal") if isinstance(structured, dict) else None

        post_reasons: list[str] = []
        risk_gate = "NOT_APPLICABLE"
        risk_reasons: tuple[str, ...] = ()
        liability_gate = "NOT_APPLICABLE"
        liability_reasons: tuple[str, ...] = ()
        what_if_seen = self._successful_tool_seen(evidence, "what_if_order")
        capital_seen = self._successful_tool_seen(evidence, "capital_feasibility")

        if validated.accepted and validated.effective_decision == "PROPOSE_TRADE":
            if not isinstance(proposal, dict):
                post_reasons.append("PROPOSAL_PAYLOAD_MISSING")
            else:
                liability = assess_proposal_liability(proposal)
                liability_gate = liability.status
                liability_reasons = liability.reason_codes
                if not liability.structurally_bounded:
                    post_reasons.extend(liability.reason_codes)

                maximum_loss_raw = proposal.get("maximum_loss")
                if maximum_loss_raw is None:
                    post_reasons.append("MAXIMUM_LOSS_REQUIRED")
                else:
                    maximum_loss = Decimal(str(maximum_loss_raw))
                    risk = RiskEngine.month1().evaluate(
                        RiskInputs(
                            experiment_equity=experiment_equity,
                            day_start_equity=experiment_equity,
                            week_start_equity=experiment_equity,
                            high_water_equity=experiment_equity,
                            estimated_loss=maximum_loss,
                            position_capital=Decimal(
                                str(proposal.get("capital_required") or maximum_loss)
                            ),
                            total_open_risk=current_open_risk + maximum_loss,
                            daily_loss=Decimal("0"),
                            weekly_drawdown=Decimal("0"),
                            total_drawdown=Decimal("0"),
                            concurrent_positions=len(
                                readonly_report.get("positions") or []
                            ),
                        )
                    )
                    risk_gate = risk.result.value
                    risk_reasons = risk.reason_codes
                    if risk.result is not RiskResult.PASS:
                        post_reasons.extend(risk.reason_codes)

            if not capital_seen:
                post_reasons.append("CAPITAL_FEASIBILITY_EVIDENCE_REQUIRED")
            if not what_if_seen:
                post_reasons.append("BROKER_WHAT_IF_EVIDENCE_REQUIRED")

        execution_ready = bool(
            validated.accepted
            and validated.effective_decision == "PROPOSE_TRADE"
            and risk_gate == RiskResult.PASS.value
            and liability_gate == "PASS"
            and capital_seen
            and what_if_seen
            and not post_reasons
        )
        combined_reasons = tuple(validated.reason_codes) + tuple(post_reasons)
        return AutonomousCycleResult(
            decision_cycle_id=cycle_id,
            invocation_id=invocation_id,
            accepted=validated.accepted,
            decision=validated.effective_decision,
            validation=validated.validation,
            proposal=proposal if isinstance(proposal, dict) else None,
            research_evidence_count=len(evidence),
            research_evidence_sha256=sha256_json(evidence),
            risk_gate=risk_gate,
            risk_reason_codes=risk_reasons,
            liability_gate=liability_gate,
            liability_reason_codes=liability_reasons,
            broker_what_if_seen=what_if_seen,
            capital_feasibility_seen=capital_seen,
            execution_ready=execution_ready,
            order_authority=False,
            reason_codes=combined_reasons,
        )

    @staticmethod
    def _successful_tool_seen(
        evidence: list[dict[str, Any]], tool_name: str
    ) -> bool:
        for item in evidence:
            request = item.get("request") or {}
            result = item.get("result") or {}
            if request.get("tool") == tool_name and result.get("status") == "PASS":
                return True
        return False
