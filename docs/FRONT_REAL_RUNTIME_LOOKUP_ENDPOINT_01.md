# FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-01: Safe Read-Only Runtime Canary Lookup Router

**Status:** COMPLETE
**Date:** 2026-06-08
**Branch:** codex/own-capital-sustainable-return
**Head:** 199d1bf2

---

## 1. Objetivo

Crear un router FastAPI read-only real que exponga el adapter de canary lookup mediante un endpoint seguro sin modificar runtime productivo principal aún.

---

## 2. Alcance

- Router FastAPI APIRouter (`tmp_agent/brain_v9/routes/canary_lookup_read_only.py`).
- Endpoint GET `/brain/read-only/canary`.
- Import reutilizado del adapter de FRONT-REAL-READ-LOOKUP-ADAPTER-01 (`brain/semantic_memory_canary_lookup_read_only.py`).
- Test smoke con FastAPI/TestClient sin arrancar servidor real.
- Verificacion de hash antes/despues del test.

---

## 3. Out of Scope

- NO modificar `tmp_agent/brain_v9/main.py`.
- NO integrar todavía al runtime principal.
- NO escribir en `memory/semantic/semantic_memory.jsonl`.
- NO modificar FAISS.
- NO promover conocimiento.
- NO arrancar servidor real.
- NO hacer network externa.

---

## 4. Relacion con FRONT-REAL-READ-LOOKUP-ADAPTER-01

Reutiliza el adapter ya verificado sin necesidad de duplicar lógica. EL router solamente expone los resultados del adapter mediante HTTP GET.

---

## 5. Ubicacion del Router

```
tmp_agent/brain_v9/routes/canary_lookup_read_only.py
```

---

## 6. Endpoint Path

- **GET** `/brain/read-only/canary`
- **Returns:** JSON seguro con:
  - `status`: `"ok"`, `"not_found"`, `"invalid"`, `"error"`
  - `found`: bool
  - `count`: int
  - `line_number`: int
  - `total_lines`: int
  - `is_last_line`: bool
  - `validation`: dict
  - `errors`: list
  - `no_write`: always True
  - `faiss_used`: always False
  - `promotion`: always False
  - `record_summary`: dict con metadatos seguros (NOT full text)

---

## 7. Response Schema

Example de una respuesta exitosa:

```json
{
  "status": "ok",
  "found": true,
  "count": 1,
  "line_number": 1706,
  "total_lines": 1706,
  "is_last_line": true,
  "validation": {
    "valid": true,
    "errors": [],
    "required_keys_present": true
  },
  "errors": [],
  "no_write": true,
  "faiss_used": false,
  "promotion": false,
  "adapter": "brain.semantic_memory_canary_lookup_read_only",
  "endpoint": "/brain/read-only/canary",
  "record_summary": {
    "id": "canary-00000000-0000-0000-0000-000000000001",
    "kind": "canary",
    "source": "front_real_canary_exec_01",
    "created_utc": "2026-06-08T20:36:10Z",
    "metadata_flags": {
      "canary": true,
      "front": "FRONT-REAL-CANARY-EXEC-01",
      "single_record_canary": true,
      "faiss_write": false,
      "promotion": false,
      "patch_application": false,
      "trading": false,
      "b8": false
    }
  }
}
```

---

## 8. Error Modes

| Status | Cause | HTTP |
|---|---|---|
| ok | Canary found y valid | 200 |
| not_found | Canary not found | 200 |
| invalid | Canary found pero validation falla | 200 |
| error | Excepción inesperada | 200 |

---

## 9. Read-Only Guarantees

- Router does not write to memory/semantic.
- Solamente usa `open(path, "r")` dentro del adapter.
- No tiene funciones de escritura.
- No importa módulos de escritura.
- No depende de servidor activo.
- No usa puerto 8090.

---

## 10. No FAISS Guarantees

- No importa `faiss`.
- No abre archivos `memory/semantic/semantic_memory_faiss.*`.
- No ejecuta rebuild ni query de índice.
- `faiss_used` siempre `False`.

---

## 11. Why main.py is Not Modified

La integración al runtime principal requiere un frente separado por las siguientes razones:
- `tmp_agent/brain_v9/main.py` aparece como dirty file preexistente.
- Modificar `main.py` implica riesgo de alterar runtime productivo.
- Se necesita planificación de security review antes de integrar routers nuevos.
- Integración = cambio de producción => requiere front FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-INTEGRATION-01.

---

## 12. Integration Deferred

El router se incluirá en una instancia FastAPI separada (TestClient) para tests.
La inclusión en `main.py` está EXPLICITAMENTE DIFERIDA al siguiente frente.

---

## 13. Safety Flags

- materialization_allowed_now: false
- patch_generation_allowed_now: false
- memory_write_allowed: false
- faiss_write_allowed: false
- real_write_allowed: false
- promotion_allowed: false
- main_py_modified: false

---

## 14. Decision

RUNTIME_LOOKUP_ROUTER_READY

---

## 15. Recommended Next Front

FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-INTEGRATION-01 — integrar router de forma segura en main.py, review de seguridad y prueba de smoke.

Alternativa: FRONT-INFRA-04 — Dockerfile/container reproducibility.
