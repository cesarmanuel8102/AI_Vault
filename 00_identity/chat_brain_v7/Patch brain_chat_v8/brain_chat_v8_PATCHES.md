# Brain Chat V8 — Diagnóstico y Parches Quirúrgicos

## El veredicto real

El V8 **no necesita rediseño**. Tiene **4 bugs concretos** que se pueden corregir
en ~20 líneas de cambios. Aquí está la prueba.

---

## Bug #1 — EL CULPABLE PRINCIPAL (línea 612-617)

### `LLMManager._init_session()` crea `ClientSession` en un `__init__` síncrono

```python
# CÓDIGO ACTUAL (ROTO con aiohttp ≥ 3.9)
def __init__(self):
    ...
    self._init_session()          # ← se llama en __init__

def _init_session(self):
    timeout = ClientTimeout(total=LLM_CONFIG["timeout"])
    self.session = ClientSession(timeout=timeout)  # ← CRASH aquí
```

**Por qué falla:** `aiohttp` ≥ 3.9 prohíbe crear `ClientSession` fuera de una
corutina. El `__init__` es síncrono, aunque se llame desde dentro de un task
async. El error se lanza, el `startup_background` lo traga silenciosamente,
y el servidor queda "vivo" pero sin ningún componente inicializado.

```python
# PARCHE — hacer la sesión lazy (igual que ya hacen TiingoConnector y PocketOptionBridge)
def __init__(self):
    ...
    # NO llamar _init_session() aquí
    self.session: Optional[ClientSession] = None  # se crea en el primer uso

async def _get_session(self) -> ClientSession:
    """Crea la sesión HTTP de forma lazy (async-safe)"""
    if self.session is None or self.session.closed:
        timeout = ClientTimeout(total=LLM_CONFIG["timeout"])
        self.session = ClientSession(timeout=timeout)
    return self.session

# Reemplazar TODAS las referencias a self.session por await self._get_session()
# en _query_gpt4, _query_claude, _query_ollama
```

---

## Bug #2 — FALLA EN IMPORTACIÓN (líneas 67-73)

### `BASE_PATH` hardcoded a `C:/AI_VAULT` con `mkdir` en nivel de módulo

```python
# CÓDIGO ACTUAL (ROTO fuera de tu máquina Windows)
BASE_PATH = Path("C:/AI_VAULT")                        # línea 67
MEMORY_PATH = BASE_PATH / "tmp_agent" / "state" / "memory"
LOGS_PATH   = BASE_PATH / "tmp_agent" / "logs"

MEMORY_PATH.mkdir(parents=True, exist_ok=True)         # línea 72 — falla en Linux
LOGS_PATH.mkdir(parents=True, exist_ok=True)           # línea 73 — falla en Linux
```

**Por qué falla:** En Linux/Mac `Path("C:/AI_VAULT")` crea el path literal
`C:/AI_VAULT` (con la barra) que probablemente no tienes permisos para crear.
La excepción se lanza al importar el módulo, antes de que FastAPI llegue a
arrancar siquiera.

```python
# PARCHE — configurable por variable de entorno
import platform

_default_base = (
    "C:/AI_VAULT" if platform.system() == "Windows"
    else str(Path.home() / "AI_VAULT")
)
BASE_PATH = Path(os.getenv("BRAIN_BASE_PATH", _default_base))
MEMORY_PATH = BASE_PATH / "tmp_agent" / "state" / "memory"
LOGS_PATH   = BASE_PATH / "tmp_agent" / "logs"

# Proteger el mkdir para que nunca tumbe el import
try:
    MEMORY_PATH.mkdir(parents=True, exist_ok=True)
    LOGS_PATH.mkdir(parents=True, exist_ok=True)
except Exception as _e:
    print(f"[WARNING] No se pudo crear directorio base: {_e}")
```

---

## Bug #3 — EXCEPCIONES SILENCIOSAS (línea 11879-11883)

### `startup_background` no captura excepciones

```python
# CÓDIGO ACTUAL (excepciones invisibles)
async def startup_background():
    """Inicialización en background - no bloquea el servidor"""
    await asyncio.sleep(1)
    await startup()   # ← si esto lanza, el error desaparece en el vacío
```

**Por qué falla:** Si `startup()` lanza cualquier excepción (como el
`ClientSession` del Bug #1), el task termina silenciosamente. El servidor
responde `200 OK` en `/health` pero `active_sessions` está vacío.

```python
# PARCHE — capturar y loggear siempre
async def startup_background():
    """Inicialización en background - no bloquea el servidor"""
    await asyncio.sleep(1)
    try:
        await startup()
    except Exception as exc:
        logging.getLogger("startup").critical(
            f"STARTUP FALLÓ: {exc}", exc_info=True
        )
        # Marcar sistema como no-inicializado para que /health devuelva 503
        active_sessions["__startup_error__"] = str(exc)
```

---

## Bug #4 — HEALTH CHECK ENGAÑOSO (línea ~4939)

### `/health` devuelve `200` aunque el sistema no esté listo

```python
# CÓDIGO ACTUAL
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
    # ← siempre 200, incluso si active_sessions está vacío
```

```python
# PARCHE — health real
@app.get("/health")
async def health_check():
    error = active_sessions.get("__startup_error__")
    if error:
        return JSONResponse(
            status_code=503,
            content={"status": "startup_failed", "error": error}
        )

    ready = "default" in active_sessions
    if not ready:
        return JSONResponse(
            status_code=503,
            content={"status": "initializing", "message": "Startup en progreso..."}
        )

    return {
        "status": "healthy",
        "sessions": len(active_sessions),
        "timestamp": datetime.now().isoformat()
    }
```

---

## Cómo aplicar los parches (orden importa)

```
1. Bug #2 primero  → líneas 67-73  (antes de cualquier otra cosa, es módulo-level)
2. Bug #1          → líneas 603-617 + actualizar _query_gpt4/claude/ollama
3. Bug #3          → línea 11879-11883
4. Bug #4          → línea ~4939
```

Tiempo estimado: 30-45 minutos de edición cuidadosa.

---

## Verificación post-parche

```bash
# Arrancar
python brain_chat_v8.py

# En otro terminal, esperar 3 segundos y verificar:
curl http://localhost:8090/health
# Debe devolver: {"status":"healthy","sessions":1,...}

# Si devuelve 503 con "startup_failed", revisar logs para ver el error real
```

---

## Por qué fallaron los intentos anteriores

| Intento          | Por qué no funcionó                                                    |
|------------------|------------------------------------------------------------------------|
| Background tasks | El Bug #1 lanza excepción dentro del task → silenciosa → nada inicia  |
| Launcher simplif.| No resuelve el `ClientSession` en `__init__` síncrono                 |
| Eventos startup  | Mismo problema: excepción dentro del evento no se propaga a uvicorn   |
| Lazy loading     | Incompleto: se aplicó a los connectors (Tiingo, Pocket) pero no a LLM |

El problema siempre fue el mismo: **Bug #1 + Bug #3 juntos** hacen que el error
sea invisible. El Bug #1 tira la excepción, el Bug #3 la esconde.

---

## Resumen ejecutivo

```
Bug #1  LLMManager._init_session()   ClientSession() en __init__ síncrono
Bug #2  BASE_PATH hardcoded          mkdir() en import, falla en Linux/servidor
Bug #3  startup_background()         excepciones silenciadas = diagnóstico ciego  
Bug #4  /health siempre 200          imposible saber si el sistema arrancó
```

Los 11,891 líneas de lógica están bien. El motor falla porque el
**arranque no puede reportar sus propios errores**.
