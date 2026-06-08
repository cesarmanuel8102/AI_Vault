# FRONT-REAL-PLAN-01: Controlled Real E2E Write Plan

**Status:** PLAN ONLY — This document does NOT authorize execution.  
**Branch:** codex/own-capital-sustainable-return  
**Date:** 2026-06-08  
**Target Store:** `memory/semantic/semantic_memory.jsonl` (JSONL, append-only)  

---

## 1. Objetivo

Diseñar un ciclo controlado de escritura real mínima en el store canónico de memoria semántica, verificable en cada paso, con backup previo, aprobación humana obligatoria, y rollback garantizado.

**Este documento es solo un plan. NO autoriza ejecución.**

## 2. Alcance

- Producir un plan verificable, auditable, reversible.
- Definir el target store exacto.
- Definir el procedimiento de backup.
- Definir el procedimiento de escritura de exactamente 1 record.
- Definir verificación de retrieval.
- Definir verificación de rollback.
- Definir condiciones de parada.
- Definir modos de fallo.

## 3. Out of Scope

- NO escribir en FAISS (`semantic_memory_faiss.index`, `.npz`, `_ids.json`).
- NO escribir en `memory/semantic` sin backup previo.
- NO modificar `tmp_agent/strategies/**`.
- NO modificar `tmp_agent/brain_v9/main.py`.
- NO modificar `tmp_agent/brain_v9/core/session.py`.
- NO modificar `brain/curated_runtime_lookup.py`.
- NO activar trading.
- NO tocar B8.
- NO aplicar patches.
- NO promover conocimiento.
- NO ejecutar el ciclo real en este frente.

## 4. Preconditions

| # | Precondition | Verification |
|---|---|---|
| 1 | Git working tree limpio (sin staged files) | `git status --short` |
| 2 | Runtime detenido | `curl -s http://127.0.0.1:8090/health` debe fallar |
| 3 | Backup creado manualmente | Copia de `semantic_memory.jsonl` con timestamp |
| 4 | Token de aprobación configurado | `BRAIN_APPROVAL_4D_DRY_GATE_TOKEN` en `.env` |
| 5 | Preflight snapshot ejecutado y aprobado | `SemanticMemoryControlledRealWritePreflightSnapshot` |
| 6 | Execution package verificado | `SemanticMemoryControlledRealWriteExecutionPackage` |
| 7 | Go/No-Go checklist aprobado | `SemanticMemoryGoNoGoReadinessChecklist` |
| 8 | Authorization packet firmado | `SemanticMemoryRealWriteAuthorizationPacket` |

## 5. Human Approval Gate

- **Approval 1:** Operador humano confirma intención de escritura controlada.
- **Approval 2:** Segunda confirmación explícita inmediatamente antes del `append`.
- **Sin ambas aprobaciones:** El gate `evaluate_readiness()` bloquea con `READY_BLOCKED`.

## 6. Target Store Exacto

```
memory/semantic/semantic_memory.jsonl
```

**Razón:**
- Formato JSONL (líneas JSON independientes).
- Append-only: una nueva línea al final no afecta líneas anteriores.
- Human-readable: cada record es un objeto JSON visible.
- Self-contained: cada línea tiene su propio `record_id`, `timestamp`, `source`.
- Backup trivial: copiar archivo.
- Rollback trivial: reemplazar archivo con backup.
- FAISS index es derivado: se puede reconstruir desde JSONL.

## 7. Backup Procedure

1. **Timestamp:** `BACKUP_TS=$(date +%Y%m%d_%H%M%S)`
2. **Source:** `memory/semantic/semantic_memory.jsonl`
3. **Destination:** `memory/semantic/semantic_memory.jsonl.backup_${BACKUP_TS}`
4. **Verification:** `wc -l` source == `wc -l` backup
5. **Hash:** `sha256sum` de ambos archivos debe coincidir.
6. **Evidence:** Registrar backup path y hash en ledger.

## 8. Single-Record Write Procedure

1. **Input controlado:** Un dict JSON predefinido, no generado por LLM.
2. **Normalización:** Validar que es un dict con `record_id`, `text`, `source`, `timestamp`.
3. **Score:** `validation_score >= 0.95` (manual, no automático).
4. **Approval:** Operador confirma que el dict es correcto.
5. **Backup:** Ejecutar backup procedure (paso 7).
6. **Append:** Escribir exactamente 1 línea JSON al final de `semantic_memory.jsonl`.
7. **Flush:** `file.flush()` + `os.fsync()`.
8. **Verification:** Verificar retrieval (paso 9).

## 9. Retrieval Verification

1. Leer `semantic_memory.jsonl` línea por línea.
2. Buscar `record_id` del record escrito.
3. Confirmar que el dict JSON parseado coincide exacto con el input.
4. Verificar que `sha256(content) == expected_hash`.
5. Si retrieval falla: detener inmediatamente, no continuar.

## 10. Rollback Procedure

1. **Source:** `memory/semantic/semantic_memory.jsonl.backup_${BACKUP_TS}`
2. **Destination:** `memory/semantic/semantic_memory.jsonl`
3. **Action:** Reemplazar archivo destino con backup.
4. **Verification:** `wc -l` backup == `wc -l` destino.
5. **Hash:** `sha256sum` backup == `sha256sum` destino.
6. **Retrieval negativo:** Confirmar que el record escrito YA NO existe en el archivo.
7. **Evidence:** Registrar rollback en ledger.

## 11. No-Mutation Fallback

Si cualquier paso falla:
- NO escribir.
- NO modificar `semantic_memory.jsonl`.
- Registrar `FAILED` en ledger con razón.
- El gate `block_real_write()` retorna `REAL_WRITE_BLOCKED`.

## 12. Evidence Files

- `tmp_agent/front_real_plan_01/test_results.txt` — Resultados de pytest.
- `tmp_agent/front_real_plan_01/security_check.json` — Validación de seguridad.
- `tmp_agent/front_real_plan_01/no_mutation_validation.json` — Confirmación de no mutación.
- `tmp_agent/front_real_plan_01/report.json` — Reporte final.
- `tmp_agent/front_real_plan_01/report.md` — Reporte final legible.

## 13. Ledger Update Requirements

Antes de ejecución real:
- `ROADMAP_STATUS.json` debe actualizarse con `last_applied_checkpoint: FRONT-REAL-APPROVAL-01`.
- `docs/MIGRATION_CONTROL_LEDGER.md` debe incluir sección FRONT-REAL-APPROVAL-01.
- `FRONT-REAL-PLAN-01` debe estar en `completed_fronts`.

## 14. Failure Modes

| Modo | Detección | Acción |
|---|---|---|
| Backup falla | `sha256sum` no coincide | Abortar, no escribir |
| Record inválido | Falta `record_id` o `text` | Rechazar antes de append |
| Append falla | Excepción de I/O | Abortar, restaurar backup si es necesario |
| Retrieval falla | Record no encontrado post-write | Rollback inmediato |
| Rollback falla | Hash post-rollback no coincide con backup | Alerta crítica, intervención manual |
| Runtime activo | `curl /health` responde 200 | Abortar, requiere runtime detenido |
| Git dirty | `git status` muestra staged/modified | Abortar, requiere working tree limpio |
| Token ausente | `BRAIN_APPROVAL_4D_DRY_GATE_TOKEN` vacío | Abortar, fail-closed |

## 15. Stop Conditions

- Cualquier `blocker` en preflight snapshot.
- Cualquier `BLOCKER` en Go/No-Go checklist.
- Cualquier fallo en backup procedure.
- Cualquier fallo en retrieval verification.
- Operador cancela en cualquier momento.
- `SIGINT` / `SIGTERM` durante append.

## 16. Safety Flags

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

## 17. Required Tests Before Execution

1. `test_semantic_memory_real_write_readiness_gate.py` (unit) — 30+ tests
2. `test_semantic_memory_controlled_real_write_preflight_snapshot.py` — preflight
3. `test_semantic_memory_go_no_go_readiness_checklist.py` — checklist
4. `test_semantic_memory_real_write_authorization_packet.py` — authorization
5. `test_semantic_memory_final_pre_execution_gate.py` — final gate
6. `test_semantic_memory_rollback_simulation.py` — rollback
7. `test_memory_semantic_backup.py` — backup
8. `test_semantic_memory_adapter_real.py` — adapter real skeleton
9. `test_semantic_memory_decision_gate_evidence_adapter.py` — evidence adapter
10. `smoke_front_real_plan_01_controlled_e2e_write_plan.py` — este plan

## 18. Explicit Statement

> **This plan does not authorize execution.**
>
> Execution of any real write requires:
> 1. A separate front: FRONT-REAL-APPROVAL-01
> 2. Human operator approval at two distinct gates
> 3. Runtime stopped
> 4. Clean git working tree
> 5. Real backup created and verified
> 6. All preflight tests passing
>
> Until FRONT-REAL-APPROVAL-01 is completed and explicitly approved, **no real write is permitted**.
