from __future__ import annotations

from .autonomy_models import AutonomyProposal, CodexCritique, CycleDecision
from .token_budget import DEFAULT_TOKEN_BUDGET, TokenBudgetPolicy


def build_teacher_prompt(state_summary: str, cycle_goal: str, policy: TokenBudgetPolicy = DEFAULT_TOKEN_BUDGET) -> str:
    prompt = (
        "Given the current Brain state and safety constraints, propose the highest-value "
        "improvement toward autonomous excellence. Return concise operational bullets only.\n\n"
        f"State: {state_summary}\n"
        f"Goal: {cycle_goal}\n"
        "Constraints: no semantic memory writes, no FAISS writes, no trading, no B8, no secrets, no raw CoT."
    )
    return policy.clamp_prompt(prompt)


def critique_proposal(proposal: AutonomyProposal) -> CodexCritique:
    text = proposal.proposal.lower()
    blocked = []
    risk = "LOW"
    if any(token in text for token in ("semantic memory write", "faiss write", "trading", "broker", "secret")):
        risk = "BLOCKED"
        blocked.append("protected_path_or_forbidden_action")
    elif any(token in text for token in ("runtime", "endpoint", "scheduler", "autonomy")):
        risk = "MEDIUM"
    return CodexCritique(
        cycle_id=proposal.cycle_id,
        risk_level=risk,  # type: ignore[arg-type]
        critique="Prefer the smallest testable artifact, evidence first, rollback note mandatory.",
        required_gates=["scope_gate", "protected_path_gate", "test_gate", "ledger_gate"],
        blocked_reasons=blocked,
    )


def decide_action(proposal: AutonomyProposal, critique: CodexCritique) -> CycleDecision:
    if critique.risk_level == "BLOCKED":
        return CycleDecision(proposal.cycle_id, "block", "BLOCKED", "Blocked by safety gate.", [], "No change applied.")
    if critique.risk_level == "HIGH":
        return CycleDecision(proposal.cycle_id, "proposal_only", "HIGH", "Plan only; human approval required.", [], "No code rollback needed.")
    return CycleDecision(
        proposal.cycle_id,
        "execute",
        critique.risk_level,
        "Execute as low/medium governed improvement if tests pass.",
        ["smoke_macro_front_brain_aggressive_governed_autonomy_excellence_01.py"],
        "Revert only the specific added artifact/commit if validation fails.",
    )
