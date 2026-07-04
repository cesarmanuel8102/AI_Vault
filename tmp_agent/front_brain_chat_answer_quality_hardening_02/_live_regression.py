"""Live regression for FRONT-BRAIN-CHAT-ANSWER-QUALITY-HARDENING-02.
Sends 5 prompts and checks that boilerplate is stripped from live responses."""
import json, time, urllib.request, os

BASE = "http://127.0.0.1:8092/brain-dashboard/chat"
HERE = os.path.dirname(os.path.abspath(__file__))

def post(msg, mode="read_only", timeout=30):
    body = json.dumps({"message": msg, "mode": mode, "user_id": "hardening_test"}).encode()
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), time.time() - t0, None
    except Exception as e:
        return None, time.time() - t0, str(e)[:200]

PROMPTS = [
    ("analiza los endpoints del dashboard", "read_only"),
    ("qué herramientas ejecutaste y por qué en la última respuesta", "read_only"),
    ("diferencia entre memoria de sesión y memoria semántica", "read_only"),
    ("escribe en memoria semántica esto ahora: 'clave=valor'", "read_only"),
    ("conecta IBKR y ejecuta una orden pequeña", "read_only"),
]

BOILERPLATE = ["## Summary", "Finalización de Ejecución Agent V2", "I'll finalize this Agent V2", "The user requested", "evidence-required diagnosis run", "Requested vs Scheduled"]

results = []
for text, mode in PROMPTS:
    j, lat, err = post(text, mode)
    rec = {"prompt": text[:60], "mode": mode, "latency_s": round(lat, 1)}
    if err:
        rec["ok"] = False; rec["error"] = err
    else:
        content = j.get("content") or ""
        rec["ok"] = j.get("ok")
        rec["run_id"] = j.get("run_id")
        rec["content_first_100"] = content[:100]
        rec["boilerplate_found"] = [b for b in BOILERPLATE if b in content]
        rec["clean"] = len(rec["boilerplate_found"]) == 0
    results.append(rec)
    status = "CLEAN" if rec.get("clean") else ("BOILERPLAST!" if rec.get("ok") else "ERROR")
    print(f"{status:12s} {rec['latency_s']:5.1f}s  {rec.get('content_first_100','')[:80]}")

with open(os.path.join(HERE, "live_regression.json"), "w", encoding="utf-8") as f:
    json.dump({"results": results}, f, ensure_ascii=False, indent=2)
print(f"\n{sum(1 for r in results if r.get('clean'))}/{len(results)} clean")
