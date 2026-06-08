# FRONT-INFRA-03: Startup/Runbook Reproducibility

**Status:** COMPLETE ✅
**Date:** 2026-06-08
**Branch:** codex/own-capital-sustainable-return
**Head:** 2d19afc6

---

## 1. Objetivo

Documentar un runbook reproducible de arranque/parada/verificacion del runtime Brain (V9) sin modificar runtime productivo ni ejecutar acciones automaticas.

---

## 2. Alcance

- Inventario de entrypoints de arranque.
- Variables de entorno requeridas.
- Comando recomendado de arranque manual.
- Comando manual de parada.
- Health check.
- Port verification.
- Safe mode guidance.
- Precondiciones de git antes de operaciones criticas.
- Troubleshooting basico.

---

## 3. Out of Scope

- NO arrancar servidor automaticamente.
- NO parar servidor automaticamente.
- NO escribir en memory/semantic.
- NO modificar FAISS.
- NO promover conocimiento.
- NO aplicar patches.
- NO tocar trading/B8.
- NO modificar codigo de produccion.

---

## 4. Precondiciones Generales

Antes de operaciones criticas (commits, escrituras reales, rollback):
1. Verificar staged vacio: `git diff --cached --name-status`
2. Verificar branch correcta: `git branch --show-current`
3. Verificar HEAD sincronizado: `git rev-parse HEAD` == remote HEAD
4. Verificar runtime detenido: health check deve fallar conexion
5. Verificar .env configurado basado en .env.example

---

## 5. Variables de Entorno Requeridas (de .env.example)

| Variable | Default | Descripcion |
|---|---|---|
| BRAIN_PORT | 8090 | Puerto del servidor Brain V9 |
| BRAIN_HOST | 127.0.0.1 | Host del servidor |
| BRAIN_ADMIN_TOKEN | "" | Token para acceso admin (local no requerido) |
| BRAIN_SAFE_MODE | false | Si true, modo seguro restringido |
| BRAIN_START_AUTONOMY | false | Autonomia (requiere approval explicito) |
| BRAIN_START_PROACTIVE | false | Proactividad (requiere approval explicito) |
| BRAIN_START_SELF_DIAGNOSTIC | false | Auto-diagnostico |
| BRAIN_START_QC_LIVE_MONITOR | false | QC monitor en vivo |
| BRAIN_WARMUP_MODEL | false | Warmup de modelo |
| BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS | false | Endpoints /dev y /godmode (riesgo) |
| BRAIN_CHAT_DEV_MODE | false | Modo dev para chat |

**IMPORTANTE:** `BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS=true` habilita endpoints potencialmente peligrosos.

---

## 6. Comandos Recomendados de Arranque Manual

### Opcion A: Servidor completo

```bash
cd /c/AI_VAULT
python -m uvicorn tmp_agent.brain_v9.main:app --host 127.0.0.1 --port 8090
```

O usando FastAPI CLI nativo:
```bash
cd /c/AI_VAULT
python tmp_agent/brain_v9/start_full_server.py
```

### Opcion B: Servidor seguro (SAFE_MODE)

```bash
cd /c/AI_VAULT
BRAIN_SAFE_MODE=true python -m uvicorn tmp_agent.brain_v9.main:app --host 127.0.0.1 --port 8090
```

---

## 7. Comando Manual de Parada

En terminal separada (PowerShell):

```powershell
# Identificar PID del proceso Python en puerto 8090
$conn = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue
$pid = $conn | Select-Object -ExpandProperty OwningProcess | Select-Object -Unique
Write-Host "PID:" $pid

# Parar proceso
Stop-Process -Id $pid -Force
```

**Nota:** Este runbook NO ejecuta parada automaticamente.

---

## 8. Health Check

```bash
# Verificar si runtime esta activo
curl -s http://127.0.0.1:8090/health | python -m json.tool
```

**Respuesta expected (activo):**
```json
{
  "status": "healthy",
  "version": "9.0.0",
  "safe_mode": false
}
```

**Respuesta expected (detenido):**
```bash
curl: (7) Failed to connect to 127.0.0.1:8090
```

---

## 9. Verificacion de Puerto 8090

PowerShell:
```powershell
Get-NetTCPConnection -LocalPort 8090 -State Listen
```

Bash/Git Bash:
```bash
netstat -ano | grep 8090
```

Si hay un proceso escuchando en 8090, runtime esta activo.
Si no hay proceso, runtime esta detenido.

---

## 10. Prevencion de safe_mode:false Accidental

```bash
# Verificar safe_mode actual
curl -s http://127.0.0.1:8090/health | python -c "import sys,json; print(json.load(sys.stdin)['safe_mode'])"
```

Para forzar safe_mode:
```bash
BRAIN_SAFE_MODE=true python tmp_agent/brain_v9/start_full_server.py
```

---

## 11. Validacion Git antes de Operaciones Criticas

```bash
# 1. Staged vacio?
git diff --cached --name-status
# Expected: (nada)

# 2. Branch correcta?
git branch --show-current
# Expected: codex/own-capital-sustainable-return

# 3. HEAD sincronizado?
git rev-parse --short HEAD
git rev-parse --short origin/codex/own-capital-sustainable-return
# Expected: iguales

# 4. Runtime detenido?
python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=3)"
# Expected: Falla con UNAbleToConnectError
```

---

## 12. Stop Conditions

Detener el runtime manualmente ANTES de:
- Cualquier escritura real en memory/semantic (apend, delete, modify)
- Cualquier commit que modifique archivos productivos
- Cualquier patch o promotion
- Cualquier operacion de FAISS (rebuild, reindex, delete)

---

## 13. Troubleshooting

### Puerto 8090 ocupado
```powershell
Get-NetTCPConnection -LocalPort 8090 -State Listen
# Si responde, runtime ya esta activo
```

### safe_mode:false en produccion
- Verificar BRAIN_SAFE_MODE en .env
- Reiniciar runtime con BRAIN_SAFE_MODE=true

### Autonomia no controlada
- Asegurar BRAIN_START_AUTONOMY=false en .env
- Reiniciar runtime con autonomia desactivada

---

## 14. Safety Flags

- materialization_allowed_now: false
- patch_file_creation_allowed_now: false
- git_apply_allowed_now: false
- target_file_modification_allowed_now: false
- memory_write_allowed: false
- faiss_write_allowed: false
- real_write_allowed: false
- promotion_allowed: false

---

## 15. Explicit Statement

**This runbook does not start or stop the runtime by itself.**
**This runbook does not write to memory/semantic.**
**This runbook does not modify FAISS.**
**This runbook does not promote knowledge.**
**This runbook does not apply patches.**
**This runbook does not touch trading or B8.**

Todos los comandos aca listados son documentacion para uso manual del operador humano.
