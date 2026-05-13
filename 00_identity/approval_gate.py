from __future__ import annotations

from typing import Any, Dict, List, Optional


# Approval Gate v1
# - Objetivo: bloquear ejecuciones de alto riesgo hasta aprobación humana.
# - En v1, solo marcamos y registramos. No ejecutamos acciones financieras aún.
#
# Contrato:
# {
#   "requires_human_approval": bool,
#   "risk_level": "low|medium|high",
#   "reasons": [str, ...],
#   "status": "not_required|pending|approved|rejected"
# }


HIGH_RISK_TOOLS = {
    # Placeholder para futuro:
    # "broker_place_order",
    # "http_request",
}


def assess_approval(
    *,
    step: Optional[Dict[str, Any]],
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    policy_eval: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    tool_calls = tool_calls or []
    policy_eval = policy_eval or {}

    reasons: List[str] = []
    risk_level = "low"
    requires = False

    # Rule 1: tools explícitamente high-risk (futuro)
    for tc in tool_calls:
        tname = str(tc.get("tool_name") or tc.get("tool") or "").strip()
        if tname in HIGH_RISK_TOOLS:
            requires = True
            risk_level = "high"
            reasons.append(f"high_risk_tool:{tname}")

    # Rule 2: policy verdict stop/replan => no aprobación; se detiene por policy, no por approval.
    # (No hacemos nada aquí; solo dejamos claro el diseño.)

    # Rule 3: dominio financiero (futuro: steps PROPOSAL/finance)
    if step and str(step.get("domain", "")).strip().lower() == "finance":
        requires = True
        risk_level = "high"
        reasons.append("finance_domain")

    # Rule 4: efectos externos (futuro: network / broker)
    # En v1 no tenemos herramientas externas habilitadas, así que no aplica.

    status = "pending" if requires else "not_required"

    return {
        "requires_human_approval": bool(requires),
        "risk_level": risk_level,
        "reasons": reasons,
        "status": status,
    }
