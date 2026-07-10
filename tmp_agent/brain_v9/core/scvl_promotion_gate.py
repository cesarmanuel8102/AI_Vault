from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional


def is_scvl_promotion_gate_enabled() -> bool:
    return os.environ.get("BRAIN_SCVL_PROMOTION_GATE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _candidate_text(candidate: Dict[str, Any]) -> str:
    for key in ("text", "content", "summary", "body"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return value
    return ""


def _report_passed(report: Dict[str, Any]) -> bool:
    if "passed" in report:
        return bool(report.get("passed"))
    try:
        score = float(report.get("coherence_score", 0.0) or 0.0)
        contradictions = int(report.get("contradictions_detected", 0) or 0)
    except (TypeError, ValueError):
        return False
    return contradictions == 0 and score >= 0.5


def _blocked(candidate: Dict[str, Any], *, reason: str, score: Optional[float], report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "enabled": True,
        "allowed": False,
        "candidate": candidate,
        "scvl": {
            "enabled": True,
            "passed": False,
            "reason": reason,
            "score": score,
            "report": report,
        },
    }


def apply_scvl_promotion_gate(
    *,
    candidate: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    logger=None,
) -> Dict[str, Any]:
    payload = dict(candidate or {})
    if not is_scvl_promotion_gate_enabled():
        return {"enabled": False, "allowed": True, "candidate": payload, "scvl": {"enabled": False}}

    text = _candidate_text(payload)
    if not text:
        if logger:
            logger.warning("SCVL promotion gate blocked: missing candidate text")
        return _blocked(payload, reason="missing_text", score=None, report={})

    context = context or {}
    validator: Optional[Callable[..., Dict[str, Any]]] = context.get("validator")
    if validator is None:
        chat_metrics = context.get("chat_metrics")
        validator = getattr(chat_metrics, "validate_semantic_coherence", None)
    if validator is None:
        try:
            from brain_v9.core.session_chat_metrics import ChatMetrics
            validator = ChatMetrics().validate_semantic_coherence
        except Exception:
            validator = None
    if validator is None:
        if logger:
            logger.warning("SCVL promotion gate blocked: validator unavailable")
        return _blocked(payload, reason="scvl_validator_unavailable", score=None, report={})

    try:
        report = validator(
            user_message=f"Promote semantic candidate: {text[:500]}",
            selected_route=str(context.get("route") or "semantic_promotion"),
            response_content=text,
            tools_used=list(context.get("tools_used") or []),
        )
    except Exception as exc:
        if logger:
            logger.warning("SCVL promotion gate blocked: validator exception: %s", exc)
        return _blocked(payload, reason="scvl_exception", score=None, report={"error": type(exc).__name__})

    if not isinstance(report, dict):
        if logger:
            logger.warning("SCVL promotion gate blocked: invalid validator report")
        return _blocked(payload, reason="scvl_invalid_report", score=None, report={})

    score = report.get("coherence_score")
    try:
        score_value = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_value = None

    if _report_passed(report):
        return {
            "enabled": True,
            "allowed": True,
            "candidate": payload,
            "scvl": {"enabled": True, "passed": True, "score": score_value},
        }

    reason = str(report.get("recommended_action") or report.get("reason") or "scvl_failed")
    if logger:
        logger.warning("SCVL promotion gate blocked: %s", reason)
    return _blocked(payload, reason=reason, score=score_value, report=report)
