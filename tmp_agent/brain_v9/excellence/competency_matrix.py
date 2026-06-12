from __future__ import annotations

COMPETENCIES = [
    "provider_reliability",
    "no_cot_safety",
    "memory_discipline",
    "coding_reliability",
    "test_discipline",
    "cei_fdot_usefulness",
    "financial_safety",
    "autonomy_planning",
    "token_efficiency",
    "operator_clarity",
]


def normalize_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def validate_matrix(scores: dict[str, float]) -> dict[str, float]:
    missing = [name for name in COMPETENCIES if name not in scores]
    if missing:
        raise ValueError(f"missing competencies: {missing}")
    return {name: normalize_score(scores[name]) for name in COMPETENCIES}
