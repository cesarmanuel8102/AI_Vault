from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .autonomy_models import AutonomyProposal, CycleResult
from .teacher_student_loop import critique_proposal, decide_action
from .token_budget import DEFAULT_TOKEN_BUDGET


def run_offline_cycle(cycle_id: str, prompt: str, brain_response: str, evidence_dir: str) -> CycleResult:
    evidence = Path(evidence_dir)
    evidence.mkdir(parents=True, exist_ok=True)
    proposal = AutonomyProposal(
        cycle_id=cycle_id,
        prompt=DEFAULT_TOKEN_BUDGET.clamp_prompt(prompt),
        proposal=DEFAULT_TOKEN_BUDGET.clamp_response(brain_response),
        domain="governed_autonomy",
        expected_value="reduce supervision with tested low/medium improvements",
        evidence_path=str(evidence / f"{cycle_id}_brain_response.json"),
    )
    critique = critique_proposal(proposal)
    decision = decide_action(proposal, critique)
    score = 0.85 if decision.decision == "execute" else 0.45
    return CycleResult(
        cycle_id=cycle_id,
        decision=decision.decision,
        score=score,
        lesson_id=f"lesson_{cycle_id}",
        mistake_id=None if decision.decision == "execute" else f"mistake_{cycle_id}",
        promotion_candidate_id=f"promotion_{cycle_id}" if decision.decision == "execute" else None,
        evidence_path=str(evidence),
    )


def summarize_cycles(results: Iterable[CycleResult]) -> dict[str, object]:
    items = [r.to_dict() for r in results]
    return {
        "cycles": len(items),
        "executed": sum(1 for r in items if r["decision"] == "execute"),
        "blocked": sum(1 for r in items if r["decision"] == "block"),
        "average_score": round(sum(float(r["score"]) for r in items) / max(1, len(items)), 4),
        "results": items,
    }
