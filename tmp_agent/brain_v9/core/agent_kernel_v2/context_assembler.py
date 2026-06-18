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

# Signals that suggest a follow-up question referring to previous topic
_FOLLOW_UP_SIGNALS = frozenset({
    # Spanish
    "haz lo mismo", "igual", "continúa", "continua", "sigue",
    "amplía", "amplia", "más profundo", "mas profundo",
    "y cómo", "y como", "entonces", "eso",
    "lo anterior", "esa búsqueda", "esa respuesta", "esa busqueda",
    "más detalle", "mas detalle", "cuéntame más", "cuentame mas",
    "explica mejor", "detalla", "aprofundiza", "enfócate", "enfocate",
    "regresa", "vuelve", "además", "ademas", "también", "tambien",
    "por qué", "porque", "sigue con", "continua con",
    # English
    "what about that", "continue", "do the same", "expand",
    "go deeper", "previous", "above", "more detail", "tell me more",
    "explain better", "elaborate", "go on", "what else", "and then",
    "what happened next", "furthermore", "moreover", "how about",
    "what about", "regarding that", "about that", "more on",
    "details on", "regarding", "focus on", "keep going",
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


def assemble_recent_context(
    user_id: str,
    current_goal: str,
    current_run_id: Optional[str] = None,
    max_turns: int = 5,
    max_chars: int = 4000,
) -> Dict[str, Any]:
    """
    Scan RUN_ROOT for recent runs by user_id, build compact summary.
    Safe for missing/malformed files.
    """
    if not RUN_ROOT.exists():
        return {"turns": [], "is_follow_up": _is_follow_up(current_goal), "summary": "", "prev_route": None}

    runs: List[Dict[str, Any]] = []
    for run_dir in RUN_ROOT.iterdir():
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
            # Prefer exact user_id match; allow shared test/local accounts
            if user_id and uid and user_id != uid and user_id not in ("local", "anonymous"):
                continue
            plan_tools = []
            if isinstance(data.get("plan"), list):
                plan_tools = [s.get("tool_name") for s in data["plan"] if s.get("tool_name")]
            runs.append({
                "run_id": rid,
                "user_id": uid,
                "goal": (data.get("goal_preview") or data.get("goal", ""))[:300],
                "route": data.get("intent_route", data.get("route", "n/a")),
                "classification": data.get("classification", "n/a"),
                "sources": [s.get("type", "") for s in data.get("evidence_sources", [])][:5],
                "tools": list(dict.fromkeys(plan_tools))[:10],
                "answer_preview": str(data.get("final_answer", ""))[:400],
                "modified_ts": run_dir.stat().st_mtime,
            })
        except Exception:
            continue

    if not runs:
        return {"turns": [], "is_follow_up": _is_follow_up(current_goal), "summary": "", "prev_route": None}

    runs.sort(key=lambda r: r["modified_ts"], reverse=True)
    recent = runs[:max_turns]

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
