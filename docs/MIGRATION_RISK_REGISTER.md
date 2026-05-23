# Migration Risk Register

## Registro de Riesgos - Migración AI_Vault

| ID | Riesgo | Severidad | Evidencia | Control | Estado |
|---|---|---|---|---|---|
| R1 | Tocar entrypoint equivocado | Alto | Root main.py vs Brain V9 launcher | Verificar launcher real antes de cambios | Vigente |
| R2 | Crear infraestructura orphan | Alto | Módulos sin integración runtime | Todo módulo nuevo debe probar caller real o declarar dry-run | Vigente |
| R3 | Mezclar memory/semantic | Crítico | Archivos en memory/semantic/ modificados sin tarea | NO tocar memory/semantic/* sin tarea explícita | Bloqueado |
| R4 | Mezclar trading artifacts | Medio | Archivos en tmp_agent/strategies/ | NO tocar tmp_agent/strategies/* sin tarea | Bloqueado |
| R5 | Fake grounded persistente | Alto | Respuestas inventadas sobre estado del proyecto | Usar ProjectStateProvider como fuente única | Parcial |
| R6 | Doble routing | Alto | Múltiples archivos definiendo rutas similares | Documentar entrypoints reales, deprecar duplicados | Vigente |
| R7 | Métricas fabricadas | Alto | N1: Métricas sin base real en tests/runtime | Validar métricas contra datos reales | Vigente |
| R8 | Auto-approval sin integridad | Crítico | N2: Aprobaciones automáticas sin verificación | Requerir approval explícito para trading/memoria | Bloqueado |
| R9 | GitHub API sin allowlist/gate | Alto | P2-F pendiente, no activar antes de tiempo | NO GitHub API antes de P2-F con gate implementado | Bloqueado |
| R10 | Escritura directa FAISS | Crítico | P2-E es dry-run, no debe escribir realmente | Validar que P2-E no escribe a vectores sin governance | Verificado |
| R11 | Refactor de session.py sin characterization tests | Crítico | session.py es cognitive monolith (B7) | NO modificar sin tests de caracterización previos | Bloqueado |
| R12 | Tests que pasan pero runtime no usa el código | Alto | Tests unitarios pasan pero integración falla | Ejecutar smoke tests contra runtime real | Parcial |

## Análisis de Riesgos

### Riesgos Bloqueados (Acción Inmediata Requerida)
- **R3, R4, R8, R9, R11**: Estos riesgos tienen controles activos que bloquean avance si se detecta incumplimiento.

### Riesgos Vigentes (Monitoreo Continuo)
- **R1, R2, R6, R7, R12**: Requieren verificación periódica mediante scripts de preflight.

### Riesgos Parcialmente Mitigados
- **R5**: ProjectStateProvider implementado, requiere uso consistente
- **R12**: Smoke tests creados, requieren ejecución regular

## Controles Implementados

1. **Preflight Script**: `ops/preflight_migration.ps1` - Verifica estado antes de cambios
2. **Scope Check**: `ops/check_scope.ps1` - Valida que no se modifiquen archivos prohibidos
3. **Smoke Tests**: `ops/smoke_brain_v9_8090.ps1` - Valida runtime real
4. **Core Tests**: `ops/run_core_tests.ps1` - Ejecuta tests mínimos obligatorios

## Acciones por Riesgo

| ID | Acción Inmediata | Responsable | Deadline |
|---|---|---|---|
| R1 | Documentar entrypoints en RUNTIME_ENTRYPOINTS.md | AI | 2026-05-23 |
| R2 | Crear checklist de integración para nuevos módulos | AI | 2026-05-24 |
| R3 | NO ejecutar git add en memory/semantic/* | Todos | Contínuo |
| R4 | NO ejecutar git add en tmp_agent/strategies/* | Todos | Contínuo |
| R5 | Usar ProjectStateProvider.get_project_status() en chat | AI | 2026-05-24 |
| R6 | Crear mapa de rutas deprecadas vs activas | AI | 2026-05-25 |
| R7 | Agregar validación de métricas en tests | AI | 2026-05-26 |
| R8 | Implementar governance gate para aprobaciones | AI | P2-G |
| R9 | NO implementar P2-F hasta tener gate | AI | P2-F |
| R10 | Verificar que P2-E usa dry-run (sin escritura real) | AI | Verificado |
| R11 | Crear tests de caracterización antes de tocar session.py | AI | P3-A |
| R12 | Ejecutar smoke tests en cada ciclo | AI | Contínuo |

## Revisión

- **Fecha última revisión**: 2026-05-23
- **Próxima revisión**: Al completar P2-E Commit 2
- **Frecuencia**: Cada milestone de P2
