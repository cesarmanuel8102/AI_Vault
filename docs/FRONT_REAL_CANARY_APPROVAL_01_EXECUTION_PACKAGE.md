# FRONT-REAL-CANARY-APPROVAL-01: Single-Record Canary Execution Package

**Status:** APPROVAL PACKAGE ONLY — This document does NOT execute the canary write.
**Branch:** codex/own-capital-sustainable-return
**Date:** 2026-06-08
**Target Store:** `memory/semantic/semantic_memory.jsonl`
**Relates to:**
- [FRONT-REAL-CANARY-PLAN-01](FRONT_REAL_CANARY_PLAN_01_SINGLE_RECORD_CANARY.md)
- [FRONT-REAL-APPROVAL-01](FRONT_REAL_APPROVAL_01_OPERATOR_APPROVAL_GATE.md)
- [FRONT-REAL-PLAN-01](FRONT_REAL_PLAN_01_CONTROLLED_E2E_WRITE_PLAN.md)

---

## 1. Objetivo

Formalizar el paquete de aprobación para una futura ejecución canary de exactamente 1 record en el store de memoria semántica, con todas las compuertas de seguridad documentadas.

Este documento **no autoriza ni ejecuta el write**. Solo empaqueta los requisitos y blockers.

## 2. Alcance

- Definir el paquete canary como unidad de aprobación.
- Definir el target store exacto.
- Definir el record canary exacto propuesto.
- Documentar requisitos del token de aprobación.
- Documentar doble confirmación requerida.
- Documentar requisito de runtime detenido.
- Documentar requisito de git limpio.
- Documentar requisito de backup.
- Documentar requisito de hash antes y después.
- Documentar requisito de retrieval verification.
- Documentar requisito de rollback verification.
- Crear Go/No-Go checklist.
- Definir blockers explícitos.
- Definir evidence package requerida.

## 3. Out of Scope

- NO ejecutar el canary write.
- NO modificar `memory/semantic/semantic_memory.jsonl`.
- NO escribir en FAISS.
- NO modificar `tmp_agent/brain_v9/main.py`.
- NO modificar `tmp_agent/brain_v9/core/session.py`.
- NO modificar `brain/curated_runtime_lookup.py`.
- NO activar trading.
- NO tocar B8.
- NO aplicar patches.
- NO promover conocimiento.

## 4. Relación con FRONT-REAL-CANARY-PLAN-01

FRONT-REAL-CANARY-PLAN-01 definió:
- Target store: `memory/semantic/semantic_memory.jsonl`
- Canary record schema y ejemplo
- Backup, rollback, retrieval procedures
- Stop conditions y failure modes

FRONT-REAL-CANARY-APPROVAL-01 empaqueta todo eso como una unidad de aprobación formal.

## 5. Relación con FRONT-REAL-APPROVAL-01

FRONT-REAL-APPROVAL-01 formalizó:
- Token `BRAIN_APPROVAL_4D_DRY_GATE_TOKEN`
- Fail-closed behavior
- Doble confirmación requerida

Este paquete asegura que todas esas compuertas están documentadas como requisitos.

## 6. Target Store Exacto

```
memory/semantic/semantic_memory.jsonl
```

- Formato: JSONL (line-delimited JSON)
- Records existentes: 1705
- Keys por record: `created_utc`, `id`, `kind`, `metadata`, `session_id`, `source`, `text`

## 7. Canary Record Exacto Propuesto

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

**ESTE RECORD ESTÁ MARCADO COMO:**
- **NOT WRITTEN**
- **NOT EXECUTED**
- **FOR FUTURE APPROVAL ONLY**

## 8. Approval Token Requirement

- **Env var:** `BRAIN_APPROVAL_4D_DRY_GATE_TOKEN`
- **Valor:** Definido por operador humano en `.env`
- **Validación:** `hmac.compare_digest` (timing-safe)
- **Fail-closed:**
  - Vacio → BLOCKED
  - Ausente → BLOCKED
  - Invalido → BLOCKED

## 9. Doble Confirmación Requerida

### Confirmación 1 — Aprobación del Plan
- Operador revisa este paquete canary.
- Operador proporciona token de aprobación.
- Sistema valida token y precondiciones.

### Confirmación 2 — Pre-Execution
- Inmediatamente antes del append.
- Operador confirma:
  - Backup existe y hash coincide.
  - Runtime está detenido.
  - Git está limpio.
  - Target es `semantic_memory.jsonl`.
  - Solo 1 record será append.

Sin ambas confirmaciones: **BLOCKED**.

## 10. Runtime Stopped Requirement

- **Status:** Detenido.
- **Verification:** `curl http://127.0.0.1:8090/health` must fail.
- **Requerido:** Sí, obligatorio.

## 11. Git Clean Requirement

- **Status:** Sin staged files. Sin archivos modificados no autorizados.
- **Verification:** `git status --short` vacio (excepto memory/semantic preexistente dirty).
- **Requerido:** Sí, obligatorio.

## 12. Backup Requirement

- **Source:** `memory/semantic/semantic_memory.jsonl`
- **Destination:** `memory/semantic/semantic_memory.jsonl.backup_${BACKUP_TS}`
- **Verificación:**
  - `wc -l` source == `wc -l` backup
  - SHA256(source) == SHA256(backup)
- **Requerido:** Sí, antes de cualquier write.

## 13. Hash Before/After Requirement

### Before Write
- SHA256 del archivo target antes del append.
- Line count antes del append.
- Hash del record canary.

### After Write
- SHA256 del archivo target después del append.
- Line count después del append (debe ser +1).
- Retrieval verification: record presente.

### After Rollback
- SHA256 del archivo post-rollback == SHA256 del backup.
- Line count post-rollback == line count backup.
- Retrieval negativo: record ausente.

## 14. Retrieval Verification Requirement

1. Leer `memory/semantic/semantic_memory.jsonl` linea por linea.
2. Buscar `id: canary-00000000-0000-0000-0000-000000000001`.
3. Confirmar dict JSON coincide con canary propuesto.
4. Verificar SHA256(record.JSON_string) == expected_hash.
5. Verificar `wc -l` después del append == `wc -l` antes + 1.

## 15. Rollback Verification Requirement

1. Reemplazar `semantic_memory.jsonl` con backup.
2. Verificar `wc -l` post-rollback == `wc -l` backup.
3. Verificar SHA256 post-rollback == SHA256 backup.
4. Verificar record canary **ya NO existe**.
5. Verificar `wc -l` post-rollback == `wc -l` antes del append.

## 16. Go/No-Go Checklist

| # | Check | Go | No-Go |
|---|---|---|---|
| 1 | Token configurado y valido | ✅ | ❌ |
| 2 | Git working tree limpio | ✅ | ❌ |
| 3 | Runtime detenido | ✅ | ❌ |
| 4 | Backup creado y verificado | ✅ | ❌ |
| 5 | Preflight snapshot aprobado | ✅ | ❌ |
| 6 | Authorization packet generado | ✅ | ❌ |
| 7 | Confirmacion 1 recibida | ✅ | ❌ |
| 8 | Confirmacion 2 recibida | ✅ | ❌ |
| 9 | Hash antes registrado | ✅ | ❌ |
| 10 | Hash record canary registrado | ✅ | ❌ |
| 11 | Retrieval verification planeado | ✅ | ❌ |
| 12 | Rollback verification planeado | ✅ | ❌ |

## 17. Explicit Blockers

- Token no configurado o vacío.
- Backup no creado o verificación falla.
- Runtime activo.
- Git dirty (staged/modified no autorizados).
- Falta confirmación 1 o 2.
- Preflight snapshot con blockers.
- Go/No-Go checklist con blockers.

## 18. Evidence Package Required Before Future Execution

Before any future FRONT-REAL-CANARY-EXEC-01 (or similar), must produce:
1. Token configured (without showing value).
2. First confirmation registered.
3. Backup created and verified.
4. Preflight snapshot passed.
5. Go/No-Go checklist approved.
6. Authorization packet generated.
7. Second confirmation registered.
8. Retrieval verification passed.
9. Rollback verification passed.
10. Evidence files:
    - `tmp_agent/front_real_canary_approval_01/test_results.txt`
    - `tmp_agent/front_real_canary_approval_01/security_check.json`
    - `tmp_agent/front_real_canary_approval_01/no_mutation_validation.json`

## 19. Ledger Requirements

Before cualquier ejecutión real:
- `ROADMAP_STATUS.json`: `last_applied_checkpoint: FRONT-REAL-CANARY-EXEC-01`.
- `docs/MIGRATION_CONTROL_LEDGER.md`: entrada FRONT-REAL-CANARY-EXEC-01.
- `FRONT-REAL-CANARY-APPROVAL-01` en `completed_fronts`.

## 20. Safety Flags

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

## 21. Future Execution Front Required

Execution of the canary write requires a separate future front, such as:
- **FRONT-REAL-CANARY-EXEC-01** — Single-record canary execution
- This future front must satisfy all requirements in this approval package.

## 22. Declaración Expícita

> **This approval package does not execute the canary write.**
>
> Ejecution del canary write requiere:
> 1. Un frente futuro separado (FRONT-REAL-CANARY-EXEC-01 o similar)
> 2. Aprobación de operador humano en dos gates
> 3. Runtime detenido
> 4. Git working tree limpio
> 5. Backup real creado y verificado
> 6. Todos los preflights aprobados
> 7. Retrieval verification post-write
> 8. Rollback verification demostrada
>
> Until a future front is explicitly approved, **no real write is permitted**.
