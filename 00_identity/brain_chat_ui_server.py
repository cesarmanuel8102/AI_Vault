"""
Brain Chat UI Server V2  [DEPRECATED]
======================================
DEPRECATED as of 2026-03-25.  DO NOT start this service.

The canonical chat system is now brain_v9/core/session.py (v4-unified),
served via brain_v9/main.py on port 8090.

This file is kept for reference only. It will be removed in a future
cleanup pass once all consumers have been verified migrated.

Known issues at deprecation time:
  - Path traversal vulnerability in _human_reply_from_plan() (reads any file unsandboxed)
  - References non-existent models: gpt-5-mini, gpt-5.2, gpt-5.2-codex
  - 190-line inline HTML string
  - Hardcoded C:\\AI_VAULT paths
"""

import os
import json
import uuid
import logging
import warnings
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

_log = logging.getLogger(__name__)
warnings.warn(
    "brain_chat_ui_server.py is DEPRECATED. Use brain_v9/core/session.py (port 8090) instead.",
    DeprecationWarning,
    stacklevel=2,
)
_log.warning("⚠ brain_chat_ui_server.py is DEPRECATED. The canonical chat is brain_v9/core/session.py on port 8090.")

BRAIN_API = os.environ.get("BRAIN_API", "http://127.0.0.1:8010").rstrip("/")
ADVISOR_API = os.environ.get("ADVISOR_API", "http://127.0.0.1:8030").rstrip("/")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL_GENERAL = os.environ.get("OPENAI_MODEL_GENERAL", os.environ.get("OPENAI_MODEL", "gpt-5-mini")).strip()
OPENAI_MODEL_REASONING = os.environ.get("OPENAI_MODEL_REASONING", "gpt-5.2").strip()
OPENAI_MODEL_CODING = os.environ.get("OPENAI_MODEL_CODING", "gpt-5.2-codex").strip()
OLLAMA_API = os.environ.get("OLLAMA_API", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")
STATE_ROOT = Path(r"C:\AI_VAULT\tmp_agent\state")
ROOMS_ROOT = STATE_ROOT / "rooms"
STATUS_PATH = STATE_ROOT / "next_level_cycle_status_latest.json"
ROADMAP_PATH = STATE_ROOT / "roadmap.json"
REGISTRY_PATH = STATE_ROOT / "roadmap_registry_v2.json"

app = FastAPI(title="Brain Chat UI Server V2")

HTML = r"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>Brain Console</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root{
      --bg:#0b1020; --panel:#121936; --panel2:#1a2247; --line:#28315e;
      --text:#edf2ff; --muted:#9aa7d7; --user:#20315d; --assistant:#162548; --err:#4d1f2a;
      --accent:#7aa2ff; --ok:#67d18d; --warn:#ffd166;
    }
    *{box-sizing:border-box}
    body{margin:0;background:linear-gradient(180deg,#0a0f1d,#101733);color:var(--text);font-family:Segoe UI,Arial,sans-serif}
    #brain-chat-shell{max-width:1100px;margin:0 auto;padding:16px;display:grid;grid-template-rows:auto 1fr auto;gap:12px;height:100vh}
    .topbar{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border:1px solid var(--line);background:rgba(18,25,54,.9);border-radius:16px;gap:12px}
    .title{font-size:20px;font-weight:700}
    .sub{font-size:12px;color:var(--muted)}
    .topbar-side{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
    .pill{padding:6px 10px;border-radius:999px;border:1px solid var(--line);background:#0d1430;color:var(--muted);font-size:12px}
    #chat-log{border:1px solid var(--line);background:rgba(18,25,54,.88);border-radius:18px;padding:16px;overflow:auto}
    .msg{max-width:82%;padding:12px 14px;border-radius:16px;margin:10px 0;white-space:pre-wrap;line-height:1.45}
    .msg.user{margin-left:auto;background:var(--user)}
    .msg.assistant{background:var(--assistant)}
    .msg.error{background:var(--err)}
    .msg.pending{background:#111a3b;color:var(--muted)}
    .meta{font-size:11px;color:var(--muted);margin-top:6px}
    .composer{display:grid;grid-template-columns:1fr auto auto auto;gap:10px;padding:12px;border:1px solid var(--line);background:rgba(18,25,54,.9);border-radius:18px}
    #chat-input{width:100%;min-height:58px;max-height:180px;resize:vertical;padding:14px;border-radius:14px;border:1px solid var(--line);background:#0e1634;color:var(--text)}
    button{border:1px solid var(--line);background:var(--panel2);color:var(--text);border-radius:14px;padding:0 14px;cursor:pointer}
    button:hover{filter:brightness(1.08)}
    #send-btn{background:#2a4db6}
    #mic-btn.active{outline:2px solid var(--warn)}
    .toolbar{display:flex;align-items:center;gap:12px;color:var(--muted);font-size:12px;padding:0 4px;flex-wrap:wrap}
    .tag{padding:4px 8px;border-radius:999px;background:#10183a;border:1px solid var(--line)}
  </style>
</head>
<body>
  <div id="brain-chat-shell">
    <div class="topbar">
      <div>
        <div class="title">Brain Console</div>
        <div class="sub">Consola conversacional para Brain con OpenAI preferente y fallback local Ollama.</div>
      </div>
      <div class="topbar-side">
        <div class="pill" id="provider-pill">provider: checking...</div>
        <div class="pill" id="health-pill">health: checking...</div>
      </div>
    </div>

    <div id="chat-log"></div>

    <div>
      <div class="toolbar">
        <label class="tag"><input type="checkbox" id="auto-apply" checked /> auto_apply</label>
        <label class="tag"><input type="checkbox" id="speak-back" /> leer respuesta</label>
        <span id="room-badge" class="tag"></span>
      </div>

      <div class="composer">
        <textarea id="chat-input" placeholder="Pídele algo al Brain. Ejemplo: lista C:\AI_VAULT\tmp_agent\state o explícame en qué fase estamos."></textarea>
        <button id="mic-btn" title="Hablar">🎤</button>
        <button id="clear-btn" title="Limpiar">Limpiar</button>
        <button id="send-btn" title="Enviar">Enviar</button>
      </div>
    </div>
  </div>

<script>
const chatLog = document.getElementById('chat-log');
const input = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const clearBtn = document.getElementById('clear-btn');
const micBtn = document.getElementById('mic-btn');
const autoApply = document.getElementById('auto-apply');
const speakBack = document.getElementById('speak-back');
const roomBadge = document.getElementById('room-badge');
const healthPill = document.getElementById('health-pill');
const providerPill = document.getElementById('provider-pill');

let roomId = "ui_" + new Date().toISOString().replace(/[:.]/g,'_');
roomBadge.textContent = roomId;

function addMessage(role, text, meta="") {
  const d = document.createElement('div');
  d.className = 'msg ' + role;
  d.textContent = text || '';
  if (meta) {
    const m = document.createElement('div');
    m.className = 'meta';
    m.textContent = meta;
    d.appendChild(m);
  }
  chatLog.appendChild(d);
  chatLog.scrollTop = chatLog.scrollHeight;
  return d;
}

async function refreshHealth() {
  try {
    const r = await fetch('/healthz');
    const j = await r.json();
    healthPill.textContent = j.ok ? 'health: ok' : 'health: fail';
    healthPill.style.color = j.ok ? '#67d18d' : '#ff8fa3';
    providerPill.textContent = 'provider: ' + (j.chat_provider || 'unknown');
    providerPill.style.color = j.provider_ready ? '#67d18d' : '#ffd166';
  } catch {
    healthPill.textContent = 'health: fail';
    healthPill.style.color = '#ff8fa3';
    providerPill.textContent = 'provider: unavailable';
    providerPill.style.color = '#ff8fa3';
  }
}

async function sendMessage() {
  const message = input.value.trim();
  if (!message) return;

  addMessage('user', message, roomId);
  input.value = '';
  const pending = addMessage('pending', 'Pensando...', 'esperando respuesta');

  const body = {
    message: message,
    room_id: roomId,
    auto_apply: !!autoApply.checked
  };

  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    const j = await r.json();
    pending.remove();

    const meta = j.kind ? ('kind=' + j.kind + ' | room=' + j.room_id) : ('room=' + roomId);
    if (j.ok) {
      addMessage('assistant', j.reply || '(sin texto)', meta);
      if (speakBack.checked && j.reply) {
        const u = new SpeechSynthesisUtterance(j.reply);
        speechSynthesis.speak(u);
      }
    } else {
      addMessage('error', j.reply || 'Falló la operación.', meta);
    }
  } catch (e) {
    pending.remove();
    addMessage('error', 'Error de red: ' + e, 'room=' + roomId);
  }
}

sendBtn.addEventListener('click', sendMessage);
clearBtn.addEventListener('click', () => { chatLog.innerHTML=''; });
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.lang = 'es-US';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => micBtn.classList.add('active');
  recognition.onend = () => micBtn.classList.remove('active');
  recognition.onresult = (event) => {
    const text = event.results[0][0].transcript || '';
    input.value = (input.value ? (input.value + ' ') : '') + text;
  };
  micBtn.addEventListener('click', () => {
    recognition.start();
  });
} else {
  micBtn.disabled = true;
  micBtn.title = 'SpeechRecognition no disponible en este navegador';
}

refreshHealth();
setInterval(refreshHealth, 8000);
</script>
</body>
</html>
"""


class ChatBody(BaseModel):
    message: str
    room_id: str | None = None
    auto_apply: bool = True


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _room_dir(room_id: str) -> Path:
    return ROOMS_ROOT / str(room_id)


def _room_plan(room_id: str):
    p = _room_dir(room_id) / "plan.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _detect_placeholder(obj) -> bool:
    try:
        blob = json.dumps(obj, ensure_ascii=False)
    except Exception:
        blob = str(obj)
    needles = [
        "fallback_placeholder_plan",
        "placeholder_plan_detected",
        "fallback_no_action",
        "advisor fallback disabled"
    ]
    return any(n in blob for n in needles)


def _extract_plan(advisor_obj):
    plan = advisor_obj.get("plan") if isinstance(advisor_obj, dict) else None
    if isinstance(plan, dict) and isinstance(plan.get("plan"), dict):
        plan = plan.get("plan")
    return plan if isinstance(plan, dict) else None


def _human_reply_from_plan(room_id: str, steps: list[dict]) -> str:
    if not steps:
        return f"Procesé la petición en room {room_id}, pero no hubo pasos."

    step = steps[0]
    tool = str(step.get("tool_name") or "")
    args = step.get("tool_args") or {}

    if tool == "list_dir":
        path = str(args.get("path") or "")
        p = Path(path)
        if p.exists() and p.is_dir():
            names = sorted([x.name for x in p.iterdir()])[:25]
            if names:
                return "Contenido de " + path + ":\n- " + "\n- ".join(names)
            return "La carpeta existe pero está vacía: " + path
        return "No existe la carpeta: " + path

    if tool == "read_file":
        path = str(args.get("path") or "")
        p = Path(path)
        if p.exists() and p.is_file():
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = p.read_text(errors="replace")
            return "Contenido de " + path + ":\n" + text[:4000]
        return "No existe el archivo: " + path

    if tool in {"write_file", "append_file"}:
        path = str(args.get("path") or "")
        return f"Ejecuté {tool} en {path} dentro del room {room_id}."

    return f"Procesé la petición en room {room_id}. Pasos del plan: {len(steps)}."


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML


# === BL_CHAT_FALLBACK_HELPERS_BEGIN ===
def _chat_history_path(room_id: str) -> Path:
    return _room_dir(room_id) / "chat_history.json"


def _load_chat_history(room_id: str) -> list[dict]:
    p = _chat_history_path(room_id)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_chat_history(room_id: str, history: list[dict]):
    p = _chat_history_path(room_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(history[-40:], ensure_ascii=False, indent=2), encoding="utf-8")


def _append_chat_turn(room_id: str, role: str, text: str) -> list[dict]:
    hist = _load_chat_history(room_id)
    hist.append({
        "role": str(role or ""),
        "text": str(text or ""),
        "utc": _now_utc()
    })
    _save_chat_history(room_id, hist)
    return hist[-40:]


def _last_user_message(room_id: str):
    hist = _load_chat_history(room_id)
    for item in reversed(hist):
        if isinstance(item, dict) and str(item.get("role") or "") == "user":
            t = str(item.get("text") or "").strip()
            if t:
                return t
    return None


def _conversation_reply(room_id: str, message: str, prev_user: str | None = None) -> str:
    msg = str(message or "").strip()
    low = msg.lower()

    if "recuerd" in low or "mensaje anterior" in low or "último mensaje" in low or "ultimo mensaje" in low:
        if prev_user:
            return f"Sí. En el room {room_id} tu mensaje anterior fue: {prev_user}"
        return f"Aún no tengo un mensaje previo persistido en el room {room_id}."

    if "continuidad" in low or "room" in low or "sesión" in low or "sesion" in low:
        turns = len(_load_chat_history(room_id))
        return f"Sí. Mantengo continuidad en el room {room_id}. Tengo {turns} turnos persistidos en esta conversación."

    if prev_user:
        return f"Te respondo en el room {room_id}. Mantengo continuidad. Tu mensaje anterior fue: {prev_user}. Mensaje actual recibido: {msg}"

    return f"Te respondo en el room {room_id}. Mantengo continuidad y ya dejé persistido este intercambio."
# === BL_CHAT_FALLBACK_HELPERS_END ===


def _read_json_file(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _canonical_status() -> dict:
    return _read_json_file(STATUS_PATH, {}) or {}


def _canonical_roadmap() -> dict:
    return _read_json_file(ROADMAP_PATH, {}) or {}


def _canonical_registry() -> dict:
    return _read_json_file(REGISTRY_PATH, {}) or {}


def _dev_mode_path(room_id: str) -> Path:
    return _room_dir(room_id) / "developer_mode.json"


def _developer_mode_enabled(room_id: str) -> bool:
    data = _read_json_file(_dev_mode_path(room_id), {}) or {}
    return bool(data.get("enabled", False))


def _set_developer_mode(room_id: str, enabled: bool) -> None:
    path = _dev_mode_path(room_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "enabled": bool(enabled),
        "updated_utc": _now_utc(),
        "room_id": room_id
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def _developer_mode_toggle_reply(room_id: str, message: str) -> str | None:
    low = str(message or "").strip().lower()
    on_tokens = ["/dev on", "/developer on", "modo desarrollador on", "modo dev on", "activar modo desarrollador"]
    off_tokens = ["/dev off", "/developer off", "modo desarrollador off", "modo dev off", "desactivar modo desarrollador"]
    if any(t in low for t in on_tokens):
        _set_developer_mode(room_id, True)
        return "Modo desarrollador activado para este room. A partir de ahora el chat debe exponer la fuente canónica, proveedor usado, estado del Brain, disponibilidad de Ollama, roadmap activo y límites gobernados sin inventar restricciones. Este modo no elimina límites legales, morales o técnicos; añade transparencia y trazabilidad."
    if any(t in low for t in off_tokens):
        _set_developer_mode(room_id, False)
        return "Modo desarrollador desactivado para este room."
    return None


def _is_capability_question(message: str) -> bool:
    low = str(message or "").strip().lower()
    hints = [
        "ollama", "modelos locales", "modificar tu codigo", "modificar tu código",
        "desarrollarte", "autodesarroll", "crear roadmap", "crear roadmaps",
        "que puedes hacer", "qué puedes hacer", "capacidades", "sin filtros",
        "modo desarrollador", "analisis sin filtros", "análisis sin filtros"
    ]
    return any(h in low for h in hints)


def _developer_transparency_block(room_id: str, provider_name: str, provider_reply: dict[str, Any] | None = None) -> str:
    status = _canonical_status()
    roadmap = _canonical_roadmap()
    local_models = status.get("local_models") or {}
    provider_errors = (provider_reply or {}).get("provider_errors") or {}
    route_reason = (provider_reply or {}).get("route_reason") or "n/a"
    route_primary = (provider_reply or {}).get("route_primary") or "n/a"
    route_secondary = (provider_reply or {}).get("route_secondary") or "n/a"
    lines = [
        "[DevMode] Fuente canónica consultada.",
        f"roadmap={status.get('active_roadmap') or roadmap.get('roadmap_id') or 'n/a'} | fase={status.get('current_phase') or status.get('phase') or 'n/a'} | etapa={status.get('current_stage') or status.get('stage') or 'n/a'}",
        f"provider_usado={provider_name}",
        f"ruta_chat={route_primary} -> {route_secondary} | razon={route_reason}",
        f"ollama_instalado={bool(local_models.get('installed'))} | modelos_locales={len(local_models.get('models') or [])}",
        "guardrails=activos (legalidad, control local, gobernanza, apply gobernado)"
    ]
    if provider_errors:
        lines.append(f"provider_errors={json.dumps(provider_errors, ensure_ascii=False)}")
    return "\n".join(lines)


def _capability_answer(room_id: str, message: str) -> str:
    low = str(message or "").strip().lower()
    status = _canonical_status()
    roadmap = _canonical_roadmap()
    registry = _canonical_registry()
    local_models = status.get("local_models") or {}
    active_roadmap = status.get("active_roadmap") or roadmap.get("roadmap_id") or "n/a"
    phase = status.get("current_phase") or status.get("phase") or "n/a"
    stage = status.get("current_stage") or status.get("stage") or "n/a"

    if "sin filtros" in low or "analisis sin filtros" in low or "análisis sin filtros" in low or "modo desarrollador" in low:
        return (
            "No conviene ni voy a afirmar un modo sin filtros que quite límites legales, morales o técnicos. "
            "Lo correcto y seguro es un modo desarrollador local de transparencia: acceso a estado canónico, roadmap activo, room, proveedor usado, disponibilidad de Ollama, evidencia reciente y errores de proveedor, sin ocultar incertidumbre ni inventar capacidades. "
            "Puedes activarlo en este room con `/dev on`. Los guardrails siguen activos."
        )

    if "ollama" in low or "modelos locales" in low:
        models = local_models.get("models") or []
        if local_models.get("installed"):
            return (
                "Sí. Brain sí tiene acceso canónico a Ollama como motor local. "
                f"En status aparecen {len(models)} modelos locales registrados y el executable configurado. "
                "La consola actual puede responder por OpenAI u Ollama según disponibilidad, pero la respuesta anterior fue incorrecta al negar ese acceso."
            )
        return "Ahora mismo no veo Ollama marcado como instalado en el estado canónico."

    if "modificar tu codigo" in low or "modificar tu código" in low or "desarrollarte" in low or "autodesarroll" in low:
        return (
            "Sí, Brain ya tiene capacidad de autodesarrollo gobernado. No equivale a edición irrestricta de cualquier archivo del repo, pero sí a abrir episodios, generar backlog, sembrar y cerrar roadmaps, producir artifacts, validarse y empujar mejoras bajo política. "
            f"El estado canónico actual está en roadmap {active_roadmap}, fase {phase}, etapa {stage}."
        )

    if "roadmap" in low and ("crear" in low or "crear" in low or "nuevo" in low):
        return "Sí. Brain ya puede crear y activar nuevos roadmaps dentro del flujo canónico local, con rooms, artifacts, bitácora y promoción gobernada."

    return (
        "Te responderé según la fuente canónica del Brain, no solo según el modelo lingüístico. "
        f"Roadmap activo: {active_roadmap}. Fase: {phase}. Etapa: {stage}."
    )




def _is_truth_first_question(message: str) -> bool:
    low = str(message or "").strip().lower()
    hints = [
        "estado", "fase", "stage", "roadmap", "dónde estamos", "donde estamos",
        "qué sigue", "que sigue", "objetivo", "premisas", "doctrina", "proveedor",
        "provider", "ollama", "modelos locales", "capacidades", "qué puedes hacer",
        "que puedes hacer", "autodesarroll", "desarrollarte", "aprendiz", "memoria",
        "límites", "limites", "legal", "moral", "técnic", "tecnic", "calidad"
    ]
    return any(h in low for h in hints)


def _canonical_context_brief(room_id: str) -> str:
    status = _canonical_status()
    roadmap = _canonical_roadmap()
    doctrine = status.get("doctrine") or {}
    local_models = status.get("local_models") or {}
    parts = [
        f"roadmap={status.get('active_roadmap') or roadmap.get('roadmap_id') or 'n/a'}",
        f"phase={status.get('current_phase') or status.get('phase') or 'n/a'}",
        f"stage={status.get('current_stage') or status.get('stage') or 'n/a'}",
        f"primary_objective={doctrine.get('primary_objective') or 'n/a'}",
        f"ollama_installed={bool(local_models.get('installed'))}",
        f"local_model_count={len(local_models.get('models') or [])}",
        f"developer_mode={_developer_mode_enabled(room_id)}"
    ]
    return " | ".join(parts)


def _truth_first_answer(room_id: str, message: str) -> str:
    low = str(message or "").strip().lower()
    status = _canonical_status()
    roadmap = _canonical_roadmap()
    doctrine = status.get("doctrine") or {}
    local_models = status.get("local_models") or {}
    active_roadmap = status.get("active_roadmap") or roadmap.get("roadmap_id") or "n/a"
    phase = status.get("current_phase") or status.get("phase") or "n/a"
    stage = status.get("current_stage") or status.get("stage") or "n/a"
    objective = doctrine.get("primary_objective") or "n/a"
    utility = doctrine.get("utility_expression") or "n/a"
    room_turns = len(_load_chat_history(room_id))
    memory_points = _recent_memory_points(room_id)

    evidence = [
        f"Roadmap activo: {active_roadmap}.",
        f"Fase actual: {phase}.",
        f"Etapa actual: {stage}.",
        f"Objetivo primario: {objective}.",
        f"Modelos locales Ollama disponibles: {len(local_models.get('models') or [])} (instalado={bool(local_models.get('installed'))}).",
        f"Turnos persistidos en este room: {room_turns}."
    ]

    inference = []
    if "qué sigue" in low or "que sigue" in low:
        if str(stage).lower() == 'done':
            inference.append("El roadmap activo ya está cerrado; lo siguiente correcto es abrir o activar el próximo roadmap útil, no seguir empujando este.")
        else:
            inference.append("El roadmap activo sigue vivo; lo siguiente correcto es cerrar la fase en progreso con evidencia material y promover la siguiente.")
    if "aprendiz" in low or "memoria" in low or "recuerd" in low or "continuidad" in low:
        inference.append("La consola ya persiste historia por room y puede reutilizar evidencia reciente; el siguiente salto de calidad es resumir mejor esa memoria y usarla como contexto operativo, no solo como historial bruto.")
    if "proveedor" in low or "provider" in low or "ollama" in low:
        inference.append("La capacidad real del Brain y el proveedor lingüístico no son lo mismo: puede responder usando OpenAI y aun así tener Ollama disponible como motor local alterno.")
    if "desarrollarte" in low or "autodesarroll" in low or "modificar tu codigo" in low or "modificar tu código" in low:
        inference.append("El Brain ya puede autodesarrollarse de forma gobernada, pero no como escritura irrestricta sobre todo el repo sin política de apply.")
    if not inference:
        inference.append("La interpretación debe salir primero del estado canónico; el modelo lingüístico solo debería redactar, no redefinir capacidades ni estado.")

    execution = []
    if "roadmap" in low:
        execution.append("Puede crear, activar y cerrar roadmaps gobernados con rooms, bitácora y promoción automática basada en evidencia.")
    if "ollama" in low or "modelos locales" in low:
        execution.append("Puede usar Ollama como fallback local cuando OpenAI no esté disponible o cuando la política local así lo indique.")
    if "desarrollarte" in low or "autodesarroll" in low or "modificar tu codigo" in low or "modificar tu código" in low:
        execution.append("Puede abrir episodios de autodesarrollo, generar backlog, validar y empujar mejoras bajo política.")
    if "aprendiz" in low or "memoria" in low or "recuerd" in low or "continuidad" in low:
        execution.append("Puede reutilizar los últimos turnos del room como memoria operativa inmediata y exponerlos de forma resumida cuando sea relevante.")
    if not execution:
        execution.append("Puede responder, consultar estado, abrir episodios del Brain y ejecutar acciones gobernadas dentro del entorno local.")

    return _render_truth_first_sections(evidence, inference, execution, memory_points, utility)
def _recent_memory_points(room_id: str, max_items: int = 3) -> list[str]:
    hist = _load_chat_history(room_id)
    user_points: list[str] = []
    brain_points: list[str] = []

    for item in reversed(hist):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        text = " ".join(str(item.get("text") or "").strip().split())
        if not text:
            continue

        if role == "user":
            point = f"usuario pidió: {text[:140]}"
            if point not in user_points:
                user_points.append(point)
            continue

        if role == "assistant":
            if "Lo siguiente correcto es" in text:
                idx = text.find("Lo siguiente correcto es")
                summary = text[idx:idx + 150]
                point = f"brain decidió: {summary}"
                if point not in brain_points:
                    brain_points.append(point)
            elif text.startswith("Modo desarrollador activado"):
                point = "brain decidió: modo desarrollador activado para este room"
                if point not in brain_points:
                    brain_points.append(point)
            continue

    points = list(reversed(user_points[:max_items]))
    if brain_points and len(points) < max_items:
        points.append(brain_points[0])
    return points[:max_items]


def _render_truth_first_sections(evidence: list[str], inference: list[str], execution: list[str], memory_points: list[str], utility: str) -> str:
    lines: list[str] = []
    lines.append("Evidencia canónica:")
    lines.extend(f"- {item}" for item in evidence)
    if memory_points:
        lines.append("")
        lines.append("Memoria útil reciente:")
        lines.extend(f"- {item}" for item in memory_points)
    lines.append("")
    lines.append("Inferencia operativa:")
    lines.extend(f"- {item}" for item in inference)
    lines.append("")
    lines.append("Ejecución posible ahora:")
    lines.extend(f"- {item}" for item in execution)
    lines.append("")
    lines.append(f"Utilidad objetivo: {utility}")
    return "\n".join(lines)

def _compact_recent_history(room_id: str, max_items: int = 6) -> list[dict[str, str]]:
    hist = _load_chat_history(room_id)
    compact: list[dict[str, str]] = []
    seen_user: set[str] = set()
    seen_brain: set[str] = set()
    for item in hist[-30:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower() or "user"
        text = " ".join(str(item.get("text") or "").strip().split())
        if not text:
            continue
        if role == "assistant":
            if "Lo siguiente correcto es" in text:
                idx = text.find("Lo siguiente correcto es")
                text = text[idx:idx + 180]
            elif text.startswith("Modo desarrollador activado"):
                text = "Modo desarrollador activado para este room."
            else:
                continue
            if text in seen_brain:
                continue
            seen_brain.add(text)
        else:
            if len(text) > 180:
                text = text[:177] + "..."
            if text in seen_user:
                continue
            seen_user.add(text)
        compact.append({"role": role, "text": text})
    return compact[-max_items:]


def _history_for_prompt(room_id: str, max_turns: int = 12) -> str:
    hist = _load_chat_history(room_id)[-max_turns:]
    lines = []
    for item in hist:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip() or "user"
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"{role.upper()}: {text}")
    return "\n".join(lines)


def _is_action_request(message: str) -> bool:
    low = str(message or "").strip().lower()
    action_hints = [
        "lista ", "lee ", "abre ", "crea ", "escribe ", "agrega ", "append ",
        "write ", "read ", "list ", "archivo", "carpeta", "directorio",
        "path ", "ruta ", "ejecuta ", "run ", "muestra ", "busca "
    ]
    return any(token in low for token in action_hints)


def _is_self_build_request(message: str) -> bool:
    low = str(message or "").strip().lower()
    build_verbs = [
        "mejora", "mejorar", "implementa", "implement", "corrige", "arregla",
        "desarrolla", "construye", "refactor", "optimiza", "añade", "agrega",
        "actualiza", "haz que", "debe poder", "extiende", "cambia"
    ]
    trigger_targets = ["brain", "consola", "chat", "ui", "agente", "sistema", "servidor", "dashboard"]
    return any(h in low for h in build_verbs) and any(t in low for t in trigger_targets)


def _safe_room_artifact_path(room_id: str, name: str) -> str:
    safe = ''.join(ch if ch.isalnum() or ch in ('-', '_', '.') else '_' for ch in str(name or 'artifact.json'))
    if not safe.lower().endswith('.json'):
        safe += '.json'
    return str(_room_dir(room_id) / safe)


def _extract_json_object_from_text(text: str) -> dict | None:
    raw = str(text or '').strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    start = raw.find('{')
    end = raw.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(raw[start:end + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _conversation_episode_payload(room_id: str, message: str) -> dict[str, Any]:
    episode_id = 'chat_conversation_' + uuid.uuid4().hex[:10]
    return {
        'room_id': room_id,
        'episode_id': episode_id,
        'phase_id': 'CHAT-CONVERSATION',
        'mission_id': 'brain_console_conversation_v1',
        'roadmap_id': 'brain_console_conversation_v1',
        'auto_apply_if_allowed': True,
        'rollback_on_failure': False,
        'proposal': {
            'summary': 'Capture a Brain Console conversation turn as canonical room state before replying.',
            'tool_name': 'runtime_snapshot_set',
            'tool_args': {
                'path': 'brain_console.conversation.last_turn',
                'value': {
                    'recorded_utc': _now_utc(),
                    'room_id': room_id,
                    'message': message,
                    'recent_history': _compact_recent_history(room_id)
                }
            },
            'acceptance': [
                'conversation turn persisted into runtime snapshot',
                'observation generated for the room',
                'linguistic response can be generated after Brain persistence'
            ],
            'target_artifact': 'runtime_snapshot.json'
        }
    }


def _fallback_episode_payload(room_id: str, message: str) -> dict[str, Any]:
    episode_id = 'chat_self_build_' + uuid.uuid4().hex[:10]
    artifact_path = _safe_room_artifact_path(room_id, f'{episode_id}_request')
    artifact = {
        'schema_version': 'chat_self_build_request_v1',
        'recorded_utc': _now_utc(),
        'room_id': room_id,
        'episode_id': episode_id,
        'source': 'brain_console_chat',
        'user_request': message,
        'recent_history': _compact_recent_history(room_id),
        'goal': 'Convert a plain-language Brain improvement request into a canonical room-scoped engineering brief.',
        'next_expected_steps': [
            'review_request',
            'synthesize_backlog',
            'seed_followup_episode_or_plan'
        ]
    }
    return {
        'room_id': room_id,
        'episode_id': episode_id,
        'phase_id': 'CHAT-SELF-BUILD',
        'mission_id': 'brain_console_agentic_requests_v1',
        'roadmap_id': 'brain_console_agentic_requests_v1',
        'auto_apply_if_allowed': True,
        'rollback_on_failure': True,
        'proposal': {
            'summary': 'Capture a self-build request from Brain Console as a canonical engineering brief.',
            'tool_name': 'write_file',
            'tool_args': {
                'path': artifact_path,
                'content': json.dumps(artifact, ensure_ascii=False, indent=2) + '\\n'
            },
            'acceptance': [
                'request brief persisted inside the room',
                'episode observation generated',
                'reinjection payload available for the next planning turn'
            ],
            'target_artifact': Path(artifact_path).name
        }
    }


def _followup_episode_payload_from_backlog(room_id: str, message: str, backlog_obj: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(backlog_obj, dict):
        return None
    backlog = list(backlog_obj.get('backlog') or [])
    if not backlog:
        return None
    item = backlog[0] if isinstance(backlog[0], dict) else {}
    title = str(item.get('title') or '').strip()
    recommended_action = str(item.get('recommended_action') or '').strip()
    if not title and not recommended_action:
        return None
    episode_id = 'chat_followup_' + uuid.uuid4().hex[:10]
    artifact_path = _safe_room_artifact_path(room_id, f'{episode_id}_next_step')
    artifact = {
        'schema_version': 'chat_followup_backlog_step_v1',
        'recorded_utc': _now_utc(),
        'room_id': room_id,
        'episode_id': episode_id,
        'source': 'brain_console_chat',
        'user_request': message,
        'backlog_title': title,
        'recommended_action': recommended_action,
        'backlog_artifact': str(backlog_obj.get('artifact') or ''),
        'next_goal': 'Continue the self-build loop from the synthesized backlog item.'
    }
    return {
        'room_id': room_id,
        'episode_id': episode_id,
        'phase_id': 'CHAT-SELF-BUILD-FOLLOWUP',
        'mission_id': 'brain_console_agentic_requests_v1',
        'roadmap_id': 'brain_console_agentic_requests_v1',
        'auto_apply_if_allowed': True,
        'rollback_on_failure': True,
        'proposal': {
            'summary': f'Persist the next self-build step from backlog: {title or recommended_action}',
            'tool_name': 'write_file',
            'tool_args': {
                'path': artifact_path,
                'content': json.dumps(artifact, ensure_ascii=False, indent=2) + '\n'
            },
            'acceptance': [
                'follow-up step persisted inside the room',
                'next bounded step visible for the Brain console',
                'room has a second episode artifact after backlog synthesis'
            ],
            'target_artifact': Path(artifact_path).name
        }
    }


def _sanitize_episode_payload(room_id: str, payload: dict[str, Any] | None, message: str) -> dict[str, Any]:
    base = _fallback_episode_payload(room_id, message)
    if not isinstance(payload, dict):
        return base
    proposal = payload.get('proposal') if isinstance(payload.get('proposal'), dict) else {}
    tool_name = str(proposal.get('tool_name') or '').strip()
    allowed_tools = {'write_file', 'append_file', 'runtime_snapshot_set', 'runtime_snapshot_get', 'read_file', 'list_dir'}
    if tool_name not in allowed_tools:
        return base
    out = dict(base)
    out['episode_id'] = str(payload.get('episode_id') or out['episode_id'])[:64]
    out['phase_id'] = str(payload.get('phase_id') or payload.get('phase') or out['phase_id'])[:64]
    out['mission_id'] = str(payload.get('mission_id') or out['mission_id'])[:128]
    out['roadmap_id'] = str(payload.get('roadmap_id') or out['roadmap_id'])[:128]
    out['auto_apply_if_allowed'] = bool(payload.get('auto_apply_if_allowed', True))
    out['rollback_on_failure'] = bool(payload.get('rollback_on_failure', True))
    clean_proposal = dict(base['proposal'])
    clean_proposal['summary'] = str(proposal.get('summary') or clean_proposal['summary'])[:400]
    clean_proposal['tool_name'] = tool_name
    tool_args = proposal.get('tool_args') if isinstance(proposal.get('tool_args'), dict) else {}
    if tool_name in {'write_file', 'append_file'}:
        requested_path = str(tool_args.get('path') or '').strip()
        requested_name = Path(requested_path).name if requested_path else f"{out['episode_id']}_artifact.json"
        safe_path = _safe_room_artifact_path(room_id, requested_name)
        clean_proposal['tool_args'] = {
            'path': safe_path,
            'content': str(tool_args.get('content') or tool_args.get('text') or json.dumps({'request': message}, ensure_ascii=False, indent=2) + '\\n')
        }
        clean_proposal['target_artifact'] = Path(safe_path).name
    elif tool_name == 'runtime_snapshot_set':
        clean_proposal['tool_args'] = {
            'key': str(tool_args.get('key') or f"{out['episode_id']}_state")[:120],
            'value': tool_args.get('value') if 'value' in tool_args else {'request': message}
        }
        clean_proposal['target_artifact'] = 'runtime_snapshot.json'
    elif tool_name == 'runtime_snapshot_get':
        clean_proposal['tool_args'] = {
            'key': str(tool_args.get('key') or 'last_state')[:120]
        }
        clean_proposal['target_artifact'] = 'runtime_snapshot.json'
    else:
        requested_path = str(tool_args.get('path') or '').strip()
        if not requested_path.lower().startswith('c:\ai_vault'):
            return base
        clean_proposal['tool_args'] = {'path': requested_path}
        clean_proposal['target_artifact'] = Path(requested_path).name
    acceptance = proposal.get('acceptance') if isinstance(proposal.get('acceptance'), list) else base['proposal']['acceptance']
    clean_proposal['acceptance'] = [str(x)[:200] for x in acceptance[:6]] or base['proposal']['acceptance']
    out['proposal'] = clean_proposal
    return out


async def _openai_episode_payload(room_id: str, message: str) -> dict[str, Any]:
    try:
        from openai import AsyncOpenAI  # type: ignore
    except Exception as e:
        return {'ok': False, 'provider': f'openai:{_select_openai_model(message)}', 'error': 'sdk_missing', 'detail': repr(e)}
    if not OPENAI_API_KEY:
        return {'ok': False, 'provider': f'openai:{_select_openai_model(message)}', 'error': 'key_missing'}
    prompt = (
        'Return exactly one JSON object for a Brain self-build episode. '
        'Use only these tool_name values: write_file, append_file, runtime_snapshot_set, runtime_snapshot_get, read_file, list_dir. '
        'If the request is broad, prefer write_file to persist a room-scoped engineering brief JSON artifact. '
        'Any write_file or append_file path must be only a file name, never an absolute path. '
        'Required shape: '
        '{"episode_id":"...","phase_id":"CHAT-SELF-BUILD","auto_apply_if_allowed":true,"rollback_on_failure":true,'
        '"proposal":{"summary":"...","tool_name":"write_file","tool_args":{},"acceptance":["..."],"target_artifact":"...json"}}\n\n'
        f'ROOM_ID: {room_id}\n'
        f'USER_REQUEST: {message}\n'
        f'RECENT_HISTORY:\n{_history_for_prompt(room_id) or "(empty)"}'
    )
    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        model_name = str(_select_openai_model(message) or OPENAI_MODEL_GENERAL)
        resp = await client.responses.create(model=model_name, input=prompt)
        out_text = getattr(resp, 'output_text', '') or ''
        payload = _extract_json_object_from_text(out_text)
        if not payload:
            return {'ok': False, 'provider': f'openai:{model_name}', 'error': 'json_missing', 'raw': out_text}
        return {'ok': True, 'provider': f'openai:{model_name}', 'payload': _sanitize_episode_payload(room_id, payload, message)}
    except Exception as e:
        failed_model = locals().get('model_name') or _select_openai_model(message)
        return {'ok': False, 'provider': f'openai:{failed_model}', 'error': 'request_failed', 'detail': repr(e)}


async def _ollama_episode_payload(room_id: str, message: str) -> dict[str, Any]:
    payload = {
        'model': OLLAMA_MODEL,
        'stream': False,
        'messages': [
            {
                'role': 'system',
                'content': (
                    'Devuelve exactamente un objeto JSON para un episodio Brain de autoconstrucción. '
                    'Usa solo tool_name permitidos: write_file, append_file, runtime_snapshot_set, runtime_snapshot_get, read_file, list_dir. '
                    'Si la solicitud es amplia, usa write_file para crear un brief JSON dentro de la room. '
                    'Si usas write_file o append_file, path debe ser solo nombre de archivo.'
                )
            },
            {
                'role': 'user',
                'content': f'ROOM_ID: {room_id}\nUSER_REQUEST: {message}\nRECENT_HISTORY:\n{_history_for_prompt(room_id) or "(vacío)"}'
            }
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f'{OLLAMA_API}/api/chat', json=payload, headers={'Content-Type': 'application/json; charset=utf-8'})
            data = resp.json()
        text = ((data.get('message') or {}).get('content') or '').strip()
        obj = _extract_json_object_from_text(text)
        if not obj:
            return {'ok': False, 'provider': 'ollama', 'error': 'json_missing', 'raw': text}
        return {'ok': True, 'provider': 'ollama', 'payload': _sanitize_episode_payload(room_id, obj, message)}
    except Exception as e:
        return {'ok': False, 'provider': 'ollama', 'error': 'request_failed', 'detail': repr(e)}


async def _self_build_episode_payload(room_id: str, message: str) -> dict[str, Any]:
    openai_result = await _openai_episode_payload(room_id, message)
    if openai_result.get('ok'):
        return openai_result
    ollama_result = await _ollama_episode_payload(room_id, message)
    if ollama_result.get('ok'):
        return ollama_result
    return {
        'ok': True,
        'provider': 'deterministic_fallback',
        'payload': _fallback_episode_payload(room_id, message),
        'provider_errors': {
            'openai': openai_result,
            'ollama': ollama_result
        }
    }


def _select_openai_model(message: str) -> str:
    low = str(message or "").strip().lower()
    if any(token in low for token in ["codigo", "código", "python", "script", "debug", "error", "roadmap", "repo", "archivo", "fastapi", "powershell", "desarrollarte", "autodesarroll"]):
        return OPENAI_MODEL_CODING
    if any(token in low for token in ["analiza", "analisis", "análisis", "razona", "estrategia", "financ", "riesgo", "capital"]):
        return OPENAI_MODEL_REASONING
    return OPENAI_MODEL_GENERAL


def _select_ollama_model(message: str) -> str:
    low = str(message or "").strip().lower()
    if any(token in low for token in ["codigo", "código", "python", "script", "debug", "error", "roadmap", "repo", "archivo", "fastapi", "powershell"]):
        return "qwen2.5:14b"
    if any(token in low for token in ["analiza", "analisis", "análisis", "razona", "estrategia", "financ", "riesgo", "capital"]):
        return "deepseek-r1:14b"
    return OLLAMA_MODEL


def _chat_route_decision(room_id: str, message: str) -> dict[str, Any]:
    low = str(message or "").strip().lower()
    dev_mode = _developer_mode_enabled(room_id)
    local_first_hints = [
        "ollama", "modelo local", "modelos locales", "localmente", "offline",
        "sin openai", "sin internet", "privado", "privacidad", "en local"
    ]
    engineering_hints = [
        "codigo", "código", "python", "script", "debug", "error", "roadmap",
        "repo", "archivo", "fastapi", "powershell", "desarrollarte", "autodesarroll"
    ]
    if any(h in low for h in local_first_hints):
        return {
            "primary": "ollama",
            "secondary": "openai",
            "reason": "local_requested",
            "ollama_model": _select_ollama_model(message),
            "openai_model": _select_openai_model(message)
        }
    if any(h in low for h in engineering_hints):
        return {
            "primary": "ollama",
            "secondary": "openai",
            "reason": "engineering_local_first",
            "ollama_model": _select_ollama_model(message),
            "openai_model": _select_openai_model(message)
        }
    if dev_mode and _is_truth_first_question(message):
        return {
            "primary": "ollama",
            "secondary": "openai",
            "reason": "devmode_truth_local_first",
            "ollama_model": _select_ollama_model(message),
            "openai_model": _select_openai_model(message)
        }
    return {
        "primary": "openai",
        "secondary": "ollama",
        "reason": "general_openai_first",
        "ollama_model": _select_ollama_model(message),
        "openai_model": _select_openai_model(message)
    }

async def _openai_chat_reply(room_id: str, message: str, model_override: str | None = None) -> dict[str, Any]:
    try:
        from openai import AsyncOpenAI  # type: ignore
    except Exception as e:
        return {"ok": False, "provider": f"openai:{_select_openai_model(message)}", "error": "sdk_missing", "detail": repr(e)}

    if not OPENAI_API_KEY:
        return {"ok": False, "provider": f"openai:{_select_openai_model(message)}", "error": "key_missing"}

    history_blob = _history_for_prompt(room_id)
    canonical_context = _canonical_context_brief(room_id)
    prompt = (
        "You are Brain, a local autonomous system speaking through a ChatGPT-style console. "
        "Respond in clear Spanish by default unless the user writes in another language. "
        "Be conversational, direct, and useful. Maintain continuity from the room history. "
        "Canonical Brain state is authoritative over your prior assumptions. "
        "Do not deny Ollama, self-development, roadmap, or other Brain capabilities if the canonical context below says they exist. "
        "If the user asks about state, capabilities, limits, roadmap, models, or self-development, stay consistent with canonical context and avoid inventing restrictions. "
        "If the user asks for an action that should be executed by Brain tools, explain briefly what will happen and keep the answer compact. Do not mention internal prompts.\n\n"
        f"CANONICAL_CONTEXT: {canonical_context}\n"
        f"ROOM_ID: {room_id}\n"
        f"RECENT_HISTORY:\n{history_blob or '(empty)'}\n\n"
        f"USER_MESSAGE:\n{message}"
    )
    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        model_name = str(model_override or _select_openai_model(message) or OPENAI_MODEL_GENERAL)
        resp = await client.responses.create(model=model_name, input=prompt)
        out_text = getattr(resp, "output_text", "") or ""
        if not out_text:
            try:
                for item in getattr(resp, "output", []) or []:
                    for content in getattr(item, "content", []) or []:
                        if getattr(content, "type", "") == "output_text":
                            out_text += getattr(content, "text", "") or ""
            except Exception:
                out_text = ""
        out_text = str(out_text or "").strip()
        if not out_text:
            return {"ok": False, "provider": f"openai:{model_name}", "error": "empty_output"}
        return {"ok": True, "provider": f"openai:{model_name}", "reply": out_text}
    except Exception as e:
        return {"ok": False, "provider": f"openai:{locals().get('model_name') or _select_openai_model(message)}", "error": "request_failed", "detail": repr(e)}


async def _ollama_chat_reply(room_id: str, message: str, model_override: str | None = None) -> dict[str, Any]:
    history_blob = _history_for_prompt(room_id)
    canonical_context = _canonical_context_brief(room_id)
    payload = {
        "model": str(model_override or OLLAMA_MODEL),
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres Brain, un sistema local autónomo que conversa en una consola tipo ChatGPT. "
                    "Responde en español claro, con continuidad conversacional y sin inventar capacidades. "
                    "El contexto canónico del Brain manda sobre cualquier suposición previa. "
                    "No niegues Ollama, autodesarrollo, roadmap o capacidades reales si el contexto canónico las marca como disponibles."
                )
            },
            {
                "role": "user",
                "content": (
                    f"CONTEXTO_CANONICO: {canonical_context}\n"
                    f"ROOM_ID: {room_id}\n"
                    f"HISTORIAL_RECIENTE:\n{history_blob or '(vacío)'}\n\n"
                    f"MENSAJE_USUARIO:\n{message}"
                )
            }
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{OLLAMA_API}/api/chat",
                json=payload,
                headers={"Content-Type": "application/json; charset=utf-8"}
            )
            data = resp.json()
        msg = ((data.get("message") or {}).get("content") or "").strip()
        if not msg:
            return {"ok": False, "provider": "ollama", "error": "empty_output", "detail": data}
        return {"ok": True, "provider": f"ollama:{str(model_override or OLLAMA_MODEL)}", "reply": msg}
    except Exception as e:
        return {"ok": False, "provider": "ollama", "error": "request_failed", "detail": repr(e)}


async def _chat_provider_reply(room_id: str, message: str) -> dict[str, Any]:
    route = _chat_route_decision(room_id, message)

    async def _call(provider_name: str) -> dict[str, Any]:
        if provider_name == "openai":
            return await _openai_chat_reply(room_id, message, model_override=str(route.get("openai_model") or _select_openai_model(message)))
        return await _ollama_chat_reply(room_id, message, model_override=str(route.get("ollama_model") or OLLAMA_MODEL))

    primary = str(route.get("primary") or "openai")
    secondary = str(route.get("secondary") or "ollama")
    primary_result = await _call(primary)
    if primary_result.get("ok"):
        primary_result["route_reason"] = route.get("reason")
        primary_result["route_primary"] = primary
        primary_result["route_secondary"] = secondary
        return primary_result

    secondary_result = await _call(secondary)
    if secondary_result.get("ok"):
        secondary_result["route_reason"] = route.get("reason")
        secondary_result["route_primary"] = primary
        secondary_result["route_secondary"] = secondary
        secondary_result["route_fallback_used"] = True
        return secondary_result

    prev_user = _last_user_message(room_id)
    return {
        "ok": True,
        "provider": "local_fallback",
        "reply": _conversation_reply(room_id, message, prev_user),
        "route_reason": route.get("reason"),
        "route_primary": primary,
        "route_secondary": secondary,
        "provider_errors": {
            primary: primary_result,
            secondary: secondary_result
        }
    }
async def _provider_health() -> dict[str, Any]:
    if OPENAI_API_KEY:
        return {
            "chat_provider": f"brain->openai:{OPENAI_MODEL_GENERAL}",
            "provider_ready": True,
            "openai_key_present": True
        }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_API}/api/tags")
            if resp.status_code == 200:
                return {
                    "chat_provider": f"brain->ollama:{OLLAMA_MODEL}",
                    "provider_ready": True,
                    "openai_key_present": False
                }
    except Exception:
        pass
    return {
        "chat_provider": "brain->fallback_only",
        "provider_ready": False,
        "openai_key_present": bool(OPENAI_API_KEY)
    }


@app.get("/healthz")
async def healthz():
    data = {
        "ok": True,
        "advisor_api": ADVISOR_API,
        "brain_api": BRAIN_API,
        "ollama_api": OLLAMA_API,
        "advisor_health": None,
        "brain_health": None
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            ar = await client.get(f"{ADVISOR_API}/healthz")
            data["advisor_health"] = ar.json()
        except Exception as e:
            data["ok"] = False
            data["advisor_health"] = {"ok": False, "error": repr(e)}

        try:
            br = await client.get(f"{BRAIN_API}/v1/agent/healthz")
            data["brain_health"] = br.json()
        except Exception as e:
            data["ok"] = False
            data["brain_health"] = {"ok": False, "error": repr(e)}

    data.update(await _provider_health())
    return JSONResponse(data)


@app.post("/api/chat")
async def api_chat(body: ChatBody):
    message = str(body.message or "").strip()
    room_id = str(body.room_id or ("ui_" + uuid.uuid4().hex[:10]))
    auto_apply = bool(getattr(body, "auto_apply", False))

    if not message:
        return JSONResponse({
            "ok": False,
            "kind": "error",
            "room_id": room_id,
            "reply": "Mensaje vacío."
        }, status_code=400)

    _append_chat_turn(room_id, "user", message)

    if _is_self_build_request(message):
        episode_provider = await _self_build_episode_payload(room_id, message)
        episode_payload = episode_provider.get('payload') or _fallback_episode_payload(room_id, message)
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                execute_resp = await client.post(
                    f"{BRAIN_API}/v1/agent/episode/execute",
                    json=episode_payload,
                    headers={"x-room-id": room_id, "Content-Type": "application/json; charset=utf-8"}
                )
                execute_obj = execute_resp.json()
            except Exception as e:
                return JSONResponse({
                    "ok": False,
                    "kind": "error",
                    "room_id": room_id,
                    "reply": f"Fallo ejecutando episodio agentic del Brain: {repr(e)}",
                    "episode_provider": episode_provider
                }, status_code=500)

            validate_obj = None
            try:
                validate_resp = await client.post(
                    f"{BRAIN_API}/v1/agent/episode/validate",
                    json={
                        "room_id": room_id,
                        "episode_id": str(execute_obj.get("episode_id") or episode_payload.get("episode_id") or ""),
                        "rollback_on_failure": True
                    },
                    headers={"x-room-id": room_id, "Content-Type": "application/json; charset=utf-8"}
                )
                validate_obj = validate_resp.json()
            except Exception:
                validate_obj = None

            backlog_obj = None
            try:
                backlog_resp = await client.post(
                    f"{BRAIN_API}/v1/agent/backlog/synthesize",
                    json={
                        "room_id": room_id,
                        "phase_id": str(episode_payload.get("phase_id") or ""),
                        "source_room_id": room_id
                    },
                    headers={"x-room-id": room_id, "Content-Type": "application/json; charset=utf-8"}
                )
                backlog_obj = backlog_resp.json()
            except Exception:
                backlog_obj = None

        observation = execute_obj.get("observation") or {}
        summary = str(((episode_payload.get("proposal") or {}).get("summary") or "")).strip()
        status = str(observation.get("status") or execute_obj.get("action") or "ok")
        artifacts = observation.get("artifacts") or []
        next_action = str(observation.get("next_recommended_action") or "")
        backlog_items = []
        if isinstance(backlog_obj, dict):
            backlog_items = list(backlog_obj.get("backlog") or [])
        reply_lines = [
            "Abrí un episodio agentic del Brain para trabajar esta solicitud.",
            f"Resumen: {summary or message}",
            f"Estado: {status}"
        ]
        if artifacts:
            reply_lines.append("Artifacts: " + ", ".join(str(x) for x in artifacts[:6]))
        if next_action:
            reply_lines.append("Siguiente paso sugerido: " + next_action)
        if validate_obj and isinstance(validate_obj, dict):
            report = validate_obj.get("report") or {}
            reply_lines.append("Validación: " + ("ok" if bool(report.get("validation_ok")) else str(report.get("status") or "revisar")))
        followup_obj = None
        followup_validation = None
        if auto_apply and backlog_items:
            followup_payload = _followup_episode_payload_from_backlog(room_id, message, backlog_obj)
            if followup_payload:
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        followup_resp = await client.post(
                            f"{BRAIN_API}/v1/agent/episode/execute",
                            json=followup_payload,
                            headers={"x-room-id": room_id, "Content-Type": "application/json; charset=utf-8"}
                        )
                        followup_obj = followup_resp.json()
                        try:
                            followup_validate_resp = await client.post(
                                f"{BRAIN_API}/v1/agent/episode/validate",
                                json={
                                    "room_id": room_id,
                                    "episode_id": str(followup_obj.get("episode_id") or followup_payload.get("episode_id") or ""),
                                    "rollback_on_failure": True
                                },
                                headers={"x-room-id": room_id, "Content-Type": "application/json; charset=utf-8"}
                            )
                            followup_validation = followup_validate_resp.json()
                        except Exception:
                            followup_validation = None
                except Exception:
                    followup_obj = None
                    followup_validation = None
        if backlog_items:
            top_titles = [str((item or {}).get("title") or "").strip() for item in backlog_items[:2]]
            top_titles = [x for x in top_titles if x]
            if top_titles:
                reply_lines.append("Backlog inicial: " + " | ".join(top_titles))
        if isinstance(followup_obj, dict) and followup_obj.get("ok"):
            followup_observation = followup_obj.get("observation") or {}
            followup_status = str(followup_observation.get("status") or followup_obj.get("action") or "ok")
            reply_lines.append("Seguimiento automático: " + followup_status)
        reply = "\n".join(reply_lines)
        _append_chat_turn(room_id, "assistant", reply)
        return JSONResponse({
            "ok": bool(execute_obj.get("ok", True)),
            "kind": "brain_episode",
            "room_id": room_id,
            "reply": reply,
            "brain_authority": True,
            "episode_provider": episode_provider,
            "brain_episode": execute_obj,
            "validation": validate_obj,
            "backlog_synthesis": backlog_obj,
            "followup_episode": followup_obj,
            "followup_validation": followup_validation
        }, status_code=200)

    if not _is_action_request(message):
        toggle_reply = _developer_mode_toggle_reply(room_id, message)
        if toggle_reply:
            _append_chat_turn(room_id, "assistant", toggle_reply)
            return JSONResponse({
                "ok": True,
                "kind": "brain_conversation",
                "room_id": room_id,
                "reply": toggle_reply,
                "brain_authority": True,
                "provider": {"provider": "deterministic_devmode"}
            }, status_code=200)

        episode_payload = _conversation_episode_payload(room_id, message)
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                execute_resp = await client.post(
                    f"{BRAIN_API}/v1/agent/episode/execute",
                    json=episode_payload,
                    headers={"x-room-id": room_id, "Content-Type": "application/json; charset=utf-8"}
                )
                execute_obj = execute_resp.json()
            except Exception as e:
                return JSONResponse({
                    "ok": False,
                    "kind": "error",
                    "room_id": room_id,
                    "reply": f"Fallo registrando el turno conversacional en Brain: {repr(e)}"
                }, status_code=500)

        provider_reply = await _chat_provider_reply(room_id, message)
        provider_name = str(provider_reply.get("provider") or "fallback")
        observation = execute_obj.get("observation") or {}
        status = str(observation.get("status") or execute_obj.get("action") or "ok")

        if _is_truth_first_question(message):
            reply = _capability_answer(room_id, message) if _is_capability_question(message) else _truth_first_answer(room_id, message)
        else:
            reply = str(provider_reply.get("reply") or "").strip() or _conversation_reply(room_id, message, _last_user_message(room_id))

        reply = reply + f"\n\n[Brain] Registré este turno en el room {room_id} y respondí usando {provider_name}. Estado Brain: {status}."
        if _developer_mode_enabled(room_id):
            reply = reply + "\n\n" + _developer_transparency_block(room_id, provider_name, provider_reply)

        _append_chat_turn(room_id, "assistant", reply)
        return JSONResponse({
            "ok": True,
            "kind": "brain_conversation",
            "room_id": room_id,
            "reply": reply,
            "brain_authority": True,
            "provider": provider_reply,
            "brain_episode": execute_obj
        }, status_code=200)
    advisor_payload = {
        "room_id": room_id,
        "publish": False,
        "mode": "planner",
        "prompt": message
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        try:
            advisor_resp = await client.post(
                f"{ADVISOR_API}/v1/advisor/next",
                json=advisor_payload,
                headers={"Content-Type": "application/json; charset=utf-8"}
            )
            advisor_obj = advisor_resp.json()
        except Exception as e:
            return JSONResponse({
                "ok": False,
                "kind": "error",
                "room_id": room_id,
                "reply": f"Fallo llamando advisor: {repr(e)}"
            }, status_code=500)

        if str(advisor_obj.get("status") or "") == "clarification_required":
            reply = str(advisor_obj.get("clarification_question") or "Necesito una aclaración.")
            _append_chat_turn(room_id, "assistant", reply)
            return JSONResponse({
                "ok": True,
                "kind": "clarification",
                "room_id": room_id,
                "reply": reply,
                "advisor": advisor_obj
            }, status_code=200)

        try:
            plan = _extract_plan(advisor_obj)
        except Exception:
            plan = None

        try:
            steps = list(plan.get("steps") or []) if isinstance(plan, dict) else []
        except Exception:
            steps = []

        if _detect_placeholder(advisor_obj) or (not isinstance(plan, dict)) or (not steps):
            provider_reply = await _chat_provider_reply(room_id, message)
            provider_name = str(provider_reply.get("provider") or "fallback")
            if _is_truth_first_question(message):
                reply = _capability_answer(room_id, message) if _is_capability_question(message) else _truth_first_answer(room_id, message)
            else:
                reply = str(provider_reply.get("reply") or "").strip() or _conversation_reply(room_id, message, _last_user_message(room_id))
            if _developer_mode_enabled(room_id):
                reply = reply + "\n\n" + _developer_transparency_block(room_id, provider_name, provider_reply)
            _append_chat_turn(room_id, "assistant", reply)
            return JSONResponse({
                "ok": True,
                "kind": "chat_orchestrated",
                "room_id": room_id,
                "reply": reply,
                "brain_authority": True,
                "history_turns": len(_load_chat_history(room_id)),
                "advisor": advisor_obj,
                "provider": provider_reply
            }, status_code=200)
        try:
            publish_resp = await client.post(
                f"{BRAIN_API}/v1/agent/plan",
                headers={
                    "x-room-id": room_id,
                    "Content-Type": "application/json; charset=utf-8"
                },
                content=json.dumps(plan, ensure_ascii=False)
            )
            publish_obj = publish_resp.json()
        except Exception as e:
            return JSONResponse({
                "ok": False,
                "kind": "error",
                "room_id": room_id,
                "reply": f"Fallo publicando plan al brain: {repr(e)}",
                "advisor": advisor_obj
            }, status_code=500)

        try:
            run_resp = await client.post(
                f"{BRAIN_API}/v1/agent/run_once",
                headers={
                    "x-room-id": room_id,
                    "Content-Type": "application/json; charset=utf-8"
                },
                content=json.dumps({"room_id": room_id, "max_steps": 1}, ensure_ascii=False)
            )
            run_obj = run_resp.json()
        except Exception as e:
            return JSONResponse({
                "ok": False,
                "kind": "error",
                "room_id": room_id,
                "reply": f"Fallo ejecutando run_once: {repr(e)}",
                "advisor": advisor_obj,
                "brain": {
                    "plan_publish": publish_obj
                }
            }, status_code=500)

        plan_after_run = _room_plan(room_id) or {}

        if auto_apply:
            approve_token = None
            try:
                for st in list(plan_after_run.get("steps") or []):
                    tok = st.get("required_approve")
                    if tok:
                        approve_token = tok
                        break
            except Exception:
                approve_token = None

            if approve_token:
                try:
                    apply_resp = await client.post(
                        f"{BRAIN_API}/v1/agent/apply",
                        headers={
                            "x-room-id": room_id,
                            "Content-Type": "application/json; charset=utf-8"
                        },
                        content=json.dumps({"room_id": room_id, "approve_token": approve_token}, ensure_ascii=False)
                    )
                    apply_obj = apply_resp.json()
                except Exception as e:
                    return JSONResponse({
                        "ok": False,
                        "kind": "error",
                        "room_id": room_id,
                        "reply": f"Fallo aplicando aprobación: {repr(e)}",
                        "advisor": advisor_obj,
                        "brain": {
                            "plan_publish": publish_obj,
                            "run_once": run_obj
                        }
                    }, status_code=500)

                try:
                    run2_resp = await client.post(
                        f"{BRAIN_API}/v1/agent/run_once",
                        headers={
                            "x-room-id": room_id,
                            "Content-Type": "application/json; charset=utf-8"
                        },
                        content=json.dumps({"room_id": room_id, "max_steps": 1}, ensure_ascii=False)
                    )
                    run2_obj = run2_resp.json()
                except Exception as e:
                    run2_obj = {"ok": False, "error": repr(e)}

                plan_after_run = _room_plan(room_id) or {}
                steps_after = list(plan_after_run.get("steps") or [])
                reply = _human_reply_from_plan(room_id, steps_after)
                _append_chat_turn(room_id, "assistant", reply)

                return JSONResponse({
                    "ok": True,
                    "kind": "executed",
                    "room_id": room_id,
                    "reply": reply,
                    "brain_authority": True,
                    "advisor": advisor_obj,
                    "brain": {
                        "plan_publish": publish_obj,
                        "run_once": run_obj,
                        "apply": apply_obj,
                        "run_once_after_apply": run2_obj
                    }
                }, status_code=200)

        reply = _human_reply_from_plan(room_id, steps)
        _append_chat_turn(room_id, "assistant", reply)

        return JSONResponse({
            "ok": True,
            "kind": "planned",
            "room_id": room_id,
            "reply": reply,
            "brain_authority": True,
            "advisor": advisor_obj,
            "brain": {
                "plan_publish": publish_obj,
                "run_once": run_obj
            }
        }, status_code=200)
