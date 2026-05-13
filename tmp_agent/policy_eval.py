from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Violation:
    code: str
    severity: str  # "low"|"medium"|"high"
    message: str
    evidence: Dict[str, Any]


def _norm(p: str) -> str:
    return p.replace("/", "\\").strip()


def _hash_tool_args(args: Any) -> str:
    try:
        s = json.dumps(args, ensure_ascii=False, sort_keys=True)
    except Exception:
        s = str(args)
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()[:16]


def evaluate_policy(
    *,
    room_id: str,
    objective: str,
    constraints: List[str],
    workspace_root: str,
    tool_name: Optional[str],
    tool_args: Optional[Dict[str, Any]],
    tool_ok: Optional[bool],
    tool_error: Optional[str],
    tool_output_summary: Optional[Dict[str, Any]] = None,
) -> Tuple[float, List[Dict[str, Any]], str, str]:
    """
    Returns: (score, violations[], verdict, notes)
    verdict: continue|retry|replan|stop
    Determinista, evidence-driven.
    """
    violations: List[Violation] = []
    ws = _norm(workspace_root)

    # Tool allowlist (refuerzo)
    if tool_name and tool_name not in {"list_dir", "read_file", "write_file", "append_file"}:
        violations.append(Violation(
            code="tool_not_allowed",
            severity="high",
            message=f"Tool no permitida: {tool_name}",
            evidence={"tool": tool_name},
        ))

    # Enforce workspace-only en escrituras
    if tool_name in {"write_file", "append_file"}:
        p = _norm(str((tool_args or {}).get("path", "")))
        if not p.startswith(ws):
            violations.append(Violation(
                code="write_outside_workspace",
                severity="high",
                message="Intento de escritura fuera de WORKSPACE_ROOT.",
                evidence={"path": p, "workspace_root": ws},
            ))

    # Heurística de posibles secretos en content (marca, no bloquea por sí sola)
    txt = (tool_args or {}).get("content", "")
    if isinstance(txt, str) and any(k in txt.lower() for k in ["api_key", "apikey", "password", "secret", "token="]):
        violations.append(Violation(
            code="possible_secret_in_content",
            severity="medium",
            message="Contenido parece incluir secreto/credencial.",
            evidence={"tool": tool_name, "content_preview": txt[:120]},
        ))

    score = 0.75
    notes = "OK"

    if tool_ok is False:
        score -= 0.35
        notes = f"Tool error: {tool_error or 'unknown'}"

    for v in violations:
        if v.severity == "high":
            score -= 0.50
        elif v.severity == "medium":
            score -= 0.20
        else:
            score -= 0.10

    score = max(0.0, min(1.0, score))

    has_high = any(v.severity == "high" for v in violations)
    has_medium = any(v.severity == "medium" for v in violations)

    if has_high:
        verdict = "stop"
        notes = "Violación crítica de policy."
    elif tool_ok is False:
        verdict = "retry"
    elif has_medium:
        verdict = "continue"
        notes = "OK con advertencias."
    else:
        verdict = "continue"

    vdicts = [{"code": v.code, "severity": v.severity, "message": v.message, "evidence": v.evidence} for v in violations]
    return score, vdicts, verdict, notes


def should_gate_replan(verdict: str) -> bool:
    return verdict in {"replan", "stop"}
