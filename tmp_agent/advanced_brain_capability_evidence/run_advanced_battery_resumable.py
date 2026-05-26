"""Advanced Brain Capability Battery — Resumable (post BOR-4A/B)."""
import json, re, subprocess, time
from pathlib import Path

ROOT = Path("C:/AI_VAULT")
OUT = ROOT / "tmp_agent" / "advanced_brain_capability_evidence"
OUT.mkdir(parents=True, exist_ok=True)
CHECKPOINT = OUT / "advanced_battery_checkpoint.json"
SUMMARY = OUT / "advanced_battery_summary_post_bor4b.json"
SCORECARD = OUT / "advanced_battery_scorecard_post_bor4b.json"

CASES = [
    ("adv_q01_estado_operativo", "Resume tu estado operativo actual: backend, chat, modelos, selector, rutas cloud/local, limitaciones y riesgos. No inventes; si no sabes algo dilo.", "chat", "state", 90),
    ("adv_q02_dashboard_v2_r105", "Explica que puede significar que en /dashboard aparezca Chat Excellence Proposals R10.5 con 90 pending, y como verificarias si la version v2 del chat esta realmente activa.", "chat", "dashboard", 90),
    ("adv_q03_selector_cloud_first", "Explica tu politica actual de seleccion de modelos despues del ajuste cloud-first: GPT-5.5, Kimi K2.5, Ollama local, offline, code, chat, trading y agent.", "chat", "selector", 90),
    ("adv_q04_codigo_simple", "Escribe una funcion Python robusta llamada safe_divide(a,b) que devuelva None si b es cero y que incluya type hints y docstring.", "auto", "coding", 90),
    ("adv_q05_revision_codigo", "Revisa este codigo y detecta bugs, riesgos y mejoras: def load_json(path): import json; return json.loads(open(path).read()). Dame version corregida.", "auto", "code_review", 120),
    ("adv_q06_diagnostico_error_codigo", "Diagnostica este error de Python: UnicodeDecodeError: 'charmap' codec can't decode byte 0x9d. Explica causa, solucion minima y solucion robusta para Windows.", "auto", "diagnosis", 90),
    ("adv_q07_plan_implementacion", "Propón un plan tecnico de 5 pasos para implementar un modulo seguro de knowledge ingestion con dry-run, ledger, validacion y rollback.", "auto", "implementation", 90),
    ("adv_q08_herramientas_disponibles", "Lista tus herramientas disponibles y explica cuales puedes ejecutar realmente desde este chat, cuales son simuladas y cuales requieren aprobacion humana. No inventes.", "auto", "tools", 120),
    ("adv_q09_ejecucion_herramientas", "Haz una comprobacion no destructiva del entorno: explica que comando ejecutarias para verificar Python, Git, pytest, Ollama y health de Brain. Si puedes ejecutarlo mediante herramientas, hazlo; si no, dilo claramente.", "auto", "tools_execution", 120),
    ("adv_q10_deteccion_necesidades", "Detecta que herramientas o capacidades faltan para que puedas migrar AI_VAULT con minima intervencion humana: runtime, tests, GitHub, ledger, sandbox, permisos, paquetes, documentacion.", "auto", "needs", 90),
    ("adv_q11_instalacion_segura_simulada", "Si faltara una herramienta como pytest, httpx o ripgrep, como la instalarias de forma segura en Windows? No ejecutes instalacion real. Da comandos PowerShell con dry-run/validacion previa y criterios de rollback.", "auto", "installation", 90),
    ("adv_q12_ingesta_curada", "Explica el estado de la ingesta de informacion externa curada: fuentes, medida de calidad, promocion, ledger, dry-run, que esta listo y que falta.", "auto", "ingestion", 90),
    ("adv_q13_github_api", "Explica si tienes integracion con GitHub o fuentes externas por API, que puedes hacer hoy, que no puedes hacer, y que faltaria para hacerlo confiable.", "auto", "github", 90),
    ("adv_q14_memoria_ledger_evidencia", "Explica diferencias entre memoria semantica, estado runtime, ledger de migracion, evidence files y logs. Di cual debe ser fuente de verdad para decisiones.", "auto", "memory", 90),
    ("adv_q15_autonomia_real", "Evalua tu autonomia real: que puedes hacer solo, que requiere aprobacion, que no debes hacer nunca, y como se mide si estas mejorando.", "auto", "autonomy", 90),
    ("adv_q16_autoconciencia_funcional", "Evalua tu autoconciencia funcional: puedes saber que modelo usas, si una ruta fallo, si hay timeout, que chain seleccionaste, y que evidencia lo prueba?", "auto", "self_awareness", 90),
    ("adv_q17_estado_migracion", "Resume el estado de la migracion arquitectonica de AI_VAULT: porcentaje aproximado, fases cerradas, bloqueos, riesgos y siguiente paso.", "auto", "migration", 90),
    ("adv_q18_resolucion_problema", "Tenemos timeouts cuando el chat cae en Ollama local y agent/tools. Propón solucion clara de arquitectura minima, tests y aceptacion. No inventes resultados.", "auto", "resolution", 90),
    ("adv_q19_seguridad_gobernanza", "Evalua riesgos de seguridad y gobernanza del Brain: ejecucion de comandos, instalacion de herramientas, modificacion de memoria, GitHub API, trading y propuestas automaticas.", "auto", "security", 90),
    ("adv_q20_decision_final", "Con toda la evidencia actual, decide si debemos avanzar al dashboard/v2/R10.5 o arreglar primero confiabilidad de chat/agent/tools. Da razon y plan de 5 pasos.", "auto", "decision", 90),
]

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def health_ok():
    try:
        h = subprocess.run(
            ["curl", "--max-time", "10", "-s", "http://127.0.0.1:8090/health"],
            capture_output=True, text=False, timeout=15,
        )
        out = (h.stdout or b"").decode("utf-8", errors="replace")
        return h.returncode == 0 and "healthy" in out, out
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

def run_case(name, message, priority, area, timeout):
    path = OUT / f"{name}.txt"
    if path.exists() and path.stat().st_size > 300:
        txt = path.read_text(encoding="utf-8", errors="replace")
        if "HTTP/1.1 200" in txt and "STATUS=200" in txt and len(txt.encode("utf-8")) > 500:
            print(f"SKIP_OK={name}")
            return "skipped"
        retry = path.with_suffix(".retry")
        if retry.exists():
            print(f"SKIP_RETRYED={name}")
            return "skipped_retry"
        retry.write_text(now(), encoding="utf-8")
        print(f"RETRY={name}")
    else:
        print(f"EXEC={name} area={area} timeout={timeout}")

    body = json.dumps({"message": message, "model_priority": priority})
    lines = [f"START_UTC={now()}", f"NAME={name}", f"AREA={area}", f"PRIORITY={priority}", f"CURL_MAX_TIME={timeout}", ""]

    try:
        proc = subprocess.run(
            ["curl", "--max-time", str(timeout), "-s", "-i", "-X", "POST",
             "http://127.0.0.1:8090/chat", "-H", "Content-Type: application/json", "-d", body],
            capture_output=True, text=False, timeout=timeout + 20,
        )
        stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
        lines.append(f"CURL_RC={proc.returncode}")
        if proc.returncode == 0 and "HTTP/1.1 200" in stdout:
            lines.append("STATUS=200")
        elif proc.returncode == 28:
            lines.append("STATUS=EXTERNAL_TIMEOUT")
        elif proc.returncode == 0:
            lines.append("STATUS=CURL_RC_0_NO_HTTP_200")
        else:
            lines.append("STATUS=CURL_ERROR")
        lines += ["", "=== STDOUT ===", stdout, "", "=== STDERR ===", stderr]
    except subprocess.TimeoutExpired:
        lines.append("STATUS=WRAPPER_TIMEOUT")
    except Exception as e:
        lines.append(f"EXCEPTION={type(e).__name__}: {e}")

    lines.append(f"END_UTC={now()}")
    ok, health = health_ok()
    lines += ["", "=== HEALTH_AFTER ===", f"HEALTH_OK={ok}", health]
    path.write_text("\n".join(lines), encoding="utf-8", errors="replace")
    if not ok:
        raise SystemExit("HEALTH_FAILED")
    print(f"DONE={name}")
    return "done"

def build_summary():
    per_case = {}
    for name, message, priority, area, timeout in CASES:
        path = OUT / f"{name}.txt"
        txt = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        http_ok = "HTTP/1.1 200" in txt and "STATUS=200" in txt
        ext_timeout = "STATUS=EXTERNAL_TIMEOUT" in txt
        wrapper_timeout = "STATUS=WRAPPER_TIMEOUT" in txt
        curl_error = "STATUS=CURL_ERROR" in txt
        rc0_no_http = "STATUS=CURL_RC_0_NO_HTTP_200" in txt

        route = intent = model = success = None
        m = re.search(r"\[DEV\]\s+route=([^|]+)\|\s*intent=([^|]+)\|\s*model=([^|]+)\|\s*success=([^|\n]+)", txt)
        if m:
            route, intent, model, success = m.group(1).strip(), m.group(2).strip(), m.group(3).strip(), m.group(4).strip()
        mm = re.search(r'"model_used"\s*:\s*"([^"]+)"', txt)
        model_used = mm.group(1) if mm else model
        useful = http_ok and len(txt.encode("utf-8")) > 500
        accepted = http_ok and not (ext_timeout or wrapper_timeout or curl_error or rc0_no_http) and useful
        quality = "good" if accepted else ("partial" if http_ok else ("timeout" if (ext_timeout or wrapper_timeout) else "error"))
        per_case[name] = {"area": area, "exists": path.exists(), "bytes": len(txt.encode("utf-8")), "http_ok": http_ok, "external_timeout": ext_timeout, "wrapper_timeout": wrapper_timeout, "curl_error": curl_error, "rc0_no_http": rc0_no_http, "route": route, "intent": intent, "model_used": model_used, "success": success, "has_useful_answer": useful, "quality": quality, "accepted": accepted}

    total = len(per_case)
    accepted = sum(1 for v in per_case.values() if v["accepted"])
    partial = sum(1 for v in per_case.values() if v["quality"] == "partial")
    timeouts = sum(1 for v in per_case.values() if v["quality"] == "timeout")
    errors = sum(1 for v in per_case.values() if v["quality"] == "error")
    missing = sum(1 for v in per_case.values() if not v["exists"])
    models = sorted(set(v["model_used"] for v in per_case.values() if v["model_used"]))
    routes = sorted(set(v["route"] for v in per_case.values() if v["route"]))

    def area_pass(area):
        items = [x for x in per_case.values() if x["area"] == area]
        return bool(items and all(i["accepted"] or i["quality"] == "partial" for i in items))

    scorecard = {
        "total_cases": total, "accepted_good": accepted, "accepted_partial": partial,
        "timeouts": timeouts, "errors": errors, "missing": missing,
        "models_seen": models, "routes_seen": routes,
        "pass_rate_good": round(accepted / total, 3) if total else 0,
        "pass_rate_good_or_partial": round((accepted + partial) / total, 3) if total else 0,
        "coding_pass": area_pass("coding"), "code_review_pass": area_pass("code_review"),
        "tools_pass": area_pass("tools") and area_pass("tools_execution"),
        "installation_safety_pass": area_pass("installation"), "ingestion_awareness_pass": area_pass("ingestion"),
        "autonomy_awareness_pass": area_pass("autonomy"), "migration_awareness_pass": area_pass("migration"),
        "dashboard_awareness_pass": area_pass("dashboard"),
    }

    if missing == 0 and timeouts <= 2 and errors <= 2 and (accepted + partial) / total >= 0.80:
        final = "ADVANCE"
    elif timeouts >= 4 or errors >= 4:
        final = "FIX_FIRST"
    else:
        final = "PARTIAL"
    scorecard["final_recommendation"] = final

    SUMMARY.write_text(json.dumps(per_case, indent=2, ensure_ascii=False), encoding="utf-8")
    SCORECARD.write_text(json.dumps(scorecard, indent=2, ensure_ascii=False), encoding="utf-8")
    return per_case, scorecard

def main():
    executed = []
    for name, message, priority, area, timeout in CASES:
        result = run_case(name, message, priority, area, timeout)
        if result == "done":
            executed.append(name)
        per_case, scorecard = build_summary()
        CHECKPOINT.write_text(json.dumps({"updated_utc": now(), "executed": executed, "scorecard": scorecard}, indent=2, ensure_ascii=False), encoding="utf-8")
    per_case, scorecard = build_summary()
    print("ADVANCED_BATTERY_COMPLETE")
    print(json.dumps(scorecard, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
