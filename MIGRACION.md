# Brain Chat V9 — Guía de Migración desde V8.0

## Lo que ya está hecho (en este scaffold)

| Archivo V9                  | Fuente                     | Estado |
|-----------------------------|----------------------------|--------|
| `config.py`                 | V8.0 líneas 67-150         | ✅ Listo, bugs corregidos |
| `core/llm.py`               | V8.0 líneas 593-863        | ✅ Listo, qwen2.5:14b |
| `core/memory.py`            | V8.0 líneas 151-371        | ✅ Listo |
| `core/session.py`           | Nuevo (reemplaza BrainChatV8) | ✅ Listo |
| `main.py`                   | Nuevo (FastAPI limpio)     | ✅ Listo |
| `brain/rsi.py`              | V8.0 líneas 3673-3861      | ✅ Listo |
| `brain/health.py`           | V8.0 líneas 3862-4054      | ✅ Listo |

---

## Lo que falta migrar (extraer de V8.0)

### Prioridad ALTA (para tener paridad con V7.2)

**`core/intent.py`** — Copiar de V8.0 líneas 376-588 (IntentDetector)
y líneas 5467-5837 (AdvancedIntentDetector). Sin cambios.

**`brain/metrics.py`** — Copiar de V8.0 líneas 4055-4341 (MetricsAggregator).
Sin cambios.

### Prioridad MEDIA (trading integration)

**`trading/tiingo.py`** — Copiar de V8.0 líneas 3127-3288.
Cambiar la ruta de secrets a: `from brain_v9.config import SECRETS`
y usar `SECRETS["tiingo"]` en lugar del path hardcoded.

**`trading/quantconnect.py`** — Copiar de V8.0 líneas 2973-3126.
Mismo cambio de path.

**`trading/pocket_option.py`** — Copiar de V8.0 líneas 3289-3417.

**`trading/metrics.py`** — Copiar de V8.0 líneas 3418-3664.

### Prioridad MEDIA (autonomía)

**`autonomy/debugger.py`** — Copiar de V8.0 líneas 7038-7473 (AutoDebugger).
**`autonomy/optimizer.py`** — Copiar de V8.0 líneas 7514-7977 (AutoOptimizer).
**`autonomy/monitor.py`** — Copiar de V8.0 líneas 8311-8612 (ProactiveMonitor).

### Prioridad BAJA (NLP avanzado)

**`core/nlp.py`** — Copiar de V8.0 líneas 5164-6805:
- TextNormalizer (5164-5462)
- ContextManager (5842-6162)
- EntityExtractor (6167-6541)
- ResponseFormatter (6546-6805)

### Agente autónomo (de V8.1 OpenCode)

**`agent/loop.py`** — Copiar de `agent_core.py` (V8.1).
Ciclo Observe-Reason-Act-Verify.

**`agent/tools.py`** — Copiar de `tools_advanced.py` (V8.1).
AST Analyzer, grep/glob, SmartEditor.

---

## UI separada del Python

En V8.0 el HTML está embebido en Python (líneas 9155-11537).
En V9 va como archivo estático:

```
brain_v9/
└── ui/
    └── index.html   ← Copiar el HTML desde V8.0 y guardarlo aquí
```

El servidor lo sirve automáticamente en `/ui`.

---

## Correcciones que NO debes olvidar al migrar clases

### 1. Imports
```python
# V8.0 (global)
from config import BASE_PATH, LLM_CONFIG

# V9 (relativo al paquete)
from brain_v9.config import BASE_PATH, LLM_CONFIG
```

### 2. Modelo Ollama
```python
# V8.0 (roto — llama2 no existe)
"model": "llama2"

# V9 (correcto)
from brain_v9.config import OLLAMA_MODEL
"model": OLLAMA_MODEL   # qwen2.5:14b por defecto
```

### 3. Paths de secrets
```python
# V8.0 (hardcoded)
secrets_path = Path("C:/AI_VAULT/tmp_agent/Secrets/tiingo_access.json")

# V9 (configurable)
from brain_v9.config import SECRETS
secrets_path = SECRETS["tiingo"]
```

### 4. ClientSession
```python
# V8.0 en algunos lugares (roto)
def __init__(self):
    self.session = ClientSession()   # ← Error en aiohttp >= 3.9

# V9 (correcto — patrón lazy ya establecido)
async def _get_session(self) -> ClientSession:
    if self.session is None or self.session.closed:
        self.session = ClientSession(timeout=ClientTimeout(total=30))
    return self.session
```

---

## Cómo instalar y arrancar

```bash
# 1. Crear el paquete
cd C:\AI_VAULT\tmp_agent
mkdir brain_v9
# (copiar los archivos de este scaffold)

# 2. Crear __init__.py en cada subcarpeta
echo "" > brain_v9/__init__.py
echo "" > brain_v9/core/__init__.py
echo "" > brain_v9/brain/__init__.py
echo "" > brain_v9/agent/__init__.py
echo "" > brain_v9/trading/__init__.py
echo "" > brain_v9/autonomy/__init__.py
echo "" > brain_v9/ui/__init__.py

# 3. Variables de entorno (opcional)
set BRAIN_BASE_PATH=C:\AI_VAULT
set OLLAMA_MODEL=qwen2.5:14b
set OPENAI_API_KEY=sk-...          # si tienes
set ANTHROPIC_API_KEY=sk-ant-...   # si tienes

# 4. Arrancar
python -m brain_v9.main

# 5. Verificar
curl http://localhost:8090/health
# Debe retornar: {"status":"healthy","sessions":1,"version":"9.0.0"}

# 6. Probar chat con Ollama local
curl -X POST http://localhost:8090/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"hola","model_priority":"ollama"}'
```

---

## Por qué funciona esto y V8.0 no

| Problema V8.0              | Solución V9                              |
|----------------------------|------------------------------------------|
| 11,891 líneas en 1 archivo | ~200 líneas por módulo                   |
| ClientSession en __init__  | Lazy: creada en primera llamada async    |
| llama2 (no existe)         | qwen2.5:14b (disponible en tu Ollama)    |
| paths hardcoded Windows    | Variables de entorno + detección de OS   |
| HTML embebido en Python    | Archivos estáticos en `ui/`              |
| Startup bloquea servidor   | asynccontextmanager + background task    |
| /health siempre 200        | 503 mientras no esté listo               |
| Errores silenciosos        | Log crítico + _startup_error visible     |
