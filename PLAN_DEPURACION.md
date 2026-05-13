# PLAN DE DEPURACIÓN Y FORTALECIMIENTO AI_VAULT
## Versión 1.0 | Fecha: 2026-03-19
## Fase: Depuración Inicial

---

## 1. RESUMEN EJECUTIVO

**Objetivo:** Eliminar deuda técnica acumulada, consolidar código duplicado y preparar el sistema para fortalecimiento.

**Estado Actual:**
- Archivos totales: 28,646 (incluye .venv)
- Archivos de proyecto reales: ~350
- Espacio ocupado: ~760 MB
- Deuda técnica: MEDIA-ALTA
- **Espacio liberable estimado: ~450 MB (40%)**

---

## 2. FASE 1: LIMPIEZA DE ARCHIVOS OBSOLETOS (CRÍTICA)

### 2.1 Backups Antiguos de Componentes Core
**Prioridad:** ALTA | **Tiempo estimado:** 2 horas

#### advisor_server.py - 50+ versiones
```powershell
# BACKUP ANTES DE ELIMINAR
Compress-Archive -Path "00_identity/advisor_server.py.*.bak_*" -DestinationPath "ARCHIVE/advisor_backups_$(Get-Date -Format 'yyyyMMdd').zip"

# ELIMINAR (mantener solo advisor_server.py y advisor_server_clean.py)
Remove-Item "00_identity/advisor_server.py.*.bak_*" -Force
Remove-Item "00_identity/advisor_server_fixed.py" -Force
Remove-Item "tmp_agent/advisor_server_working.py" -Force
Remove-Item "tmp_agent/advisor_server_simple.py" -Force
```

#### brain_server.py - 40+ versiones
```powershell
# CONSOLIDAR EN VERSION CANÓNICA
# Mantener: brain_server.py, brain_server_limpio.py
# Archivar y eliminar el resto
Compress-Archive -Path "00_identity/brain_server.py.*.BAK_*,00_identity/brain_server.py.*.LKG_*" -DestinationPath "ARCHIVE/brain_server_backups.zip"
Remove-Item "00_identity/brain_server.py.*.BAK_*" -Force
Remove-Item "00_identity/brain_server.py.*.LKG_*" -Force
Remove-Item "00_identity/brain_server_backup.py" -Force
Remove-Item "00_identity/brain_server_reparado.py" -Force
```

#### agent_loop.py - 20+ versiones
```powershell
Compress-Archive -Path "*/agent_loop.py.bak_*" -DestinationPath "ARCHIVE/agent_loop_backups.zip"
Remove-Item "*/agent_loop.py.bak_*" -Force
Remove-Item "*/agent_loop.py.BAK_*" -Force
```

#### brain_router.py - 30+ versiones
```powershell
Compress-Archive -Path "*/brain_router.py.bak_*" -DestinationPath "ARCHIVE/brain_router_backups.zip"
Remove-Item "*/brain_router.py.bak_*" -Force
```

### 2.2 Archivos Temporales y Logs
**Prioridad:** ALTA | **Tiempo estimado:** 1 hora

```powershell
# Limpiar archivos .pyc compilados
Get-ChildItem -Path "C:\AI_VAULT" -Filter "*.pyc" -Recurse | Remove-Item -Force

# Limpiar carpetas __pycache__
Get-ChildItem -Path "C:\AI_VAULT" -Filter "__pycache__" -Recurse | Remove-Item -Recurse -Force

# Archivar logs antiguos (>30 días)
$cutoffDate = (Get-Date).AddDays(-30)
Get-ChildItem -Path "*/logs/*.log" | Where-Object {$_.LastWriteTime -lt $cutoffDate} | Compress-Archive -DestinationPath "ARCHIVE/old_logs.zip"
Get-ChildItem -Path "*/logs/*.log" | Where-Object {$_.LastWriteTime -lt $cutoffDate} | Remove-Item -Force
```

### 2.3 Dashboards Duplicados
**Prioridad:** MEDIA | **Tiempo estimado:** 1 hora

```powershell
# CONSOLIDAR DASHBOARDS
# Mantener: 00_identity/autonomy_system/unified_dashboard_live.html
# Eliminar duplicados en tmp_agent/dashboard/
Remove-Item "tmp_agent/dashboard_*.py" -Force
Remove-Item "tmp_agent/dashboard_alternative.py" -Force
Remove-Item "tmp_agent/dashboard_simple_working.py" -Force
Remove-Item "tmp_agent/dashboard_super_simple.py" -Force
# (Conservar por ahora: dashboard_professional/)
```

---

## 3. FASE 2: CONSOLIDACIÓN DE CÓDIGO DUPLICADO

### 3.1 Unificación advisor_server.py
**Estrategia:** Canonical en 00_identity/

```python
# 00_identity/advisor_server.py (CANÓNICO)
# tmp_agent/advisor_server.py → ELIMINAR (symlink o referencia)
# tmp_agent/advisor_server_working.py → ELIMINAR
# tmp_agent/advisor_server_simple.py → ELIMINAR
```

### 3.2 Unificación brain_router.py
**Estrategia:** Canonical en 00_identity/

```python
# 00_identity/brain_router.py (CANÓNICO)
# tmp_agent/brain_router.py → ELIMINAR
```

### 3.3 Unificación agent_loop.py
**Estrategia:** Canonical en 00_identity/

```python
# 00_identity/agent_loop.py (CANÓNICO)
# tmp_agent/agent_loop.py → ELIMINAR
```

### 3.4 Eliminación duplicados financial_autonomy

```python
# ELIMINAR (mantener en bridge/):
# financial_autonomy/trust_score_integration.py
# financial_autonomy/financial_autonomy_bridge.py
# (Conservar en bridge/ como versiones definitivas)
```

---

## 4. FASE 3: ARCHIVAR HISTORIAL DE OPERACIONES

### 4.1 tmp_agent/ops/ - 500+ carpetas
**Prioridad:** MEDIA | **Tiempo estimado:** 2 horas | **Espacio:** ~100+ MB

```powershell
# Crear estructura de archivo
New-Item -ItemType Directory -Force -Path "ARCHIVE/operations_$(Get-Date -Format 'yyyy')"

# Mover operaciones antiguas (>60 días)
$cutoffDate = (Get-Date).AddDays(-60)
Get-ChildItem -Path "tmp_agent/ops/" -Directory | 
    Where-Object {$_.LastWriteTime -lt $cutoffDate} |
    ForEach-Object {
        $dest = "ARCHIVE/operations_$(Get-Date -Format 'yyyy')/$($_.Name)"
        Move-Item -Path $_.FullName -Destination $dest
    }

# Comprimir archivo anual
Compress-Archive -Path "ARCHIVE/operations_$(Get-Date -Format 'yyyy')" -DestinationPath "ARCHIVE/operations_$(Get-Date -Format 'yyyy').zip"
Remove-Item "ARCHIVE/operations_$(Get-Date -Format 'yyyy')" -Recurse -Force
```

---

## 5. FASE 4: IMPLEMENTAR ROTACIÓN DE LOGS

### 5.1 Configurar rotación automática

```python
# log_rotation_config.py
import logging
from logging.handlers import RotatingFileHandler
import os

LOG_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'rotating_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/brain.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'level': 'INFO',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
        }
    },
    'loggers': {
        'brain': {
            'handlers': ['rotating_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        }
    }
}
```

### 5.2 Script de limpieza diaria

```powershell
# daily_cleanup.ps1
# Ejecutar como tarea programada diaria

# Limpiar logs >30 días
$cutoffDate = (Get-Date).AddDays(-30)
Get-ChildItem -Path "*/logs/*" -Include "*.log", "*.ndjson" | 
    Where-Object {$_.LastWriteTime -lt $cutoffDate -and $_.Name -notlike "*current*"} |
    Remove-Item -Force

# Limpiar archivos temporales
Get-ChildItem -Path "*/tmp/*" | 
    Where-Object {$_.LastWriteTime -lt (Get-Date).AddDays(-7)} |
    Remove-Item -Recurse -Force

# Reporte
Write-Host "Limpieza completada: $(Get-Date)"
```

---

## 6. CHECKLIST DE VERIFICACIÓN

### Pre-Depuración
- [ ] Backup completo del sistema
- [ ] Documentar estado actual
- [ ] Verificar servicios en ejecución

### Durante Depuración
- [ ] Revisar cada archivo antes de eliminar
- [ ] Verificar dependencias
- [ ] Probar servicios después de cada cambio

### Post-Depuración
- [ ] Verificar sistema operativo
- [ ] Ejecutar tests de regresión
- [ ] Documentar espacio liberado
- [ ] Actualizar FULL_ADN_INTEGRAL.json

---

## 7. MÉTRICAS DE ÉXITO

**Objetivos:**
- Reducir archivos totales de 350 a ~200 (proyecto real)
- Liberar 300-450 MB de espacio
- Eliminar 100% de duplicados críticos
- Implementar rotación de logs automática
- Reducir tiempo de carga/inicio en 30%

**Indicadores:**
- `du -sh C:\AI_VAULT` < 500 MB (objetivo)
- `find . -name "*.bak_*" | wc -l` = 0
- `find . -name "*.pyc" | wc -l` = 0
- `find . -name "__pycache__" | wc -l` = 0

---

## 8. RIESGOS Y MITIGACIÓN

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Eliminación accidental de archivo crítico | Baja | Alto | Backup completo antes de iniciar |
| Pérdida de historial importante | Media | Medio | Archivar, no eliminar historial >60 días |
| Fallo de servicios después de limpieza | Baja | Alto | Tests de regresión obligatorios |
| Duplicados necesarios para rollback | Baja | Medio | Mantener últimas 3 versiones LKG |

---

## 9. SIGUIENTE PASO: FORTALECIMIENTO SISTÉMICO

Una vez completada la depuración, proceder con:

1. **Consolidación de Arquitectura**
2. **Implementación de Testing Automatizado**
3. **Mejoras de Seguridad**
4. **Optimización de Rendimiento**
5. **Documentación Completa**

Ver documento: `PLAN_FORTALECIMIENTO_SISTEMICO.md`

---

## 10. BITÁCORA DE DEPURACIÓN

| Fecha | Acción | Archivos | Espacio Liberado | Responsable | Estado |
|-------|--------|----------|------------------|-------------|--------|
| 2026-03-19 | Creación del plan | - | - | Sistema | ✅ COMPLETADO |
| | | | | | |

---

**Notas:**
- Este plan debe ejecutarse durante horario de mantenimiento
- Todos los cambios deben registrarse en la bitácora
- Ejecutar en orden: Fase 1 → Fase 2 → Fase 3 → Fase 4
- No omitir fases sin aprobación explícita
