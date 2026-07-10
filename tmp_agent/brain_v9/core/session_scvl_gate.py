from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional


def is_scvl_gate_enabled() -> bool:
    return os.environ.get("BRAIN_SCVL_GATE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _extract_tools_used(result: Dict[str, Any]) -> list[str]:
    names = result.get("tool_names")
    if isinstance(names, list):
        return [str(name) for name in names if name]
    name = result.get("tool_name")
    return [str(name)] if name else []


def _report_passed(report: Dict[str, Any]) -> bool:
    if "passed" in report:
        return bool(report.get("passed"))
    score = float(report.get("coherence_score", 0.0) or 0.0)
    contradictions = int(report.get("contradictions_detected", 0) or 0)
    return contradictions == 0 and score >= 0.5


def _blocked_result(result: Dict[str, Any], *, reason: str, score: Optional[float], report: Dict[str, Any]) -> Dict[str, Any]:
    content = (
        "Respuesta bloqueada por validacion semantica SCVL. "
        f"Motivo: {reason}. Reformula la solicitud o pide una verificacion mas concreta."
    )
    blocked = dict(result)
    blocked.update(
        {
            "success": False,
            "content": content,
            "response": content,
            "scvl": {
                "enabled": True,
                "passed": False,
                "reason": reason,
                "score": score,
                "report": report,
            },
        }
    )
    return blocked


def apply_scvl_final_answer_gate(
    *,
    message: str,
    result: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    logger=None,
) -> Dict[str, Any]:
    if not is_scvl_gate_enabled():
        return result
    if not isinstance(result, dict) or result.get("success") is False:
        return result

    context = context or {}
    validator: Optional[Callable[..., Dict[str, Any]]] = context.get("validator")
    if validator is None:
        chat_metrics = context.get("chat_metrics")
        validator = getattr(chat_metrics, "validate_semantic_coherence", None)
    if validator is None:
        if logger:
            logger.warning("SCVL final answer gate blocked: validator unavailable")
        return _blocked_result(result, reason="scvl_validator_unavailable", score=None, report={})

    response_content = str(result.get("content") or result.get("response") or "")
    selected_route = str(context.get("route") or result.get("route") or "unknown")
    tools_used = context.get("tools_used") or _extract_tools_used(result)

    try:
        report = validator(
            user_message=message,
            selected_route=selected_route,
            response_content=response_content,
            tools_used=tools_used,
        )
    except Exception as exc:
        if logger:
            logger.warning("SCVL final answer gate blocked: validator exception: %s", exc)
        return _blocked_result(result, reason="scvl_exception", score=None, report={"error": type(exc).__name__})

    if not isinstance(report, dict):
        if logger:
            logger.warning("SCVL final answer gate blocked: invalid validator report")
        return _blocked_result(result, reason="scvl_invalid_report", score=None, report={})

    score = report.get("coherence_score")
    try:
        score_value = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_value = None

    if _report_passed(report):
        passed = dict(result)
        passed["scvl"] = {
            "enabled": True,
            "passed": True,
            "reason": "passed",
            "score": score_value,
        }
        return passed

    reason = str(report.get("recommended_action") or report.get("reason") or "scvl_failed")
    if logger:
        logger.warning("SCVL final answer gate blocked: %s", reason)
    return _blocked_result(result, reason=reason, score=score_value, report=report)
