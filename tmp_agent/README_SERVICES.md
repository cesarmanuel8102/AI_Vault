# AI_VAULT - Resumen de Configuración

## ✅ TAREA COMPLETADA: Sistema de Aprendizaje

Se implementó el sistema de aprendizaje para Brain V9 con:
- Forzado de ejecución después de 3 skips consecutivos
- Registro de U History
- Contador de skips
- Dashboard mejorado con métricas de aprendizaje

## 🚀 INICIAR SERVICIOS AHORA

### Opción 1: Diagnóstico Completo (Recomendado)
Haz doble clic en:
```
C:\AI_VAULT\tmp_agent\diagnose_and_start.bat
```

Esto:
1. Verifica Python y dependencias
2. Libera puertos ocupados
3. Mata procesos previos
4. Inicia servicios con ventanas visibles (para ver errores)
5. Verifica que funcionan

### Opción 2: Inicio Silencioso (Después de confirmar que funcionan)
Haz doble clic en:
```
C:\AI_VAULT\tmp_agent\start_now.bat
```

## 📁 ARCHIVOS CREADOS

### Sistema de Aprendizaje
- `brain_v9/util.py` - Contador de skips
- `brain_v9/trading/utility_util.py` - Historial de U
- `brain_v9/config.py` - Configuración de rutas
- Checkpoint: `checkpoint_v9_learning_system_2026-03-25_19-07.md`

### Auto-inicio
- `services_manager.ps1` - Control de servicios
- `start_now.bat` - Inicio silencioso
- `start_clean.py` - Inicio controlado
- `diagnose_and_start.bat` - Diagnóstico y arranque
- `setup_autostart.ps1` - Configurar auto-inicio

## 🔧 COMANDOS MANUALES

Si necesitas iniciar manualmente desde CMD:

```batch
:: Brain V9
cd C:\AI_VAULT\tmp_agent
python -m brain_v9.main

:: Dashboard (en otra ventana)
cd C:\AI_VAULT\00_identity\autonomy_system
python dashboard_server.py
```

## 🌐 ACCESO

Una vez iniciados:
- **Brain V9**: http://127.0.0.1:8090
- **Dashboard**: http://127.0.0.1:8070
- **Dashboard operativo real**: http://127.0.0.1:8090/dashboard

## 📊 DASHBOARD MEJORADO

El dashboard ahora muestra:
- **Skips Consecutivos**: Contador con alerta de forzado
- **Trades Hoy**: Contador diario
- **Estado Ejecución**: Indica si está pausado o ejecutando
- Loop Autónomo con información detallada de skips
- **Modo Operativo**: Contexto real del fair test PO OTC
- **Fair Test PO**: Progreso 50 trades, filtros activos y estado de captura oficial
- **Mantenimiento**: Estado de `Brain V9`, `PO Bridge`, `Edge`, `IBKR Gateway`, `brain_watchdog` y acciones remotas básicas
- En `8090/dashboard`:
  - `Modo Operativo`: fair test PO OTC y blockers actuales
  - `Mantenimiento`: estado y acciones del runtime real de Brain V9
  - `Platforms`: foco operativo visible, `Selected Platform` explícito y comparación sin etiquetas ambiguas de `Best/Worst`
  - `Platforms`: `U Score` canónico desde `tmp_agent/state/platforms/*_u.json`, más `Lifetime Trades` y snapshot live de `IBKR` (`positions`, `accounts`)
  - `Platforms`: `Platform Comparison` conserva `N/A` cuando una plataforma está en `monitoring_live_positions` o `inactive`; ya no convierte `null` en `0.0000`
  - `Platforms`: la tabla compara `Resolved PnL` y `Resolved Trades` canónicos; la actividad broker live se lee en la card individual de la plataforma
  - `Platforms`: `Pocket Option` ya no mezcla `U` basado en performance histórica con un `Win Rate` corto del sample actual; la card distingue `Resolved Sample WR` de `Reference Win Rate`, y `Platform Comparison` usa `Reference WR / Reference PnL / Reference Trades` según la misma base del `U`
  - `Overview`: `Recent Activity` y `Platform U Scores` usan la misma semántica; `IBKR` muestra `live positions | no resolved sample` en vez de fingir `0 trades`
  - `Overview`: `Utility U (Effective)` deja explícito que el KPI global usa el alineamiento `governance + real venue guardrail`; no es el mismo concepto que el `U` por plataforma
  - `Overview`: `Venue Anchor` muestra el peor `U` numérico real de venue y `Governance U` deja aislado el componente de gobernanza
  - `Overview`: el KPI `Canonical Top` y el bloque `Top Ranked Candidates` separan `top canónico` de `ranking técnico`, evitando mezclar una selección ausente con el edge del líder rankeado
  - `Overview`, `Platforms` y `Strategy Engine`: estados `loading / empty / error / info` ya usan un contrato común con roles semánticos y `aria-live`, reduciendo ambigüedad visual y técnica
  - `Overview`: franja ejecutiva `Decision Frame / Focus Lane / Sample Pressure / Infrastructure` para lectura operativa en segundos
  - `Overview`: nota explícita para distinguir `Utility U (Effective)` de `Venue Anchor`
  - `Mantenimiento`: `IBKR Gateway` usa proceso + puerto + snapshot live read-only; ya no cae a `running` solo porque el probe artifact quede stale mientras el gateway siga conectado
  - `Strategy Engine`: separación entre `Canonical Top` y `Ranked Leader` para no inventar liderazgo cuando `top_strategy=null`
  - `Strategy Engine`: `Selection Semantics`, `Operating Summary` y `Global Ranked Candidates` separan decisión canónica, ranking técnico y foco operativo
  - `Strategy Engine`: sección `Focus Lane Strategies` para priorizar lectura operativa de la lane activa sin reescribir el ranking canónico
  - `8090/dashboard`: la capa reutilizable de presentación se sirve ahora desde `tmp_agent/brain_v9/ui/dashboard_components.js`, reduciendo el peso semántico del HTML principal
  - `8090/dashboard`: los paneles primarios `Overview`, `Platforms` y `Strategy Engine` ya se sirven desde `tmp_agent/brain_v9/ui/dashboard_primary_panels.js`
  - `8090/dashboard`: los paneles secundarios `Autonomy`, `Roadmap`, `Meta`, `Self-Improvement`, `System` y `Learning` ya se sirven desde `tmp_agent/brain_v9/ui/dashboard_secondary_panels.js`
  - `8090/dashboard`: normalización de payloads y view-models compartidos servidos desde `tmp_agent/brain_v9/ui/dashboard_view_models.js`
  - `8090/dashboard`: mejoras responsive y de accesibilidad servidas desde `tmp_agent/brain_v9/ui/dashboard_accessibility.css`
  - `8090/dashboard`: estilos base extraídos a `tmp_agent/brain_v9/ui/dashboard_core.css`; el HTML principal ya no carga un bloque `<style>` monolítico
  - `8090/dashboard`: smoke tests del frontend modular dentro de pytest validan sintaxis de assets JS con `node --check` y que `main.py` sirva `/dashboard` y assets críticos `/ui/...`
  - `8090/dashboard`: smoke de navegador real disponible en `tmp_agent/tests/ui/dashboard_browser_smoke.mjs`, usando `Microsoft Edge` headless + CDP contra el dashboard vivo para detectar excepciones JS y roturas de render
  - `8090/dashboard`: `Chart.js` ya no depende de `cdn.jsdelivr`; se sirve localmente desde `tmp_agent/brain_v9/ui/chart.umd.min.js`
  - `8090/dashboard`: favicon local servido desde `tmp_agent/brain_v9/ui/favicon.svg`, eliminando ruido `404 /favicon.ico` en browser smoke
  - `8090/dashboard`: `Learning` y `System` ya tienen franjas ejecutivas propias para bajar densidad cognitiva y separar decisión operativa de diagnóstico técnico
  - `8090/dashboard`: `Autonomy` y `Roadmap` ya tienen también franjas ejecutivas y notas semánticas, manteniendo un estándar de lectura operativa más consistente entre paneles
  - `8090/dashboard`: `Operating Context` y `Roadmap / Development` compactan listas largas (`Blockers`, `Next Actions`, `Current Work`, `Execution Blockers`) en chips resumidos para bajar densidad cognitiva sin perder verdad canónica
  - `8090/dashboard`: `Autonomy`, `Roadmap`, `Meta`, `System` y `Learning` usan también `tableWrap()` en tablas secundarias clave, manteniendo scroll horizontal controlado fuera de los paneles principales
  - `8090/dashboard`: listas compactadas de `Blockers`, `Next Actions` y bloques similares humanizan tokens internos en la UI, pero conservan el id crudo en tooltip para no perder trazabilidad canónica
  - `Platforms` y tablas clave: wrappers `table-wrap` para scroll horizontal controlado en anchos reducidos
  - `Platforms`: tabs accesibles por teclado (`tabindex`, `role=tab`, `aria-selected`, activación `Enter/Space`)
  - Plan maestro de subida a `10/10`: `tmp_agent/dashboard_frontend_10_plan_2026-04-02.md`

### Endpoints nuevos del Command Center

- `GET /api/command-center`
  expone `operating_context` con el estado del fair test
- `GET /api/maintenance/status`
  expone estado resumido de servicios y componentes de control
- `POST /api/maintenance/action`
  permite ejecutar acciones controladas de mantenimiento desde el dashboard
  hoy soporta `brain_v9`, `pocket_option_bridge`, `brain_watchdog` y `edge_browser` según script disponible

Referencia de sesión:
- `checkpoint_dashboard_command_center_2026-04-02.md`
- `checkpoint_brain_v9_dashboard_operator_context_2026-04-02.md`

## ⚠️ NOTA IMPORTANTE

Los servicios NO están corriendo actualmente. Por favor usa el archivo `diagnose_and_start.bat` para iniciarlos correctamente.

## 🔄 AUTO-INICIO

La tarea programada `AI_VAULT_AutoStart_Silent` está configurada para iniciar servicios automáticamente al loguearte (con 30 segundos de delay).

---
**Última actualización:** 2026-03-25 19:45 UTC
