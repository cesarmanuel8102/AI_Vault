"""
Brain Chat V8 — Script de parches quirúrgicos
Aplica los 4 fixes que hacen que V8 arranque correctamente.

Uso:
    python apply_patches_v8.py brain_chat_v8.py

Crea: brain_chat_v8_patched.py  (el original no se toca)
"""

import re
import shutil
import sys
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# PARCHE 1 — BASE_PATH configurable + mkdir protegido  (líneas 67-73)
# ─────────────────────────────────────────────────────────────────────────────
PATCH_1_OLD = 'BASE_PATH = Path("C:/AI_VAULT")'

PATCH_1_NEW = '''\
import platform as _platform

_default_base = (
    "C:/AI_VAULT"
    if _platform.system() == "Windows"
    else str(Path.home() / "AI_VAULT")
)
BASE_PATH = Path(os.getenv("BRAIN_BASE_PATH", _default_base))'''


# El mkdir que está en nivel de módulo:
PATCH_1B_OLD = '''\
MEMORY_PATH.mkdir(parents=True, exist_ok=True)
LOGS_PATH.mkdir(parents=True, exist_ok=True)'''

PATCH_1B_NEW = '''\
try:
    MEMORY_PATH.mkdir(parents=True, exist_ok=True)
    LOGS_PATH.mkdir(parents=True, exist_ok=True)
except Exception as _mkdir_err:
    print(f"[WARNING] No se pudo crear directorio base: {_mkdir_err}")
    print(f"[WARNING] Establece BRAIN_BASE_PATH=<ruta> en variables de entorno")'''


# ─────────────────────────────────────────────────────────────────────────────
# PARCHE 2 — LLMManager: ClientSession lazy (líneas 603-617 + 731, 779, 819)
# ─────────────────────────────────────────────────────────────────────────────
PATCH_2_OLD = (
    "        self._init_session()\n"
    "    \n"
    "    def _init_session(self):\n"
    "        \"\"\"Inicializa la sesi\u00f3n HTTP\"\"\"\n"
    "        timeout = ClientTimeout(total=LLM_CONFIG[\"timeout\"])\n"
    "        self.session = ClientSession(timeout=timeout)"
)

PATCH_2_NEW = (
    "        # Sesi\u00f3n lazy: se crea en el primer uso dentro de una corutina (aiohttp >= 3.9)\n"
    "\n"
    "    async def _get_session(self) -> ClientSession:\n"
    "        \"\"\"Obtiene o crea la sesi\u00f3n HTTP de forma lazy y async-safe.\n\n"
    "        aiohttp >= 3.9 proh\u00edbe crear ClientSession fuera de una corutina.\n"
    "        \"\"\"\n"
    "        if self.session is None or self.session.closed:\n"
    "            timeout = ClientTimeout(total=LLM_CONFIG[\"timeout\"])\n"
    "            self.session = ClientSession(timeout=timeout)\n"
    "        return self.session"
)


# Las 3 líneas que usan self.session.post directamente:
PATCH_2_GPT4_OLD  = "        async with self.session.post(\n            API_ENDPOINTS[\"gpt4\"],"
PATCH_2_GPT4_NEW  = "        session = await self._get_session()\n        async with session.post(\n            API_ENDPOINTS[\"gpt4\"],"

PATCH_2_CLAUDE_OLD = "        async with self.session.post(\n            API_ENDPOINTS[\"claude\"],"
PATCH_2_CLAUDE_NEW = "        session = await self._get_session()\n        async with session.post(\n            API_ENDPOINTS[\"claude\"],"

PATCH_2_OLLAMA_OLD = "        async with self.session.post(\n            API_ENDPOINTS[\"ollama\"],"
PATCH_2_OLLAMA_NEW = "        session = await self._get_session()\n        async with session.post(\n            API_ENDPOINTS[\"ollama\"],"


# ─────────────────────────────────────────────────────────────────────────────
# PARCHE 3 — startup_background con manejo de errores  (línea ~11879)
# ─────────────────────────────────────────────────────────────────────────────
PATCH_3_OLD = '''\
async def startup_background():
    """Inicialización en background - no bloquea el servidor"""
    await asyncio.sleep(1)  # Esperar a que FastAPI inicie
    await startup()'''

PATCH_3_NEW = '''\
async def startup_background():
    """Inicialización en background - no bloquea el servidor."""
    await asyncio.sleep(1)  # Esperar a que FastAPI inicie
    _startup_log = logging.getLogger("startup_background")
    try:
        await startup()
    except Exception as _exc:
        _startup_log.critical(
            "STARTUP FALLÓ — el servidor está vivo pero NO inicializado. "
            f"Error: {_exc}",
            exc_info=True,
        )
        # Registrar el error para que /health devuelva 503
        active_sessions["__startup_error__"] = str(_exc)'''


# ─────────────────────────────────────────────────────────────────────────────
# PARCHE 4 — /health devuelve 503 si el sistema no está listo  (línea ~4939)
# ─────────────────────────────────────────────────────────────────────────────
PATCH_4_OLD = '''\
@app.get("/health")
async def health_check():'''

PATCH_4_NEW = '''\
@app.get("/health")
async def health_check():
    # Parche: devolver 503 mientras el sistema no esté inicializado
    _startup_error = active_sessions.get("__startup_error__")
    if _startup_error:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "status": "startup_failed",
                "error": _startup_error,
                "hint": "Revisa los logs del servidor para ver el error completo",
            },
        )
    if "default" not in active_sessions:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "initializing", "message": "Startup en progreso..."},
        )'''


# ─────────────────────────────────────────────────────────────────────────────
# Motor del patcheador
# ─────────────────────────────────────────────────────────────────────────────

def apply_patch(content: str, old: str, new: str, label: str) -> str:
    if old not in content:
        print(f"  [WARN] {label}: fragmento no encontrado — ¿ya aplicado?")
        return content
    count = content.count(old)
    if count > 1:
        print(f"  [WARN] {label}: fragmento encontrado {count} veces — aplicando al primero")
    result = content.replace(old, new, 1)
    print(f"  [OK]   {label}")
    return result


def apply_all_patches(src: str) -> str:
    patches = [
        (PATCH_1_OLD,        PATCH_1_NEW,        "Bug #2a — BASE_PATH configurable"),
        (PATCH_1B_OLD,       PATCH_1B_NEW,       "Bug #2b — mkdir protegido en módulo"),
        (PATCH_2_OLD,        PATCH_2_NEW,        "Bug #1a — LLMManager: eliminar _init_session()"),
        (PATCH_2_GPT4_OLD,   PATCH_2_GPT4_NEW,   "Bug #1b — LLMManager: lazy session en _query_gpt4"),
        (PATCH_2_CLAUDE_OLD, PATCH_2_CLAUDE_NEW,  "Bug #1c — LLMManager: lazy session en _query_claude"),
        (PATCH_2_OLLAMA_OLD, PATCH_2_OLLAMA_NEW,  "Bug #1d — LLMManager: lazy session en _query_ollama"),
        (PATCH_3_OLD,        PATCH_3_NEW,        "Bug #3  — startup_background: captura excepciones"),
        (PATCH_4_OLD,        PATCH_4_NEW,        "Bug #4  — /health: 503 mientras no esté listo"),
    ]

    for old, new, label in patches:
        src = apply_patch(src, old, new, label)

    return src


def main():
    if len(sys.argv) < 2:
        target = Path("brain_chat_v8.py")
    else:
        target = Path(sys.argv[1])

    if not target.exists():
        print(f"[ERROR] No se encontró: {target}")
        sys.exit(1)

    out = target.with_name(target.stem + "_patched.py")

    print(f"\nBrain Chat V8 — Patcheador quirúrgico")
    print(f"{'─' * 50}")
    print(f"Origen : {target}")
    print(f"Destino: {out}")
    print(f"{'─' * 50}\n")

    content = target.read_text(encoding="utf-8")
    patched = apply_all_patches(content)

    out.write_text(patched, encoding="utf-8")

    print(f"\n{'─' * 50}")
    print(f"Listo. Prueba con:")
    print(f"  python {out.name}")
    print(f"\nVerificación (espera ~3 segundos después de arrancar):")
    print(f"  curl http://localhost:8090/health")
    print(f"\nVariables de entorno opcionales:")
    print(f"  BRAIN_BASE_PATH   → ruta base (default: C:/AI_VAULT en Windows)")
    print(f"  OPENAI_API_KEY    → clave OpenAI")
    print(f"  ANTHROPIC_API_KEY → clave Anthropic")
    print(f"{'─' * 50}\n")


if __name__ == "__main__":
    main()
