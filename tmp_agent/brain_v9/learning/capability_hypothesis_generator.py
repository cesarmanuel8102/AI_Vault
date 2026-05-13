from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from brain_v9.core.state_io import write_json


TARGET_CAPABILITIES = [
    "planning_coherence",
    "execution_reliability",
    "tool_use_accuracy",
    "governance_quality",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _source_key(source_id: str) -> str:
    raw = str(source_id or "").replace("github_", "")
    raw = raw.rsplit("_", 1)[0]
    return raw.upper()


def _infer_target(pattern_id: str) -> str:
    if "debate" in pattern_id or "graph" in pattern_id:
        return "planning_coherence"
    if "tool" in pattern_id or "repair" in pattern_id:
        return "tool_use_accuracy"
    if "checkpoint" in pattern_id or "sandbox" in pattern_id:
        return "execution_reliability"
    return "governance_quality"


def _semantic_key(target: str, pattern: Dict[str, Any]) -> str:
    return f"{target}:{pattern.get('semantic_family') or pattern.get('pattern_id')}"


def generate_hypotheses(
    source_manifest: Dict[str, Any],
    pattern_report: Dict[str, Any],
    output_path,
) -> Dict[str, Any]:
    hypotheses: List[Dict[str, Any]] = []
    source_id = source_manifest.get("source_id")
    source_key = _source_key(source_id)
    for idx, pattern in enumerate(pattern_report.get("patterns", []), start=1):
        target = _infer_target(pattern.get("pattern_id", ""))
        hypotheses.append({
            "hypothesis_id": f"HYP_{source_key}_{pattern.get('pattern_id', 'pattern').upper()}_{idx:03d}",
            "semantic_key": _semantic_key(target, pattern),
            "inspired_by_sources": [source_id],
            "target_capability": target,
            "claim": f"Adoptar el patron `{pattern.get('pattern_id')}` puede mejorar `{target}` sin copiar codigo externo.",
            "expected_metric_lift": {
                "plan_validity_score": "+8%" if target == "planning_coherence" else "+3%",
                "loop_failure_rate": "-15%" if target in {"planning_coherence", "execution_reliability"} else "-5%",
                "execution_success_rate": "+5%" if target == "execution_reliability" else "+2%",
                "tool_error_rate": "-10%" if target == "tool_use_accuracy" else "-2%",
            },
            "risk": "medium" if pattern.get("risk", 0) >= 4 else "low",
            "recommended_next_step": "sandbox_patch_later",
            "source_attribution": {
                "source_id": source_id,
                "pattern_id": pattern.get("pattern_id"),
                "semantic_family": pattern.get("semantic_family"),
                "evidence_refs": pattern.get("evidence_refs", []),
            },
        })

    report = {
        "source_id": source_id,
        "generated_at_utc": _utc_now(),
        "hypotheses": hypotheses,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, report)
    return report
