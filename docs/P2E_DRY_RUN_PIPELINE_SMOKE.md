# P2-E Dry-Run Pipeline Smoke Test

## Commit 3I: Smoke Test del Pipeline P2-E

### Objetivo

Validar que el **pipeline completo P2-E dry-run** funciona correctamente end-to-end, verificando:

1. Pipeline aprobado ejecuta semantic adapter dry-run
2. Pipeline rechazado no ejecuta semantic adapter
3. Bloqueo explícito de escritura real funciona
4. Todas las integraciones funcionan sin escritura real

### Qué Valida el Smoke

El smoke test valida las siguientes condiciones:

#### Caso 1: Pipeline Aprobado

- ✅ Crea `SemanticMemoryAdapterDryRun`
- ✅ Crea `CuratedMemoryDryRunFlow(semantic_adapter=adapter)`
- ✅ Ejecuta `run_approval_flow` con `approve=True`
- ✅ Verifica `status == COMPLETED_DRY_RUN`
- ✅ Verifica `dry_run_only == True`
- ✅ Verifica `allow_real_write == False`
- ✅ Verifica `approval_request_id` y `approval_decision_id` existen
- ✅ Verifica `audit_entry_ids` no vacío
- ✅ Verifica `observability_event_ids` no vacío
- ✅ Verifica `semantic_adapter_run_id` existe
- ✅ Verifica `semantic_adapter_status == "DRY_RUN_READY"`
- ✅ Verifica metadata contiene `semantic_adapter_dry_run=True`
- ✅ Verifica metadata contiene `semantic_adapter_would_call_method="add_memory"`
- ✅ Verifica NO hay escritura real

#### Caso 2: Pipeline Rechazado

- ✅ Crea adapter y flow
- ✅ Ejecuta `run_approval_flow` con `approve=False`
- ✅ Verifica `status == REJECTED_DRY_RUN`
- ✅ Verifica `dry_run_only == True`
- ✅ Verifica `allow_real_write == False`
- ✅ Verifica `semantic_adapter_run_id is None`
- ✅ Verifica `semantic_adapter_status is None`
- ✅ Verifica metadata contiene `semantic_adapter_skipped=True`
- ✅ Verifica NO se ejecutó semantic adapter

#### Caso 3: Bloqueo Explícito

- ✅ Crea `SemanticMemoryAdapterDryRun`
- ✅ Construye payload con `build_payload`
- ✅ Ejecuta `block_real_write`
- ✅ Verifica `status == REAL_WRITE_BLOCKED`
- ✅ Verifica `dry_run_only == True`
- ✅ Verifica `allow_real_write == False`
- ✅ Verifica warnings no vacío
- ✅ Verifica warning indica bloqueo

### Qué NO Valida

Este smoke test explícitamente **NO** valida:

- ❌ Promoción real (requiere Commit 4)
- ❌ Escritura en memoria semántica real
- ❌ Integración con FAISS real
- ❌ Runtime V9 activo
- ❌ Endpoints HTTP
- ❌ Persistencia de datos

### Qué Sigue Bloqueado

Antes de promoción real (Commit 4), debe cumplirse:

1. ✅ Pipeline dry-run validado (P2-E 3E-3I)
2. ✅ SemanticMemory adapter integrado (P2-E 3H-3I)
3. ✅ Governance completo (P2-E 3A-3D)
4. ✅ Audit trail operativo (P2-E 3B)
5. ✅ Rollback planificado (P2-E 3C)
6. ✅ Observabilidad mínima (P2-E 3D)
7. ⏸️ Smoke test real con datos de prueba
8. ⏸️ Permitir `allow_real_write=True` con governance
9. ⏸️ Implementar `add_memory` real con FAISS
10. ⏸️ Implementar `execute_rollback_real()`

### Cómo Ejecutar

```bash
# Desde el directorio raíz del proyecto (C:\AI_VAULT)
python tests/smoke/smoke_p2e_curated_memory_pipeline_dry_run.py
```

### Resultado Esperado

```
======================================================================
P2-E Commit 3I: Smoke Test del Pipeline Dry-Run
======================================================================

=== Approved Pipeline Smoke ===
[PASS] Expected COMPLETED_DRY_RUN, got COMPLETED_DRY_RUN
[PASS] dry_run_only must be True
[PASS] allow_real_write must be False
[PASS] approval_request_id must not be None
[PASS] approval_decision_id must not be None
[PASS] audit_entry_ids must not be empty
[PASS] observability_event_ids must not be empty
[PASS] semantic_adapter_run_id must not be None
[PASS] semantic_adapter_status must be DRY_RUN_READY
[PASS] semantic_adapter_dry_run must be True in metadata
[PASS] would_call_method should be 'add_memory' (text only, not actual call)
[PASS] metadata must contain semantic_adapter_dry_run flag
[INFO] Approved pipeline smoke completed successfully
[INFO] Flow ID: flow_xxxxxxxxxxxxxxxx
[INFO] Semantic Adapter Run ID: adapter_run_xxxxxxxxxxxxxxxx
[INFO] Semantic Adapter Status: DRY_RUN_READY

=== Rejected Pipeline Smoke ===
[PASS] Expected REJECTED_DRY_RUN, got REJECTED_DRY_RUN
[PASS] dry_run_only must be True
[PASS] allow_real_write must be False
[PASS] semantic_adapter_run_id must be None for rejected flow
[PASS] semantic_adapter_status must be None for rejected flow
[PASS] semantic_adapter_skipped must be True in metadata
[INFO] Rejected pipeline smoke completed successfully
[INFO] Flow ID: flow_xxxxxxxxxxxxxxxx
[INFO] Semantic Adapter: SKIPPED (correct for rejected flow)

=== Adapter Block Real Write Smoke ===
[PASS] Expected REAL_WRITE_BLOCKED, got REAL_WRITE_BLOCKED
[PASS] dry_run_only must be True
[PASS] allow_real_write must be False
[PASS] warnings must not be empty
[PASS] warning should indicate blocked write
[INFO] Adapter block smoke completed successfully
[INFO] Adapter Run ID: adapter_run_xxxxxxxxxxxxxxxx
[INFO] Status: REAL_WRITE_BLOCKED
[INFO] Warning: WRITE_BLOCKED: ...

======================================================================
SMOKE_P2E_CURATED_MEMORY_PIPELINE_DRY_RUN_OK
======================================================================
```

### Requisitos Antes de Promote_Real

El smoke test P2-E dry-run es **requisito previo** para Commit 4 (promoción real):

1. ✅ Este smoke debe pasar completamente
2. ✅ Todos los unit tests deben pasar
3. ✅ No debe haber escritura accidental en memoria
4. ✅ No debe haber import de faiss
5. ✅ No debe haber llamadas a endpoints
6. ✅ Ledger debe estar actualizado

### Próximo Paso Recomendado

**P2-E Commit 4**: Promoción real sobre memoria semántica

Cuando todos los requisitos estén cumplidos:

1. Implementar `add_memory` real con FAISS
2. Permitir `allow_real_write=True` con governance completo
3. Implementar `execute_rollback_real()` con FAISS
4. Agregar persistencia de eventos observability
5. Crear dashboard de métricas
6. Pruebas de integración con runtime
7. Solo entonces: habilitar promoción real

**Alternativa**: P2-F GitHubSourceConnector si se prioriza otra funcionalidad.

---

**Estado**: P2-E Commit 3I completado  
**Scope**: Smoke test pipeline dry-run  
**Módulos validados**: Flow + Adapter + Governance + Audit + Rollback + Observability  
**Escritura real**: BLOQUEADA  
**Branch**: codex/own-capital-sustainable-return
