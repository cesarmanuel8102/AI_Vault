from __future__ import annotations

from .competency_matrix import COMPETENCIES, validate_matrix


def compute_excellence_score(scores: dict[str, float]) -> dict[str, object]:
    normalized = validate_matrix(scores)
    overall = round(sum(normalized.values()) / len(COMPETENCIES), 4)
    weakest = sorted(normalized.items(), key=lambda item: item[1])[:3]
    return {"overall": overall, "scores": normalized, "weakest": weakest}
