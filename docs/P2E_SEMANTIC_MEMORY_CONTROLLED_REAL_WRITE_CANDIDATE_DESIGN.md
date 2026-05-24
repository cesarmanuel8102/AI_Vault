# P2-E Commit 4D-ControlledRealWriteCandidateDesign

## Objetivo

Este documento describe el **Controlled Real Write Candidate Design** para SemanticMemory - un diseño read-only del candidato exacto para una futura controlled real write.

**Importante**: Este commit **NUNCA** ejecuta escrituras reales. Solo define el candidato, alcance, precondiciones, backup/rollback esperado, dry-run final y criterios de segunda confirmación.

## Por qué existe después del AuthorizationPacket

El `RealWriteAuthorizationPacket` modeló la autorización humana explícita. El `ControlledRealWriteCandidateDesign` es el paso donde se diseña el candidato exacto de escritura real, especificando todos los detalles necesarios para una futura ejecución controlada.

- **RealWriteAuthorizationPacket**: Modela autorización humana explícita
- **ControlledRealWriteCandidateDesign**: Diseña el candidato exacto de escritura

## Evidencia requerida

```python
{
    "authorization_decision": "AUTHORIZATION_PACKET_READY",
    "authorization_hash": "819be9f2",
    "go_no_go_hash": "433c5842",
    "commits_pending_post_push": 0,
    "staged_files": [],
    "memory_semantic_in_scope": False,
    "runtime_active": False,
    "faiss_write_enabled": False,
    "add_memory_enabled": False,
    "allows_auto_execute": False,
    "can_execute_real_write": False,
    "allow_real_write": False,
    "dry_run_only": True,
    "simulated_only": True,
    "requires_second_confirmation": True,
    "security_validation_ok": True
}
```

## Candidate Request requerido

```python
{
    "requested_by": "Cesar",
    "candidate_scope": "single_curated_fact_probe",
    "target_room": "migration_p2e_probe",
    "candidate_fact_key": "p2e_real_write_probe",
    "candidate_fact_value": "controlled candidate design only; not executed",
    "operation_mode": "design_only",
    "expects_no_runtime": True,
    "expects_no_write": True,
    "expects_second_confirmation": True
}
```

## Decisiones

### CANDIDATE_DESIGN_READY

El diseño del candidato está listo para revisión humana final. No ejecuta escritura real.

### MANUAL_REVIEW_REQUIRED

Falta información del candidato. Requiere revisión manual.

### BLOCK_CANDIDATE_DESIGN

Hay bloqueadores críticos. No se puede proceder.

## Por qué no ejecuta real write

Este commit **NUNCA** ejecuta escrituras reales:

- `can_execute_real_write` es siempre `False`
- `allow_real_write` es siempre `False`
- `dry_run_only` es siempre `True`
- `simulated_only` es siempre `True`
- `requires_second_confirmation` es siempre `True`
- `requires_runtime_down` es siempre `True`
- `requires_clean_git_gate` es siempre `True`

## Qué prohíbe

- ❌ Escritura real automática
- ❌ Ejecución de add memory real
- ❌ Modificación de `memory/semantic/`
- ❌ Operaciones FAISS de escritura
- ❌ Ejecución de runtime
- ❌ Auto-promoción de candidatos
- ❌ Ejecución real de rollback

## Qué será necesario antes de ejecución real futura

Antes de cualquier escritura real:

1. ✅ Runtime debe estar apagado (`requires_runtime_down=True`)
2. ✅ Git debe estar limpio (`requires_clean_git_gate=True`)
3. ✅ Backup completo validado
4. ✅ Plan de rollback validado
5. ✅ Segunda confirmación explícita de Cesar
6. ✅ Security validation OK

## Cómo ejecutar tests/smoke

```bash
python tests/smoke/smoke_semantic_memory_controlled_real_write_candidate_design.py
```

Debe imprimir:
```
SMOKE_SEMANTIC_MEMORY_CONTROLLED_REAL_WRITE_CANDIDATE_DESIGN_OK
```

## Próxima fase recomendada

Después de este commit, la siguiente fase es:

**P2-E Commit 4D: Controlled Real Write Execution**

Esta fase:
- Requiere que el candidate design haya emitido `CANDIDATE_DESIGN_READY`
- Requiere runtime apagado
- Requiere git limpio
- Ejecuta escritura real controlada con todas las salvaguardas
- Incluye rollback automático en caso de fallo

## Confirmaciones de seguridad

Este commit:
- **NO** escribe en `memory/semantic/`
- **NO** borra archivos
- **NO** mueve archivos
- **NO** toca FAISS
- **NO** importa semantic memory bridge
- **NO** llama add memory real
- **NO** ejecuta runtime
- Solo genera un diseño candidato read-only
- La escritura real requiere otra fase separada y segunda confirmación de Cesar
