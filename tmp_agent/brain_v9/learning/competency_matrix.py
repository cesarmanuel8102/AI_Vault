from __future__ import annotations

import json
from pathlib import Path
from typing import Any

COMPETENCY_MATRIX_PATH = Path(__file__).resolve().parent / "competency_matrix.json"
DEFAULT_COMPETENCIES = {
    "provider_reliability": 0.88,
    "no_cot_safety": 0.94,
    "memory_discipline": 0.95,
    "coding_reliability": 0.78,
    "test_discipline": 0.82,
    "cei_fdot_usefulness": 0.68,
    "financial_safety": 0.80,
    "autonomy_planning": 0.72,
    "token_efficiency": 0.62,
    "operator_clarity": 0.76,
}


def build_competency_matrix(overrides: dict[str, float] | None = None) -> dict[str, Any]:
    scores = dict(DEFAULT_COMPETENCIES)
    if overrides:
        for key, value in overrides.items():
            scores[key] = max(0.0, min(1.0, float(value)))
    return {"version": "1.0", "scores": scores, "overall": round(sum(scores.values()) / len(scores), 4)}


def write_competency_matrix(path: Path = COMPETENCY_MATRIX_PATH, overrides: dict[str, float] | None = None) -> dict[str, Any]:
    matrix = build_competency_matrix(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    return matrix
