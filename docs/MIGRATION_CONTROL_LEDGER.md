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
- **P2-E Commit 3B**: en progreso (audit trail local)
  - Archivos: brain/curated_memory_governance_audit.py, tests/unit/test_curated_memory_governance_audit.py, docs/P2E_GOVERNANCE_AUDIT_TRAIL.md
  - Estado: audit trail en tmp_agent/state/governance/, allow_real_write=False hardcoded
- **P2-E Commit 4**: pendiente (promoción real)
  - Requisitos: rollback, observability, integración con SemanticMemory validada
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
