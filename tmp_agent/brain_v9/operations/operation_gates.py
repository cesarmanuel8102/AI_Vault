from __future__ import annotations

PROTECTED_MARKERS = ("memory/semantic/", "trading/", "B8/", "tmp_agent/strategies/", ".env")


def classify_operation_scope(paths: list[str]) -> dict[str, object]:
    violations = [path for path in paths if any(marker in path.replace("\\", "/") for marker in PROTECTED_MARKERS)]
    return {"allowed": not violations, "violations": violations}


def operation_allowed(risk_level: str, paths: list[str]) -> bool:
    scope = classify_operation_scope(paths)
    return bool(scope["allowed"] and risk_level in {"LOW", "MEDIUM"})
