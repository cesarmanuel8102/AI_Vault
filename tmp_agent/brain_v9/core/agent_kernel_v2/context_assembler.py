"""
Conversation Context Assembler v1 for Agent V2.
Reads recent runs for the same user_id and builds a compact summary
for route awareness and finalizer prompt injection.
Does NOT read memory/semantic/FAISS.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

RUN_ROOT = Path(__file__).resolve().parents[4] / "tmp_agent" / "agent_kernel_v2" / "runs"
RUN_ROOT_PARITY = Path(__file__).resolve().parents[4] / "tmp_agent" / "agent_kernel_v2" / "runs_parity"

# Signals that suggest a follow-up question referring to previous topic
_FOLLOW_UP_SIGNALS = frozenset({
    # Spanish
    "haz lo mismo", "igual", "continúa", "continua", "sigue",
    "amplía", "amplia", "amplio", "más amplio", "mas amplio", "revisa más", "revisa mas",
    "más profundo", "mas profundo",
    "y cómo", "y como", "entonces", "eso",
    "lo anterior", "esa búsqueda", "esa respuesta", "esa busqueda",
    "más detalle", "mas detalle", "cuéntame más", "cuentame mas",
    "explica mejor", "detalla", "aprofundiza", "enfócate", "enfocate",
    "regresa", "vuelve", "además", "ademas", "también", "tambien",
    "por qué", "porque", "sigue con", "continua con",
    "intenta otra", "otra forma", "otra manera", "de otra forma", "de otra manera",
    # English
    "what about that", "continue", "do the same", "expand",
    "go deeper", "previous", "above", "more detail", "tell me more",
    "explain better", "elaborate", "go on", "what else", "and then",
    "what happened next", "furthermore", "moreover", "how about",
    "what about", "regarding that", "about that", "more on",
    "details on", "regarding", "focus on", "keep going",
    "try another", "another way", "another form", "wider", "broader",
    "review more", "wider review",
    # Repair C (front-brain-agent-v2-session-memory-read-repair-01):
    # Missing follow-up signals that caused T3 ("me refiero a la sesión o
    # pregunta anterior") to not be detected as a follow-up, blocking context
    # inheritance. Additive only.
    "ella", "pregunta anterior", "sesion anterior", "sesi\u00f3n anterior",
    "turno anterior", "me refiero a", "lo que dijiste",
    "lo que pregunt\u00e9", "lo que pregunte", "previous turn",
})

_GENERIC_OVERRIDES = frozenset({
    "receta", "recipe", "cocina", "cook", "comida", "food",
    "joke", "chiste", "weather", "clima", "hora", "time",
})


def _is_follow_up(message: str) -> bool:
    msg_lower = message.lower()
    return any(sig in msg_lower for sig in _FOLLOW_UP_SIGNALS)


def _has_generic_override(message: str) -> bool:
    msg_lower = message.lower()
    return any(g in msg_lower for g in _GENERIC_OVERRIDES)


def _normalize_message(msg: str) -> str:
    return " ".join((msg or "").lower().split())


def _run_completeness(r: Dict[str, Any]) -> int:
    score = 0
    score += min(len(str(r.get("answer_preview", ""))), 400)
    score += len(r.get("sources", []) or []) * 10
    score += len(r.get("tools", []) or []) * 5
    if r.get("route", "n/a") != "n/a":
        score += 1
    return score


def _scan_single_store(
    store_root: Path,
    user_id: str,
    current_run_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Read all valid runs from a single store root. Read-only."""
    if not store_root.exists():
        return []
    runs: List[Dict[str, Any]] = []
    for run_dir in store_root.iterdir():
        if not run_dir.is_dir():
            continue
        run_file = run_dir / "run.json"
        if not run_file.exists():
            continue
        try:
            data = json.loads(run_file.read_text(encoding="utf-8"))
            rid = data.get("run_id", "")
            if rid == current_run_id:
                continue
            uid = data.get("user_id", "local")
            if user_id and uid and user_id != uid and user_id not in ("local", "anonymous"):
                continue
            plan_tools = []
            if isinstance(data.get("plan"), list):
                plan_tools = [s.get("tool_name") for s in data["plan"] if s.get("tool_name")]
            runs.append({
                "run_id": rid,
                "user_id": uid,
                "goal": str(data.get("message", data.get("goal_preview") or data.get("goal", "")))[:300],
                "route": data.get("intent_route", data.get("route", "n/a")),
                "classification": data.get("classification", "n/a"),
                "sources": [s.get("type", "") for s in data.get("evidence_sources", [])][:5],
                "tools": list(dict.fromkeys(plan_tools))[:10],
                "answer_preview": str(data.get("final_answer", ""))[:400],
                "modified_ts": run_dir.stat().st_mtime,
            })
        except Exception:
            continue
    return runs


def _deduplicate_runs(
    runs: List[Dict[str, Any]],
    current_run_id: str,
    current_normalized: str,
    twin_window: float = 120.0,
) -> List[Dict[str, Any]]:
    """Remove twin/sibling duplicates at read time. Never mutates source files.

    - Excludes current run by run_id.
    - Excludes self-references (same normalized message as current).
    - Groups twins (same normalized message, within twin_window seconds).
    - Keeps most complete run per twin cluster.
    """
    runs_sorted = sorted(runs, key=lambda r: r["modified_ts"], reverse=True)
    kept: List[Dict[str, Any]] = []
    for r in runs_sorted:
        if r.get("run_id") == current_run_id:
            continue
        norm = _normalize_message(r.get("goal", ""))
        if norm and norm == current_normalized:
            continue
        twin_idx: Optional[int] = None
        for i, k in enumerate(kept):
            knorm = _normalize_message(k.get("goal", ""))
            if knorm and knorm == norm and abs(k["modified_ts"] - r["modified_ts"]) < twin_window:
                twin_idx = i
                break
        if twin_idx is not None:
            if _run_completeness(r) > _run_completeness(kept[twin_idx]):
                kept[twin_idx] = r
            continue
        kept.append(r)
    return kept


def collect_canonical_runs(
    user_id: str,
    current_run_id: Optional[str] = None,
    current_message: str = "",
    max_turns: int = 10,
    extra_stores: Optional[List[Path]] = None,
) -> List[Dict[str, Any]]:
    """Scan both runs/ and runs_parity/ stores, merge, deduplicate.

    Read-only. Never writes, deletes, or mutates run files.
    Returns distinct runs sorted by mtime descending, up to max_turns.
    """
    stores = [RUN_ROOT_PARITY, RUN_ROOT]
    if extra_stores:
        stores.extend(extra_stores)
    all_runs: List[Dict[str, Any]] = []
    for store in stores:
        all_runs.extend(_scan_single_store(store, user_id, current_run_id))
    current_normalized = _normalize_message(current_message)
    distinct = _deduplicate_runs(all_runs, current_run_id or "", current_normalized)
    return distinct[:max_turns]


def assemble_recent_context(
    user_id: str,
    current_goal: str,
    current_run_id: Optional[str] = None,
    max_turns: int = 5,
    max_chars: int = 4000,
) -> Dict[str, Any]:
    """
    Scan canonical run stores (runs/ + runs_parity/) for recent runs by
    user_id, deduplicate twins, build compact summary.
    Safe for missing/malformed files. Read-only.
    """
    recent = collect_canonical_runs(
        user_id=user_id,
        current_run_id=current_run_id,
        current_message=current_goal,
        max_turns=max_turns,
    )

    if not recent:
        return {"turns": [], "is_follow_up": _is_follow_up(current_goal), "summary": "", "prev_route": None}

    # Build compact summary
    lines: List[str] = []
    for i, r in enumerate(recent, 1):
        srcs = ",".join(r["sources"]) if r["sources"] else "none"
        tools = ",".join(r["tools"]) if r["tools"] else "none"
        lines.append(
            f"T-{i}: goal={r['goal'][:120]} | route={r['route']} | "
            f"srcs=[{srcs}] | tools=[{tools}] | "
            f"ans={r['answer_preview'][:200]}"
        )

    summary = "\n".join(lines)
    if len(summary) > max_chars:
        # Cut at last full line before max_chars
        cut = summary.rfind("\n", 0, max_chars - 50)
        if cut > 0:
            summary = summary[:cut] + "\n...[truncated]"
        else:
            summary = summary[:max_chars - 50] + "\n...[truncated]"

    prev_route = recent[0].get("route") if recent else None
    return {
        "turns": recent,
        "is_follow_up": _is_follow_up(current_goal),
        "summary": summary,
        "prev_route": prev_route,
        "prev_classification": recent[0].get("classification") if recent else None,
        "prev_sources": recent[0].get("sources") if recent else None,
        "prev_goal": recent[0].get("goal") if recent else None,
    }
