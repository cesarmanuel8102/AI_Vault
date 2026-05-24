# P2-E Commit 4D-EvidenceInjection: Semantic Memory External Evidence Contract

## Propósito

Contrato read-only para inyectar evidencia externa verificada al DecisionGate. Este módulo valida bundles de evidencia producidos por el agente o humano, SIN ejecutar subprocess, SIN leer archivos de runtime, SIN escribir nada.

## Alcance

- Validar estructura de bundles de evidencia
- Verificar flags de seguridad
- Asegurar consistencia de evidencia
- Emitir reporte de aceptación/rechazo
- Bloquear SIEMPRE escritura real

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│  P2-E Commit 4D-EvidenceInjection                               │
│  SemanticMemoryExternalEvidenceContract                         │
├─────────────────────────────────────────────────────────────────┤
│  Responsabilidades:                                              │
│  - Validar bundles de evidencia externa                       │
│  - Verificar git_state, risk_summary, security_validation       │
│  - Verificar test_summary, smoke_summary                        │
│  - Emitir reporte ACCEPTED/REJECTED/PARTIAL/MISSING            │
├─────────────────────────────────────────────────────────────────┤
│  Limitaciones DURAS:                                             │
│  - Solo valida objetos/dicts proporcionados externamente        │
│  - NO ejecuta git, subprocess, o runtime                         │
│  - NO modifica archivos                                         │
│  - NO importa faiss, semantic_memory_bridge                     │
│  - SIEMPRE bloquea allow_real_write                            │
└─────────────────────────────────────────────────────────────────┘
```

## Evidencia Aceptada

El contrato acepta bundles con las siguientes secciones:

### 1. git_state
- `verified`: True
- `pending_commits_vs_origin`: 0
- `staged_files`: []
- `memory_semantic_in_commit`: False
- `tmp_agent_strategies_in_commit`: False
- `nul_in_commit`: False
- `runtime_active`: False

### 2. risk_summary
- `verified`: True
- `unresolved_high_risk_count`: 0
- `unresolved_write_like_count`: 0 (WARNING si > 0)
- `unresolved_runtime_like_count`: 0 (WARNING si > 0)

### 3. security_validation
- `verified`: True
- `no_open`: True
- `no_subprocess`: True
- `no_faiss`: True
- `no_requests_httpx`: True
- `no_semantic_memory_bridge`: True
- `no_add_memory`: True
- `no_write_ops`: True
- `no_delete_ops`: True
- `no_move_ops`: True
- `no_allow_real_write_true`: True

### 4. test_summary
- `verified`: True
- `failed`: 0
- `decision_gate_tests_passed`: True (WARNING si False)
- `p2e_regression_tests_passed`: True (WARNING si False)

### 5. smoke_summary
- `verified`: True
- `failed`: 0
- `decision_gate_smoke_ok`: True (WARNING si False)
- `p2e_regression_smokes_ok`: True (WARNING si False)

## Estados de Validación

- **ACCEPTED**: Todas las verificaciones pasaron, sin blockers
- **REJECTED**: Hay blockers críticos
- **PARTIAL**: Hay warnings, requiere revisión manual
- **MISSING**: Faltan datos requeridos

## API

```python
from brain.semantic_memory_external_evidence_contract import (
    SemanticMemoryExternalEvidenceContract,
    SemanticMemoryExternalEvidenceBundle,
    SemanticMemoryExternalEvidenceValidationReport,
)

# Crear contrato
contract = SemanticMemoryExternalEvidenceContract(repo_root=".")

# Validar bundle
report = contract.validate_bundle_read_only(bundle)

# Verificar resultado
if report.status == SemanticMemoryEvidenceStatus.ACCEPTED:
    print("Evidencia aceptada para DecisionGate")
else:
    print(f"Evidencia rechazada: {report.status}")
```

## Bloqueos de Seguridad

El contrato SIEMPRE mantiene:

```python
report.allow_real_write = False  # SIEMPRE False
report.dry_run_only = True       # SIEMPRE True
report.can_execute_real_write = False  # SIEMPRE False
```

## Archivos

- `brain/semantic_memory_external_evidence_contract.py`: Implementación
- `tests/unit/test_semantic_memory_external_evidence_contract.py`: Tests unitarios (37 tests)
- `tests/smoke/smoke_semantic_memory_external_evidence_contract.py`: Smoke test
- `docs/P2E_SEMANTIC_MEMORY_EXTERNAL_EVIDENCE_CONTRACT.md`: Este documento

## Registro en Migration Control Ledger

- **Commit**: P2-E Commit 4D-EvidenceInjection
- **Estado**: Completado
- **Tests**: 37 unit tests passing + smoke test passing
- **Seguridad**: allow_real_write=False, dry_run_only=True, SECURITY_VALIDATION_OK

## Requisitos para Aceptación

Para que un bundle sea ACCEPTED:

1. Todas las secciones presentes y verificadas
2. Sin blockers de seguridad
3. Sin commits pendientes vs origin
4. Sin archivos staged
5. Sin memory/semantic en commit
6. Sin tmp_agent/strategies en commit
7. Sin riesgos altos sin resolver
8. Todos los tests pasando
9. Todos los smoke tests pasando

## Siguiente Paso

El reporte de validación ACCEPTED puede ser consumido por:
- `SemanticMemoryRealWriteDecisionGate` (P2-E Commit 4D-DecisionGate)
- Para tomar decisiones de escritura real (que SIEMPRE serán bloqueadas)

## Notas de Implementación

- El contrato NO genera evidencia, solo valida la proporcionada
- El contrato NO llama git, subprocess, ni runtime
- El contrato NO importa faiss, requests, semantic_memory_bridge
- El contrato NO escribe archivos
- El contrato está diseñado para ser seguro por construcción
