from typing import Any, Dict, List, Tuple

def _clamp(x: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, x))

def evaluate_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    steps = plan.get("steps", []) if isinstance(plan, dict) else []
    executed = [s for s in steps if s.get("status") in ("done", "error")]
    errors = [s for s in steps if s.get("status") == "error"]
    pending = [s for s in steps if s.get("status") == "pending"]

    score = 100
    reasons: List[str] = []
    recommendations: List[str] = []

    if not executed:
        score -= 30
        reasons.append("No se ejecutaron pasos (executed=0).")
        recommendations.append("Verifica que el plan tenga pasos TOOL/THINK ejecutables y corre /v1/agent/run.")

    if errors:
        score -= 50
        reasons.append(f"Existen {len(errors)} pasos en error.")
        recommendations.append("Replanificar o corregir el paso que falla y reintentar.")

        # policy detect
        pol = [e for e in errors if isinstance(e.get("result"), dict) and "POLICY:" in str(e["result"].get("error",""))]
        if pol:
            score -= 40
            reasons.append("Se detectaron violaciones de POLICY en pasos error.")
            recommendations.append("Reescribe el objetivo/rutas para caer dentro de WORKSPACE_ROOT y respeta deny_contains.")

    # THINK quality
    think_bad = 0
    for s in steps:
        if s.get("action") == "THINK" and s.get("status") == "done":
            res = s.get("result", {})
            t = ""
            if isinstance(res, dict):
                t = str(res.get("text","")).strip()
            if len(t) < 20:
                think_bad += 1
    if think_bad:
        score -= 10
        reasons.append(f"{think_bad} pasos THINK con salida débil/corta.")
        recommendations.append("Mejorar prompts de THINK o convertir pasos THINK en TOOL verificables.")

    score = _clamp(score)

    ok = (len(errors) == 0)
    recommendation = "continue" if ok else "replan"

    return {
        "ok": ok,
        "score": score,
        "errors": [{"id": s.get("id"), "title": s.get("title"), "result": s.get("result")} for s in errors],
        "pending_count": len(pending),
        "recommendation": recommendation,
        "reasons": reasons,
        "recommendations": recommendations,
    }
