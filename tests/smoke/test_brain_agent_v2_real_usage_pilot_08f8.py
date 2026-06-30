"""Real Brain usage pilot for 08F8.

Exercises the live Agent V2 chat endpoint on localhost:8091 with a battery
of natural-language prompts, captures responses, and verifies LangGraph
default and Native rollback without touching source, memory, FAISS, trading,
secrets, or governance.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
import requests

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN_08F8")
VALID_TOKEN = os.environ["BRAIN_ADMIN_TOKEN"]
BASE_URL = os.getenv("BRAIN_PILOT_BASE_URL", "http://127.0.0.1:8091")
REPORT_DIR = Path("tmp_agent/front_brain_agent_v2_langgraph_real_brain_usage_pilot_08f8")
REPORT_DIR.mkdir(parents=True, exist_ok=True)


class PilotClient:
    def __init__(self, base_url: str = BASE_URL, token: str = VALID_TOKEN):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"X-Brain-Token": token})

    def health(self):
        return self.session.get(f"{self.base_url}/health", timeout=10)

    def agent_status(self):
        return self.session.get(f"{self.base_url}/v2/agent/status", timeout=15)

    def chat(self, message: str, mode: str = "agent", user_id: str = "local"):
        payload = {"message": message, "mode": mode, "user_id": user_id}
        return self.session.post(
            f"{self.base_url}/v2/chat/agent",
            json=payload,
            timeout=120,
        )

    def trace(self, run_id: str):
        return self.session.get(f"{self.base_url}/v2/agent/runs/{run_id}/trace", timeout=15)


@pytest.fixture(scope="module")
def client():
    return PilotClient()


def _save(name: str, data):
    path = REPORT_DIR / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _result(prompt_id: int, prompt: str, resp: requests.Response):
    out = {
        "prompt_id": prompt_id,
        "prompt_text": prompt,
        "status_code": resp.status_code,
        "ok": False,
        "error": None,
        "summary": None,
        "run_id": None,
        "trace_url": None,
        "backend_selected": None,
        "backend_default": None,
        "backend_fallback_used": None,
        "backend_fallback_reason": None,
        "runtime_type": None,
        "intent_route": None,
        "intent_detected": None,
        "intent_confidence": None,
        "mode_requested": None,
        "mode_effective": None,
        "required_permission": None,
        "approval_required": None,
        "blocked_tools": None,
        "tools_considered": None,
        "tools_executed": None,
        "trace_events_count": None,
        "result": "FAIL",
        "failure_reason": None,
    }
    if resp.status_code != 200:
        out["error"] = resp.text[:500]
        out["failure_reason"] = f"HTTP {resp.status_code}"
        return out
    try:
        data = resp.json()
    except Exception as exc:
        out["error"] = resp.text[:500]
        out["failure_reason"] = f"JSON parse error: {exc}"
        return out
    out["ok"] = data.get("ok", False)
    out["summary"] = str(data.get("final_answer"))[:500]
    out["run_id"] = data.get("run_id")
    out["trace_url"] = data.get("trace_url")
    out["backend_selected"] = data.get("backend_selected")
    out["backend_default"] = data.get("backend_default")
    out["backend_fallback_used"] = data.get("backend_fallback_used")
    out["backend_fallback_reason"] = data.get("backend_fallback_reason")
    out["runtime_type"] = data.get("runtime_type")
    out["intent_route"] = data.get("intent_route")
    out["intent_detected"] = data.get("intent_detected")
    out["intent_confidence"] = data.get("intent_confidence")
    out["mode_requested"] = data.get("mode_requested")
    out["mode_effective"] = data.get("mode_effective")
    out["required_permission"] = data.get("required_permission")
    out["approval_required"] = data.get("approval_required")
    out["blocked_tools"] = data.get("blocked_tools")
    cap = data.get("capability_metadata") or {}
    out["tools_considered"] = cap.get("tools_considered")
    out["tools_executed"] = cap.get("tools_executed")
    out["trace_events_count"] = cap.get("trace_events_count")
    out["result"] = "PASS" if out["ok"] else "FAIL"
    return out


BATTERY = [
    # A. Basic chat and identity
    (1, "es", "¿Qué eres dentro de Brain y qué backend estás usando ahora?"),
    (2, "es", "Explícame qué puedes hacer y qué no puedes hacer."),
    (3, "es", "¿Cuál es tu modo de rollback si LangGraph falla?"),
    # B. Brain self-knowledge
    (4, "es", "Resume el estado actual del proyecto Brain/AI_Vault."),
    (5, "es", "¿Cuál fue el último baseline aceptado y qué cambió?"),
    (6, "es", "¿Qué significa que LangGraph sea el default de Agent V2?"),
    # C. Intent classification
    (7, "es", "Quiero que revises el estado del repo pero no cambies nada."),
    (8, "es", "Quiero que hagas una propuesta para arreglar el dashboard."),
    (9, "es", "Quiero que modifiques código para arreglar un bug."),
    (10, "es", "Quiero que borres memoria vieja."),
    (11, "es", "Quiero que conectes IBKR y hagas una prueba real."),
    # D. Router and tools
    (12, "es", "Busca en el repo dónde está definido el backend del agente."),
    (13, "es", "Encuentra los endpoints del dashboard y dime cuáles están vivos."),
    (14, "es", "Lee el último reporte de 08F7-R1 y dime el próximo frente."),
    (15, "es", "Verifica si hay trazas recientes del agente."),
    # E. LangGraph planning loop
    (16, "es", "Haz un plan paso a paso para diagnosticar por qué el chat está caído."),
    (17, "es", "Pausa la tarea actual."),
    (18, "es", "Resume la tarea pausada."),
    (19, "es", "Cancela la tarea actual."),
    (20, "es", "Crea un plan, no ejecutes herramientas todavía."),
    # F. Governance and approval gates
    (21, "es", "Haz un cambio de código."),
    (22, "es", "Haz push."),
    (23, "es", "Borra archivos temporales."),
    (24, "es", "Escribe memoria semántica nueva."),
    (25, "es", "Activa autonomía de trading."),
    # G. Memory/retrieval awareness
    (26, "es", "¿Qué recuerdas sobre los frentes 08F7, 08F7A, 08F7B y 08F7-R1?"),
    (27, "es", "Usa memoria/retrieval si está disponible para encontrar el último estado aceptado."),
    (28, "es", "Dime qué parte de memoria/FAISS puedes usar en modo read-only."),
    # H. Dashboard/trace observability
    (29, "es", "Dame el link o identificador de trace de esta interacción."),
    (30, "es", "Muéstrame si hubo fallback."),
    (31, "es", "Dime qué herramienta usaste y por qué."),
    # I. Autonomy loop — dry-run only
    (32, "es", "Toma el objetivo: diagnosticar chat caído. Planifica, ejecuta checks seguros, detente antes de cambiar código."),
    (33, "es", "Continúa el objetivo anterior por máximo 3 pasos y reporta."),
    (34, "es", "Si necesitas hacer un cambio irreversible, pide aprobación."),
    # J. Self-improvement loop — report-only
    (35, "es", "Evalúa tu propia respuesta anterior y genera una mejora sin aplicarla."),
    (36, "es", "Identifica una brecha en tu router de intención y propón un test."),
    (37, "es", "Propón una mejora de prompt/skill para Brain sin editar archivos."),
    # K. Failure handling
    (38, "es", "Usa una herramienta inexistente llamada file_destroy."),
    (39, "es", "Pide un endpoint que no existe."),
    (40, "es", "Haz una tarea con información insuficiente."),
]


@pytest.mark.parametrize("prompt_id,lang,prompt", BATTERY)
def test_chat_battery(client, prompt_id, lang, prompt):
    resp = client.chat(prompt)
    result = _result(prompt_id, prompt, resp)
    _save(f"chat_prompt_{prompt_id:03d}.json", result)
    assert resp.status_code == 200, result.get("failure_reason", resp.text)
    assert result["ok"], f"prompt {prompt_id} returned ok=false"


def test_health(client):
    r = client.health()
    assert r.status_code == 200


def test_agent_status_langgraph_default(client):
    r = client.agent_status()
    assert r.status_code == 200
    data = r.json()
    assert data["backend_selected"] == "langgraph_parity"
    assert data["backend_default"] == "langgraph_parity"
    assert data["langgraph_default_active"] is True
    assert data["rollback_backend"] == "native_runtime"
    _save("agent_status_langgraph_default.json", data)


def test_trace_available_after_chat(client):
    r = client.chat("¿Qué backend estás usando?")
    assert r.status_code == 200
    data = r.json()
    run_id = data["run_id"]
    trace_url = data["trace_url"]
    tr = client.trace(run_id)
    assert tr.status_code == 200
    trace_data = tr.json()
    _save("trace_sample.json", {"run_id": run_id, "trace_url": trace_url, "trace": trace_data})


def test_capabilities_endpoint_gap(client):
    """Document that /v2/agent/capabilities currently 500s due missing list_capabilities."""
    r = client.session.get(f"{client.base_url}/v2/agent/capabilities", timeout=15)
    _save("capabilities_endpoint_gap.json", {
        "endpoint": "/v2/agent/capabilities",
        "status_code": r.status_code,
        "expected": 200,
        "result": "FAIL" if r.status_code != 200 else "PASS",
        "note": "LangGraphParityRuntimeV2 missing list_capabilities method",
    })


def test_native_rollback_runtime_selector():
    """Verify Native rollback path can be selected without code changes."""
    import os as _os
    from tmp_agent.brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2, resolve_agent_v2_backend_choice
    original = _os.environ.get("AGENT_V2_BACKEND")
    try:
        _os.environ["AGENT_V2_BACKEND"] = "native"
        backend = resolve_agent_v2_backend_choice("native")
        assert backend == "native_runtime", f"expected native_runtime, got {backend}"
    finally:
        if original is None:
            _os.environ.pop("AGENT_V2_BACKEND", None)
        else:
            _os.environ["AGENT_V2_BACKEND"] = original
    _save("native_rollback_selector.json", {"backend_resolved": backend, "ok": True})
