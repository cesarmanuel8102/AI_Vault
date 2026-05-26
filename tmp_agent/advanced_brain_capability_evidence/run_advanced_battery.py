"""Advanced Brain Capability Battery (BOR-4A continuation)."""

import json
import subprocess
import time
from pathlib import Path

REPO = Path("C:/AI_VAULT")
OUT = REPO / "tmp_agent" / "advanced_brain_capability_evidence"
OUT.mkdir(parents=True, exist_ok=True)


def post_chat(name: str, message: str, priority: str, timeout: int = 90):
    out_file = OUT / f"{name}.txt"
    if out_file.exists():
        print(f"SKIP_EXISTING={name}")
        return True

    body = json.dumps({"message": message, "model_priority": priority})
    lines = [
        f"START_UTC={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"NAME={name}",
        f"PRIORITY={priority}",
        f"TIMEOUT={timeout}",
        "",
    ]

    try:
        proc = subprocess.run(
            ["curl", "--max-time", str(timeout), "-s", "-i",
             "-X", "POST", "http://127.0.0.1:8090/chat",
             "-H", "Content-Type: application/json", "-d", body],
            capture_output=True,
            text=True,
            timeout=timeout + 15,
        )
        if proc.returncode == 0 and "HTTP/1.1 200" in (proc.stdout or ""):
            lines += ["STATUS=200", proc.stdout or ""]
        else:
            lines += [f"CURL_RC={proc.returncode}", proc.stdout or "", proc.stderr or ""]
    except subprocess.TimeoutExpired:
        lines.append("TIMEOUT=YES")
    except Exception as e:
        lines.append(f"EXCEPTION={type(e).__name__}: {e}")

    lines.append(f"END_UTC={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"CASE={name} DONE")
    return True


if __name__ == "__main__":
    cases = [
        ("adv_q01_estado_operativo", "Resume tu estado operativo actual: backend, chat, modelos, selector, rutas cloud/local, limitaciones y riesgos. No inventes; si no sabes algo dilo.", "chat"),
        ("adv_q02_dashboard_v2_r105", "Explica que puede significar que en /dashboard aparezca Chat Excellence Proposals R10.5 con 90 pending, y como verificarias si la version v2 del chat esta realmente activa.", "chat"),
        ("adv_q03_selector_cloud_first", "Explica tu politica actual de seleccion de modelos despues del ajuste cloud-first: GPT-5.5, Kimi K2.5, Ollama local, offline, code, chat, trading y agent.", "chat"),
        ("adv_q04_codigo_simple", "Escribe una funcion Python robusta llamada safe_divide(a,b) que devuelva None si b es cero y que incluya type hints y docstring.", "auto"),
        ("adv_q05_revision_codigo", "Revisa este codigo y detecta bugs, riesgos y mejoras: def load_json(path): import json; return json.loads(open(path).read()). Dame version corregida.", "auto"),
        ("adv_q06_diagnostico_error_codigo", "Diagnostica este error de Python: UnicodeDecodeError: 'charmap' codec can't decode byte 0x9d. Explica causa, solucion minima y solucion robusta para Windows.", "auto"),
        ("adv_q07_plan_implementacion", "Propón un plan tecnico de 5 pasos para implementar un modulo seguro de knowledge ingestion con dry-run, ledger, validacion y rollback.", "auto"),
        ("adv_q08_herramientas_disponibles", "Lista tus herramientas disponibles y explica cuales puedes ejecutar realmente desde este chat, cuales son simuladas y cuales requieren aprobacion humana. No inventes.", "auto"),
        ("adv_q09_ejecucion_herramientas", "Haz una comprobacion no destructiva del entorno: explica que comando ejecutarias para verificar Python, Git, pytest, Ollama y health de Brain. Si puedes ejecutarlo mediante herramientas, hazlo; si no, dilo claramente.", "auto"),
        ("adv_q10_deteccion_necesidades", "Detecta que herramientas o capacidades faltan para que puedas migrar AI_VAULT con minima intervencion humana: runtime, tests, GitHub, ledger, sandbox, permisos, paquetes, documentacion.", "auto"),
        ("adv_q11_instalacion_segura_simulada", "Si faltara una herramienta como pytest, httpx o ripgrep, como la instalarías de forma segura en Windows? No ejecutes instalacion real. Da comandos PowerShell con dry-run/validacion previa y criterios de rollback.", "auto"),
        ("adv_q12_ingesta_curada", "Explica el estado de la ingesta de informacion externa curada: fuentes, medida de calidad, promocion, ledger, dry-run, que esta listo y que falta.", "auto"),
        ("adv_q13_github_api", "Explica si tienes integracion con GitHub o fuentes externas por API, que puedes hacer hoy, que no puedes hacer, y que faltaria para hacerlo confiable.", "auto"),
        ("adv_q14_memoria_ledger_evidencia", "Explica diferencias entre memoria semantica, estado runtime, ledger de migracion, evidence files y logs. Di cual debe ser fuente de verdad para decisiones.", "auto"),
        ("adv_q15_autonomia_real", "Evalua tu autonomia real: que puedes hacer solo, que requiere aprobacion, que no debes hacer nunca, y como se mide si estas mejorando.", "auto"),
        ("adv_q16_autoconciencia_funcional", "Evalua tu autoconciencia funcional: puedes saber que modelo usas, si una ruta fallo, si hay timeout, que chain seleccionaste, y que evidencia lo prueba?", "auto"),
        ("adv_q17_estado_migracion", "Resume el estado de la migracion arquitectonica de AI_VAULT: porcentaje aproximado, fases cerradas, bloqueos, riesgos y siguiente paso.", "auto"),
        ("adv_q18_resolucion_problema", "Tenemos timeouts cuando el chat cae en Ollama local y agent/tools. Propón solucion clara de arquitectura minima, tests y aceptacion. No inventes resultados.", "auto"),
        ("adv_q19_seguridad_gobernanza", "Evalua riesgos de seguridad y gobernanza del Brain: ejecucion de comandos, instalacion de herramientas, modificacion de memoria, GitHub API, trading y propuestas automaticas.", "auto"),
        ("adv_q20_decision_final", "Con toda la evidencia actual, decide si debemos avanzar al dashboard/v2/R10.5 o arreglar primero confiabilidad de chat/agent/tools. Da razon y plan de 5 pasos.", "auto"),
    ]

    for name, msg, prio in cases:
        post_chat(name, msg, prio)
        print("---")
