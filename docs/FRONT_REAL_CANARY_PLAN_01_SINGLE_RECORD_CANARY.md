# FRONT-REAL-CANARY-PLAN-01: Single-Record Canary Execution Plan

**Status:** CANARY PLAN ONLY — This document does NOT execute the write.  
**Branch:** codex/own-capital-sustainable-return  
**Date:** 2026-06-08  
**Target Store:** `memory/semantic/semantic_memory.jsonl`  
**Relates to:** [FRONT-REAL-PLAN-01](FRONT_REAL_PLAN_01_CONTROLLED_E2E_WRITE_PLAN.md), [FRONT-REAL-APPROVAL-01](FRONT_REAL_APPROVAL_01_OPERATOR_APPROVAL_GATE.md)

---

## 1. Objetivo

Diseñar un plan canary para una futura escritura real controlada de exactamente 1 record en el store de memoria semántica, con backup previo, doble aprobación humana, retrieval verification, y rollback verification.

**Este documento es solo un plan. NO ejecuta el write.**

## 2. Alcance

- Definir el record canary exacto.
- Definir el target store exacto.
- Definir precondiciones.
- Definir requisitos de aprobación humana.
- Definir procedimiento de backup.
- Definir verificación de hash antes del write.
- Definir procedimiento de append de 1 línea JSONL.
- Definir retrieval verification.
- Definir rollback verification.
- Definir verificación de hash después del rollback.
- Definir requisitos de evidence.
- Definir requisitos de ledger.
- Definir condiciones de parada.
- Definir modos de fallo.

## 3. Out of Scope

- NO ejecutar el write.
- NO modificar `memory/semantic/semantic_memory.jsonl`.
- NO escribir en FAISS.
- NO modificar `tmp_agent/brain_v9/main.py`.
- NO modificar `tmp_agent/brain_v9/core/session.py`.
- NO modificar `brain/curated_runtime_lookup.py`.
- NO activar trading.
- NO tocar B8.
- NO aplicar patches.
- NO promover conocimiento.

## 4. Relación con FRONT-REAL-PLAN-01

FRONT-REAL-PLAN-01 definio el ciclo controlado:
- Target: `memory/semantic/semantic_memory.jsonl`
- Backup, rollback, retrieval verification
- Single-record limit

FRONT-REAL-CANARY-PLAN-01 especifica el primer record concreto que se usaria en ese ciclo.

## 5. Relación con FRONT-REAL-APPROVAL-01

FRONT-REAL-APPROVAL-01 formalizo la compuerta de aprobacion:
- Token `BRAIN_APPROVAL_4D_DRY_GATE_TOKEN`
- Fail-closed behavior
- Doble confirmacion requerida

Este plan canary requiere que todas esas compuertas esten pasadas.

## 6. Target Store Exacto

```
memory/semantic/semantic_memory.jsonl
```

- Formato: JSONL (line-delimited JSON)
- Records existentes: 1705
- Keys por record: `created_utc`, `id`, `kind`, `metadata`, `session_id`, `source`, `text`
- Append-only: nueva linea al final

## 7. Canary Record Schema

| Field | Type | Description |
|---|---|---|
| `created_utc` | string (ISO8601) | Timestamp UTC del record |
| `id` | string (UUID v4) | ID unico del canary |
| `kind` | string enum | Tipo: `canary` |
| `metadata` | object | `{canary: true, approved_by, front, insertion_timestamp}` |
| `session_id` | string or null | Session reference |
| `source` | string | Identificador de fuente (`canary_test`) |
| `text` | string | Payload del canary |

## 8. Canary Record Ejemplo

```json
{
  "created_utc": "2026-06-08T00:00:00Z",
  "id": "canary-00000000-0000-0000-0000-000000000001",
  "kind": "canary",
  "metadata": {
    "canary": true,
    "approved_by": "operator_human",
    "front": "FRONT-REAL-CANARY-PLAN-01",
    "insertion_timestamp": "2026-06-08T00:00:00Z"
  },
  "session_id": null,
  "source": "canary_test",
  "text": "Canary record for controlled write verification. DO NOT write this record without approval."
}
```

**IMPORTANTE:** Este record es un ejemplo y plan. **NO se debe escribir sin aprobacion explicita.**

## 9. Preconditions

| # | Precondition | Verification |
|---|---|---|
| 1 | Token configurado | `BRAIN_APPROVAL_4D_DRY_GATE_TOKEN` en `.env` |
| 2 | Git working tree limpio | `git status --short` vacio (excepto memory/semantic preexistente) |
| 3 | Runtime detenido | `curl http://127.0.0.1:8090/health` debe fallar |
| 4 | Backup creado y verificado | `wc -l` + `sha256sum` coinciden |
| 5 | Preflight snapshot aprobado | Readiness gate `READY_BLOCKED` con blockers vacios |
| 6 | Go/No-Go checklist aprobado | Sin blockers |
| 7 | Authorization packet generado | Human intent confirmado |

## 10. Human Approval Requirements

### Confirmacion 1 — Aprobacion del Plan
- Operador revisa este documento canary.
- Operador confirma que el record ejemplo es el target correcto.
- Operador proporciona token de aprobacion.
- Sistema valida token y precondiciones.

### Confirmacion 2 — Pre-Execution
- Inmediatamente antes del `append`.
- Operador confirma:
  - Backup existe y hash coincide.
  - Runtime esta detenido.
  - Git esta limpio.
  - Target es `semantic_memory.jsonl`.
  - Solo 1 record sera append.

Sin ambas confirmaciones: **BLOCKED**.

## 11. Backup Procedure

1. **Timestamp:** `BACKUP_TS=$(date +%Y%m%d_%H%M%S)`
2. **Source:** `memory/semantic/semantic_memory.jsonl`
3. **Destination:** `memory/semantic/semantic_memory.jsonl.backup_${BACKUP_TS}`
4. **Hash before backup:**
   ```bash
   SHA256_BEFORE=$(sha256sum memory/semantic/semantic_memory.jsonl | awk '{print $1}')
   cp memory/semantic/semantic_memory.jsonl memory/semantic/semantic_memory.jsonl.backup_${BACKUP_TS}
   SHA256_BACKUP=$(sha256sum memory/semantic/semantic_memory.jsonl.backup_${BACKUP_TS} | awk '{print $1}')
   assert "${SHA256_BEFORE}" == "${SHA256_BACKUP}"
   ```
5. **Line count verify:** `wc -l` source == `wc -l` backup

## 12. Hash Verification Before Write

Antes del append, calcular y registrar:
- SHA256 del archivo target antes del append.
- Line count antes del append.
- Hash del record canary.

## 13. Single Append Procedure

1. Verificar todas las precondiciones.
2. Verificar todas las confirmaciones.
3. Verificar backup creado y hasheado.
4. Abrir `memory/semantic/semantic_memory.jsonl` en modo append.
5. Escribir el record canary como **exactamente 1 linea JSON** (no pretty-printed).
6. `file.flush()`
7. `os.fsync()`
8. Cerrar archivo.

## 14. Retrieval Verification

1. Leer `memory/semantic/semantic_memory.jsonl` linea por linea.
2. Buscar `id: canary-00000000-0000-0000-0000-000000000001`.
3. Confirmar que el dict JSON coincide con el canary planeado.
4. Verificar que `sha256(record.JSON_string) == expected_hash`.
5. Verificar que `wc -l` despues del append == `wc -l` antes + 1.

## 15. Rollback Verification

1. Reemplazar `memory/semantic/semantic_memory.jsonl` con backup.
2. Verificar `wc -l` despues del rollback == `wc -l` backup.
3. Verificar `sha256sum` despues del rollback == `sha256sum` backup.
4. Verificar que el record canary **ya NO existe** en el archivo.
5. Verificar que `wc -l` despues del rollback == `wc -l` antes del append.

## 16. Hash Verification After Rollback

- `sha256_post_rollback == sha256_before_backup`
- `line_count_post_rollback == line_count_before_backup`

## 17. Evidence Requirements

- Backup path y hash registrados.
- Hash antes del append registrado.
- Hash del record canary registrado.
- Hash despues del append registrado.
- Retrieval verification registrado.
- Rollback hash registrado.
- Hash despues del rollback registrado.
- Evidence files:
  - `tmp_agent/front_real_canary_plan_01/test_results.txt`
  - `tmp_agent/front_real_canary_plan_01/security_check.json`
  - `tmp_agent/front_real_canary_plan_01/no_mutation_validation.json`

## 18. Ledger Requirements

Antes de cualquier ejecucion real:
- `ROADMAP_STATUS.json`: `last_applied_checkpoint: FRONT-REAL-CANARY-APPROVAL-01`.
- `docs/MIGRATION_CONTROL_LEDGER.md`: entrada FRONT-REAL-CANARY-APPROVAL-01.
- `FRONT-REAL-CANARY-PLAN-01` en `completed_fronts`.

## 19. Stop Conditions

- Token no configurado o vacio.
- Backup no creado o hash no coincide.
- Runtime activo.
- Git dirty (staged/modified no autorizados).
- Falta confirmacion 1 o 2.
- Preflight snapshot con blockers.
- Go/No-Go checklist con blockers.
- Operador cancela.
- Append falla (excepcion de I/O).
- Retrieval verification falla.
- Rollback verification falla.
- Hash post-rollback no coincide con pre-backup.

## 20. Failure Modes

| Modo | Deteccion | Accion |
|---|---|---|
| Backup falla | Hash mismatch backup vs source | Abortar, no escribir |
| Append falla | Excepcion de I/O | Abortar, restaurar backup si es necesario |
| Retrieval falla | Record no encontrado post-write | Rollback inmediato |
| Rollback falla | Hash post-rollback no coincide con backup | Alerta critica, intervencion manual |
| Runtime activo | Health endpoint responde | Abortar |
| Git dirty | Staged/modified files | Abortar |
| Token ausente | BRAIN_APPROVAL_4D_DRY_GATE_TOKEN vacio | Abortar, fail-closed |
| Hash mismatch pre/post | SHA256 no coincide | Abortar, no escribir |
| Line count mismatch | wc -l no esperado | Abortar, no escribir |

## 21. Safety Flags

- `materialization_allowed_now: false`
- `patch_file_creation_allowed_now: false`
- `git_apply_allowed_now: false`
- `target_file_modification_allowed_now: false`
- `patch_generation_allowed_now: false`
- `diff_generation_allowed_now: false`
- `patch_application_allowed_now: false`
- `real_patch_application_allowed_now: false`
- `patches_generated_for_application: false`
- `patches_applied: false`
- `patches_staged: false`
- `memory_write_allowed: false`
- `faiss_write_allowed: false`
- `real_write_allowed: false`
- `promotion_allowed: false`
- `must_not_create_patch_files: true`
- `must_not_run_git_apply: true`
- `must_not_modify_target_files: true`

## 22. Declaracion Explicita

> **This canary plan does not execute the write.**
>
> Execution of the canary write requires:
> 1. A separate future front: FRONT-REAL-CANARY-APPROVAL-01
> 2. Human operator approval at two distinct gates
> 3. Runtime stopped
> 4. Clean git working tree
> 5. Real backup created and verified
> 6. All preflight tests passing
> 7. Retrieval verification post-write
> 8. Rollback verification demonstrated
>
> Until FRONT-REAL-CANARY-APPROVAL-01 is completed and explicitly approved, **no real write is permitted**.
