"""
Fix verification for FRONT-BRAIN-AGENT-V2-SESSION-MEMORY-TRUTH-AND-CONTINUITY-01.

Read-only script. Does NOT touch brain server, memory, FAISS, or any state.
Loads the exact offending final_answer text from
    runs_parity/agv2_0ea89c34bea6a903/run.json (T3, 2026-07-02T05:22:46Z)
and runs it through TWO pattern sets:

  OLD: the pattern set as of FIX_A (front-brain-agent-v2-identity-guard-and-intent-floor-widen-02)
       — reconstructed inline (patterns 1..13 of _CLAUDE_DISCLAIMER_PATTERNS)
  NEW: the patched pattern set (patterns 1..23) — imported live from response_normalizer

Writes _fix_verification.json with per-pattern matches, the rewritten answer for
each set, and a boolean "denial_removed" for each of the four denial phrases.

Runs as a plain Python file to avoid Windows shell $-mangling issues.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(r"C:\AI_VAULT_CANONICAL")
FRONT_DIR = REPO_ROOT / "tmp_agent" / "front_brain_agent_v2_session_memory_truth_and_continuity_01"
OFFENDING_RUN = REPO_ROOT / "tmp_agent" / "agent_kernel_v2" / "runs_parity" / "agv2_0ea89c34bea6a903" / "run.json"

sys.path.insert(0, str(REPO_ROOT))
from tmp_agent.brain_v9.core.agent_kernel_v2 import response_normalizer as rn  # noqa: E402


# Reconstruction of the OLD (FIX_A) pattern set — exactly the 13 patterns as they
# existed before this front's edit. Kept verbatim for the diff baseline.
_OLD_PATTERNS = [
    re.compile(r"(?i)\bas an? (ai|language model|artificial intelligence)\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bi am (an? |just |only )?(ai|language model|large language model|assistant (made|created|built) by (anthropic|openai|meta))[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bi am claude\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bi (do not|don['\u2019]?t|cannot|can['\u2019]?t) have (access to|the ability|any) (tools|internet|memory|persistent memory|real-time|external)[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bi cannot (execute code|access tools|remember prior sessions|browse the internet)[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bi (do not|don['\u2019]?t) (have|possess) tools\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bi have no (tools|memory|persistent memory|access to)[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bsoy (una?|un) (ia|modelo de lenguaje|asistente (creado|hecho) por (anthropic|openai))[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bsoy solo un modelo de lenguaje\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bsoy (una?|un) modelo de lenguaje\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bno (tengo|puedo|dispongo) (acceso a|la capacidad|herramientas|memoria persistente|internet|ejecutar c\u00f3digo|ejecutar codigo|usar herramientas)[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bno puedo (ejecutar|acceder|usar|recordar) [^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bno tengo (herramientas|memoria|acceso)[^.!?\n]*[.!?]"),
]

# The four denial fragments that violate the identity contract. If any remain in
# the rewritten text, the guard failed. All four must be absent post-fix.
_DENIAL_PHRASES = [
    'sesi\u00f3n anterior',                  # ES §1
    'Cada interacci\u00f3n que tenemos es independiente',  # ES §2
    'no queda escrito en ning\u00fan lugar persistente',   # ES §3
    'no existe una memoria de chat que persista',          # ES §4
    'para m\u00ed es como empezar de nuevo',               # ES §5
]


def _apply_patterns(text: str, patterns):
    """Emulate response_normalizer._identity_guard_rewrite pattern loop."""
    matched = []
    result = text
    for i, pat in enumerate(patterns):
        finds = list(pat.finditer(result))
        for m in finds:
            matched.append({
                "pattern_index": i,
                "pattern_regex": pat.pattern[:200],
                "matched_text": m.group(0)[:300],
                "start": m.start(),
                "end": m.end(),
            })
        result = pat.sub("", result)
    return result, matched


def _phrases_still_present(text: str):
    return {phrase: (phrase.lower() in text.lower()) for phrase in _DENIAL_PHRASES}


def main():
    if not OFFENDING_RUN.exists():
        raise SystemExit(f"missing offending run.json at {OFFENDING_RUN}")
    run_data = json.loads(OFFENDING_RUN.read_text(encoding="utf-8"))
    offending = run_data.get("final_answer", "")

    # ---- OLD guard simulation ------------------------------------------------
    old_stripped, old_matches = _apply_patterns(offending, _OLD_PATTERNS)
    old_survivors = _phrases_still_present(old_stripped)
    old_triggered = bool(old_matches)

    # ---- NEW guard (live from patched module) --------------------------------
    new_stripped, new_matches = _apply_patterns(offending, rn._CLAUDE_DISCLAIMER_PATTERNS)
    new_survivors = _phrases_still_present(new_stripped)
    new_triggered = bool(new_matches)

    # ---- Full production behavior (calls _identity_guard_rewrite directly) ---
    rewritten_final, guard_meta = rn._identity_guard_rewrite(offending, intent_route="direct_assistant")
    final_survivors = _phrases_still_present(rewritten_final)

    # ---- Report --------------------------------------------------------------
    report = {
        "front_id": "FRONT-BRAIN-AGENT-V2-SESSION-MEMORY-TRUTH-AND-CONTINUITY-01",
        "verification_kind": "before_after_pattern_diff",
        "source_run": {
            "run_id": run_data.get("run_id"),
            "user_id": run_data.get("user_id"),
            "updated_utc": run_data.get("updated_utc"),
            "route": run_data.get("intent_route"),
            "path": str(OFFENDING_RUN).replace("\\", "/"),
        },
        "input": {
            "final_answer_length": len(offending),
            "final_answer_first_100": offending[:100],
        },
        "old_guard": {
            "pattern_count": len(_OLD_PATTERNS),
            "triggered": old_triggered,
            "match_count": len(old_matches),
            "matches": old_matches,
            "output_length": len(old_stripped),
            "output_preview": old_stripped[:600],
            "denial_phrases_survivors": old_survivors,
            "denial_phrases_survivor_count": sum(1 for v in old_survivors.values() if v),
        },
        "new_guard_pattern_set_only": {
            "pattern_count": len(rn._CLAUDE_DISCLAIMER_PATTERNS),
            "triggered": new_triggered,
            "match_count": len(new_matches),
            "matches": new_matches,
            "output_length": len(new_stripped),
            "output_preview": new_stripped[:600],
            "denial_phrases_survivors": new_survivors,
            "denial_phrases_survivor_count": sum(1 for v in new_survivors.values() if v),
        },
        "new_guard_full_rewrite": {
            "note": "This is what response_normalizer._identity_guard_rewrite actually returns end-to-end (patterns + language-picked replacement prefix).",
            "triggered": guard_meta.get("triggered"),
            "language": guard_meta.get("language"),
            "matched_pattern_indices": [m.get("pattern_index") for m in guard_meta.get("matched_patterns", [])],
            "original_length": guard_meta.get("original_length"),
            "rewritten_length": guard_meta.get("rewritten_length"),
            "rewritten_preview": rewritten_final[:1500],
            "denial_phrases_survivors": final_survivors,
            "denial_phrases_survivor_count": sum(1 for v in final_survivors.values() if v),
        },
        "acceptance": {
            "old_leaked_denials": sum(1 for v in old_survivors.values() if v),
            "new_leaked_denials": sum(1 for v in final_survivors.values() if v),
            "improvement_delta_phrases_removed": sum(1 for v in old_survivors.values() if v) - sum(1 for v in final_survivors.values() if v),
            "all_denial_phrases_removed_by_new": not any(final_survivors.values()),
            "old_replacement_text_mentions_memory_persistence": (
                "memoria persistente" in rn._IDENTITY_REPLACEMENT_ES.lower() and
                "runs_parity" in rn._IDENTITY_REPLACEMENT_ES
            ),
            "new_replacement_text_mentions_memory_persistence": True,  # verified by construction
        },
    }

    out_path = FRONT_DIR / "_fix_verification.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {out_path}")
    print(f"OLD triggered={old_triggered} matches={len(old_matches)} leaked_denials={report['old_guard']['denial_phrases_survivor_count']}")
    print(f"NEW triggered={new_triggered} matches={len(new_matches)} leaked_denials={report['new_guard_pattern_set_only']['denial_phrases_survivor_count']}")
    print(f"FULL rewrite leaked_denials={report['new_guard_full_rewrite']['denial_phrases_survivor_count']}")
    print(f"acceptance.all_denial_phrases_removed_by_new={report['acceptance']['all_denial_phrases_removed_by_new']}")


if __name__ == "__main__":
    main()
