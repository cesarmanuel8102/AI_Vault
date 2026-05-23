# AI_Vault Migration Control Ledger

## 1. Estado inicial
- **Fecha/hora local**: 2026-05-23 12:59:36 EDT
- **Branch**: codex/own-capital-sustainable-return
- **Commit remoto base**: ec92be4b59ba526a7f9ffb4d2f7ff710342338b7
- **Commits locales pendientes**: 0 (hay 2 archivos staged pero sin commit hash asignado)
- **Runtime activo**: Brain V9
- **Puerto runtime**: 8090
- **Launcher real**: tmp_agent/brain_v9/start_full_server.py
- **App real**: brain_v9.main:app
- **Working tree sucio**: Sí - múltiples archivos modificados y untracked

## 2. Decisiones arquitectónicas activas
- Estrategia: Strangler/internal modular monolith primero, microservicios después.
- No migrar a microservicios reales hasta estabilizar runtime, contracts, tests y observabilidad.
- No aceptar infraestructura orphan como éxito.
- Todo módulo nuevo debe probar caller real o declarar explícitamente dry-run/no-runtime.
- No escritura real de memoria sin governance gate.
- No GitHub API antes de P2-F.
- No trading real desde chat sin approval.

## 3. Estado P2
- **P2-C**: CuratedRecord → LearningValidator adapter (completado - commit e4c1fd2f)
- **P2-D**: docs + smoke (completado - commit 54b8ccb4)
- **P2-E Commit 1**: CuratedMemoryPromotion dry-run service (completado y pusheado - commit 7ad320c4)
  - Archivos: brain/curated_memory_promotion.py, tests/unit/test_curated_memory_promotion.py
  - Tests pasando: 13/13
- **P2-E Commit 2**: completado y pusheado, hash cabc8fb8
  - Archivos: tests/smoke/smoke_curated_memory_promotion_dry_run.py, docs/P2E_GOVERNED_CURATED_MEMORY_PROMOTION.md
  - Estado: tests passing (13 + 11 + smoke), documentación lista
- **P2-E Commit 3A**: completado y pusheado, hash ef01172c
  - Archivos: brain/curated_memory_governance.py, tests/unit/test_curated_memory_governance.py, docs/P2E_GOVERNANCE_CONTRACT.md
  - Estado: contract/stub only, allow_real_write=False hardcoded
- **P2-E Commit 3B**: completado y pusheado, hash e55cb912
  - Archivos: brain/curated_memory_governance_audit.py, tests/unit/test_curated_memory_governance_audit.py, docs/P2E_GOVERNANCE_AUDIT_TRAIL.md
  - Estado: audit trail en tmp_agent/state/governance/, allow_real_write=False hardcoded
- **P2-E Commit 3C**: completado y pusheado, hash be071d97
  - Archivos: brain/curated_memory_rollback.py, tests/unit/test_curated_memory_rollback.py, docs/P2E_ROLLBACK_CONTRACT.md
  - Estado: rollback contract only, NO execute_rollback_real, allow_real_write=False hardcoded
- **P2-E Commit 3D**: completado y pusheado, hash f328b171
  - Archivos: brain/curated_memory_observability.py, tests/unit/test_curated_memory_observability.py, docs/P2E_OBSERVABILITY.md
  - Estado: observability en memoria solo, NO persistencia, NO runtime integration, allow_real_write=False hardcoded
- **P2-E Commit 3E**: completado y pusheado, hash 53782af1
  - Archivos: brain/curated_memory_dry_run_flow.py, tests/unit/test_curated_memory_dry_run_flow.py, docs/P2E_DRY_RUN_FLOW.md
  - Estado: orquestador dry-run integrando promotion+governance+audit+rollback+observability, NO escritura real, allow_real_write=False hardcoded
- **P2-E Commit 3F**: completado y pusheado, hash 563a40ea
  - Archivos: brain/semantic_memory_probe.py, tests/unit/test_semantic_memory_probe.py, docs/P2E_SEMANTIC_MEMORY_PROBE.md
  - Estado: probe read-only, inspección sin escritura, NO importa faiss, allow_real_write=False hardcoded
  - Tests: 14 tests passing
- **P2-E Commit 3G**: completado y pusheado, hash 7d0e7daa
  - Archivos: brain/semantic_memory_adapter_dry_run.py, tests/unit/test_semantic_memory_adapter_dry_run.py, docs/P2E_SEMANTIC_MEMORY_ADAPTER_DRY_RUN.md
  - Estado: adapter dry-run con validación de payloads, NO escritura real, NO importa faiss
- **P2-E Commit 3H**: completado y pusheado, hash 4a96ca58
  - Archivos: brain/curated_memory_dry_run_flow.py, tests/unit/test_curated_memory_dry_run_flow.py, docs/P2E_DRY_RUN_FLOW.md
  - Estado: flow integra semantic adapter en approve=True, NO escritura real, NO add_memory real
- **P2-E Commit 3I**: completado y pusheado, hash 6576cd8d
  - Archivos: tests/smoke/smoke_p2e_curated_memory_pipeline_dry_run.py, docs/P2E_DRY_RUN_PIPELINE_SMOKE.md
  - Estado: smoke test valida pipeline end-to-end, NO escritura real, NO add_memory real
- **P2-E Commit 3J**: en progreso, cierre formal dry-run y gate no-real-write
  - Archivos: tests/smoke/smoke_p2e_no_real_write_gate.py, docs/P2E_DRY_RUN_CLOSURE_REVIEW.md
  - Estado: gate valida que pipeline sigue sin escritura real, documenta requisitos Commit 4
  - Requisito: cerrar fase 3 dry-run antes de Commit 4 (promoción real)
- **P2-E Commit 4**: pendiente (promoción real)
  - Requisitos: pruebas SemanticMemory controladas + runtime contract + rollback real validado
  - Blockers: allow_real_write=False (bloqueado hasta cumplir requisitos)
- **P2-F GitHubSourceConnector**: pendiente, no activo

## 4. Brechas principales heredadas
- **B1**: doble routing / autoridad de rutas
- **B2**: módulos huérfanos
- **B3**: fake grounded
- **B7**: session.py cognitive monolith
- **N1**: fabricated metrics
- **N2**: auto-approval risk
- **N5**: failing/import/path tests
- **Orphan infra**: infraestructura creada pero no integrada runtime

## 5. Archivos prohibidos sin tarea explícita
- memory/semantic/*
- nul
- tmp_agent/strategies/*
- tmp_agent/reports/*
- campaign_gate_*
- market_cache/*.csv

## 6. Tests mínimos obligatorios actuales
- python -m pytest tests/unit/test_curated_memory_promotion.py -q (13 passed)
- python -m pytest tests/unit/test_curation_validation_adapter.py -q (11 passed)
- python tests/smoke/smoke_curation_validation_adapter.py (SMOKE_CURATION_VALIDATION_ADAPTER_OK)

## 7. Próximo paso autorizado
- Crear preflight/scope/smoke scripts.
- No runtime refactor.
- No push.

## 8. Rollback policy
- Todo commit debe ser pequeño.
- Todo cambio debe tener scope explícito.
- Si falla smoke runtime, no avanzar.
- Si aparece modificación prohibida, detener y reportar.
