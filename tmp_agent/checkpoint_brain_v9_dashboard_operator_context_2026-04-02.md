# Checkpoint: Dashboard Operativo en 8090

**Fecha:** 2026-04-02  
**Ámbito:** `tmp_agent/brain_v9/main.py` + `tmp_agent/brain_v9/ui/dashboard.html`

## Objetivo

Corregir el frente equivocado y llevar el trabajo al dashboard real del operador:

- `8090/dashboard`
- mantener la apariencia actual
- reordenar la información para que refleje la verdad operativa del fair test
- añadir mantenimiento visible y accionable desde el propio Brain V9

## Cambios implementados

### 1. Contexto operativo canónico en 8090

Se añadió:

- `GET /brain/operating-context`

Expone:

- modo activo `baseline_data_collection`
- marco del fair test de `50` trades
- progreso real desde el ledger paper
- `win_rate`, `expectancy_per_trade`, `net_profit`
- lane activa `pocket_option / EURUSD_otc / 1m`
- filtros operativos relevantes
- estado de `closed_trades`
- blockers y next actions

### 2. Panel de mantenimiento en 8090

Se añadieron:

- `GET /brain/maintenance/status`
- `POST /brain/maintenance/action`

Componentes visibles:

- `brain_v9`
- `pocket_option_bridge`
- `edge_browser`
- `ibkr_gateway`
- `brain_watchdog`
- `closed_trades_pipeline`

Acciones soportadas:

- `brain_v9`: `restart`
- `pocket_option_bridge`: `start`, `restart`, `stop`
- `brain_watchdog`: `start`, `stop`
- `edge_browser`: `restart` si existe `restart_edge.ps1`

### 3. Rejerarquización en `dashboard.html`

En `Overview` ahora aparecen primero:

- `Modo Operativo`
- `Mantenimiento`

En `System Health` ahora aparecen además:

- `Operating Context`
- `Maintenance Controls`
- `Maintenance Log`

No se cambió el lenguaje visual base del dashboard.

### 4. Corrección semántica en `Platforms` y `Strategy Engine`

Se corrigió un problema de integridad visual:

- si `ranking-v2.top_strategy = null`, la UI ya no inventa un `Top Strategy` usando el primer `ranked`
- el dashboard ahora distingue explícitamente entre:
  - `Canonical Top`
  - `Ranked Leader`

Además:

- `Platforms` muestra `Operating Focus` con la lane activa del fair test
- `Platforms` distingue `Focus Platform` de `Selected Platform` para no mezclar la lane operativa con el tab inspeccionado
- los tabs de plataforma ya no dependen de `textContent`, así que el badge `[focus]` no rompe el estado visual del tab activo
- el resumen de comparación usa `Ranked Leader` y `Last By Ranking` en vez de `Best/Worst`, evitando contradicciones cuando el backend expone heurísticas distintas
- `Platform Comparison` ya no degrada `U = null` a `0.0000`; las plataformas en monitoreo o inactivas se muestran como `N/A` y no se rankean como si tuvieran `U` numérico
- `Platform Comparison` marca la plataforma foco con badge `focus`
- `Platform Comparison` renombra columnas a `Resolved PnL` y `Resolved Trades`, y añade una nota visible de que la tabla compara muestra resuelta canónica, no actividad live del broker
- la card de cada plataforma añade una nota contextual según `display_basis`, por ejemplo en `IBKR`: hay posiciones live, pero `U` permanece `N/A` hasta tener muestra resuelta canónica del Brain
- `Overview` se alinea con esa misma semántica:
  - `Recent Trades` pasa a `Recent Activity`
  - `broker_position` se etiqueta como `open-position`
  - el mini panel `Platform U Scores` distingue entre `resolved sample`, `live positions` e `inactive`, en vez de mostrar genéricamente `0 trades`
  - el KPI superior `Utility U` se reetiqueta como `Utility U (Effective)` y muestra `alignment_mode`, `governance_u_score` y `venue guardrail`, para no confundirlo con el `U` de performance por plataforma
  - `Overview` añade `Venue Anchor` y `Governance U` como KPIs separados, para que el `effective U` no esconda la severidad real de la venue ni mezcle control global con performance canónica
  - el KPI `Top Strategy` se corrige a `Canonical Top`; cuando no existe top canónico, la UI muestra `none_selected` y usa el subtítulo `ranked leader ... | edge ...` sin fingir que existe una estrategia top seleccionada
  - el bloque lateral se renombra a `Top Ranked Candidates`, porque lista ranking técnico y no una selección operativa definitiva
- el panel de mantenimiento de `IBKR Gateway` ya no depende solo del artifact `ibkr_marketdata_probe_status.json`; ahora combina proceso, puerto y snapshot live read-only del mismo backend canónico usado por `Platforms`, evitando falsos `running` cuando la UI de IBKR ya está conectada
- `Strategy Engine` muestra `Operating Focus` con:
  - lane activa
  - `Canonical Top`
  - `Ranked Leader`
  - blocker principal
- `Strategy Engine` añade `Focus Lane Strategies` para mostrar primero las estrategias relevantes al fair test actual sin alterar el ranking canónico subyacente
- la tabla de ranking marca qué estrategias pertenecen a la lane foco del fair test
- `Ready Now` se reetiquetó como `Signal Ready` para no sugerir erróneamente que una estrategia bloqueada ya está aprobada para operar

### 4b. Fase 1 de endurecimiento frontend

Se empezó la subida estructural del dashboard hacia un estándar frontend más alto sin cambiar lógica del Brain:

- se añadió un plan explícito de mejora a `10/10` en `tmp_agent/dashboard_frontend_10_plan_2026-04-02.md`
- `dashboard.html` ahora tiene helpers reutilizables para:
  - `renderKpiCard`
  - `renderUiState`
  - `renderTargetHtml`
  - `noteBlock`
- los estados `loading / empty / error / info` dejan de ser cadenas sueltas dispersas y pasan a tener:
  - clase común
  - `data-state-kind`
  - `role=status` o `role=alert`
  - `aria-live`
- esto ya se aplica en los bloques principales de:
  - `Overview`
  - `Platforms`
  - `Strategy Engine`
  - feedback de mantenimiento

Objetivo de esta fase:

- reducir fragilidad del render
- unificar la semántica de ausencia de datos
- dejar base para seguir subiendo el dashboard sin volver a introducir contradicciones

### 4c. Fase 2 de jerarquía operativa

Se empezó la capa ejecutiva del dashboard sin alterar el runtime:

- `Overview` añade `overview-decision-strip` con cuatro tarjetas ejecutivas:
  - `Decision Frame`
  - `Focus Lane`
  - `Sample Pressure`
  - `Infrastructure`
- `Overview` añade una nota semántica explícita bajo KPIs:
  - `Utility U (Effective)` no debe leerse como sinónimo de `Venue Anchor`
- `Strategy Engine` añade:
  - `strategy-decision-strip`
  - `Selection Semantics`
  - `Operating Summary`
- el bloque de ranking se renombra a `Global Ranked Candidates`
- el ranking y la validación ahora incluyen notas visibles para separar:
  - ranking técnico global
  - selección canónica
  - foco operativo
  - estado de validación

Objetivo de esta fase:

- bajar el tiempo de comprensión del operador
- dejar claro qué decide y qué solo diagnostica
- evitar que una estrategia bien rankeada parezca automáticamente operativa

### 4d. Modularización parcial del frontend

Se redujo la concentración de responsabilidad del HTML principal:

- se creó `tmp_agent/brain_v9/ui/dashboard_components.js`
- la capa reutilizable de presentación y helpers se movió ahí:
  - utilidades de formato
  - estados UI
  - helpers de KPIs
  - helpers ejecutivos
  - helpers de mantenimiento
  - semántica de `Platforms` y `Strategy Engine`
- `dashboard.html` ahora carga ese módulo por `script src="/ui/dashboard_components.js"`
- el HTML inline conserva el flujo específico de refresh por panel, pero ya no carga con toda la semántica reutilizable

Objetivo de esta fase:

- bajar deuda técnica
- hacer el dashboard menos frágil a futuras correcciones
- abrir camino a seguir separando `presentation layer` del flujo de paneles

### 4e. Responsive y accesibilidad básica

Se añadió una capa externa de UX dura sin tocar el runtime:

- `tmp_agent/brain_v9/ui/dashboard_accessibility.css`
- `dashboard.html` ahora la carga como asset adicional

Mejoras aplicadas:

- foco visible en:
  - sidebar links
  - tabs de plataforma
  - botones de mantenimiento
- `table-wrap` con scroll horizontal controlado para tablas críticas
- tablas principales de:
  - `Overview`
  - `Platforms`
  - `Strategy Engine`
  - `Recent Activity`
  ya se renderizan con wrapper responsive
- `platform tabs` ahora exponen:
  - `tabindex`
  - `role=tab`
  - `aria-selected`
  - activación por teclado `Enter` / `Space`
- ajustes responsive adicionales para `topbar`, `content` y `section-body`

Objetivo de esta fase:

- que el dashboard no se rompa semánticamente al estrechar el ancho
- mejorar interacción sin depender solo del mouse

### 4f. Extracción del CSS principal

Se dio otro paso de modularización estructural:

- se creó `tmp_agent/brain_v9/ui/dashboard_core.css`
- el HTML principal ya no contiene el gran bloque `<style>...</style>`
- `dashboard.html` ahora carga:
  - `dashboard_core.css`
  - `dashboard_accessibility.css`
  - `dashboard_components.js`

Objetivo de esta fase:

- reducir peso y responsabilidad del HTML embebido
- facilitar mantenimiento visual sin tocar el archivo principal
- dejar el dashboard servido como composición de assets reales, no como página monolítica cerrada

### 4g. Extracción del runtime del dashboard

Se separó otra responsabilidad del HTML principal:

- `tmp_agent/brain_v9/ui/dashboard_runtime.js`

Ahora ese módulo concentra:

- `panelNames`
- `showPanel`
- `refreshCurrentPanel`
- `startAutoRefresh`
- `initDashboardRuntime`

Con esto:

- el HTML principal ya no define navegación ni dispatcher de refresh
- `dashboard.html` solo inicializa `DOMContentLoaded -> initDashboardRuntime`

Objetivo de esta fase:

- separar `presentation`, `assets` y `runtime UI`
- seguir rompiendo el monolito sin tocar el backend

### 4h. Extracción de paneles primarios

Se modularizó la lógica más pesada que seguía dentro de `dashboard.html`:

- se creó `tmp_agent/brain_v9/ui/dashboard_primary_panels.js`
- ahí viven ahora:
  - `refreshOverview`
  - `refreshOverviewTrades`
  - `refreshPlatforms`
  - `renderPlatformView`
  - `switchPlatform`
  - `refreshStrategy`
- `dashboard.html` ya no contiene ese bloque extenso; conserva solo:
  - helper API mínimo
  - wiring de assets
  - paneles secundarios no extraídos aún

Objetivo de esta fase:

- reducir tamaño y acoplamiento del HTML principal
- mover los paneles más sensibles a un asset propio
- preparar la siguiente ronda de modularización por dominio sin tocar el backend

### 4i. Extracción de paneles secundarios

Se continuó la modularización del frontend del dashboard:

- se creó `tmp_agent/brain_v9/ui/dashboard_secondary_panels.js`
- ahí viven ahora los paneles restantes:
  - `Autonomy`
  - `Roadmap`
  - `Meta`
  - `Self-Improvement`
  - `System`
  - `Learning`
- también se movieron:
  - `renderSessionWRChart`
  - `renderConfidenceChart`

Con esto:

- `dashboard.html` queda reducido casi por completo a shell estructural + asset wiring + helper API mínimo
- la lógica de refresh por panel ya no está embebida en el HTML principal

Objetivo de esta fase:

- seguir rompiendo el monolito
- dejar separado `layout`, `runtime`, `panel renderers` y `styles`
- preparar una futura capa de view-models sin tocar el backend

### 4j. Capa de view-models

Se añadió una capa explícita entre payload canónico y render:

- `tmp_agent/brain_v9/ui/dashboard_view_models.js`

Helpers introducidos:

- `asArray`
- `platformTradeArray`
- `platformHistoryArray`
- `deriveVenueAnchor`
- `deriveOverviewPlatformRow`
- `derivePlatformContextNote`
- `deriveCanonicalTopState`
- `deriveFocusStrategies`
- `normalizeReports`
- `normalizeSessionRows`
- `normalizeAdaptationItems`

Aplicación real:

- `dashboard_primary_panels.js` ya usa esa capa para:
  - anchor de venue
  - filas de plataformas en overview
  - normalización de trades e history
  - top canónico vs ranked leader
  - estrategias foco
- `dashboard_secondary_panels.js` ya la usa para:
  - normalización de reports
  - filas de session windows
  - items de adaptación

Objetivo de esta fase:

- reducir duplicación de normalización
- bajar fragilidad frente a cambios menores de shape
- acercar el frontend a una arquitectura con view-models reales sin tocar backend

### 5. Corrección canónica del backend de `Platforms`

Se corrigió una falsedad real del backend de plataformas:

- la tarjeta estaba recalculando `U Score` desde `scorecards/ledger` del fair test reseteado
- eso borraba el `u_proxy` canónico guardado en `tmp_agent/state/platforms/*_u.json`
- además `IBKR` dependía demasiado de un probe que podía fallar por `clientId already in use`

Ahora:

- `U Score` usa el estado canónico de plataforma (`*_u.json`)
- se siguen mostrando los `resolved trades` del experimento actual
- además se expone contexto de plataforma viva:
  - `Lifetime Trades`
  - `Open Entries`
  - `IBKR Live Positions`
  - `IBKR Open Trades`
  - `Accounts Visible`
- `Pocket Option` ya no mezcla `U` basado en `lifetime_performance` con un `Win Rate` de muestra resuelta corta:
  - la card distingue `Resolved Sample WR` de `Reference Win Rate`
  - la base de referencia se expone como `Reference Basis`
  - `Platform Comparison` usa `Reference WR / Reference PnL / Reference Trades` alineados con la misma base que el `U` mostrado

Para `IBKR`, el dashboard usa un snapshot read-only en subprocess hacia `IB Gateway`, evitando conflictos con el event loop del runtime principal.

## Tests agregados

Archivo nuevo:

- `tmp_agent/tests/ui/test_brain_v9_dashboard_operator_context.py`

Cobertura:

- contrato HTML del dashboard real `8090`
- helper de `operating_context`
- helper de `maintenance_status`
- acción de restart de Edge
- separación semántica entre `Canonical Top` y `Ranked Leader`
- smoke de assets modulares del dashboard:
  - `node --check` sobre `dashboard_components.js`, `dashboard_view_models.js`, `dashboard_primary_panels.js`, `dashboard_secondary_panels.js`, `dashboard_runtime.js`
  - rutas HTTP reales `/dashboard`, `/ui/dashboard_primary_panels.js` y `/ui/dashboard_runtime.js` servidas por `main.py`
- smoke opcional de navegador real:
  - `tmp_agent/tests/ui/dashboard_browser_smoke.mjs`
  - usa `Microsoft Edge` headless + CDP contra `http://127.0.0.1:8090/dashboard`
  - falla si detecta excepciones JS, `Refresh error`, `... is not defined` o estados `data-state-kind="error"` persistentes
  - incorpora un reintento para filtrar flakes transitorios tipo `ERR_NETWORK_CHANGED`
  - el wrapper pytest usa puerto CDP dinámico para evitar colisiones entre procesos headless

### 6. Eliminación de dependencia externa para gráficos

Se quitó la dependencia del CDN de `Chart.js` en el dashboard real:

- `dashboard.html` ahora carga `/ui/chart.umd.min.js`
- se vendorizó `Chart.js v4.4.7` en `tmp_agent/brain_v9/ui/chart.umd.min.js`
- esto elimina warnings de privacidad/Tracking Prevention ligados a `cdn.jsdelivr.net` y reduce fragilidad del render
- se añadió favicon local `tmp_agent/brain_v9/ui/favicon.svg` y `dashboard.html` ahora lo referencia con `rel="icon"`, eliminando el `404 /favicon.ico` en el smoke browser

### 7. Rejerarquización operativa de paneles secundarios

Se bajó la densidad cognitiva en paneles secundarios sin tocar el runtime:

- `Learning` ahora abre con `learning-decision-strip`
  - `Learning Posture`
  - `Adaptation Coverage`
  - `Post-Trade Evidence`
  - `Audit Integrity`
- `Learning` añade `learning-note` para separar evidencia de aprendizaje, cobertura de adaptación y calidad de auditoría
- `System` ahora abre con `system-decision-strip`
  - `Runtime Health`
  - `Safety Policy`
  - `Pipeline Confidence`
  - `Ops Dependencies`
- `System` añade `system-note` para separar contexto operativo, mantenimiento, health, pipeline y policy

Objetivo:

- responder primero `qué vigilar` y luego `qué detalle técnico lo respalda`
- reducir lectura técnica innecesaria antes de la toma de decisión

### 8. Rejerarquización operativa de `Autonomy` y `Roadmap`

Se alinearon `Autonomy` y `Roadmap` con la misma jerarquía operativa:

- `Autonomy` ahora abre con `autonomy-decision-strip`
  - `Loop Posture`
  - `Sample Accumulation`
  - `IBKR Ingest`
  - `Recent Diagnostics`
- `Autonomy` añade `autonomy-note` para separar salud de orquestación, acumulación de muestra e informes de diagnóstico
- `Roadmap` ahora abre con `roadmap-decision-strip`
  - `Canonical Phase`
  - `Development Execution`
  - `Acceptance Gate`
  - `Post-BL Continuation`
- `Roadmap` añade `roadmap-note` para separar gobernanza canónica, ejecución actual y continuidad post-BL

Objetivo:

- mantener el mismo estándar de lectura ejecutiva en todos los paneles importantes
- evitar que `Autonomy` y `Roadmap` queden como bloques densos puramente diagnósticos

### 9. Compactación visual de listas largas

Se redujo la densidad de lectura en bloques que seguían verbosos:

- `renderOperatingContext()` ahora usa un patrón reusable `compactListSection()`
  - `Blockers`
  - `Next Actions`
- `Roadmap / Development` también usa el mismo patrón para:
  - `Current Work`
  - `Execution Blockers`
- se añadieron `pill()` y estilos `.pill`, `.pill-row`, `.compact-list-section`

Objetivo:

- reducir escaneo vertical innecesario
- mantener la verdad canónica sin esconder severidad
- hacer más legible el dashboard cuando las listas crecen

### 10. Wrappers responsive consistentes en paneles secundarios

Se normalizó el uso de `tableWrap()` en tablas secundarias que aún salían "crudas":

- `Autonomy / Reports`
- `Roadmap / Post-BL items`
- `Meta / Domains`
- `System / Pipeline tests`
- `System / Platform policy`
- `Learning / Threshold adaptation`
- `Learning / ADN quality`

Objetivo:

- mantener scroll horizontal controlado también fuera de `Overview` y `Platforms`
- evitar ruptura visual en anchos medios o paneles con columnas largas

### 11. Humanización de tokens canónicos en bloques compactos

Se mejoró la lectura de listas compactadas sin alterar la verdad del backend:

- `compactListSection()` ahora usa `humanizeToken()`
- los chips muestran etiquetas legibles:
  - `no_positive_edge` -> `No Positive Edge`
  - `run_probation_carefully` -> `Run Probation Carefully`
- el id canónico bruto se conserva en `title` para inspección rápida al pasar el cursor

Objetivo:

- bajar traducción mental innecesaria
- mantener compatibilidad con ids internos del runtime

## Verificación ejecutada

- `python -m py_compile tmp_agent/brain_v9/main.py`
- `python -m pytest tmp_agent/tests/ui/test_brain_v9_dashboard_operator_context.py -q`

## Nota

El trabajo anterior en `8070` no era el frente visible principal del operador. Este checkpoint corrige esa desviación y mueve la capa operativa al dashboard embebido real de Brain V9.
