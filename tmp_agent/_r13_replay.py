"""R13 - Replay regression suite.

Reads state/conversations/*.json, replays the FIRST user message of each room
against the current brain (port 8090), captures the new response, and produces
a side-by-side comparison report with simple regression heuristics:

  - improved : new response avoids the old failure pattern (e.g. "missing
               required argument", "Error desconocido", "no puedo acceder",
               "faltan detalles")
  - regressed : old worked, new fails
  - same      : both succeeded or both failed similarly
  - new_session : room had no prior assistant reply

Output: state/r13_replay/report_<ts>.json + console summary table.
"""
from __future__ import annotations
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

CONV_DIR = Path("C:/AI_VAULT/tmp_agent/state/conversations")
OUT_DIR = Path("C:/AI_VAULT/tmp_agent/state/r13_replay")
OUT_DIR.mkdir(parents=True, exist_ok=True)
BRAIN = "http://127.0.0.1:8090"
TIMEOUT = 120
MAX_ROOMS = 30  # safety cap

# Heuristics for "old failed" detection (these were the symptoms we targeted)
FAILURE_MARKERS = [
    "missing required argument",
    "error desconocido",
    "faltan detalles",
    "no puedo acceder",
    "needs_clarification",
    "missing_args",
    "(sin respuesta)",
    "no obtuve resultados",
    "no tengo herramientas",
]

# Heuristics for "new is better" - either avoids the old marker entirely, or
# produces the new structured hint (which guides the user instead of dead-ending)
IMPROVEMENT_MARKERS = [
    "firma",
    "signature",
    "re-invoke",
    "truncated",
    "policy",
    "forbidden_path_markers",
    "god mode",
    "ledger",
    "filter_name",
    "refine",
]


def post_chat(message: str, session_id: str) -> dict:
    body = json.dumps({
        "session_id": session_id,
        "message": message,
        "model_priority": "ollama",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BRAIN}/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"response": f"HTTP_ERROR {e.code} {e.reason}", "success": False}
    except Exception as e:
        return {"response": f"EXCEPTION {type(e).__name__}: {e}", "success": False}


def has_marker(text: str, markers: list) -> str:
    t = (text or "").lower()
    for m in markers:
        if m in t:
            return m
    return ""


def classify(old_text: str, new_text: str, new_success: bool) -> str:
    old_failed = bool(has_marker(old_text, FAILURE_MARKERS)) or not old_text.strip()
    new_failed = bool(has_marker(new_text, FAILURE_MARKERS))
    new_improved = bool(has_marker(new_text, IMPROVEMENT_MARKERS))

    if old_failed and not new_failed:
        return "improved"
    if old_failed and new_improved:
        return "improved_with_hint"
    if not old_failed and new_failed:
        return "regressed"
    if old_failed and new_failed:
        return "still_failing"
    return "same_ok"


def main() -> int:
    files = sorted(CONV_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    files = files[:MAX_ROOMS]
    print(f"Replaying {len(files)} most recent rooms against brain at {BRAIN}")
    print(f"Failure markers: {FAILURE_MARKERS}")
    print()

    # Brain health gate
    try:
        with urllib.request.urlopen(f"{BRAIN}/health", timeout=5) as r:
            h = json.loads(r.read())
            if h.get("status") != "healthy":
                print(f"BRAIN NOT HEALTHY: {h}")
                return 1
    except Exception as e:
        print(f"BRAIN UNREACHABLE: {e}")
        return 1

    results = []
    counts: dict = {}
    for i, fp in enumerate(files):
        try:
            doc = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  SKIP {fp.name}: {e}")
            continue
        msgs = doc.get("messages", [])
        first_user = next((m for m in msgs if m.get("role") == "user"), None)
        first_asst = next((m for m in msgs if m.get("role") == "assistant"), None)
        if not first_user:
            continue
        user_msg = first_user.get("content", "").strip()
        old_resp = (first_asst or {}).get("content", "") if first_asst else ""
        if not user_msg or len(user_msg) > 500:
            continue

        sid = f"r13_replay_{int(time.time())}_{i}"
        t0 = time.monotonic()
        new = post_chat(user_msg, sid)
        elapsed = time.monotonic() - t0
        new_resp = new.get("response", "")
        verdict = classify(old_resp, new_resp, new.get("success", False))
        counts[verdict] = counts.get(verdict, 0) + 1

        old_marker = has_marker(old_resp, FAILURE_MARKERS) or "-"
        new_marker = has_marker(new_resp, FAILURE_MARKERS) or "-"
        new_improv = has_marker(new_resp, IMPROVEMENT_MARKERS) or "-"

        results.append({
            "room": fp.name,
            "user_msg": user_msg[:120],
            "old_len": len(old_resp),
            "old_failure_marker": old_marker,
            "new_len": len(new_resp),
            "new_failure_marker": new_marker,
            "new_improvement_marker": new_improv,
            "new_success": new.get("success"),
            "elapsed_s": round(elapsed, 1),
            "verdict": verdict,
            "old_resp_preview": old_resp[:200],
            "new_resp_preview": new_resp[:300],
        })
        print(f"  [{verdict:20s}] ({elapsed:5.1f}s) old_mark={old_marker:30s} -> new_mark={new_marker}")
        print(f"    Q: {user_msg[:90]}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"report_{ts}.json"
    out_path.write_text(
        json.dumps({
            "generated": datetime.now().isoformat(),
            "rooms_evaluated": len(results),
            "verdict_counts": counts,
            "results": results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print()
    print("=" * 60)
    print(f"R13 REPLAY SUMMARY ({len(results)} rooms)")
    print("=" * 60)
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        pct = 100.0 * v / max(1, len(results))
        print(f"  {k:25s} {v:3d}  ({pct:5.1f}%)")
    print()
    print(f"Report saved: {out_path}")
    improved = counts.get("improved", 0) + counts.get("improved_with_hint", 0)
    regressed = counts.get("regressed", 0)
    print()
    print(f"NET IMPROVEMENT: +{improved} improved / -{regressed} regressed")
    return 0 if regressed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
