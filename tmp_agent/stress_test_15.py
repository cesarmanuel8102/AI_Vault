"""Stress-test: 15 varied queries to Brain V9 chat endpoint."""
import requests, json, time, sys

URL = "http://localhost:8090/chat"
TIMEOUT = 45  # strict per-query timeout

QUERIES = [
    # --- English queries (3) ---
    ("EN: greeting",          "Hello, how are you?"),
    ("EN: capabilities",      "What can you do?"),
    ("EN: system status",     "Show me the system status"),

    # --- Agent tool-call tasks (4) ---
    ("AGENT: chat metrics",   "dame las metricas del chat"),
    ("AGENT: port check 11434","verifica si el puerto 11434 esta activo"),
    ("AGENT: self-test hist", "muestrame el historial de self-test"),
    ("AGENT: read file",      "lee las primeras 5 lineas de brain_v9/core/session.py"),

    # --- LLM reasoning (2) ---
    ("LLM: explain concept",  "explicame brevemente que es el ratio de sharpe"),
    ("LLM: code question",    "que hace la funcion _maybe_fastpath en session.py"),

    # --- Fastpath / slash (3) ---
    ("FAST: disk space",      "cuanto espacio tengo en disco"),
    ("FAST: python version",  "version de python instalada"),
    ("CMD: /risk",            "/risk"),

    # --- Edge cases (3) ---
    ("EDGE: empty-ish",       "   "),
    ("EDGE: unknown command", "/nonexistent"),
    ("EDGE: very long",       "necesito que analices detalladamente todas las posibles mejoras que se podrian hacer al sistema de trading incluyendo analisis de volatilidad mejorado y gestion de riesgo dinamica y backtesting con datos historicos de multiples timeframes y optimizacion de parametros usando algoritmos geneticos y machine learning para prediccion de precios"),
]

results = []
total_start = time.time()

for i, (label, msg) in enumerate(QUERIES, 1):
    t0 = time.time()
    try:
        r = requests.post(URL, json={"message": msg}, timeout=TIMEOUT)
        elapsed = (time.time() - t0) * 1000
        data = r.json()
        reply = data.get("response", "")
        success = data.get("success", False)
        model = data.get("model_used", "?")
        has_content = len(reply.strip()) > 0
        passed = success and has_content
        status = "PASS" if passed else "FAIL"
        reason = "ok" if passed else ("empty_response" if not has_content else f"success={success}")
    except requests.exceptions.Timeout:
        elapsed = (time.time() - t0) * 1000
        status = "FAIL"
        reason = "timeout_45s"
        model = "timeout"
        passed = False
        reply = ""
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        status = "FAIL"
        reason = str(e)[:80]
        model = "error"
        passed = False
        reply = ""

    results.append({
        "idx": i,
        "label": label,
        "status": status,
        "reason": reason,
        "model": model,
        "latency_ms": round(elapsed),
        "reply_len": len(reply),
    })
    icon = "OK" if passed else "XX"
    print(f"  [{icon}] {i:2d}/15  {label:25s}  {model:15s}  {round(elapsed):6d}ms  {reason}")
    # small gap to avoid hammering
    if i < len(QUERIES):
        time.sleep(1)

total_elapsed = time.time() - total_start
passed_count = sum(1 for r in results if r["status"] == "PASS")
failed_count = 15 - passed_count

print(f"\n{'='*60}")
print(f"  STRESS TEST RESULTS: {passed_count}/15 passed, {failed_count} failed")
print(f"  Total time: {total_elapsed:.1f}s")
print(f"{'='*60}")

if failed_count > 0:
    print("\n  FAILURES:")
    for r in results:
        if r["status"] == "FAIL":
            print(f"    #{r['idx']} {r['label']}: {r['reason']}")

# Save results
out = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "total": 15,
    "passed": passed_count,
    "failed": failed_count,
    "total_time_s": round(total_elapsed, 1),
    "results": results,
}
with open("C:/AI_VAULT/tmp_agent/state/brain_metrics/stress_test_15.json", "w") as f:
    json.dump(out, f, indent=2)
print(f"\n  Results saved to state/brain_metrics/stress_test_15.json")
