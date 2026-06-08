# FRONT-REAL-READ-LOOKUP-ADAPTER-01: Read-Only Canary Lookup Adapter

**Status:** COMPLETE
**Date:** 2026-06-08
**Branch:** codex/own-capital-sustainable-return
**Head:** a5565fb4

---

## 1. Objetivo

Implementar una capacidad real y util: un adapter read-only que pueda localizar y validar el canary directamente desde `memory/semantic/semantic_memory.jsonl`.

---

## 2. Alcance

- Módulo Python real (`brain/semantic_memory_canary_lookup_read_only.py`) que solo lee el archivo JSONL.
- Funciones claras e importables.
- Tests smoke que verifican el comportamiento real sin mutar datos.
- Verificacion de hash antes/despues del adapter.
- Documento de uso.

---

## 3. Out of Scope

- NO escribir en `memory/semantic/semantic_memory.jsonl`.
- NO modificar FAISS ni archivos de índice.
- NO promover conocimiento.
- NO aplicar patches.
- NO tocar trading/B8.
- NO arrancar servidor.

---

## 4. Relacion con FRONT-REAL-READ-VERIFY-01

La decision de FRONT-REAL-READ-VERIFY-01 (`NEED_READ_ONLY_LOOKUP_ADAPTER`) motivo este frente. Normbramos un adapter aislado para cumplir esa necesidad.

---

## 5. Ubicacion del Adapter

```
brain/semantic_memory_canary_lookup_read_only.py
```

---

## 6. API del Adapter

### `lookup_canary_record(target_path, canary_id)`

Devuelve dict con:

| Campo | Tipo | Descripcion |
|---|---|---|
| `found` | bool | Si se encontro o no |
| `count` | int | Veces encontrado |
| `line_number` | int | Numero de linea en JSONL |
| `total_lines` | int | Total de lineas en el archivo |
| `is_last_line` | bool | Si el canary esta al final |
| `record` | dict | El record del canary hallado |
| `validation` | dict | Resultado de `validate_canary_record()` |
| `no_write` | bool | Siempre True |
| `faiss_used` | bool | Siempre False |
| `errors` | list | Lista de errores, vacia cuando `found=True` y `count=1` |

### `validate_canary_record(record)`

Valida estructura del canary:

| Campo | Tipo | Descripcion |
|---|---|---|
| `valid` | bool | Si pasa todas las validaciones |
| `errors` | list | Claves fallidas, vacia si `valid=True` |
| `required_keys_present` | bool | Si existe `created_utc`, `id`, `kind`, `metadata`, `session_id`, `source`, `text` |

### `hash_file(path)`

Devuelve SHA-256 del archivo sin escribir.

---

## 7. Garantias Read-Only

- El adapter solo usa `open(path, "r", encoding="utf-8")`.
- No abre archivos para escritura ni append.
- No modifica Python `sys.modules`.
- No invoca FAISS.
- No depende de red.
- No accede al runtime.

## 8. Garantias de No FAISS

- No importa `faiss`.
- No toca path `memory/semantic/semantic_memory_faiss.*`.
- No ejecute operacion de rebuild, add, o query de indice.
- `faiss_used` en resultado es siempre `False`.

## 9. Resultado Canary Lookup Esperado

```python
from brain.semantic_memory_canary_lookup_read_only import lookup_canary_record

res = lookup_canary_record()
assert res["found"] is True
assert res["count"] == 1
assert res["is_last_line"] is True
assert res["validation"]["valid"] is True
assert res["no_write"] is True
assert res["faiss_used"] is False
assert res["errors"] == []
```

## 10. Modos de Fallo

| Error | Causa | Resultado |
|---|---|---|
| target_missing | Archivo no existe | found=False, errors=["target_missing"] |
| invalid_jsonl | Linea JSONL corrupta | found=False, errors=["invalid_jsonl"] |
| duplicate_canary | ID repetido | found=True, count>1, errors=["duplicate_canary"] |
| id_mismatch | ID distinta al esperado | validation.errors=["id_mismatch"] |
| kind_not_canary | kind != "canary" | validation.errors=["kind_not_canary"] |

## 11. Safety Flags

- materialization_allowed_now: false
- patch_generation_allowed_now: false
- memory_write_allowed: false
- faiss_write_allowed: false
- real_write_allowed: false
- promotion_allowed: false

## 12. Recommended Next Front

FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-PLAN-01 — expose adapter through safe read-only runtime endpoint.
Alternativa: FRONT-INFRA-04 — Dockerfile/container reproducibility.
