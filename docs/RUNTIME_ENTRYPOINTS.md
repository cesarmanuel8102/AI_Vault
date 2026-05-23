# Runtime Entrypoints Documentation

## 1. Runtime Brain V9 Actual

### Launcher Real
- **Path**: `tmp_agent/brain_v9/start_full_server.py`
- **Uso**: `python tmp_agent/brain_v9/start_full_server.py`
- **Descripción**: Este es el launcher validado y activo para el runtime de Brain V9.

### App Module
- **Import Path**: `brain_v9.main:app`
- **Descripción**: Módulo ASGI/WSGI principal para Brain V9.

### Puerto Usual
- **Puerto**: 8090
- **Health Check**: `GET http://127.0.0.1:8090/health`
- **Chat Endpoint**: `POST http://127.0.0.1:8090/chat`

## 2. Root main.py

### Estado
- **Existe**: Sí, en raíz del repo (`C:\AI_VAULT\main.py`)
- **Estado**: NO asumir que es runtime activo de 8090
- **Regla**: Cualquier hallazgo en root main.py debe verificarse contra launcher real antes de modificar

### Verificación Requerida
```powershell
# Antes de tocar chat/runtime, ejecutar grep
grep -r "8090" tmp_agent/brain_v9/start_full_server.py
grep -r "brain_v9" tmp_agent/brain_v9/start_full_server.py
```

## 3. Memoria Semántica

### Endpoint
- **Estado**: Endpoint explícito/protegido de Brain V9 si existe
- **Restricción**: NO escritura desde P2-E dry-run
- **Restricción**: NO llamar endpoint en este ciclo
- **Archivos**: memory/semantic/*

### Política
- Toda escritura a FAISS/vectores debe pasar por governance gate
- P2-E es dry-run: simula promoción sin escribir realmente

## 4. ProjectStateProvider

### Función
- **Fuente**: Local para estado P2
- **Root Canónico**: Usa repo root canónico (`C:\AI_VAULT`)
- **Integración**: Integrado al chat para respuestas grounded

### Archivos Relacionados
- `brain/project_state_provider.py`
- Tests en `tests/unit/test_project_state_provider.py`

## 5. Reglas de Verificación

### Antes de Cualquier Cambio Runtime
1. Verificar launcher real: `tmp_agent/brain_v9/start_full_server.py`
2. Verificar app real: `brain_v9.main:app`
3. Verificar que el cambio afecta el entrypoint real, no el root main.py
4. Ejecutar smoke tests después del cambio

### Prohibiciones
- NO modificar `session.py` sin characterization tests
- NO modificar `main.py` raíz sin verificar impacto en Brain V9
- NO modificar `tmp_agent/brain_v9/main.py` sin smoke tests
- NO activar escritura real de memoria sin governance gate
- NO activar trading real sin approval explícito

## 6. Checklist de Verificación Pre-Cambio

```powershell
# 1. Puerto activo
netstat -ano | findstr "8090"

# 2. Health check (si está activo)
curl -s http://127.0.0.1:8090/health

# 3. Verificar launcher real existe
Test-Path "tmp_agent/brain_v9/start_full_server.py"

# 4. Verificar no hay archivos prohibidos modificados
git status --short | findstr "memory/semantic"
git status --short | findstr "tmp_agent/strategies"
git status --short | findstr "tmp_agent/reports"
```
