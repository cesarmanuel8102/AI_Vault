from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

REQUIRED_FIELDS = {
    "front",
    "objective",
    "actions_taken",
    "files_changed",
    "tests_run",
    "evidence_paths",
    "gates_passed",
    "gates_failed",
    "memory_mutated",
    "faiss_mutated",
    "trading_touched",
    "secrets_exposed",
    "raw_cot_exposed",
    "runtime_used",
    "next_recommended_front",
    "human_review_needed",
}


def validate_observer_report(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    missing = sorted(REQUIRED_FIELDS - set(payload))
    if missing:
        errors.append(f"missing_fields:{','.join(missing)}")
    for key in ["memory_mutated", "faiss_mutated", "trading_touched", "secrets_exposed", "raw_cot_exposed", "human_review_needed"]:
        if key in payload and not isinstance(payload[key], bool):
            errors.append(f"{key}_must_be_bool")
    return errors


def write_observer_report(path: str | Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    errors = validate_observer_report(payload)
    result = {"valid": not errors, "errors": errors, "report": payload}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
