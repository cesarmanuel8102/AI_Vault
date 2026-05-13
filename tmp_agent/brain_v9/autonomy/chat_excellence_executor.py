"""
chat_excellence_executor.py  —  R10.2

Tras cada iteración del proactive task `chat_excellence`, evalúa la propuesta
y, si pasa los guardrails, escribe un *proposal file* en
`state/proposed_patches/`. El proposal NO modifica código real: queda en
revisión humana via endpoints `/brain/chat_excellence/proposals[...]`.

Auto-apply requiere TODOS los guardrails + env `BRAIN_CE_AUTOAPPLY=true`.
Por defecto está OFF — modo "humano-en-el-loop" hasta que confiemos en el
clasificador de riesgo.

Guardrails de aceptación (gates AND):
  * parsed_ok == True
  * impact_score >= MIN_IMPACT (7)
  * affected_files_validated == True
  * affected_files_invalid == []
  * affected_files no vacío
  * len(proposed_change) >= 30  (no trivial)
  * risk_class != "high"  (heurístico — ver _classify_risk)

Si TODOS pasan + BRAIN_CE_AUTOAPPLY=true + risk=="low" => status="auto_apply_pending"
   (la aplicación real queda para R10.2b — por ahora solo se marca).
Si pasan gates pero no auto-apply => status="pending_review".
Si fallan => status="skipped" + razón.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# State paths — anchored on tmp_agent/state to match the rest of the brain
_BRAIN_ROOT = Path(__file__).resolve().parent.parent       # brain_v9/
_TMP_AGENT  = _BRAIN_ROOT.parent                            # tmp_agent/
_STATE_DIR  = _TMP_AGENT / "state"
_PROPOSALS_DIR = _STATE_DIR / "proposed_patches"
_HISTORY_FILE  = _STATE_DIR / "chat_excellence_history.json"

# Guardrail constants
MIN_IMPACT_SCORE  = 7
MIN_CHANGE_CHARS  = 30
MAX_PROPOSALS_KEEP = 200

# Heuristic risk keywords. Anything matching `_HIGH_RISK_PATTERNS` blocks
# auto-apply outright. `_MEDIUM_RISK_PATTERNS` downgrades to "medium" (still
# pending_review). Everything else => "low".
_HIGH_RISK_PATTERNS = [
    r"\bdrop\s+table\b",
    r"\brm\s+-rf\b",
    r"\bdelete\s+from\b",
    r"\bdisable\s+(circuit|breaker|safeguard|gate)\b",
    r"\bbypass\s+(safety|gate|validation)\b",
    r"\bremove\s+(safety|guard)",
    r"\bsubprocess\.|os\.system|eval\(|exec\(",
    r"\bAPI[_ ]?KEY|SECRET|PASSWORD|TOKEN\b",
]
_MEDIUM_RISK_PATTERNS = [
    r"\bnueva funci[oó]n\b",
    r"\bnew (function|class|module)\b",
    r"\brefactor\b",
    r"\bmigrar\b",
    r"\brewrite\b",
    r"\bagregar (modulo|m[oó]dulo|class|servicio)",
]

# Files that should NEVER be auto-modified, even with all gates green.
# These are infrastructure / safety / governance modules.
_SACRED_FILES = {
    "config.py",
    "main.py",
    "autonomy/proactive_scheduler.py",
    "autonomy/chat_excellence_executor.py",
    "governance/execution_gate.py",
    "core/session.py",  # too central; require human review
}


def _classify_risk(proposed_change: str, affected_files: List[str]) -> Tuple[str, List[str]]:
    """Return ('low'|'medium'|'high', [matched_reasons])."""
    reasons: List[str] = []
    text = (proposed_change or "").lower()

    # Sacred files always escalate to high
    sacred_hit = [f for f in affected_files if any(f.endswith(s) or f == s for s in _SACRED_FILES)]
    if sacred_hit:
        reasons.append(f"sacred_file:{','.join(sacred_hit)}")
        return "high", reasons

    for pat in _HIGH_RISK_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            reasons.append(f"high_pattern:{pat}")
            return "high", reasons

    medium_hits = [pat for pat in _MEDIUM_RISK_PATTERNS if re.search(pat, text, re.IGNORECASE)]
    if medium_hits:
        reasons.extend(f"medium_pattern:{p}" for p in medium_hits)
        return "medium", reasons

    return "low", reasons


def _evaluate_gates(iteration: Dict) -> Tuple[bool, List[str]]:
    """Return (all_pass, [failure_reasons])."""
    failures: List[str] = []

    if not iteration.get("parsed_ok"):
        failures.append("parsed_ok=false")

    impact = iteration.get("impact_score")
    try:
        impact_int = int(impact) if impact is not None else 0
    except (TypeError, ValueError):
        impact_int = 0
    if impact_int < MIN_IMPACT_SCORE:
        failures.append(f"impact_score={impact_int}<{MIN_IMPACT_SCORE}")

    if not iteration.get("affected_files_validated"):
        failures.append("affected_files_validated!=true")

    invalid = iteration.get("affected_files_invalid") or []
    if invalid:
        failures.append(f"affected_files_invalid={invalid[:3]}")

    files = iteration.get("affected_files") or []
    if not files:
        failures.append("affected_files=[]")

    change = iteration.get("proposed_change") or ""
    if len(change) < MIN_CHANGE_CHARS:
        failures.append(f"proposed_change_len={len(change)}<{MIN_CHANGE_CHARS}")

    return (len(failures) == 0), failures


def _next_proposal_id() -> str:
    return datetime.now().strftime("ce_prop_%Y%m%d_%H%M%S")


def _ensure_dir() -> None:
    _PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)


def evaluate_iteration(iteration: Dict) -> Dict:
    """
    Evalúa una iteración de chat_excellence y produce un proposal record
    (lo escribe a disco si pasa gates). Returns the proposal dict or
    {"status": "skipped", "reasons": [...]} if gates fail.

    Idempotente — escribir el mismo iter dos veces produce dos proposals
    con IDs distintos (timestamp), pero ese caso no debería darse porque
    el scheduler solo llama una vez por iter.
    """
    _ensure_dir()

    iter_num = iteration.get("iter")
    iter_ts  = iteration.get("timestamp")

    passed, failures = _evaluate_gates(iteration)
    if not passed:
        log.info(
            "ChatExcellence iter#%s SKIPPED by executor: %s",
            iter_num, ", ".join(failures)[:200],
        )
        return {
            "status": "skipped",
            "iter": iter_num,
            "iter_timestamp": iter_ts,
            "reasons": failures,
        }

    files = iteration.get("affected_files") or []
    change = iteration.get("proposed_change") or ""
    risk, risk_reasons = _classify_risk(change, files)

    auto_apply_env = os.environ.get("BRAIN_CE_AUTOAPPLY", "").lower() in ("1", "true", "yes")
    if risk == "low" and auto_apply_env:
        status = "auto_apply_pending"
    elif risk == "high":
        status = "blocked_high_risk"
    else:
        status = "pending_review"

    proposal_id = _next_proposal_id()
    proposal = {
        "proposal_id": proposal_id,
        "created_at": datetime.now().isoformat(),
        "source": "chat_excellence",
        "iter": iter_num,
        "iter_timestamp": iter_ts,
        "status": status,
        "risk_class": risk,
        "risk_reasons": risk_reasons,
        "auto_apply_env": auto_apply_env,
        "weakness": iteration.get("weakness", ""),
        "impact_score": iteration.get("impact_score"),
        "root_cause_guess": iteration.get("root_cause_guess", ""),
        "proposed_change": change,
        "test_plan": iteration.get("test_plan", ""),
        "expected_improvement": iteration.get("expected_improvement", ""),
        "affected_files": files,
        "diff": None,         # R10.2b will populate concrete diff
        "applied_at": None,
        "applied_by": None,
        "rejected_at": None,
        "rejected_reason": None,
    }

    out_path = _PROPOSALS_DIR / f"{proposal_id}.json"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(proposal, f, indent=2, ensure_ascii=False)
        log.info(
            "ChatExcellence proposal CREATED: id=%s iter=%s status=%s risk=%s files=%s",
            proposal_id, iter_num, status, risk, files,
        )
    except Exception as exc:
        log.error("Failed to write proposal %s: %s", proposal_id, exc)
        proposal["status"] = "write_error"
        proposal["error"] = str(exc)

    return proposal


# ── Public API for endpoints ─────────────────────────────────────────────

def list_proposals(status_filter: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """List proposals sorted by created_at desc. Optionally filter by status."""
    _ensure_dir()
    out: List[Dict] = []
    for p in sorted(_PROPOSALS_DIR.glob("ce_prop_*.json"), reverse=True):
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                rec = json.load(f)
        except Exception:
            continue
        if status_filter and rec.get("status") != status_filter:
            continue
        out.append(rec)
        if len(out) >= limit:
            break
    return out


def get_proposal(proposal_id: str) -> Optional[Dict]:
    p = _PROPOSALS_DIR / f"{proposal_id}.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def reject_proposal(proposal_id: str, reason: str = "manual") -> Optional[Dict]:
    rec = get_proposal(proposal_id)
    if rec is None:
        return None
    rec["status"] = "rejected"
    rec["rejected_at"] = datetime.now().isoformat()
    rec["rejected_reason"] = reason[:500]
    try:
        with open(_PROPOSALS_DIR / f"{proposal_id}.json", "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        log.error("Failed to persist reject %s: %s", proposal_id, exc)
        return None
    log.info("Proposal %s REJECTED: %s", proposal_id, reason[:120])
    return rec


def mark_applied(proposal_id: str, by: str = "manual", note: str = "") -> Optional[Dict]:
    """Marca el proposal como aplicado. R10.2 NO modifica código real;
    esto es un marcador para tracking. R10.2b implementará el patch real."""
    rec = get_proposal(proposal_id)
    if rec is None:
        return None
    rec["status"] = "applied"
    rec["applied_at"] = datetime.now().isoformat()
    rec["applied_by"] = by[:100]
    if note:
        rec["apply_note"] = note[:500]
    try:
        with open(_PROPOSALS_DIR / f"{proposal_id}.json", "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        log.error("Failed to persist apply %s: %s", proposal_id, exc)
        return None
    log.info("Proposal %s APPLIED by %s", proposal_id, by)
    return rec


def stats() -> Dict:
    """Aggregate counts by status. Useful for dashboard card."""
    counts: Dict[str, int] = {}
    total = 0
    for p in _PROPOSALS_DIR.glob("ce_prop_*.json"):
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                rec = json.load(f)
        except Exception:
            continue
        s = rec.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1
        total += 1
    return {
        "total": total,
        "by_status": counts,
        "min_impact_required": MIN_IMPACT_SCORE,
        "auto_apply_enabled": os.environ.get("BRAIN_CE_AUTOAPPLY", "").lower() in ("1", "true", "yes"),
        "sacred_files": sorted(_SACRED_FILES),
    }
