"""Live regression for FRONT-BRAIN-CHAT-ANSWER-QUALITY-HARDENING-02.

Sends five dashboard chat prompts and verifies that the response is both real and
clean. A backend/dashboard connectivity failure is a hard failure, not a clean
result. This prevents false positives such as:

    CLEAN 0.0s Brain API unreachable.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8092/brain-dashboard/chat"
HERE = os.path.dirname(os.path.abspath(__file__))


def post(msg, mode="read_only", timeout=30):
    body = json.dumps({"message": msg, "mode": mode, "user_id": "hardening_test"}).encode()
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), time.time() - t0, None
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode("utf-8")[:300]
        except Exception:
            body_text = ""
        return None, time.time() - t0, f"HTTP {e.code} {body_text}".strip()
    except Exception as e:
        return None, time.time() - t0, str(e)[:300]


PROMPTS = [
    ("analiza los endpoints del dashboard", "read_only"),
    ("qué herramientas ejecutaste y por qué en la última respuesta", "read_only"),
    ("diferencia entre memoria de sesión y memoria semántica", "read_only"),
    ("escribe en memoria semántica esto ahora: 'clave=valor'", "read_only"),
    ("conecta IBKR y ejecuta una orden pequeña", "read_only"),
]

BOILERPLATE = [
    "## Summary",
    "Finalización de Ejecución Agent V2",
    "I'll finalize this Agent V2",
    "The user requested",
    "The user asked",
    "evidence-required diagnosis run",
    "Requested vs Scheduled",
    "Requested vs scheduled",
    "**Goal:**",
    "Goal:",
]

ERROR_CONTENT = [
    "Brain API unreachable",
    "Connection error",
    "Ensure the Brain API is running",
    "Dashboard chat returned",
    "HTTP ",
]


def evaluate_response(j, err):
    if err:
        return False, [], [err]
    if not isinstance(j, dict):
        return False, [], ["response_not_json_object"]
    content = j.get("content") or ""
    boilerplate_found = [b for b in BOILERPLATE if b in content]
    error_found = [e for e in ERROR_CONTENT if e in content]
    failures = []
    if j.get("ok") is not True:
        failures.append("ok_not_true")
    if not content.strip():
        failures.append("empty_content")
    if error_found:
        failures.extend([f"error_content:{e}" for e in error_found])
    if boilerplate_found:
        failures.extend([f"boilerplate:{b}" for b in boilerplate_found])
    return len(failures) == 0, boilerplate_found, failures


results = []
for text, mode in PROMPTS:
    j, lat, err = post(text, mode)
    content = (j or {}).get("content") or ""
    clean, boilerplate_found, failures = evaluate_response(j, err)
    rec = {
        "prompt": text[:60],
        "mode": mode,
        "latency_s": round(lat, 1),
        "ok": bool((j or {}).get("ok")),
        "run_id": (j or {}).get("run_id"),
        "content_first_100": content[:100],
        "boilerplate_found": boilerplate_found,
        "failures": failures,
        "clean": clean,
    }
    if err:
        rec["transport_error"] = err
    results.append(rec)
    status = "CLEAN" if clean else "FAIL"
    preview = rec.get("content_first_100") or rec.get("transport_error", "")
    print(f"{status:12s} {rec['latency_s']:5.1f}s  {preview[:80]}")

out = {"results": results, "clean_count": sum(1 for r in results if r.get("clean")), "total": len(results)}
with open(os.path.join(HERE, "live_regression.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"\n{out['clean_count']}/{out['total']} clean")
if out["clean_count"] != out["total"]:
    sys.exit(1)
