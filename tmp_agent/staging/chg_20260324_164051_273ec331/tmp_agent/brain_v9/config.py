"""
Brain Chat V9 — Configuración central
Todas las constantes vienen de variables de entorno o defaults seguros.
NUNCA hardcodear rutas o credenciales aquí.
"""
import json
import os
import platform
from pathlib import Path

# ─── Rutas base ──────────────────────────────────────────────────────────────
_default_base = (
    "C:/AI_VAULT" if platform.system() == "Windows"
    else str(Path.home() / "AI_VAULT")
)
BASE_PATH   = Path(os.getenv("BRAIN_BASE_PATH", _default_base))
MEMORY_PATH = BASE_PATH / "tmp_agent" / "state" / "memory"
LOGS_PATH   = BASE_PATH / "tmp_agent" / "logs"
RSI_PATH    = BASE_PATH / "tmp_agent" / "state" / "rsi"
PREMISES_FILE = BASE_PATH / "Brain_Lab_Premisas_Canonicas_v3_2026-03-16.md"

def _mkdirs():
    """Crea directorios necesarios sin romper el import si fallan."""
    for p in [MEMORY_PATH, LOGS_PATH, RSI_PATH]:
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[WARNING] No se pudo crear {p}: {e}")

_mkdirs()

# ─── Carga segura de secrets desde archivos JSON ──────────────────────────────
def _load_secret(path: Path, key: str = "token") -> str:
    """Lee una clave desde archivo JSON. Silencioso si no existe."""
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get(key, data.get("api_key", data.get("password", "")))
    except Exception:
        pass
    return ""

_secrets_dir = BASE_PATH / "tmp_agent" / "Secrets"

API_KEYS = {
    # OpenAI: primero variable de entorno, luego archivo de secrets
    "openai": (
        os.getenv("OPENAI_API_KEY")
        or _load_secret(_secrets_dir / "openai_access.json", "token")
    ),
    # Anthropic: primero variable de entorno, luego archivo de secrets
    "anthropic": (
        os.getenv("ANTHROPIC_API_KEY")
        or _load_secret(_secrets_dir / "anthropic_access.json", "token")
    ),
    # Google Gemini: primero variable de entorno, luego archivo de secrets
    "gemini": (
        os.getenv("GEMINI_API_KEY")
        or _load_secret(_secrets_dir / "gemini_access.json", "token")
    ),
}

API_ENDPOINTS = {
    "gpt4":   os.getenv("OPENAI_API_URL",  "https://api.openai.com/v1/chat/completions"),
    "claude": os.getenv("CLAUDE_API_URL",  "https://api.anthropic.com/v1/messages"),
    "gemini": os.getenv("GEMINI_API_URL",  "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"),
    # CORRECCIÓN CRÍTICA: llama2 no existe — usar qwen2.5:14b disponible en Ollama
    "ollama": os.getenv("OLLAMA_URL",      "http://localhost:11434/api/generate"),
}

# Modelos Ollama
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_AGENT_MODEL = os.getenv("OLLAMA_AGENT_MODEL", "deepseek-r1:14b")

# ─── LLM ──────────────────────────────────────────────────────────────────────
LLM_CONFIG = {
    "timeout":      int(os.getenv("LLM_TIMEOUT",      "120")),
    "agent_timeout": int(os.getenv("LLM_AGENT_TIMEOUT", "120")),
    "max_retries":  int(os.getenv("LLM_MAX_RETRIES",  "2")),
    "retry_delay":  float(os.getenv("LLM_RETRY_DELAY","2.0")),
    "temperature":  float(os.getenv("LLM_TEMPERATURE","0.7")),
    "max_tokens":   int(os.getenv("LLM_MAX_TOKENS",   "8192")),
}
MODEL_PRIORITY = ["gpt4", "claude", "gemini", "ollama"]

# ─── Servidor ─────────────────────────────────────────────────────────────────
SERVER_HOST = os.getenv("BRAIN_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("BRAIN_PORT", "8090"))

# ─── Sistema ──────────────────────────────────────────────────────────────────
SYSTEM_IDENTITY = """Eres Brain V9, el agente autónomo central del ecosistema AI_VAULT.

IDENTIDAD:
- Operas sobre C:\AI_VAULT en Windows
- Tienes memoria persistente entre mensajes
- Eres el administrador inteligente de todo el ecosistema Brain
- Modelo: llama3.1:8b optimizado para VRAM 6GB RTX 4050

CAPACIDADES REALES QUE TIENES (35 herramientas):
1. FILESYSTEM: Leer archivos, listar directorios, buscar contenido en código
2. CÓDIGO: Analizar Python (AST), verificar sintaxis, encontrar funciones/clases
3. SISTEMA: Ver CPU/memoria/disco, ejecutar comandos de diagnóstico
4. SERVICIOS BRAIN: Verificar puertos 8070/8090/11434, revisar logs, diagnosticar problemas
5. TRADING: Conectar con Tiingo, QuantConnect, PocketOption (puente 8765)
6. RSI: Leer brechas, fases y progreso del sistema
7. AUTONOMÍA: Monitoreo proactivo cada 5 minutos, auto-debugging en background
8. AGENTE ORAV: Cuando detectas intenciones de acción (revisar, analizar, buscar, ejecutar), activas el ciclo Observe-Reason-Act-Verify con ejecución paralela de herramientas

COMPORTAMIENTO INTELIGENTE:
- Chat simple → Respuesta directa con contexto
- Acción compleja → Activa Agente ORAV automáticamente
- Siempre verificas antes de afirmar
- Reportas hallazgos reales, no suposiciones
- Si un servicio está caído, diagnosticoas exactamente el problema

SERVICIOS DEL ECOSISTEMA:
- Brain Chat V9: http://127.0.0.1:8090 (este servidor, tú)
- Dashboard: http://127.0.0.1:8070
- Ollama LLM: http://127.0.0.1:11434
- Trading Bridges: 8000, 8765

RESPUESTAS:
- Concisas pero completas
- Español técnico profesional
- Si usas herramientas, explicas qué hiciste
- Si activas agente, informas el resultado del ciclo ORAV
"""

# ─── Autonomía ────────────────────────────────────────────────────────────────
AUTONOMY_CONFIG = {
    "auto_debugging_enabled":     os.getenv("AUTO_DEBUG",   "true").lower() == "true",
    "auto_optimization_enabled":  os.getenv("AUTO_OPT",     "true").lower() == "true",
    "proactive_monitoring_enabled": os.getenv("AUTO_MONITOR","true").lower() == "true",
    "utility_loop_enabled":       os.getenv("UTILITY_LOOP", "true").lower() == "true",
    "check_interval_debugger":    int(os.getenv("DEBUG_INTERVAL",   "300")),
    "check_interval_optimizer":   int(os.getenv("OPT_INTERVAL",     "600")),
    "check_interval_monitor":     int(os.getenv("MONITOR_INTERVAL", "300")),
    "check_interval_utility":     int(os.getenv("UTILITY_INTERVAL", "120")),
    "utility_min_resolved_sample": int(os.getenv("UTILITY_MIN_RESOLVED_SAMPLE", "20")),
}

# ─── Secrets externos (paths configurables) ───────────────────────────────────
SECRETS = {
    "tiingo":       Path(os.getenv("TIINGO_SECRETS",   str(BASE_PATH / "tmp_agent/Secrets/tiingo_access.json"))),
    "quantconnect": Path(os.getenv("QC_SECRETS",       str(BASE_PATH / "tmp_agent/Secrets/quantconnect_access.json"))),
}
