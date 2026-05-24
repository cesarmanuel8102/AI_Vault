# P2-E Commit 4D-DecisionGateEvidenceAdapter: Semantic Memory Decision Gate Evidence Adapter

## Propósito

Adaptador read-only para integrar SemanticMemoryExternalEvidenceContract con SemanticMemoryRealWriteDecisionGate. Este módulo crea un puente entre el contrato de evidencia externa y el decision gate, permitiendo que el gate consuma bundles de evidencia validados.

## Alcance

- Recibir bundles de evidencia externa
- Validar bundles usando SemanticMemoryExternalEvidenceContract
- Traducir evidencia aceptada a decisiones del gate
- Mantener SIEMPRE `allow_real_write=False`

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│  P2-E Commit 4D-DecisionGateEvidenceAdapter                     │
│  SemanticMemoryDecisionGateEvidenceAdapter                      │
├─────────────────────────────────────────────────────────────────┤
│  Responsabilidades:                                             │
│  - Recibir bundles de evidencia externa                         │
│  - Validar bundles usando SemanticMemoryExternalEvidenceContract│
│  - Traducir evidencia aceptada a decisiones del gate            │
│  - Mapear ACCEPTED → ALLOW_MANUAL_REAL_WRITE_CANDIDATE          │
│  - Mapear PARTIAL → CANARY_NOOP_ONLY                            │
│  - Mapear REJECTED → BLOCK_REAL_WRITE                           │
├─────────────────────────────────────────────────────────────────┤
│  Limitaciones DURAS:                                            │
│  - Solo valida objetos/dicts proporcionados                     │
│  - NO subprocess execution                                      │
│  - NO file system writes                                        │
│  - NO runtime activation                                        │
│  - NO FAISS import                                            │
│  - NO semantic_memory_bridge import                            │
│  - NO add_memory calls                                          │
│  - allow_real_write=False SIEMPRE                               │
│  - dry_run_only=True SIEMPRE                                    │
│  - can_execute_real_write=False SIEMPRE                       │
└─────────────────────────────────────────────────────────────────┘
```

## Flujo de Trabajo

```
┌─────────────────────────────────────────────────────────────────┐
│  External Evidence Bundle                                       │
│  (Producido por agente/humano)                                  │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  SemanticMemoryDecisionGateEvidenceAdapter                      │
│  evaluate_with_evidence_read_only(bundle)                      │
│                                                                 │
│  Step 1: Validar evidencia usando EvidenceContract             │
│  Step 2: Mapear estado de evidencia a decisión                 │
│  Step 3: Generar reporte con findings                          │
│  Step 4: Mantener flags de seguridad (always False)            │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  SemanticMemoryDecisionGateEvidenceAdapterReport                │
│                                                                 │
│  - status: ACCEPTED_FOR_GATE / REJECTED_BY_EVIDENCE            │
│  - decision: ALLOW_MANUAL_REAL_WRITE_CANDIDATE                 │
│  - allow_real_write: False (always)                             │
│  - dry_run_only: True (always)                                  │
│  - can_execute_real_write: False (always)                     │
└─────────────────────────────────────────────────────────────────┘
```

## Estados del Adaptador

- **ACCEPTED_FOR_GATE**: Evidencia aceptada, puede pasar al decision gate
- **REJECTED_BY_EVIDENCE**: Evidencia rechazada por el contrato
- **PARTIAL_EVIDENCE**: Evidencia parcial, requiere revisión manual
- **BLOCKED**: Bloqueado explícitamente
- **UNKNOWN**: Estado desconocido

## Mapeo de Evidencia a Decisión

| Evidencia Status | Adapter Status | Decision Gate |
|------------------|----------------|---------------|
| ACCEPTED | ACCEPTED_FOR_GATE | ALLOW_MANUAL_REAL_WRITE_CANDIDATE |
| PARTIAL | PARTIAL_EVIDENCE | CANARY_NOOP_ONLY |
| REJECTED | REJECTED_BY_EVIDENCE | BLOCK_REAL_WRITE |
| MISSING | BLOCKED | BLOCK_REAL_WRITE |
| UNKNOWN | UNKNOWN | BLOCK_REAL_WRITE |

## API

```python
from brain.semantic_memory_decision_gate_evidence_adapter import (
    SemanticMemoryDecisionGateEvidenceAdapter,
    SemanticMemoryEvidenceAdapterStatus,
    SemanticMemoryDecisionGateEvidenceAdapterReport,
)

# Crear adaptador
adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=".")

# Evaluar bundle de evidencia
report = adapter.evaluate_with_evidence_read_only(bundle)

# Verificar resultado
if report.accepted_for_decision_gate:
    print("Bundle aceptado para decision gate")
    print(f"Decision: {report.decision}")
else:
    print("Bundle rechazado")
    print(f"Blockers: {report.blockers}")

# Bloquear adaptador explícitamente
blocked_report = adapter.block_adapter("Razón del bloqueo")
```

## Estructura del Reporte

```python
@dataclass
class SemanticMemoryDecisionGateEvidenceAdapterReport:
    adapter_id: str
    created_at_utc: str
    status: SemanticMemoryEvidenceAdapterStatus
    evidence_status: str
    decision: str
    findings: List[SemanticMemoryEvidenceAdapterFinding]
    blocker_count: int
    warning_count: int
    info_count: int
    git_state_verified: bool
    risk_summary_verified: bool
    security_validation_verified: bool
    tests_verified: bool
    smokes_verified: bool
    accepted_for_decision_gate: bool
    allow_real_write: bool = False  # SIEMPRE False
    dry_run_only: bool = True  # SIEMPRE True
    can_execute_real_write: bool = False  # SIEMPRE False
    requires_manual_review: bool = True
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

## Reglas de Seguridad

1. **allow_real_write=False SIEMPRE**: El adaptador nunca permite escritura real
2. **dry_run_only=True SIEMPRE**: Solo opera en modo dry-run
3. **can_execute_real_write=False SIEMPRE**: No puede ejecutar escritura real
4. **NO subprocess**: No ejecuta subprocess
5. **NO file writes**: No escribe archivos
6. **NO FAISS**: No importa faiss
7. **NO semantic_memory_bridge**: No importa semantic_memory_bridge
8. **NO add_memory**: No llama add_memory

## Tests

### Unit Tests

```bash
cd /c/AI_VAULT
python -m pytest tests/unit/test_semantic_memory_decision_gate_evidence_adapter.py -v
```

Tests incluidos:
- Bundle válido devuelve ACCEPTED_FOR_GATE
- Bundle válido devuelve ALLOW_MANUAL_REAL_WRITE_CANDIDATE
- Git con commits pendientes devuelve BLOCKED
- Git con archivos staged devuelve BLOCKED
- Riesgo alto sin resolver devuelve BLOCKED
- Evidencia parcial devuelve CANARY_NOOP_ONLY
- Bundle vacío devuelve BLOCKED
- allow_real_write siempre es False
- dry_run_only siempre es True
- No subprocess import
- No open() calls
- No faiss import
- No semantic_memory_bridge import
- No add_memory calls

### Smoke Tests

```bash
cd /c/AI_VAULT
python tests/smoke/smoke_semantic_memory_decision_gate_evidence_adapter.py
```

Smoke tests validan:
- Importación exitosa
- Creación de adaptador
- Evaluación de bundle válido
- Evaluación de bundle inválido (git)
- Evaluación de bundle inválido (risk)
- Bloqueo explícito del adaptador

## Archivos

- `brain/semantic_memory_decision_gate_evidence_adapter.py`: Implementación del adaptador
- `tests/unit/test_semantic_memory_decision_gate_evidence_adapter.py`: Tests unitarios
- `tests/smoke/smoke_semantic_memory_decision_gate_evidence_adapter.py`: Smoke tests

## Commit

```bash
git add brain/semantic_memory_decision_gate_evidence_adapter.py
git add tests/unit/test_semantic_memory_decision_gate_evidence_adapter.py
git add tests/smoke/smoke_semantic_memory_decision_gate_evidence_adapter.py
git add docs/P2E_SEMANTIC_MEMORY_DECISION_GATE_EVIDENCE_ADAPTER.md
git add docs/MIGRATION_CONTROL_LEDGER.md
git commit -m "Add SemanticMemory decision gate evidence adapter"
```

## Próximo Paso

El adaptador está listo para integrarse con el DecisionGate. El siguiente paso es:

1. Revisión humana del reporte generado
2. Verificación manual de los findings
3. Decisión sobre permitir o bloquear escritura real

## Referencias

- `brain/semantic_memory_external_evidence_contract.py`: Contrato de evidencia externa
- `brain/semantic_memory_real_write_decision_gate.py`: Decision gate para escritura real
- `docs/P2E_SEMANTIC_MEMORY_EXTERNAL_EVIDENCE_CONTRACT.md`: Documentación del contrato de evidencia

## Estado

- **Implementación**: ✅ Completada
- **Tests Unitarios**: ✅ 26/26 passing
- **Smoke Tests**: ✅ Passing
- **Documentación**: ✅ Completada
- **Ledger**: ✅ Actualizado

## Changelog

### 2026-05-24
- Implementación inicial del adaptador
- Integración con EvidenceContract
- Mapeo de estados de evidencia a decisiones
- Tests unitarios completos
- Smoke tests
- Documentación
