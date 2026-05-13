# Checkpoint: Dashboard Command Center y Mantenimiento

**Fecha:** 2026-04-02  
**Ámbito:** `00_identity/autonomy_system/dashboard_server.py` + `00_identity/autonomy_system/unified_dashboard.html`

## Objetivo

Reordenar el dashboard unificado para que exprese la verdad operativa actual del Brain sin cambiar su funcionamiento:

- exponer el contexto del fair test PO OTC como capa ejecutiva
- mantener la apariencia general del dashboard
- añadir un panel de mantenimiento con estado y acciones de servicios
- no interferir con el runtime principal ni con desarrollos paralelos

## Cambios implementados

### 1. Contexto operativo canónico

Se añadió `operating_context` dentro de `/api/command-center` con:

- `mode=baseline_data_collection`
- `decision_framework` del fair test de 50 trades
- progreso del test: `executed_trades`, `resolved_trades`, `wins`, `losses`, `win_rate`, `expectancy_per_trade`
- lane actual: `platform`, `venue`, `symbol`, `timeframe`, `setup_variant`
- filtros activos:
  - `put_only`
  - `min_signal_reasons`
  - `call_block_enabled`
  - `blocked_regimes`
  - `hour_filter` con distinción entre activo y desactivado para baseline
  - `duration_targets`
- estado de captura oficial de `closed_trades`

Esto permite que el dashboard deje de obligar al operador a reconstruir manualmente la situación real del sistema.

### 2. Panel de mantenimiento

Se añadieron:

- `GET /api/maintenance/status`
- `POST /api/maintenance/action`

Componentes expuestos:

- `brain_v9`
- `pocket_option_bridge`
- `edge_browser`
- `ibkr_gateway`
- `brain_watchdog`
- `dashboard_8070`
- `closed_trades_pipeline`

Acciones soportadas:

- `brain_v9`: `start`, `restart`, `stop`
- `pocket_option_bridge`: `start`, `restart`, `stop`
- `brain_watchdog`: `start`, `stop`
- `edge_browser`: `restart` si existe `C:/Users/<user>/restart_edge.ps1`

Notas:

- `edge_browser` se reporta por proceso real `msedge.exe` y frescura del `browser_bridge_latest.json`
- `ibkr_gateway` se reporta por `ibgateway.exe`, puerto `4002` y probe canónico `ibkr_marketdata_probe_status.json`
- `closed_trades_pipeline` es observabilidad, no un proceso arrancable
- el panel está diseñado para no tocar la lógica de trading ni el runtime interno

### 3. Rejerarquización visual en `unified_dashboard.html`

Se añadieron secciones superiores:

- `Modo Operativo`
- `Fair Test PO OTC`
- `Mantenimiento`

El resto de secciones técnicas se conserva:

- roadmap
- utility governance
- strategy engine
- plataformas
- monitor

La intención es que el usuario vea primero:

1. qué experimento está activo
2. cuál es el estado de decisión
3. qué servicios están arriba o abajo
4. qué necesita atención manual

## Tests agregados

Archivo nuevo:

- `tmp_agent/tests/ui/test_unified_dashboard_command_center_p54.py`

Cobertura:

- presencia de secciones nuevas en el HTML servido
- contrato de `operating_context` en `/api/command-center`
- contrato de `/api/maintenance/status`
- respuesta de `/api/maintenance/action`

## Verificación ejecutada en sesión

### Sintaxis

- `python -m py_compile 00_identity/autonomy_system/dashboard_server.py`

### Endpoints

- `http://127.0.0.1:8070/api/health`
- `http://127.0.0.1:8070/api/command-center`
- `http://127.0.0.1:8070/api/maintenance/status`
- `http://127.0.0.1:8070/api/maintenance/action`

### HTML servido

Verificado que el HTML publicado por `8070` contiene:

- `id="operating-mode"`
- `id="fair-test"`
- `id="maintenance"`
- referencias a `/api/maintenance/status`

## Estado final observado

- `Brain V9`: saludable
- `PO Bridge`: saludable
- `closed_trades_pipeline`: pendiente hasta validar captura oficial desde Edge/PO UI
- `brain_watchdog`: el dashboard lo refleja según detección real de proceso visible
- `edge_browser`: se marca saludable solo si Edge está corriendo y el bridge sigue fresco
- `ibkr_gateway`: queda visible en el mismo panel con estado de proceso, puerto y probe

## Siguiente paso recomendado

No tocar la lógica operativa desde este frente. Los siguientes cambios razonables en dashboard son:

- mostrar explícitamente `sin dato` vs `bloqueado` vs `pendiente manual`
- añadir cards de observabilidad para `runner QC V10.13b` cuando exista una fuente canónica estable
- documentar en README de servicios el uso del panel de mantenimiento
