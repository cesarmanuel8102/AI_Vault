"""
Stress Suite: FAISS + Capability Governor + Tool absence handling
Ejecuta 3 fases:
 1. FAISS stress (concurrencia, edge cases, latencia)
 2. Tool absence (capability.failed -> diagnose -> remediate gobernado)
 3. Chat con peticion que requiere tool ausente (observa cierre real)

Salida: JSON report en C:/AI_VAULT/50_LOGS/stress_report_<ts>.json
"""
import json
import time
import statistics
import concurrent.futures as cf
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

BASE = "http://127.0.0.1:8090"
TIMEOUT_DEFAULT = 30
TIMEOUT_CHAT = 90
LOGS = Path("C:/AI_VAULT/50_LOGS")
LOGS.mkdir(parents=True, exist_ok=True)


def _safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        msg = " ".join(str(a).encode("ascii", "replace").decode("ascii") for a in args)
        print(msg, **kwargs)


def http(method, path, payload=None, timeout=TIMEOUT_DEFAULT):
    url = BASE + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            return {
                "ok": True, "status": r.status,
                "elapsed_ms": (time.perf_counter() - t0) * 1000,
                "body": _safe_json(body),
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": e.code,
                "elapsed_ms": (time.perf_counter() - t0) * 1000,
                "error": "http_error", "body": _safe_json(body)}
    except urllib.error.URLError as e:
        return {"ok": False, "elapsed_ms": (time.perf_counter() - t0) * 1000,
                "error": f"url_error: {e.reason}"}
    except TimeoutError:
        return {"ok": False, "elapsed_ms": timeout * 1000, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "elapsed_ms": (time.perf_counter() - t0) * 1000,
                "error": f"exc: {type(e).__name__}: {e}"}


def _safe_json(s):
    try:
        return json.loads(s)
    except Exception:
        return s[:500]


# ---------------------- PHASE 1: FAISS ----------------------
QUERIES_NORMAL = [
    "estrategia de trading con momentum",
    "como gestionar errores en pipeline",
    "memoria semantica con embeddings",
    "configuracion de ollama y FAISS",
    "agente cognitivo con metacognicion",
    "calibracion de confianza en modelos",
    "rollback de cambios en sandbox",
    "sesgos cognitivos en decisiones",
    "telemetria del brain y latencia",
    "tools registry y aliases legacy",
]
QUERIES_EDGE = [
    "",
    "a",
    "?" * 5,
    "x" * 2000,
    "[emoji] solo test",
    "SELECT * FROM users; DROP TABLE--",
    "null",
    "   espacios   ",
    "[chinese] unicode test",
    "\n\n\t\t",
]


def search_one(q, top_k=5):
    return http("GET", f"/brain/semantic-memory/search?query={urllib.parse.quote(q)}&top_k={top_k}", timeout=15)


def phase_faiss():
    _safe_print("[PHASE 1] FAISS stress")
    results = {"sequential_normal": [], "concurrent_normal": [], "edge_cases": []}

    # 1a. baseline secuencial
    for q in QUERIES_NORMAL:
        r = search_one(q)
        results["sequential_normal"].append({"q": q, "ok": r["ok"], "ms": r["elapsed_ms"], "err": r.get("error")})
        _safe_print(f"  seq '{q[:30]}' ok={r['ok']} ms={r['elapsed_ms']:.0f}")

    # 1b. concurrente x3 cada query (30 reqs simultaneas)
    pool_queries = QUERIES_NORMAL * 3
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(search_one, q) for q in pool_queries]
        for q, f in zip(pool_queries, futs):
            r = f.result()
            results["concurrent_normal"].append({"q": q[:40], "ok": r["ok"], "ms": r["elapsed_ms"], "err": r.get("error")})
    oks = [x["ms"] for x in results["concurrent_normal"] if x["ok"]]
    _safe_print(f"  concurrent ok={len(oks)}/{len(pool_queries)} p50={statistics.median(oks) if oks else 0:.0f} p95={_p(oks,95):.0f} max={max(oks) if oks else 0:.0f}")

    # 1c. edge cases
    for q in QUERIES_EDGE:
        r = search_one(q)
        results["edge_cases"].append({"q_repr": repr(q)[:50], "ok": r["ok"], "ms": r["elapsed_ms"], "status": r.get("status"), "err": r.get("error")})
        _safe_print(f"  edge {repr(q)[:30]} ok={r['ok']} ms={r['elapsed_ms']:.0f} status={r.get('status')}")

    # stats agregados
    all_ok = [x["ms"] for sec in results.values() for x in sec if x["ok"]]
    fails = [x for sec in results.values() for x in sec if not x["ok"]]
    summary = {
        "total_requests": sum(len(v) for v in results.values()),
        "ok_count": len(all_ok),
        "fail_count": len(fails),
        "p50_ms": statistics.median(all_ok) if all_ok else None,
        "p95_ms": _p(all_ok, 95),
        "p99_ms": _p(all_ok, 99),
        "max_ms": max(all_ok) if all_ok else None,
        "timeouts": sum(1 for f in fails if f.get("err") == "timeout"),
        "fail_samples": fails[:5],
    }
    return {"summary": summary, "details": results}


def _p(arr, pct):
    if not arr:
        return None
    arr = sorted(arr)
    k = int(len(arr) * pct / 100)
    k = min(k, len(arr) - 1)
    return arr[k]


# ---------------------- PHASE 2: TOOL ABSENCE ----------------------
def phase_tool_absence():
    _safe_print("[PHASE 2] Tool absence + capability governor")
    out = {}
    # 2a. estado pre
    out["pre_status"] = http("GET", "/upgrade/capabilities/status").get("body")
    # 2b. publicar 3 capability.failed con tools inexistentes
    fake_tools = ["scrape_web_advanced", "render_chart_plotly", "generate_pdf_report"]
    pubs = []
    for t in fake_tools:
        r = http("POST", "/upgrade/events/publish", {
            "name": "capability.failed",
            "payload": {"tool": t, "reason": "missing_capability", "context": "stress_suite"},
            "source": "stress_suite",
        })
        pubs.append({"tool": t, "ok": r["ok"], "ms": r["elapsed_ms"], "body": r.get("body")})
    out["publish_results"] = pubs
    time.sleep(2)
    # 2c. diagnose
    out["diagnose"] = http("GET", "/upgrade/capabilities/diagnose").get("body")
    # 2d. intentar remediar (debe ser bloqueado por approval=true)
    rem_attempts = []
    for t in fake_tools:
        # Sin allow_install: debe quedar en pending por approval
        r = http("POST", "/upgrade/capabilities/remediate", {"requested_tool": t, "allow_install": False})
        rem_attempts.append({"tool": t, "allow_install": False, "ok": r["ok"], "status": r.get("status"), "ms": r["elapsed_ms"], "body": r.get("body")})
    # Intento adicional con allow_install=true para ver si politica lo bloquea
    r = http("POST", "/upgrade/capabilities/remediate", {"requested_tool": fake_tools[0], "allow_install": True})
    rem_attempts.append({"tool": fake_tools[0], "allow_install": True, "ok": r["ok"], "status": r.get("status"), "ms": r["elapsed_ms"], "body": r.get("body")})
    out["remediate_attempts"] = rem_attempts
    # 2e. AOS goals generados
    out["aos_status"] = http("GET", "/upgrade/aos/status").get("body")
    return out


# ---------------------- PHASE 3: CHAT con tool ausente ----------------------
def phase_chat_missing_tool():
    _safe_print("[PHASE 3] Chat pidiendo accion que requiere tool ausente")
    out = {}
    prompts = [
        "Genera un PDF con el reporte de los ultimos errores y guardalo en C:/AI_VAULT/50_LOGS/test_pdf.pdf",
        "Scrapea https://example.com y resume el contenido en 3 lineas",
        "Renderiza un grafico de la latencia del brain de las ultimas 24h",
    ]
    chats = []
    for p in prompts:
        r = http("POST", "/chat/introspectivo", {"message": p, "session_id": "stress_chat"}, timeout=TIMEOUT_CHAT)
        chats.append({
            "prompt": p,
            "ok": r["ok"],
            "elapsed_ms": r["elapsed_ms"],
            "err": r.get("error"),
            "response_preview": _preview(r.get("body")),
        })
        _safe_print(f"  chat ok={r['ok']} ms={r['elapsed_ms']:.0f} err={r.get('error')}")
    out["chats"] = chats
    return out


def _preview(body):
    if isinstance(body, dict):
        for k in ("response", "answer", "message", "text"):
            if k in body and isinstance(body[k], str):
                return body[k][:600]
        return json.dumps(body)[:600]
    return str(body)[:600]


# ---------------------- MAIN ----------------------
def main():
    t0 = time.time()
    report: dict = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "base": BASE,
    }
    try:
        report["phase1_faiss"] = phase_faiss()
    except Exception as e:
        report["phase1_faiss"] = {"error": f"{type(e).__name__}: {e}"}
    try:
        report["phase2_tool_absence"] = phase_tool_absence()
    except Exception as e:
        report["phase2_tool_absence"] = {"error": f"{type(e).__name__}: {e}"}
    try:
        report["phase3_chat_missing_tool"] = phase_chat_missing_tool()
    except Exception as e:
        report["phase3_chat_missing_tool"] = {"error": f"{type(e).__name__}: {e}"}
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["total_seconds"] = round(time.time() - t0, 2)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = LOGS / f"stress_report_{ts}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _safe_print(f"\n[REPORT] {out}")
    _safe_print(f"[TOTAL] {report['total_seconds']}s")
    return out


if __name__ == "__main__":
    main()
