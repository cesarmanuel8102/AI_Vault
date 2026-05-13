"""
chat_excellence_patcher.py  —  R10.2b

Aplica realmente proposals creados por `chat_excellence_executor` cuando
contienen un cambio simple de constante numerica. Diseno conservador:

  * SOLO ficheros en `_PATCHABLE_FILES` (whitelist estricta).
  * SOLO cambios extraibles via regex: "_NAME ... 2 a 5", "from 2 to 5",
    "2 -> 5", "2 => 5", "(de|elevar|reducir|bajar|subir) X (a|to) Y".
  * Backup `.bak.<ts>` + edit + `py_compile` validate. Si compile falla,
    rollback automatico.
  * NO hace restart del brain (operador o R10.2c). Solo deja el fichero
    modificado y persiste `applied_pending_restart` + diff + backup_path.
  * `dry_run=True` por defecto: solo genera diff sin tocar nada.
  * `rollback_proposal` restaura desde backup en cualquier momento.

API:
  * extract_constant_changes(text) -> List[ConstChange]
  * dry_run_proposal(id)           -> {ok, diff, ...}
  * apply_proposal(id, by, note)   -> {ok, diff, backup_path, ...}
  * rollback_proposal(id, reason)  -> {ok, restored_from, ...}

Persistencia: todos los campos nuevos viven dentro del proposal JSON
existente (`state/proposed_patches/<id>.json`).
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import py_compile
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BRAIN_ROOT     = Path(__file__).resolve().parent.parent      # brain_v9/
_TMP_AGENT      = _BRAIN_ROOT.parent                           # tmp_agent/
_STATE_DIR      = _TMP_AGENT / "state"
_PROPOSALS_DIR  = _STATE_DIR / "proposed_patches"

# Whitelist de ficheros patcheables. Se extiende a medida que confiamos
# en mas modulos. Paths relativos a brain_v9/.
# R10.6: ampliado de 1 -> 3 ficheros. La infra de health-gate + auto-rollback
# (R10.2c) hace seguro este crecimiento; cada nuevo fichero debe tener su
# entrada correspondiente en _FORBIDDEN_CONSTANTS_BY_FILE si tiene constantes
# que jamas debe tocarse (data-integrity / semver / etc).
_PATCHABLE_FILES = {
    "core/llm.py",
    "autonomy/chat_excellence_executor.py",   # R10.6: thresholds del propio loop CE
    "autonomy/proactive_scheduler.py",        # R10.6: cadencia de tasks ORAV
}

# Constantes numericas que jamas tocar incluso si estan en un fichero
# whitelisted (ej. semver, defaults criticos).
# R10.6: ahora estructurado como dict file -> set, con clave "*" para
# constantes prohibidas globalmente en cualquier fichero.
_FORBIDDEN_CONSTANTS_BY_FILE: Dict[str, set] = {
    "*": {
        "_PERSIST_EVERY",        # afecta IO disk pattern (legacy)
        "_LATENCY_WINDOW",       # afecta memoria, no comportamiento (legacy)
    },
    "autonomy/chat_excellence_executor.py": {
        "MAX_PROPOSALS_KEEP",    # tocar esto puede borrar audit-trail
    },
    "autonomy/proactive_scheduler.py": {
        "MAX_HISTORY",           # tocar esto puede borrar audit-trail
    },
}

# Compat: legacy callers que esperan _FORBIDDEN_CONSTANTS como set plano
# obtienen la union de todas las claves (vista pesimista).
_FORBIDDEN_CONSTANTS = set().union(*_FORBIDDEN_CONSTANTS_BY_FILE.values())


def _is_forbidden(name: str, rel_path: str) -> bool:
    """R10.6: True si `name` esta prohibido globalmente o para ese fichero."""
    if name in _FORBIDDEN_CONSTANTS_BY_FILE.get("*", set()):
        return True
    if name in _FORBIDDEN_CONSTANTS_BY_FILE.get(rel_path, set()):
        return True
    return False


# R10.6b: bounds explicitos por constante. Cierra el riesgo de bootstrapping
# loop (ej. el patcher reduciendo MIN_IMPACT_SCORE iterativamente hasta
# aceptar cualquier proposal). Una constante sin entrada aqui solo esta
# limitada por _MAX_DELTA_RATIO (modo permisivo, backward-compat).
# Formato: {rel_path: {const_name: (min_inclusive, max_inclusive)}}
_BOUNDS_BY_FILE: Dict[str, Dict[str, Tuple[float, float]]] = {
    "core/llm.py": {
        "_CB_FAIL_THRESHOLD": (1, 20),
        "_CB_COOLDOWN_S":     (10, 3600),
    },
    "autonomy/chat_excellence_executor.py": {
        "MIN_IMPACT_SCORE":   (3, 10),    # < 3 acepta basura, > 10 nunca aplica
        "MIN_CHANGE_CHARS":   (10, 500),
    },
    "autonomy/proactive_scheduler.py": {
        "CHECK_INTERVAL":     (10, 600),  # < 10s satura LLM, > 10min mata responsiveness
    },
}


# Cache para deduplicar warnings de "constante sin bounds declarados".
# Sin esto, cada dry-run/apply spammeria el log con el mismo mensaje.
_WARNED_NO_BOUNDS: set = set()


def _check_bounds(name: str, rel_path: str, new_value) -> Tuple[bool, str]:
    """R10.6b: valida que new_value caiga en el rango declarado para
    (file, name). Si no hay rango declarado, devuelve (True, '') -- modo
    permisivo (solo aplica _MAX_DELTA_RATIO). Si esta fuera, (False, msg).

    Higiene: si la constante esta en un fichero whitelisted pero no tiene
    entry en _BOUNDS_BY_FILE, emite WARN una unica vez para que el operador
    decida si debe declarar rangos explicitos."""
    file_bounds = _BOUNDS_BY_FILE.get(rel_path, {})
    rng = file_bounds.get(name)
    if rng is None:
        key = (rel_path, name)
        if key not in _WARNED_NO_BOUNDS:
            _WARNED_NO_BOUNDS.add(key)
            log.warning(
                "patcher: no _BOUNDS_BY_FILE entry for %s::%s -- only _MAX_DELTA_RATIO applies. "
                "Consider declaring explicit bounds.",
                rel_path, name,
            )
        return True, ""
    lo, hi = rng
    try:
        v = float(new_value)
    except (TypeError, ValueError):
        return False, f"new_value={new_value!r} not numeric"
    if v < lo or v > hi:
        return False, f"out_of_bounds new_value={new_value} not in [{lo}, {hi}]"
    return True, ""

# Limites duros: el extractor puede sugerir cambios extremos de los
# que la LLM exagera. Rechazamos cambios > X% de magnitud.
_MAX_DELTA_RATIO = 10.0   # nuevo no puede ser >10x ni <1/10 del viejo


# ── R11: Closed-loop self-evaluation ─────────────────────────────────────
# Mapping (rel_path, const_name) -> metric_name. Tras un apply exitoso,
# capturamos baseline; despues podemos comparar contra current y auto-rollback
# si hay regression. Solo constantes con metric runtime claro tienen entry.
_METRIC_BY_CONST: Dict[Tuple[str, str], str] = {
    ("core/llm.py", "_CB_FAIL_THRESHOLD"): "llm_fail_rate",
    ("core/llm.py", "_CB_COOLDOWN_S"):     "llm_fail_rate",
}

_METRICS_DIR = _STATE_DIR / "brain_metrics"


def _capture_metric_snapshot(metric_name: str) -> Optional[Dict]:
    """R11: lee llm_metrics_latest.json (o el correspondiente) y devuelve
    {metric, value, total, failed, captured_at}. None si no disponible."""
    if metric_name == "llm_fail_rate":
        f = _METRICS_DIR / "llm_metrics_latest.json"
        if not f.exists():
            return None
        try:
            data = json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            log.warning("R11: cannot read llm_metrics: %s", exc)
            return None
        total  = int(data.get("total")  or 0)
        failed = int(data.get("failed") or 0)
        rate   = failed / total if total > 0 else 0.0
        return {
            "metric": metric_name,
            "value": rate,
            "total": total,
            "failed": failed,
            "captured_at": datetime.now().isoformat(),
            "source_persisted_at": data.get("persisted_at"),
        }
    return None


def _baseline_for_edits(edits: List[Dict]) -> Dict:
    """Para cada edit con metric mapping, captura snapshot. Devuelve
    {const_key: snapshot}. Skips silenciosos si no hay metric."""
    out: Dict[str, Dict] = {}
    seen_metrics: Dict[str, Dict] = {}
    for e in edits:
        rel_path = e["rel_path"]
        name     = e["change"]["name"]
        metric   = _METRIC_BY_CONST.get((rel_path, name))
        if not metric:
            continue
        # Reuse same snapshot if multiple edits share metric (atomicity)
        if metric not in seen_metrics:
            snap = _capture_metric_snapshot(metric)
            if snap is None:
                continue
            seen_metrics[metric] = snap
        out[f"{rel_path}::{name}"] = {
            "metric": metric,
            "snapshot": seen_metrics[metric],
        }
    return out


def evaluate_proposal(proposal_id: str, min_age_minutes: int = 30,
                      regression_threshold: float = 0.20,
                      min_sample: int = 20,
                      auto_rollback: bool = True) -> Dict:
    """R11: evalua si una proposal applied_active esta degradando metricas.
    Si delta_rate > baseline_rate * (1 + regression_threshold) -> rollback.

    Returns: {ok, proposal_id, status, decision, comparisons[], ...}
      decision in {"too_young", "no_baseline", "insufficient_sample",
                   "validated", "regression_rollback", "regression_no_rollback"}
    """
    rec = _load_proposal(proposal_id)
    if rec is None:
        return {"ok": False, "error": "proposal_not_found"}

    if rec.get("status") not in ("applied_active", "applied_pending_restart"):
        return {"ok": True, "proposal_id": proposal_id,
                "decision": "skip_status", "status": rec.get("status")}

    baseline = rec.get("r11_baseline") or {}
    if not baseline:
        return {"ok": True, "proposal_id": proposal_id,
                "decision": "no_baseline"}

    # Age check
    applied_at_s = rec.get("applied_at") or rec.get("health_gate_completed_at")
    if applied_at_s:
        try:
            applied_at = datetime.fromisoformat(applied_at_s.replace("Z", ""))
            age_min = (datetime.now() - applied_at).total_seconds() / 60
            if age_min < min_age_minutes:
                return {"ok": True, "proposal_id": proposal_id,
                        "decision": "too_young",
                        "age_minutes": round(age_min, 1),
                        "min_age_minutes": min_age_minutes}
        except Exception:
            pass

    comparisons = []
    regression_count = 0
    insufficient_count = 0

    for const_key, info in baseline.items():
        metric = info.get("metric")
        snap_b = info.get("snapshot") or {}
        snap_n = _capture_metric_snapshot(metric)
        if snap_n is None:
            comparisons.append({"const": const_key, "verdict": "metric_unavailable"})
            continue

        delta_total  = snap_n.get("total", 0)  - snap_b.get("total", 0)
        delta_failed = snap_n.get("failed", 0) - snap_b.get("failed", 0)
        if delta_total < min_sample:
            comparisons.append({
                "const": const_key, "metric": metric,
                "verdict": "insufficient_sample",
                "delta_total": delta_total, "min_sample": min_sample,
            })
            insufficient_count += 1
            continue
        delta_rate = (delta_failed / delta_total) if delta_total > 0 else 0.0
        baseline_rate = snap_b.get("value", 0.0)
        # Tolerancia: si baseline_rate es 0, comparar con threshold absoluto
        threshold_rate = max(baseline_rate * (1 + regression_threshold),
                             baseline_rate + 0.02)  # min 2pp absolute slack
        is_regression = delta_rate > threshold_rate
        comp = {
            "const": const_key, "metric": metric,
            "baseline_rate": round(baseline_rate, 4),
            "delta_rate": round(delta_rate, 4),
            "threshold_rate": round(threshold_rate, 4),
            "delta_total": delta_total, "delta_failed": delta_failed,
            "verdict": "regression" if is_regression else "ok",
        }
        comparisons.append(comp)
        if is_regression:
            regression_count += 1

    rec["r11_eval_at"] = datetime.now().isoformat()
    rec["r11_comparisons"] = comparisons

    if regression_count > 0:
        if auto_rollback:
            _persist_proposal(proposal_id, rec)  # save comparisons before rollback
            roll = rollback_proposal(proposal_id, reason=f"r11_metric_regression: {regression_count}/{len(comparisons)} comp")
            return {"ok": True, "proposal_id": proposal_id,
                    "decision": "regression_rollback",
                    "comparisons": comparisons,
                    "rollback": roll,
                    "restart_hint": "Run powershell C:/AI_VAULT/tmp_agent/_kill_cim.ps1"}
        else:
            rec["r11_regression_detected"] = True
            _persist_proposal(proposal_id, rec)
            return {"ok": True, "proposal_id": proposal_id,
                    "decision": "regression_no_rollback",
                    "comparisons": comparisons}

    if insufficient_count == len(comparisons) and comparisons:
        _persist_proposal(proposal_id, rec)
        return {"ok": True, "proposal_id": proposal_id,
                "decision": "insufficient_sample",
                "comparisons": comparisons}

    rec["r11_validated"] = True
    _persist_proposal(proposal_id, rec)
    return {"ok": True, "proposal_id": proposal_id,
            "decision": "validated",
            "comparisons": comparisons}


def evaluate_active_proposals(min_age_minutes: int = 30,
                              regression_threshold: float = 0.20,
                              min_sample: int = 20,
                              auto_rollback: bool = True) -> Dict:
    """R11: itera todos los proposals applied_active con r11_baseline,
    evalua cada uno. Devuelve resumen agregado."""
    if not _PROPOSALS_DIR.exists():
        return {"ok": False, "error": "proposals_dir_missing"}
    results: List[Dict] = []
    for p in sorted(_PROPOSALS_DIR.glob("ce_prop_*.json")):
        try:
            rec = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if rec.get("status") not in ("applied_active", "applied_pending_restart"):
            continue
        if not rec.get("r11_baseline"):
            continue
        if rec.get("r11_validated") is True:
            continue  # already validated, no point re-evaluating
        results.append(evaluate_proposal(
            rec.get("id") or p.stem,
            min_age_minutes=min_age_minutes,
            regression_threshold=regression_threshold,
            min_sample=min_sample,
            auto_rollback=auto_rollback,
        ))
    summary = {"total": len(results)}
    for r in results:
        d = r.get("decision", "unknown")
        summary[d] = summary.get(d, 0) + 1
    return {"ok": True, "summary": summary, "results": results}


# ── Regex helpers ────────────────────────────────────────────────────────

# Patron tipo: "_CB_FAIL_THRESHOLD: elevar de 2 a 5"
#              "_CB_COOLDOWN_S de 180s a 60s"
#              "_CB_FAIL_THRESHOLD from 2 to 5"
#              "_CB_COOLDOWN_S: 180 -> 60"
#              "_CB_COOLDOWN_S: 180 => 60"
# R10.6: ampliado para aceptar tambien constantes ALL_CAPS sin '_' prefijo
# siempre que contengan al menos un underscore intermedio (ej. CHECK_INTERVAL,
# MIN_IMPACT_SCORE). Esto desbloquea los nuevos ficheros del whitelist sin
# generar falsos positivos con palabras comunes (TRUE, NONE, MAX, OK, etc).
# Patron: opcional '_' inicial + letra + chars + AL MENOS un '_' interno.
_CONST_NAME_RE = r"(_?[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){1,8})"
_NUM_RE        = r"(-?\d+(?:\.\d+)?)"

_PATTERNS = [
    # _NAME ... <num1> a <num2>      (espanol)
    re.compile(rf"{_CONST_NAME_RE}[^\d\n]{{0,80}}?(?:de\s+)?{_NUM_RE}\s*[a-z]?\s*(?:a|->|=>)\s*{_NUM_RE}", re.IGNORECASE),
    # _NAME ... from <num1> to <num2>
    re.compile(rf"{_CONST_NAME_RE}[^\d\n]{{0,80}}?from\s+{_NUM_RE}\s*[a-z]?\s+to\s+{_NUM_RE}", re.IGNORECASE),
]


def extract_constant_changes(text: str) -> List[Dict]:
    """
    Extrae propuestas de cambio de constante numerica desde texto libre.
    Returns list of {name, old_value, new_value} (deduped por name, primer
    match gana). Conservador: si hay ambiguedad lo deja fuera.
    """
    if not text:
        return []
    out: Dict[str, Dict] = {}
    for pat in _PATTERNS:
        for m in pat.finditer(text):
            name, old_s, new_s = m.group(1), m.group(2), m.group(3)
            if name in out:
                continue
            try:
                old_v = float(old_s)
                new_v = float(new_s)
            except ValueError:
                continue
            if old_v == new_v:
                continue
            # delta sanity
            if old_v != 0:
                ratio = abs(new_v / old_v) if old_v else 0
                if ratio > _MAX_DELTA_RATIO or ratio < (1 / _MAX_DELTA_RATIO):
                    log.info("extract_constant_changes: skipped %s (delta_ratio=%.2f)", name, ratio)
                    continue
            # cast to int if both look integer
            if old_s.lstrip("-").isdigit() and new_s.lstrip("-").isdigit():
                old_v = int(old_v)
                new_v = int(new_v)
            out[name] = {
                "name": name,
                "old_value": old_v,
                "new_value": new_v,
            }
    return list(out.values())


# ── File helpers ─────────────────────────────────────────────────────────

def _resolve_patchable_file(rel_or_abs: str) -> Optional[Path]:
    """Devuelve Path absoluta si el fichero esta en _PATCHABLE_FILES,
    o None. Acepta tanto 'core/llm.py' como 'brain_v9/core/llm.py' o
    abs path."""
    s = (rel_or_abs or "").replace("\\", "/").strip()
    if not s:
        return None
    # normalize: strip leading 'brain_v9/' or absolute prefix
    candidates = []
    for w in _PATCHABLE_FILES:
        if s == w or s.endswith("/" + w) or s.endswith(w):
            candidates.append(_BRAIN_ROOT / w)
    for c in candidates:
        if c.exists():
            return c
    return None


def _find_constant_line(text: str, name: str) -> Optional[Tuple[int, str, float]]:
    """Localiza la linea que define `name = <num>` (asignacion top-level
    o indented dentro de class). Devuelve (idx, line, current_value) o None.
    Si hay multiples matches, devuelve None (ambiguo - mas seguro abortar)."""
    pat = re.compile(rf"^(\s*){re.escape(name)}\s*=\s*{_NUM_RE}\s*(?:#.*)?$")
    matches: List[Tuple[int, str, float]] = []
    for i, line in enumerate(text.splitlines()):
        m = pat.match(line)
        if m:
            try:
                val = float(m.group(2))
                if m.group(2).lstrip("-").isdigit():
                    val = int(val)
            except ValueError:
                continue
            matches.append((i, line, val))
    if len(matches) != 1:
        return None
    return matches[0]


def _replace_value_in_line(line: str, name: str, new_value) -> str:
    pat = re.compile(rf"^(\s*{re.escape(name)}\s*=\s*){_NUM_RE}(\s*(?:#.*)?)$")
    m = pat.match(line)
    if not m:
        return line
    return f"{m.group(1)}{new_value}{m.group(3)}"


def _build_diff(orig: str, new: str, rel_path: str) -> str:
    return "".join(difflib.unified_diff(
        orig.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
        n=3,
    ))


# ── Proposal IO (lightweight, mirrors executor module) ───────────────────

def _load_proposal(proposal_id: str) -> Optional[Dict]:
    p = _PROPOSALS_DIR / f"{proposal_id}.json"
    if not p.exists():
        return None
    try:
        # utf-8-sig tolerates a leading BOM (PowerShell may write one if
        # the gate persists status changes via Set-Content -Encoding UTF8)
        with open(p, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def _persist_proposal(proposal_id: str, rec: Dict) -> bool:
    try:
        with open(_PROPOSALS_DIR / f"{proposal_id}.json", "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False)
        return True
    except Exception as exc:
        log.error("persist_proposal failed for %s: %s", proposal_id, exc)
        return False


# ── Core: plan -> dry-run -> apply ───────────────────────────────────────

def _plan_changes(rec: Dict) -> Dict:
    """Construye un plan: para cada (file, change) determina si es
    aplicable. Devuelve dict con keys ok/reason/edits.
    edits = [{rel_path, abs_path, line_idx, old_line, new_line, change}]"""
    files = rec.get("affected_files") or []
    text  = rec.get("proposed_change") or ""

    if not files:
        return {"ok": False, "reason": "no_affected_files"}
    if rec.get("status") not in ("pending_review", "auto_apply_pending"):
        return {"ok": False, "reason": f"status={rec.get('status')} not patchable"}

    changes = extract_constant_changes(text)
    if not changes:
        return {"ok": False, "reason": "no_constant_changes_extracted"}

    # R10.6: filtrado per-file se aplica MAS ABAJO (cuando ya conocemos
    # rel_path); aqui solo filtramos los globales para abortar temprano si
    # TODO el cambio era global-forbidden.
    global_forbidden = _FORBIDDEN_CONSTANTS_BY_FILE.get("*", set())
    if all(c["name"] in global_forbidden for c in changes):
        return {"ok": False, "reason": "all_changes_in_forbidden_list"}

    edits: List[Dict] = []
    skipped: List[Dict] = []
    for f in files:
        abs_p = _resolve_patchable_file(f)
        if abs_p is None:
            skipped.append({"file": f, "reason": "not_in_whitelist_or_missing"})
            continue
        try:
            content = abs_p.read_text(encoding="utf-8")
        except Exception as exc:
            skipped.append({"file": f, "reason": f"read_error:{exc}"})
            continue
        rel_path = str(abs_p.relative_to(_BRAIN_ROOT)).replace("\\", "/")
        for ch in changes:
            if _is_forbidden(ch["name"], rel_path):
                skipped.append({"file": rel_path, "constant": ch["name"], "reason": "forbidden_constant"})
                continue
            loc = _find_constant_line(content, ch["name"])
            if loc is None:
                skipped.append({"file": rel_path, "constant": ch["name"], "reason": "not_found_or_ambiguous"})
                continue
            line_idx, old_line, current_value = loc
            # sanity: current_value debe coincidir con old_value (sino el LLM se equivoco)
            if current_value != ch["old_value"]:
                skipped.append({
                    "file": rel_path, "constant": ch["name"],
                    "reason": f"current_value={current_value} mismatch_proposal_old={ch['old_value']}",
                })
                continue
            # R10.6b: bounds check explicito (solo aplica si la constante
            # tiene rango declarado para este file en _BOUNDS_BY_FILE)
            ok_b, msg_b = _check_bounds(ch["name"], rel_path, ch["new_value"])
            if not ok_b:
                skipped.append({
                    "file": rel_path, "constant": ch["name"],
                    "reason": msg_b,
                })
                continue
            new_line = _replace_value_in_line(old_line, ch["name"], ch["new_value"])
            if new_line == old_line:
                skipped.append({"file": rel_path, "constant": ch["name"], "reason": "replace_noop"})
                continue
            edits.append({
                "rel_path": rel_path,
                "abs_path": str(abs_p),
                "line_idx": line_idx,
                "old_line": old_line,
                "new_line": new_line,
                "change": ch,
            })

    if not edits:
        return {"ok": False, "reason": "no_applicable_edits", "skipped": skipped}
    return {"ok": True, "edits": edits, "skipped": skipped}


def _build_full_diff(edits: List[Dict]) -> str:
    """Para cada fichero afectado, lee contenido actual, aplica todos los
    edits en memoria y produce un unified diff combinado."""
    by_file: Dict[str, List[Dict]] = {}
    for e in edits:
        by_file.setdefault(e["abs_path"], []).append(e)

    parts: List[str] = []
    for abs_path, file_edits in by_file.items():
        try:
            orig = Path(abs_path).read_text(encoding="utf-8")
        except Exception as exc:
            parts.append(f"# diff_error {abs_path}: {exc}\n")
            continue
        lines = orig.splitlines(keepends=True)
        # ensure newline preserved
        for fe in file_edits:
            idx = fe["line_idx"]
            if idx >= len(lines):
                continue
            ending = "\n" if lines[idx].endswith("\n") else ""
            lines[idx] = fe["new_line"] + ending if not fe["new_line"].endswith("\n") else fe["new_line"]
        new_content = "".join(lines)
        rel_path = file_edits[0]["rel_path"]
        parts.append(_build_diff(orig, new_content, rel_path))
    return "".join(parts)


def dry_run_proposal(proposal_id: str) -> Dict:
    rec = _load_proposal(proposal_id)
    if rec is None:
        return {"ok": False, "error": "proposal_not_found"}
    plan = _plan_changes(rec)
    if not plan["ok"]:
        return {
            "ok": False,
            "proposal_id": proposal_id,
            "reason": plan["reason"],
            "skipped": plan.get("skipped", []),
        }
    diff = _build_full_diff(plan["edits"])
    # persist diff (no status change)
    rec["diff"] = diff
    rec["dry_run_at"] = datetime.now().isoformat()
    rec["planned_edits"] = [
        {k: v for k, v in e.items() if k != "abs_path"} for e in plan["edits"]
    ]
    rec["planned_skipped"] = plan.get("skipped", [])
    _persist_proposal(proposal_id, rec)
    return {
        "ok": True,
        "proposal_id": proposal_id,
        "diff": diff,
        "edits_count": len(plan["edits"]),
        "skipped": plan.get("skipped", []),
    }


def _backup_path(abs_path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{abs_path}.bak.{ts}"


def apply_proposal(proposal_id: str, by: str = "manual", note: str = "",
                   auto_restart: bool = False, poll_seconds: int = 90,
                   respawn_wait: int = 50) -> Dict:
    """Aplica el proposal de verdad. Backup + edit + py_compile + persist.
    Si `auto_restart=True`, lanza el health gate detached que reinicia el
    brain, valida /health, y hace auto-rollback si no recupera. El brain
    morira durante el restart - el health gate sobrevive porque corre
    detached. Resultado final visible en proposal status + health gate log."""
    rec = _load_proposal(proposal_id)
    if rec is None:
        return {"ok": False, "error": "proposal_not_found"}

    if rec.get("status") not in ("pending_review", "auto_apply_pending"):
        return {"ok": False, "error": f"status={rec.get('status')} not patchable"}

    plan = _plan_changes(rec)
    if not plan["ok"]:
        return {"ok": False, "error": plan["reason"], "skipped": plan.get("skipped", [])}

    edits = plan["edits"]
    # group edits by file -> single backup per file
    by_file: Dict[str, List[Dict]] = {}
    for e in edits:
        by_file.setdefault(e["abs_path"], []).append(e)

    backups: Dict[str, str] = {}
    applied_files: List[str] = []
    try:
        for abs_path, file_edits in by_file.items():
            bkp = _backup_path(abs_path)
            shutil.copy2(abs_path, bkp)
            backups[abs_path] = bkp

            # apply edits
            content = Path(abs_path).read_text(encoding="utf-8")
            lines = content.splitlines(keepends=True)
            for fe in file_edits:
                idx = fe["line_idx"]
                if idx >= len(lines):
                    raise RuntimeError(f"line_idx out of range for {abs_path}")
                ending = "\n" if lines[idx].endswith("\n") else ""
                new_line = fe["new_line"]
                if not new_line.endswith("\n"):
                    new_line = new_line + ending
                lines[idx] = new_line
            new_content = "".join(lines)
            Path(abs_path).write_text(new_content, encoding="utf-8")

            # validate compile
            try:
                py_compile.compile(abs_path, doraise=True)
            except py_compile.PyCompileError as exc:
                # rollback this file immediately
                shutil.copy2(bkp, abs_path)
                raise RuntimeError(f"py_compile failed for {abs_path}: {exc}") from exc

            applied_files.append(abs_path)

        diff = _build_full_diff(edits)
        rec["status"] = "applied_pending_restart"
        rec["applied_at"] = datetime.now().isoformat()
        rec["applied_by"] = by[:100]
        if note:
            rec["apply_note"] = note[:500]
        rec["diff"] = diff
        rec["backups"] = backups
        rec["applied_edits"] = [
            {k: v for k, v in e.items() if k != "abs_path"} for e in edits
        ]

        # R11: capturar baseline de metricas para constantes con mapping.
        # Esto permite evaluate_proposal mas tarde detectar regression.
        baseline = _baseline_for_edits(edits)
        if baseline:
            rec["r11_baseline"] = baseline
            log.info("Proposal %s R11 baseline captured: %d const(s)",
                     proposal_id, len(baseline))

        gate_spawned = False
        gate_error: Optional[str] = None
        if auto_restart:
            rec["status"] = "applied_pending_health"
            rec["health_gate_started_at"] = datetime.now().isoformat()
            rec["health_gate_poll_seconds"] = poll_seconds
            rec["health_gate_respawn_wait"] = respawn_wait
            try:
                gate_spawned = _spawn_health_gate(proposal_id, poll_seconds, respawn_wait)
            except Exception as gexc:
                gate_error = str(gexc)
                rec["health_gate_spawn_error"] = gate_error[:500]
                # leave status as applied_pending_health so operator sees it
        _persist_proposal(proposal_id, rec)
        log.info(
            "Proposal %s APPLIED by %s (files=%s, auto_restart=%s, gate_spawned=%s)",
            proposal_id, by, list(backups.keys()), auto_restart, gate_spawned,
        )
        return {
            "ok": True,
            "proposal_id": proposal_id,
            "status": rec["status"],
            "diff": diff,
            "backups": backups,
            "auto_restart": auto_restart,
            "health_gate_spawned": gate_spawned,
            "health_gate_error": gate_error,
            "restart_hint": (
                "Health gate running detached - poll /brain/chat_excellence/proposals/{id} for status"
                if auto_restart else
                "Run powershell C:/AI_VAULT/tmp_agent/_kill_cim.ps1 to restart brain"
            ),
        }
    except Exception as exc:
        # rollback any already-applied file
        rollback_log: List[str] = []
        for abs_path in applied_files:
            bkp = backups.get(abs_path)
            if bkp and Path(bkp).exists():
                try:
                    shutil.copy2(bkp, abs_path)
                    rollback_log.append(abs_path)
                except Exception as rexc:
                    log.error("rollback failed for %s: %s", abs_path, rexc)
        rec["status"] = "apply_failed"
        rec["apply_error"] = str(exc)[:500]
        rec["apply_failed_at"] = datetime.now().isoformat()
        rec["rolled_back_on_failure"] = rollback_log
        _persist_proposal(proposal_id, rec)
        log.error("Proposal %s APPLY FAILED: %s (rolled_back=%s)", proposal_id, exc, rollback_log)
        return {
            "ok": False,
            "proposal_id": proposal_id,
            "error": str(exc),
            "rolled_back": rollback_log,
        }


_HEALTH_GATE_SCRIPT = _TMP_AGENT / "_apply_health_gate.ps1"
_HEALTH_GATE_LOGS   = _STATE_DIR / "health_gate_logs"


def _spawn_health_gate(proposal_id: str, poll_seconds: int = 90, respawn_wait: int = 50) -> bool:
    """Lanza el health gate como Windows Scheduled Task one-shot.
    Inicialmente intentamos `subprocess.Popen` con DETACHED_PROCESS, pero
    en este entorno el brain corre dentro de un job object con
    KILL_ON_JOB_CLOSE: cuando el gate matase al brain, el propio gate
    morira tambien (mismo job). schtasks crea la tarea bajo el Task
    Scheduler service, que es totalmente independiente del proceso brain.

    Returns True si schtasks /create devuelve 0; raises sino."""
    if not _HEALTH_GATE_SCRIPT.exists():
        raise RuntimeError(f"health gate script missing: {_HEALTH_GATE_SCRIPT}")
    _HEALTH_GATE_LOGS.mkdir(parents=True, exist_ok=True)

    if sys.platform != "win32":
        raise RuntimeError("health gate currently only supported on Windows")

    # Task name unique per proposal (will overwrite if rerun, /F)
    task_name = f"BrainHealthGate_{proposal_id}"

    # Run ~90s in the future. schtasks /ST has HH:MM precision (no seconds),
    # so if we land in the same minute as 'now' the task is "in the past" and
    # schtasks emits a WARNING + the task never fires. +90s pushes us safely
    # into the next minute (worst case it runs ~30s after we wanted).
    from datetime import datetime as _dt, timedelta as _td
    run_at = _dt.now() + _td(seconds=90)
    # Round down to the minute (already at HH:MM:00 by formatter)
    st = run_at.strftime("%H:%M")
    sd = run_at.strftime("%m/%d/%Y")

    # Action: powershell -File gate.ps1 -ProposalId <id> -PollSeconds <s>
    tr = (
        f'powershell.exe -ExecutionPolicy Bypass -NoProfile -File '
        f'"{_HEALTH_GATE_SCRIPT}" -ProposalId {proposal_id} -PollSeconds {int(poll_seconds)} -RespawnWait {int(respawn_wait)}'
    )

    spawn_log = _HEALTH_GATE_LOGS / f"{proposal_id}.spawn.log"
    with open(spawn_log, "ab") as f:
        f.write(f"\n[{datetime.now().isoformat()}] schtasks create task={task_name} run_at={st} {sd}\n".encode("utf-8"))
        # Use /sc once + /st + /sd for one-shot
        cmd = [
            "schtasks.exe", "/Create", "/F",
            "/TN", task_name,
            "/TR", tr,
            "/SC", "ONCE",
            "/ST", st,
            "/SD", sd,
            "/RL", "LIMITED",
        ]
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=10,
                check=False,
            )
            f.write(res.stdout or b"")
            f.write(f"\n[schtasks exit={res.returncode}]\n".encode("utf-8"))
            if res.returncode != 0:
                raise RuntimeError(f"schtasks create failed rc={res.returncode}: {(res.stdout or b'').decode('utf-8', errors='replace')[:300]}")
        except subprocess.TimeoutExpired as exc:
            f.write(f"\n[schtasks TIMEOUT: {exc}]\n".encode("utf-8"))
            raise RuntimeError(f"schtasks timeout: {exc}")

    log.info("health gate scheduled task created for %s (run_at=%s)", proposal_id, st)
    return True


def get_health_gate_log(proposal_id: str, tail: int = 200) -> Dict:
    """Lee el log del health gate para un proposal. Devuelve last N lineas."""
    log_path = _HEALTH_GATE_LOGS / f"{proposal_id}.log"
    spawn_log = _HEALTH_GATE_LOGS / f"{proposal_id}.spawn.log"
    out: Dict = {
        "proposal_id": proposal_id,
        "log_exists": log_path.exists(),
        "log_path": str(log_path),
        "spawn_log_exists": spawn_log.exists(),
    }
    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            out["lines_total"] = len(lines)
            out["lines"] = lines[-tail:]
        except Exception as exc:
            out["read_error"] = str(exc)
    if spawn_log.exists() and not out.get("lines"):
        try:
            out["spawn_lines"] = spawn_log.read_text(encoding="utf-8", errors="replace").splitlines()[-50:]
        except Exception:
            pass
    return out


def rollback_proposal(proposal_id: str, reason: str = "manual") -> Dict:
    rec = _load_proposal(proposal_id)
    if rec is None:
        return {"ok": False, "error": "proposal_not_found"}
    backups = rec.get("backups") or {}
    if not backups:
        return {"ok": False, "error": "no_backups_recorded"}
    restored: List[str] = []
    failed: List[Dict] = []
    for abs_path, bkp in backups.items():
        if not Path(bkp).exists():
            failed.append({"file": abs_path, "reason": "backup_missing"})
            continue
        try:
            shutil.copy2(bkp, abs_path)
            restored.append(abs_path)
        except Exception as exc:
            failed.append({"file": abs_path, "reason": str(exc)})
    rec["status"] = "rolled_back"
    rec["rolled_back_at"] = datetime.now().isoformat()
    rec["rollback_reason"] = reason[:500]
    rec["rollback_restored"] = restored
    rec["rollback_failed"] = failed
    _persist_proposal(proposal_id, rec)
    log.info("Proposal %s ROLLED BACK: restored=%s failed=%s", proposal_id, restored, failed)
    return {
        "ok": len(failed) == 0,
        "proposal_id": proposal_id,
        "restored": restored,
        "failed": failed,
        "restart_hint": "Run powershell C:/AI_VAULT/tmp_agent/_kill_cim.ps1 to restart brain",
    }


# ── R10.7: Bulk apply queue ──────────────────────────────────────────────

def apply_batch_proposals(proposal_ids: List[str], by: str = "manual",
                          note: str = "", auto_restart: bool = False,
                          poll_seconds: int = 90, respawn_wait: int = 50,
                          stop_on_error: bool = True) -> Dict:
    """R10.7: aplica varias proposals secuencialmente con UN solo health-gate
    al final.

    Diseno:
      * Itera ids in-order. Para cada uno llama apply_proposal con
        auto_restart=False (NO restart entre proposals).
      * Acumula backups con FIRST-WRITE-WINS per abs_path: el primer
        .bak de un fichero contiene el estado PRE-batch real (los siguientes
        .bak ya tendrian cambios previos del batch).
      * Si stop_on_error=True y un apply falla, aborta el batch y deja los
        previos aplicados (cada uno tiene su propio rollback individual).
        Si False, sigue con el resto.
      * Crea un proposal sintetico `ce_batch_<ts>.json` con `backups` mergeados,
        para que el health-gate detached pueda hacer rollback de TODO el batch
        si el restart falla. Status: applied_pending_health (si auto_restart)
        o applied_pending_restart (si no).
      * Si auto_restart=True, spawneamos UN unico health gate contra el id
        sintetico del batch. NO se spawnean gates individuales.

    Returns:
      {ok, batch_id, applied: [...], failed: [...], skipped_already: [...],
       merged_backups: {...}, health_gate_spawned: bool, ...}
    """
    if not proposal_ids:
        return {"ok": False, "error": "empty_proposal_ids"}

    applied: List[Dict] = []
    failed: List[Dict] = []
    skipped: List[Dict] = []
    merged_backups: Dict[str, str] = {}
    aggregated_diff: List[str] = []

    for pid in proposal_ids:
        rec = _load_proposal(pid)
        if rec is None:
            failed.append({"proposal_id": pid, "error": "proposal_not_found"})
            if stop_on_error:
                break
            continue
        # Skip if already applied/rolled-back
        if rec.get("status") not in ("pending_review", "auto_apply_pending"):
            skipped.append({"proposal_id": pid, "status": rec.get("status")})
            continue

        result = apply_proposal(
            pid, by=f"batch:{by}", note=note,
            auto_restart=False,    # batch-level gate handles restart
        )
        if not result.get("ok"):
            failed.append({"proposal_id": pid, "error": result.get("error"),
                           "skipped_edits": result.get("skipped")})
            if stop_on_error:
                break
            continue

        applied.append({"proposal_id": pid, "status": result.get("status")})
        # Merge backups FIRST-WRITE-WINS (preserves pre-batch content)
        for abs_path, bkp in (result.get("backups") or {}).items():
            if abs_path not in merged_backups:
                merged_backups[abs_path] = bkp
        if result.get("diff"):
            aggregated_diff.append(f"# proposal {pid}\n{result['diff']}")

    # Build synthetic batch record so health-gate has somewhere to look
    batch_id = f"ce_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    batch_rec: Dict = {
        "id": batch_id,
        "type": "batch",
        "created_at": datetime.now().isoformat(),
        "applied_by": by[:100],
        "apply_note": note[:500] if note else "",
        "status": "applied_pending_restart",
        "applied_at": datetime.now().isoformat(),
        "member_proposal_ids": proposal_ids,
        "applied_members": [a["proposal_id"] for a in applied],
        "failed_members":  failed,
        "skipped_members": skipped,
        "backups": merged_backups,
        "diff": "\n".join(aggregated_diff),
    }

    gate_spawned = False
    gate_error: Optional[str] = None
    if auto_restart and merged_backups:
        batch_rec["status"] = "applied_pending_health"
        batch_rec["health_gate_started_at"] = datetime.now().isoformat()
        batch_rec["health_gate_poll_seconds"] = poll_seconds
        batch_rec["health_gate_respawn_wait"] = respawn_wait
        # Persist BEFORE spawn: gate reads file via $ProposalPath
        _persist_proposal(batch_id, batch_rec)
        try:
            gate_spawned = _spawn_health_gate(batch_id, poll_seconds, respawn_wait)
        except Exception as gexc:
            gate_error = str(gexc)
            batch_rec["health_gate_spawn_error"] = gate_error[:500]
            _persist_proposal(batch_id, batch_rec)
    else:
        _persist_proposal(batch_id, batch_rec)

    log.info(
        "Batch %s applied: %d ok, %d failed, %d skipped, gate=%s",
        batch_id, len(applied), len(failed), len(skipped), gate_spawned,
    )

    return {
        "ok": len(failed) == 0 and len(applied) > 0,
        "batch_id": batch_id,
        "applied": applied,
        "failed": failed,
        "skipped_already": skipped,
        "merged_backups": merged_backups,
        "files_touched": list(merged_backups.keys()),
        "auto_restart": auto_restart,
        "health_gate_spawned": gate_spawned,
        "health_gate_error": gate_error,
        "restart_hint": (
            f"Health gate running detached - poll /brain/chat_excellence/proposals/{batch_id}"
            if gate_spawned else
            "Run powershell C:/AI_VAULT/tmp_agent/_kill_cim.ps1 to restart brain"
        ),
    }
