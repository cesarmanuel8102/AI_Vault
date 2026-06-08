# FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-INTEGRATION-01: Integrate Safe Read-Only Canary Router into Main App

**Status:** COMPLETE ✅  
**Date:** 2026-06-08  
**Branch:** codex/own-capital-sustainable-return  
**Front ID:** FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-INTEGRATION-01  

---

## 1. Objetivo

Integrar el router read-only `canary_lookup_read_only` en la app FastAPI principal `tmp_agent/brain_v9/main.py` para exponer el endpoint `GET /brain/read-only/canary` desde el runtime principal.

## 2. Alcance

- Importar `canary_lookup_read_only_router` en `main.py`
- Incluir router con `app.include_router(canary_lookup_read_only_router)`
- Validar que el endpoint responde correctamente vía TestClient
- Documentar el cambio

## 3. Out of Scope

- No modificar endpoints existentes
- No modificar middleware, auth, o security
- No modificar session.py
- No modificar memory/semantic/semantic_memory.jsonl
- No modificar FAISS
- No ejecutar runtime real (puerto 8090)
- No hacer promotion o patch application
- No tocar trading/B8/Docker/network/install/.env

## 4. Router Integrado

| Campo | Valor |
|---|---|
| Router file | `tmp_agent/brain_v9/routes/canary_lookup_read_only.py` |
| Import line | `from brain_v9.routes.canary_lookup_read_only import router as canary_lookup_read_only_router` |
| Include line | `app.include_router(canary_lookup_read_only_router)` |
| Endpoint | `GET /brain/read-only/canary` |

## 5. Main.py Change Summary

```python
# Added import (line ~169)
from brain_v9.routes.canary_lookup_read_only import router as canary_lookup_read_only_router

# Added include_router (line ~175)
app.include_router(canary_lookup_read_only_router)
```

**Cambio mínimo y seguro.** Solo 2 líneas agregadas.

## 6. Endpoint Path

- **URL:** `GET /brain/read-only/canary`
- **Respuesta:** JSON con canary record (sin full text)
- **Status esperado:** 200
- **Found:** True
- **Count:** 1
- **Validation:** valid=True

## 7. Runtime Behavior Expected

Cuando el runtime principal arranque, el endpoint estará disponible en:
`http://localhost:8090/brain/read-only/canary`

No requiere reinicio especial ni configuración adicional.

## 8. Read-Only Guarantees

- Endpoint solo expone GET
- No escribe en memory/semantic/semantic_memory.jsonl
- No modifica FAISS
- No ejecuta promotion
- No ejecuta patch application
- No requiere arranque de servidor en este front

## 9. No FAISS Guarantees

- Router no importa FAISS
- Respuesta incluye `faiss_used: false`
- Respuesta incluye `no_write: true`

## 10. Test Strategy

- TestClient desde FastAPI (no servidor real)
- Validar import de app
- Validar import de router
- Validar que main.py contiene import e include
- Validar que TestClient responde 200
- Validar canary found=True
- Validar no_write=True
- Validar faiss_used=False
- Validar que semantic_memory.jsonl hash no cambió
- Validar que FAISS hashes no cambiaron

## 11. Safety Flags

- `materialization_allowed_now`: false
- `patch_generation_allowed_now`: false
- `memory_write_allowed`: false
- `faiss_write_allowed`: false
- `real_write_allowed`: false
- `promotion_allowed`: false
- `runtime_started`: false (en este front)
- `integration_only`: true
- `no_mutations`: true

## 12. Recommended Next Front

**FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-LIVE-SMOKE-01** — local runtime smoke para endpoint integrado

---

## Decision

**RUNTIME_LOOKUP_ENDPOINT_INTEGRATED**

Endpoint `GET /brain/read-only/canary` ahora está montado en la app principal y listo para ser servido por el runtime en puerto 8090.

---

*Endpoint is now mounted into main app.*
*Integration only exposes GET /brain/read-only/canary.*
*Endpoint does not write memory.*
*Endpoint does not import FAISS.*
*Endpoint does not promote knowledge.*
*Runtime real smoke is deferred to a separate front.*
