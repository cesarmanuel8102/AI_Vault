# FRONT-BRAIN-OLLAMA-CONFIG-HARDCODE-AUDIT-11D-A

## Executive verdict

```
FRONT-BRAIN-OLLAMA-CONFIG-CENTRALIZATION-11D:
NO-GO / SCOPE EXPANDED / NO COMMIT
```

11D fue intentado como microfix para centralizar el endpoint de Ollama hacia
`API_ENDPOINTS["ollama"]` en `brain_v9/config.py`. El intento resultó en
**NO-GO** porque los hardcodes de Ollama (`localhost:11434` /
`127.0.0.1:11434`) están repartidos en **más de 5 archivos productivos**,
incluyendo áreas bloqueadas como `session.py` y
`trading/qc_iteration_engine.py`.

Un microfix que toca `session.py` o `trading/` viola las restricciones de
no-touch de los frentes B7-STRANGLER y trading/QC/IBKR. Por lo tanto, 11D
no puede ejecutarse como un solo frente seguro.

El intento parcial fue **revertido completamente**. El estado del repo fue
restaurado a `efd8cab` con tracked diff vacío y staged vacío.

Esta auditoría es **docs-only**: no toca runtime, tests, workflows ni
archivos productivos.

## Base state

| Campo | Valor |
|-------|-------|
| Repo | `C:\AI_VAULT_CANONICAL` |
| Branch | `codex/own-capital-sustainable-return` |
| HEAD esperado | `efd8cab` |
| origin esperado | `efd8cab` |
| Último frente cerrado | 11C (FRONT-BRAIN-AUTONOMY-E2E-MEMORY-TOOL-FALLBACK-11C) |
| Intento 11D previo | NO-GO / revertido |
| Tracked diff | vacío |
| Staged diff | vacío |
| Untracked preexistentes | no tocados |

## Canonical source

El endpoint canónico de Ollama debe definirse en un único lugar:

**Archivo:** `tmp_agent/brain_v9/config.py`

```python
API_ENDPOINTS = {
    ...
    "ollama": os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat"),
    ...
}

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    API_ENDPOINTS["ollama"].replace("/api/chat", "").rstrip("/"),
)
```

Reglas canónicas:

1. `API_ENDPOINTS["ollama"]` es la **fuente canónica** para el endpoint
   `/api/chat` de Ollama.
2. `OLLAMA_BASE_URL` debe **derivarse** de `API_ENDPOINTS["ollama"]`
   (no ser independiente).
3. Ningún archivo productivo debe definir su propio
   `API_ENDPOINTS = {"ollama": "http://..."}` como fallback inline.
4. Ningún archivo productivo debe hardcodear `localhost:11434` o
   `127.0.0.1:11434` directamente en llamadas HTTP.
5. Los archivos productivos deben importar `API_ENDPOINTS` desde
   `brain_v9.config` y usar `API_ENDPOINTS["ollama"]`.

## Productive hardcodes under tmp_agent/brain_v9

Los siguientes archivos productivos contienen hardcodes de Ollama detectados
mediante `git grep` read-only:

### 1. `tmp_agent/brain_v9/brain/codegen.py`

- **Línea 26:** fallback `except Exception:` define
  `API_ENDPOINTS = {"ollama": "http://localhost:11434/api/chat"}`
- **Línea 106:** llamada con fallback inline:
  `API_ENDPOINTS.get("ollama", "http://localhost:11434/api/chat")`
- **Clasificación:** PRODUCTIVE_HARDCODE
- **Riesgo:** medium — el fallback inline duplica el endpoint canónico y
  puede divergir si `config.py` cambia.

### 2. `tmp_agent/brain_v9/brain/health.py`

- **Línea 32:** URL hardcodeada inline:
  `"url": "http://127.0.0.1:11434/api/tags"`
- **Clasificación:** PRODUCTIVE_HARDCODE
- **Riesgo:** low/medium — health check usa `/api/tags` (no `/api/chat`),
  por lo que no deriva directamente de `API_ENDPOINTS["ollama"]`; requiere
  `OLLAMA_BASE_URL + "/api/tags"`.

### 3. `tmp_agent/brain_v9/core/self_diagnostic.py`

- **Línea 217:** URL hardcodeada inline:
  `async with session.get("http://localhost:11434/api/tags")`
- **Clasificación:** PRODUCTIVE_HARDCODE
- **Riesgo:** low/medium — diagnóstico usa `/api/tags` (no `/api/chat`).

### 4. `tmp_agent/brain_v9/core/session.py`

- **Línea 1080:** string de mensaje de error hardcodea la URL:
  `f"Proxima accion: verificar que Ollama este corriendo en 127.0.0.1:11434, "`
- **Clasificación:** BLOCKED_SESSION
- **Riesgo:** high — `session.py` está bajo refactor B7-STRANGLER activo;
  cualquier cambio requiere parity tests dedicados y no debe mezclarse con
  microfixes de configuración.

### 5. `tmp_agent/brain_v9/core/agent_kernel_v2/capability_registry.py`

- **Línea 14:** fallback `except Exception:` define
  `API_ENDPOINTS = {"ollama": "http://127.0.0.1:11434/api/chat"}`
- **Clasificación:** PRODUCTIVE_HARDCODE
- **Riesgo:** medium — el fallback puede divergir del endpoint canónico.

### 6. `tmp_agent/brain_v9/core/agent_kernel_v2/finalizer.py`

- **Línea 11:** fallback `except Exception:` define
  `API_ENDPOINTS = {"ollama": "http://127.0.0.1:11434/api/chat"}`
- **Clasificación:** PRODUCTIVE_HARDCODE
- **Riesgo:** medium — el fallback puede divergir del endpoint canónico.

### 7. `tmp_agent/brain_v9/core/agent_kernel_v2/intent_classifier.py`

- **Línea 16:** fallback `except Exception:` define
  `API_ENDPOINTS = {"ollama": "http://127.0.0.1:11434/api/chat"}`
- **Clasificación:** PRODUCTIVE_HARDCODE
- **Riesgo:** medium — el fallback puede divergir del endpoint canónico.

### 8. `tmp_agent/brain_v9/trading/qc_iteration_engine.py`

- **Línea 260:** URL hardcodeada inline:
  `async with session.post("http://localhost:11434/api/generate", json=payload)`
- **Clasificación:** BLOCKED_TRADING
- **Riesgo:** blocked — trading/QC/IBKR está fuera de scope para todos los
  frentes no-trading. No se toca hasta que la roadmap de trading se reabra.

### 9. `tmp_agent/brain_v9/core/semantic_memory_faiss.py` (ya parcialmente centralizado)

- **Línea 48:** `OLLAMA_URL = OLLAMA_BASE_URL or API_ENDPOINTS.get("ollama", "http://localhost:11434/api/chat").replace("/api/chat", "")`
- **Clasificación:** PRODUCTIVE_HARDCODE (con fallback residual)
- **Riesgo:** low — ya importa `OLLAMA_BASE_URL` y `API_ENDPOINTS` desde
  config; el hardcode `http://localhost:11434` aparece sólo como fallback
  final en `.get()`. No prioritario.

### 10. `tmp_agent/ui_proxy_server.py`

- **Línea 10:** `OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434").rstrip("/")`
- **Clasificación:** PRODUCTIVE_HARDCODE
- **Riesgo:** low — proxy UI con fallback de env var; no está bajo
  `brain_v9/` pero usa el mismo endpoint. Prioridad baja.

### Otros (no productivos — no requieren split)

- `docs/` — DOC_ONLY (documentación histórica, no runtime).
- `tests/smoke/test_front_brain_provider_centralization_01.py` — TEST_STATIC_GUARD (guardias que niegan hardcodes; no se tocan).
- `tmp_agent/brain_v9/.env.bat.backup_*` — LEGACY_ARCHIVE (backup de env).
- `tmp_agent/staging/chg_*` — LEGACY_ARCHIVE (staging histórico).
- `tmp_agent/brain_v9/config.py.bak` / `core/llm.py.bak.*` — LEGACY_ARCHIVE (backups).
- `tmp_agent/dashboard_v2_r105_audit_evidence/dashboard_file_inventory.json` — LEGACY_ARCHIVE (evidence dump).
- `tmp_agent/front_brain_agent_v2_*/` — LEGACY_ARCHIVE (evidence/reportes de frentes cerrados).
- `tmp_agent/iniciar_como_admin.ps1` / `emergency_start.ps1` — ops scripts (no Python productivo brain_v9).
- `tmp_agent/external_intel/github/microsoft_autogen/` — external reference snippet (no nuestro código).

## Risk classification

| File | Classification | Risk | Recommended handling |
|------|---------------|------|---------------------|
| `brain/codegen.py` | PRODUCTIVE_HARDCODE | medium | 11D-B safe batch |
| `brain/health.py` | PRODUCTIVE_HARDCODE | low/medium | 11D-B safe batch |
| `core/self_diagnostic.py` | PRODUCTIVE_HARDCODE | low/medium | 11D-B safe batch |
| `core/agent_kernel_v2/capability_registry.py` | PRODUCTIVE_HARDCODE | medium | 11D-B safe batch |
| `core/agent_kernel_v2/finalizer.py` | PRODUCTIVE_HARDCODE | medium | 11D-B safe batch |
| `core/agent_kernel_v2/intent_classifier.py` | PRODUCTIVE_HARDCODE | medium | 11D-B safe batch |
| `core/semantic_memory_faiss.py` | PRODUCTIVE_HARDCODE (residual fallback) | low | 11D-B safe batch (opcional) |
| `ui_proxy_server.py` | PRODUCTIVE_HARDCODE | low | 11D-B safe batch (opcional) |
| `core/session.py` | BLOCKED_SESSION | high | defer to 11D-C |
| `trading/qc_iteration_engine.py` | BLOCKED_TRADING | blocked | defer until trading roadmap reopens |

## Required split

### 11D-B — safe productive batch

**Scope:**
- `tmp_agent/brain_v9/brain/codegen.py`
- `tmp_agent/brain_v9/brain/health.py`
- `tmp_agent/brain_v9/core/self_diagnostic.py`
- `tmp_agent/brain_v9/core/agent_kernel_v2/capability_registry.py`
- `tmp_agent/brain_v9/core/agent_kernel_v2/finalizer.py`
- `tmp_agent/brain_v9/core/agent_kernel_v2/intent_classifier.py`
- `tmp_agent/brain_v9/core/semantic_memory_faiss.py` (opcional — fallback residual)
- `tmp_agent/ui_proxy_server.py` (opcional — proxy UI)

**Rules:**
- No `session.py`.
- No `trading/`.
- No SCVL.
- No memory/semantic runtime data.
- No FAISS rebuild.
- No runtime calls (sólo refactor de imports/constantes).
- No servers arrancados.
- Los fallbacks `except Exception:` que definen `API_ENDPOINTS` inline deben
  eliminarse y reemplazarse por import directo desde `brain_v9.config`.
- Los hardcodes inline `http://localhost:11434` / `http://127.0.0.1:11434`
  deben reemplazarse por `API_ENDPOINTS["ollama"]` o `OLLAMA_BASE_URL`.
- Para endpoints `/api/tags` y `/api/generate`, derivar desde
  `OLLAMA_BASE_URL + "/api/tags"` o `OLLAMA_BASE_URL + "/api/generate"`.
- Tests de guardia (`test_front_brain_provider_centralization_01.py`) deben
  seguir pasando.

### 11D-C — session-specific batch

**Scope:**
- `tmp_agent/brain_v9/core/session.py`

**Rules:**
- Dedicated parity tests required (behavioral parity contra parent commit).
- No opportunistic edits.
- No broad session refactor.
- Sólo reemplazar el string hardcode de `127.0.0.1:11434` en línea 1080 por
  una referencia derivada de `OLLAMA_BASE_URL` o `API_ENDPOINTS`.
- Debe ejecutarse como frente separado con su propio commit y CI.

### 11D-D — trading blocked batch

**Scope:**
- `tmp_agent/brain_v9/trading/qc_iteration_engine.py`

**Rules:**
- Defer hasta que la roadmap de trading/QC/IBKR se reabra.
- No tocar durante frentes non-trading.
- Cuando se habilite, reemplazar `http://localhost:11434/api/generate` por
  `OLLAMA_BASE_URL + "/api/generate"` o `API_ENDPOINTS["ollama"]` derivado.

## No-touch confirmation

Esta auditoría **no toca**:

- SCVL gates
- Semantic promotion logic
- Memory/semantic runtime data
- FAISS runtime
- Curated ingestion/promotion
- `dry_run_only`
- Rooms
- `session.py`
- Trading/QC/IBKR
- Dashboard
- `main.py` routers
- Tests
- Workflows
- Runtime Python productivo

Único archivo creado: `docs/audit/OLLAMA_CONFIG_HARDCODE_AUDIT_11D_A.md`

## Next recommended front

```
FRONT-BRAIN-OLLAMA-CONFIG-CENTRALIZATION-SAFE-BATCH-11D-B
```

Frente seguro con scope limitado a los 6-8 archivos productivos no
bloqueados. No toca `session.py` ni `trading/`.