# BRAIN LAB / AI_VAULT — ROADMAP MAESTRO CANÓNICO AL 101%

**Roadmap ID:** `BRAIN-101`
**Versión:** `1.0.0-reconstructed-glm-harmonized`
**Destinatario operativo:** Codex
**Propietario constitucional:** César Manuel
**Repositorio:** `cesarmanuel8102/AI_Vault`
**Rama de integración:** `codex/own-capital-sustainable-return`
**Arquitectura objetivo inmediata:** modular monolith estricto
**Agent Loop:** iniciado técnicamente, pero todavía no roadmap-aware
**Ejecutor preferido:** `ollama-cloud/kimi-k2.7-code`
**Supervisor:** Codex
**Autoridad humana final:** obligatoria
**Auto-merge:** prohibido
**Canonical local sync:** prohibido salvo autorización explícita
**Capital real:** no autorizado por este documento

---

## 0. MANDATO A CODEX

Codex queda encargado de llevar Brain Lab desde el HEAD remoto actual hasta:

```text
STATUS: BRAIN_101_CERTIFIED
```

La estructura permanente es:

```text
Constitución humana
  ↓
Roadmap canónico + manifest
  ↓
Codex: dirección técnica y supervisión
  ↓
Agent Loop: fábrica gobernada de cambios
  ↓
Kimi K2.7 Code: ejecutor de construcción
  ↓
Draft PR + CI + evidencia
  ↓
Revisión humana final
```

Brain y Agent Loop no son la misma entidad:

- **Brain** es el runtime cognitivo gobernado: interpreta, planifica, usa herramientas, recupera memoria y evalúa.
- **Agent Loop** es la fábrica autónoma de desarrollo: consume Issues, genera cambios y deja Draft PRs.
- **Codex** dirige, audita, revisa y mantiene el roadmap.
- **César** conserva la autoridad constitucional y el veto.

Codex no debe sustituir este roadmap, priorizar microservicios sobre gaps funcionales, habilitar auto-merge, habilitar canonical sync, autorizar dinero real ni declarar una fase cerrada porque el código existe o compila.

---

# 1. FUENTES Y LÍNEA BASE

## 1.1 Auditoría GLM 5.2 principal

```text
Archivo: FINAL_MICROSERVICES_AUDIT_REPORT (2).md
Fecha: 2026-07-16
Auditor: GLM 5.2
Rama: codex/own-capital-sustainable-return
HEAD auditado: 759edfb
Modo: read-only
```

Estado observado en ese HEAD:

- `main.py`: 4,606 → 2,441 líneas.
- Endpoints directos: 169 → 50.
- Routers: 8 → 23.
- `session.py`: 6,296 → 3,052 líneas.
- E2E: 3 → 5.
- Contract tests: 8 → 14.
- Modular monolith readiness: 60%.
- Overall microservices readiness: 40%.
- Distributed microservices readiness: 25%.
- `financial_autonomy/`: código válido, pero sin wiring runtime.
- `memory/semantic/*`: ownership ambiguo.
- PortfolioManager: ausente.
- Compliance: ausente.
- LiveTradingGate: ausente.
- Backtester local usable: ausente.
- `agent/tools.py` y `agent/loop.py` legacy aún presentes.
- CI primario todavía insuficiente.

## 1.2 Auditorías previas que siguen siendo referencias de riesgo

Auditoría externa del 2 de junio de 2026:

- credenciales en repositorio;
- GOD mode bypass;
- self-dev con capacidad de alterar governance;
- dev endpoints activos por defecto;
- ausencia de RBAC;
- testing de core insuficiente;
- autonomía fire-and-forget;
- ausencia de consola visual completa.

Auditoría financiera/Agent V2 del 18 de junio de 2026:

- Agent V2 canónico y gobernado existente;
- stack financiero paper-only existente;
- promotion pipeline con snapshot/rollback existente;
- risk contract canónico existente;
- no live trading;
- no backtester local usable;
- ausencia de PortfolioManager, Compliance y LiveTradingGate.

## 1.3 Trabajo posterior conocido

Después de `759edfb` hubo trabajo adicional, incluyendo reducción adicional de `main.py`, extracción de fastpaths y Tool01 gateway, hardening de Agent Loop v1.5.7, piloto Issue #33, Draft PR #34, scheduler activo y ejecución con `ollama-cloud/kimi-k2.7-code`.

**Regla:** todo hallazgo histórico debe reauditarse contra el HEAD remoto actual. No se permite marcarlo abierto o cerrado por memoria.

---

# 2. DEFINICIÓN OPERATIVA DE “101%”

## 2.1 El 100%

Brain está al 100% cuando se demuestra, en runtime y con evidencia:

1. Seguridad y secretos saneados.
2. Gobernanza fail-closed.
3. RBAC y approvals de un solo uso.
4. Modular monolith estricto.
5. Agent V2 como runtime cognitivo canónico.
6. Planner → Executor → Evaluator persistente.
7. Herramientas gobernadas.
8. Chat/UI coherente.
9. Memoria semántica con propietario único.
10. Promoción, recuperación y rollback reales.
11. Observabilidad y Visual Trace Console.
12. Agent Loop roadmap-aware.
13. Autoaprendizaje controlado.
14. Automejora controlada.
15. Motor financiero paper-only integral.
16. PortfolioManager.
17. Risk Engine.
18. Compliance.
19. Backtester local.
20. LiveTradingGate implementado y bloqueado por defecto.
21. CI, contratos, E2E y recovery suficientes.
22. Documentación y runbooks completos.

## 2.2 El 1% adicional

El 1% adicional exige resiliencia adversarial: crash recovery, corrupción simulada, pérdida de proveedor/red, rollback, restore, kill switch, FAISS rebuild, replay denial, scope denial, symlink/reparse denial, prompt-injection tests, soak test y cero afirmaciones sin evidencia.

## 2.3 Lo que 101% no autoriza

`BRAIN_101_CERTIFIED` no autoriza automáticamente capital real, auto-merge, ejecución P3, canonical sync, eliminación de autoridad humana, exposición ilimitada ni cambio de risk contract. La transición a dinero real requiere autorización constitucional separada y explícita.

---

# 3. FUENTES DE VERDAD CANÓNICAS

Codex debe crear y mantener:

```text
docs/roadmap/BRAIN_101_ROADMAP.md
docs/roadmap/BRAIN_101_MANIFEST.json
docs/roadmap/BRAIN_101_SCORECARD.json
ROADMAP_STATUS.json
docs/MIGRATION_CONTROL_LEDGER.md
```

## 3.1 Jerarquía

1. Decisiones explícitas de César.
2. `BRAIN_101_MANIFEST.json`.
3. `BRAIN_101_ROADMAP.md`.
4. `BRAIN_101_SCORECARD.json`.
5. `ROADMAP_STATUS.json`.
6. `MIGRATION_CONTROL_LEDGER.md`.
7. Issues/PRs.
8. Logs locales.

## 3.2 Campos obligatorios por Issue

```json
{
  "roadmap_id": "BRAIN-101",
  "roadmap_version": "1.0.0",
  "roadmap_sha256": "<sha256>",
  "roadmap_item_id": "R4.2",
  "objective": "<objetivo cerrado>",
  "expected_base_sha": "<sha>",
  "work_branch": "<branch>",
  "test_profile": "<perfil>",
  "allowed_paths": [],
  "forbidden_paths": [],
  "acceptance_criteria": [],
  "tests_required": [],
  "rollback_plan": [],
  "max_cycles": 3,
  "human_final_authority": true
}
```

El worker debe bloquear roadmap inexistente, hash incorrecto, versión no aprobada, task no registrado, dependencia abierta, base movida, path fuera de scope o perfil no autorizado.

---

# 4. DOCTRINA DE EJECUCIÓN

## 4.1 Un frente, una responsabilidad

No mezclar arquitectura y trading; memoria y governance; test-only y feature productiva sin justificación; migración y cambio de riesgo; limpieza masiva y funcionalidad.

## 4.2 Cierre real

Una tarea solo se considera `CLOSED_WITH_RUNTIME_EVIDENCE` cuando está fusionada, el runtime la usa, existe prueba positiva, prueba negativa, rollback, CI del mismo HEAD y actualización de scorecard/ledger.

No constituyen cierre: archivo creado, AST OK, compilación, unit test aislado, código desconectado, mock sintético o declaración del agente.

## 4.3 Clasificación de gates

```text
CONSTITUTIONAL
PRODUCTIVE_SAFETY
CONTRACTUAL
TEST_HARNESS
OPTIMIZATION
OPTIONAL
```

Solo los tres primeros bloquean una activación, salvo decisión explícita de César.

---

# 5. ROADMAP MAESTRO

## R0 — REBASELINE ACTUAL Y CANONIZACIÓN

**Objetivo:** convertir este documento en fuente de verdad del HEAD actual.

Trabajo:

- obtener HEAD remoto exacto;
- comparar `759edfb..HEAD`;
- inventariar merges y frentes posteriores;
- revalidar P0/P1;
- clasificar cada hallazgo como OPEN, PARTIALLY_CLOSED, CLOSED_WITH_RUNTIME_EVIDENCE, REGRESSED o SUPERSEDED;
- verificar Issue #33 y PR #34;
- verificar worker SHA, config SHA, scheduler, modelo y procesos;
- crear roadmap, manifest y scorecard;
- reconciliar `ROADMAP_STATUS.json` sin hash-chasing;
- registrar deuda residual.

Salida:

```text
R0_STATUS: CLOSED_WITH_RUNTIME_EVIDENCE
ROADMAP_VERSION: BRAIN-101-v1
```

No ejecutar frentes generales antes de cerrar R0.

## R1 — AGENT LOOP ROADMAP-AWARE

**Objetivo:** pasar del perfil `pilot` a una fábrica gobernada de roadmap.

Perfiles:

```text
audit-read-only
roadmap-doc
test-only
code-low-risk
code-governed
```

Trabajo:

- validar roadmap ID/version/hash;
- validar dependencias y base SHA;
- una tarea activa;
- rechazar Issues terminales, paths fuera de scope y base movida;
- Draft PR obligatorio;
- CI y supervisor en el mismo HEAD;
- evidence binding;
- no auto-merge;
- no canonical sync;
- recovery, idempotencia y evidencia estructurada;
- separación executor/supervisor.

Pruebas: Issue sin roadmap, hash incorrecto, dependencia abierta, base movida y scope violation deben bloquear. Roadmap-doc, test-only y code-low-risk deben producir Draft PR válido.

Salida:

```text
R1_STATUS: AGENT_LOOP_ROADMAP_AWARE
```

## R2 — SEGURIDAD CONSTITUCIONAL Y RBAC

**Objetivo:** ningún modo o componente puede evitar la constitución.

Trabajo:

- escaneo y rotación de secretos;
- historial Git auditado;
- dev endpoints OFF por defecto;
- RBAC: owner, operator, reviewer, executor y read-only;
- GOD local sin bypass P3;
- self-dev sin acceso a governance/risk/policy/workflows;
- approvals de un solo uso, expirables y ligados a actor/scope/hash;
- unificar sistemas de gate;
- proteger lifecycle endpoints;
- rate limiting y session isolation;
- append-only audit;
- threat model.

Tests: auth bypass, replay, expiry, wrong scope, wrong actor, P3 denial, self-dev denial, path traversal, symlink/reparse, prompt injection, cross-room, cross-user y dev-default denial.

Salida:

```text
R2_STATUS: GOVERNANCE_FAIL_CLOSED
```

## R3 — TESTING, CI, RECOVERY Y ROLLBACK

**Objetivo:** evidencia productiva suficiente.

Targets mínimos heredados de GLM:

- 12+ E2E relevantes;
- 20+ contract tests relevantes;
- unit tests de core;
- Windows/Ubuntu;
- PS5.1/PS7 donde corresponda.

Contratos: runtime, intent, planner, evaluator, finalizer, tool gateway, memory service, provider gateway, execution gate, strategy engine, financial autonomy, observability, dashboard y Agent Loop.

E2E: chat→intent→plan→tool→evaluate; brain evidence; mixed reasoning; promote→retrieve→use; rollback; FAISS rebuild; provider fallback; crash resume; Issue→commit→PR→CI→audit; auth denial; paper order; kill switch; state corruption recovery.

Salida:

```text
R3_STATUS: VERIFICATION_FOUNDATION_COMPLETE
```

## R4 — MODULAR MONOLITH ESTRICTO

**Objetivo:** cerrar Stage 1 antes de extraer servicios.

Targets:

- `session.py` < 1,500 LOC;
- `main.py` con máximo 10 endpoints directos de composición/health;
- `agent/tools.py` migrado o deprecado;
- `agent/loop.py` migrado o deprecado;
- interfaces internas explícitas;
- cero business logic en routers;
- cero state ownership ambiguo;
- feature flags y rollback por módulo.

Módulos objetivo: `session_chat.py`, `session_routing.py`, `session_governance.py`, `session_memory.py`, `session_tools.py`, `session_observability.py`.

Salida:

```text
R4_STATUS: MODULAR_MONOLITH_COMPLETE
```

## R5 — AGENT V2 COMO RUNTIME COGNITIVO ÚNICO

**Objetivo:** eliminar rutas paralelas y comportamiento inconsistente.

Trabajo:

- Agent V2 canónico;
- Planner→Executor→Evaluator persistente;
- `mission_id`, `run_id`, `room_id`;
- checkpoints y reanudación;
- intent router para direct LLM, brain evidence, mixed reasoning, learning external, code task y financial research;
- finalizer estable;
- evidence source mapping;
- conversation context assembler;
- ningún fastpath fuera de governance;
- tool results normalizados;
- timeouts y fallbacks explícitos;
- Kimi primary y fallbacks por policy.

Calidad: preguntas genéricas llaman LLM; preguntas sobre Brain recuperan evidencia; no hay “sin respuesta sintetizada” silencioso; fallos de herramientas son explicados; streaming, cancelación y retry explícito.

Salida:

```text
R5_STATUS: AGENT_V2_CANONICAL
```

## R6 — MEMORIA, RAG, PROMOCIÓN Y APRENDIZAJE

**Objetivo:** Brain aprende sin corrupción ni writers múltiples.

Crear `MemoryService` con `retrieve`, `stage_candidate`, `promote`, `rollback`, `integrity_check`, `rebuild_index` y `snapshot`.

Trabajo:

- eliminar acceso directo externo a `memory/semantic/*`;
- un writer;
- staging, approval, deduplicación, provenance y trust score;
- snapshot y rollback;
- FAISS consistency, rebuild/hydration;
- retention y promotion queue;
- controlled ingestion;
- separación curated/semantic;
- retrieval benchmark;
- promote→retrieve→use E2E;
- canary-first.

Criterios: JSONL/FAISS/IDs consistentes, cero blank snippets, cero writer externo, rollback restaura hashes, provenance visible y memoria runtime no se commitea accidentalmente.

Salida:

```text
R6_STATUS: GOVERNED_LEARNING_COMPLETE
```

## R7 — OBSERVABILIDAD Y VISUAL TRACE CONSOLE

**Objetivo:** pensamiento operacional visible sin exponer chain-of-thought privado.

Trabajo:

- unificar writers de eventos;
- trace schema versionado;
- métricas reales;
- correlation IDs;
- run timeline;
- tool calls, gates, state changes y memory hits;
- provider health y cost/token accounting;
- error taxonomy;
- SSE/WebSocket;
- dashboard moderno;
- Visual Trace Console v1;
- operator console;
- audit download;
- replay controlado;
- health checks reales.

Salida:

```text
R7_STATUS: OPERABLE_AND_OBSERVABLE
```

## R8 — PROVIDER GATEWAY

**Objetivo:** centralizar proveedores antes de microservicios amplios.

Trabajo: eliminar último hardcode Ollama, provider policy, Kimi K2.7 Code primary, fallbacks autorizados, health, circuit breaker, timeout/retry, cost accounting, capability registry, prompt/version registry, no hidden fallback, redacción de secretos y contratos provider-independent.

Puede permanecer como módulo interno.

Salida:

```text
R8_STATUS: PROVIDER_GATEWAY_COMPLETE
```

## R9 — CURATED KNOWLEDGE

**Objetivo:** conocimiento curado read-only, evaluado y utilizable por Brain.

Trabajo: inventario canónico, taxonomías, calidad, chat-safe lookup, no mutación FAISS, controlled ingestion authorization, canary ingestion, provenance, versioning, benchmark, routes y contratos.

Primer candidato opcional de extracción: `curated-knowledge-service`.

Salida:

```text
R9_STATUS: CURATED_KNOWLEDGE_PRODUCTION_READY
```

## R10 — AUTOAPRENDIZAJE Y AUTOMEJORA GOBERNADOS

**Objetivo:** cerrar observar→proponer→evaluar→canary→promover→rollback.

Trabajo: capability evaluator, gap detector, proposal schema, patch generation, sandbox, riesgo P0-P3, benchmark, tests, canary, promotion gate, human approval, rollback, learning journal y provenance.

Prohibido modificar governance, risk contract o canonical directamente. Prohibido auto-merge.

E2E:

```text
issue → evidence → plan → patch → tests → Draft PR → CI → review → canary → promote/reject → memory
```

Salida:

```text
R10_STATUS: GOVERNED_SELF_IMPROVEMENT_COMPLETE
```

## R11 — FINANCIAL AUTONOMY WIRING

**Objetivo:** conectar el código financiero existente sin habilitar live trading.

Trabajo: inventariar `financial_autonomy/`, eliminar dead code, wiring vía interfaz, feature flag OFF, dry-run, paper-only, audit events, risk gate, memory boundary, strategy contract, broker gateway y rollback.

Salida:

```text
R11_STATUS: FINANCIAL_AUTONOMY_WIRED_PAPER_ONLY
```

## R12 — PORTFOLIO MANAGER Y RISK ENGINE

PortfolioManager: allocation, sizing, exposure, correlation, concentration, rebalance, cash reserve, throttling, regimes, attribution y portfolio ledger.

Risk Engine: MaxDailyLoss 2%, MaxWeeklyDD 6%, MaxExposure 70%, kill switch, drawdown, VaR/CVaR, liquidity, slippage, fees, gap risk, stale data, broker disconnect, duplicate orders y reconciliation.

Los límites son baseline constitucional y no se modifican sin aprobación.

Salida:

```text
R12_STATUS: PORTFOLIO_AND_RISK_COMPLETE
```

## R13 — COMPLIANCE

**Objetivo:** ninguna operación financiera evita compliance.

Trabajo: PDT, wash sale, market hours, restricted symbols, short-sale constraints, account permissions, data licensing, jurisdiction/config, audit trail, tax lots, duplicate prevention, manual review queue, paper/live distinction y fail-closed.

Salida:

```text
R13_STATUS: COMPLIANCE_GATE_COMPLETE
```

## R14 — BACKTESTER LOCAL Y VALIDATION LAB

**Objetivo:** evaluar estrategias sin depender del cloud y sin autoengaño.

Trabajo: data adapters, corporate actions, survivorship controls, lookahead prevention, slippage, fees, latency, walk-forward, OOS, regimes, stress, Monte Carlo, bootstrap, benchmark, reproducibility, registry, experiment ledger y QC parity.

Ninguna estrategia avanza sin OOS, recent, stress, bear, costs, no breaches y reproducibility.

Salida:

```text
R14_STATUS: LOCAL_VALIDATION_LAB_COMPLETE
```

## R15 — PAPER TRADING INTEGRAL

**Objetivo:** demostrar operación completa con broker paper y reconciliación.

Trabajo: IBKR paper, market data, order lifecycle, partial fills, cancel/replace, reconciliation, disconnect, duplicate prevention, PortfolioManager, Compliance, Risk, observability, daily close, incident recovery y reports.

Soak mínimo: 30 días calendario, múltiples regímenes, cero bypass, cero inconsistencia de ledger, cero orden duplicada, kill switch y recovery probados.

Salida:

```text
R15_STATUS: PAPER_TRADING_CERTIFIED
```

## R16 — LIVETRADINGGATE, BLOQUEADO POR DEFECTO

**Objetivo:** implementar transición técnica a live sin activarla.

Trabajo: multi-factor approval, account binding, operator confirmation, capital cap, loss cap, symbol/strategy allowlists, time window, kill switch, preview, audit receipt y rollback a paper.

Aunque pase:

```text
LIVE_TRADING_ENABLED=false
```

Solo César puede autorizar el cambio.

Salida:

```text
R16_STATUS: LIVE_GATE_IMPLEMENTED_DISABLED
```

## R17 — MICROSERVICIOS SELECTIVOS

Orden condicionado: curated knowledge, provider gateway, observability, memory, agent orchestrator, financial engine y execution gate.

Prerrequisitos: ownership único, contratos, E2E, rollback, no shared mutable filesystem, APIs versionadas, deployment support, observability y feature flags.

Prohibido: distributed monolith, shared FAISS writes, extraer `session.py` como god service, microservicios antes de gaps funcionales y k8s por moda.

La certificación no exige extraer todos los servicios. Puede quedar `JUSTIFIABLY_DEFERRED`.

Salida:

```text
R17_STATUS: SELECTIVE_EXTRACTION_COMPLETE_OR_JUSTIFIABLY_DEFERRED
```

## R18 — PRODUCTO, OPERACIONES Y UX

Trabajo: chat moderno, dashboard moderno, trace console, notifications, operator inbox, approval UI, incident UI, responsive/accessibility, docs, runbooks, install/upgrade, backup/restore, release notes, health page, version display, support bundle y errores accionables.

Salida:

```text
R18_STATUS: PRODUCT_OPERABLE
```

## R19 — CERTIFICACIÓN 101%

Auditoría final independiente: seguridad, arquitectura, runtime, memoria, Agent Loop, UX, operaciones, documentación y financial paper validation.

Adversarial tests: secrets, P3 bypass, replay, scope violation, model refusal/hallucination, provider/GitHub/broker outage, disk full, JSON/FAISS corruption, stale data, duplicate event/order, crash, scheduler restart, rollback, restore, kill switch y live no autorizado.

Certificación:

```text
STATUS: BRAIN_101_CERTIFIED
LIVE_TRADING_ENABLED: false
AUTO_MERGE: false
CANONICAL_LOCAL_SYNC: false
HUMAN_FINAL_AUTHORITY: true
```

---

# 6. ORDEN Y DEPENDENCIAS

```text
R0
 ├─ R1
 ├─ R2
 └─ R3
      ↓
R4
      ↓
R5
 ├─ R6
 ├─ R7
 └─ R8
      ↓
R9
      ↓
R10
      ↓
R11 → R12 → R13 → R14 → R15 → R16
      ↓
R17 (selectivo/opcional)
      ↓
R18
      ↓
R19
```

R2 y R3 pueden avanzar parcialmente en paralelo. Trading permanece al final y no se adelanta sobre seguridad, arquitectura, memoria y Agent V2.

---

# 7. SCORECARD 101%

| Dominio | Peso |
|---|---:|
| Seguridad y governance | 12 |
| Testing, CI, recovery | 10 |
| Modular monolith | 10 |
| Agent V2 y chat | 10 |
| Memoria y aprendizaje | 10 |
| Observabilidad y UX | 8 |
| Agent Loop | 8 |
| Provider/curated knowledge | 5 |
| Autoaprendizaje/automejora | 8 |
| Financial autonomy wiring | 4 |
| Portfolio/Risk | 5 |
| Compliance | 3 |
| Backtester | 3 |
| Paper trading | 3 |
| Live gate disabled | 1 |
| **Total base** | **100** |
| Resiliencia adversarial | **+1** |

Reglas:

- código desconectado no puntúa;
- sin prueba negativa no puntúa;
- si runtime usa otra ruta no puntúa;
- un Critical abierto limita el total a 69;
- un bypass de governance limita el total a 49;
- live accidental invalida la certificación;
- 101 solo con R19 aprobado.

---

# 8. BACKLOG NO OCULTABLE

Registrar scripts sueltos, `.bak`, archivos top-level, archives, estrategias QC, duplicación `brain/` vs `tmp_agent/brain_v9/brain/`, tests duplicados, deuda Windows-only, Docker/k8s, legacy runtime, datos generados trackeados y documentación obsoleta.

Cada deuda necesita owner, severidad, disposición, fecha y razón de deferment.

---

# 9. PRIMEROS ISSUES

1. `[BRAIN-101][R0] Rebaseline current HEAD and canonicalize roadmap`
2. `[BRAIN-101][R1.1] Add roadmap manifest validation to Agent Loop`
3. `[BRAIN-101][R1.2] Add roadmap-doc and test-only profiles`
4. `[BRAIN-101][R2.1] Reaudit constitutional security blockers`
5. `[BRAIN-101][R3.1] Build current contract/E2E gap matrix`

No crear Issues R4+ antes de aprobar R0.

---

# 10. FORMATO OBLIGATORIO DE REPORTE

```text
STATUS:
ROADMAP_ID:
ROADMAP_VERSION:
ROADMAP_SHA256:
ROADMAP_ITEM:
WORKING_DIRECTORY:
BRANCH:
BASE_SHA:
HEAD_SHA:
ISSUE:
PR:
CHANGED_FILES:
SCOPE_MATCH:
ROOT_CAUSE:
IMPLEMENTATION:
RUNTIME_WIRING:
POSITIVE_TESTS:
NEGATIVE_TESTS:
CONTRACT_TESTS:
E2E_TESTS:
CI:
ROLLBACK:
SECURITY:
CANONICAL_UNTOUCHED:
AUTO_MERGE:
TASK_STATE:
ACTIVE_WORKERS:
EVIDENCE:
SCORE_BEFORE:
SCORE_AFTER:
OPEN_RISKS:
LEDGER_UPDATED:
MANIFEST_UPDATED:
NEXT_GATE:
```

Estados permitidos:

```text
READY_FOR_HUMAN_AUDIT
BLOCKED_CONSTITUTIONAL
BLOCKED_PRODUCTIVE_SAFETY
BLOCKED_CONTRACTUAL
BLOCKED_SCOPE
FAILED_IMPLEMENTATION
CLOSED_WITH_RUNTIME_EVIDENCE
BRAIN_101_CERTIFIED
```

No usar `COMPLETE` sin evidencia runtime.

---

# 11. PRIMERA ORDEN A CODEX

Ejecutar R0 en modo read-only:

1. Leer este documento.
2. Obtener HEAD remoto actual.
3. Comparar desde `759edfb`.
4. Auditar estado real de cada fase.
5. Crear scorecard factual.
6. Crear manifest canónico.
7. Proponer Issues.
8. No modificar producción.
9. No ejecutar trading.
10. No habilitar auto-merge.
11. No tocar canonical.
12. Dejar Draft PR de documentación para revisión humana.

Resultado requerido:

```text
STATUS: READY_FOR_BRAIN_101_ROADMAP_ADOPTION
```

Después de aprobación humana del Draft PR, iniciar R1.

---

# 12. DECLARACIÓN FINAL

Este roadmap conserva las decisiones acordadas:

- Brain Lab es primero un motor financiero especializado.
- La arquitectura inmediata es modular monolith, no microservicios masivos.
- Seguridad, governance, memoria, Agent V2, observabilidad y Agent Loop preceden al motor financiero final.
- Trading queda al final.
- PortfolioManager, Compliance, LiveTradingGate y backtester son gaps funcionales obligatorios.
- Kimi K2.7 Code ejecuta.
- Codex supervisa y dirige.
- César conserva autoridad constitucional.
- La autonomía nace de estabilidad demostrada.
- El cierre exige runtime, pruebas, evidencia y rollback.
- El dinero real requiere una autorización distinta.

```text
ROADMAP_STATUS: READY_FOR_CODEX_HANDOFF
```

---

# 13. R0 REBASELINE FACTUAL — 2026-07-22

Esta sección registra la reconciliación del documento de handoff contra el estado real del repositorio. No sustituye los criterios de cierre de R1-R19 y no certifica producción.

## 13.1 Identidad y delta

| Campo | Valor verificado |
|---|---|
| Repositorio | `cesarmanuel8102/AI_Vault` |
| Rama de integración | `codex/own-capital-sustainable-return` |
| Baseline GLM 5.2 | `759edfb` |
| HEAD remoto | `53da8ae93158cc3f9a06468c64d955816044c6d2` |
| Commits `759edfb..HEAD` | 93 |
| Archivos cambiados | 60 |
| Inserciones / eliminaciones | 13,283 / 298 |
| Naturaleza dominante del delta | Agent Loop v1.5.3-v1.5.7, contratos, recovery, CI y extracción incremental de rutas |

## 13.2 Evidencia de runtime del Agent Loop

| Evidencia | Valor |
|---|---|
| Worker SHA-256 instalado | `5261A8EDA5EEA8A2851F2088454BD4A129BE4072D06AD7F8621F6C176DEEA79A` |
| Config SHA-256 instalada | `AF6515841140487EADAA66B2BD2D647FC899E570446EDA88857401C8221C0D25` |
| Scheduled Task | `AI_Vault_Kimi_GitHub_Worker` — Running |
| Workers activos | 1 |
| Issue piloto | [#33](https://github.com/cesarmanuel8102/AI_Vault/issues/33) — `loop:ready-human-audit` |
| Draft PR piloto | [#34](https://github.com/cesarmanuel8102/AI_Vault/pull/34) — open/draft |
| Head del piloto | `8b9c08b417992b8bcc883f4c7690e4e04d4fdc83` |
| Alcance piloto | exactamente `PILOT_MARKER.md` y `EXECUTOR_REPORT.json` |
| Checks | deterministic, Codex, publish, phase1, nontrading, memory, trace y policy: SUCCESS |

Esta evidencia cierra la pregunta de si existe un loop técnico gobernado. No cierra R1: el worker todavía no valida roadmap ID/version/hash, dependencias entre fases ni perfiles generales de ejecución BRAIN-101.

## 13.3 Métricas arquitectónicas actuales

| Superficie | Estado actual | Target BRAIN-101 | Resultado |
|---|---:|---:|---|
| `tmp_agent/brain_v9/main.py` | 2,164 LOC; 30 endpoints directos | máximo 10 endpoints directos | OPEN |
| `tmp_agent/brain_v9/core/session.py` | 3,052 LOC | menos de 1,500 LOC | OPEN |
| `tmp_agent/brain_v9/agent/tools.py` | 3,519 LOC | migrado o deprecado | OPEN |
| `tmp_agent/brain_v9/agent/loop.py` | 2,912 LOC | migrado o deprecado | OPEN |
| Routers con `APIRouter` | 28 archivos | boundaries explícitos | PARTIALLY_CLOSED |
| Agent V2 default | `langgraph_parity` | runtime cognitivo único | PARTIALLY_CLOSED |
| Tests presentes por nombre | 48 contract, 124 unit, 288 smoke, 7 E2E-like | matriz R3 completa | PARTIALLY_CLOSED |

## 13.4 Matriz de hallazgos revalidada

| Hallazgo | Estado R0 | Evidencia y límite |
|---|---|---|
| Auth estricta en Agent V2/OpenAI-compatible | CLOSED_WITH_RUNTIME_EVIDENCE | Routers dependen de `require_strict_operator_access`; existen integration/smoke contracts. |
| Dev endpoints OFF por defecto | CLOSED_WITH_RUNTIME_EVIDENCE | `BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS` default false y tests negativos. Los launchers inseguros siguen siendo deuda operativa controlada. |
| RBAC constitucional completo | PARTIALLY_CLOSED | Viewer/operator/admin y permissions existen; faltan los cinco roles constitucionales y la matriz adversarial total. |
| Signed approvals/P3 fail-closed | PARTIALLY_CLOSED | Signed token wiring, wrong-scope/expiry tests y P3 denial existen; falta unificación total de gates y threat model final. |
| Agent Loop técnico | CLOSED_WITH_RUNTIME_EVIDENCE | v1.5.7 y piloto gobernado #33/#34 comprobados. |
| Agent Loop roadmap-aware | OPEN | No enforcement de manifest, dependencias, perfiles y una tarea BRAIN-101 activa. |
| Modular monolith | PARTIALLY_CLOSED | Rutas extraídas, pero cuatro superficies god/legacy incumplen targets R4. |
| Agent V2 canónico | PARTIALLY_CLOSED | LangGraph parity es default y tiene tests; permanecen rutas/fastpaths legacy. |
| MemoryService/ownership único | OPEN | No existe boundary `MemoryService`; promoción, semantic y FAISS siguen distribuidos. |
| Observabilidad/Visual Trace | PARTIALLY_CLOSED | TraceStore, SSE, timeline y dashboard existen; faltan writer único, accounting y certificación de replay. |
| ProviderGateway | OPEN | Hay provider selection/fallback, pero no gateway único y quedan referencias activas distribuidas. |
| Curated Knowledge | PARTIALLY_CLOSED | Lookup read-only y contratos presentes; falta cierre de benchmark, versioning e ingestion gobernada productiva. |
| Automejora gobernada | PARTIALLY_CLOSED | Dry-runs, gates y Agent Loop existen; no está cerrado el E2E canary→promote→rollback. |
| `financial_autonomy/` | PARTIALLY_CLOSED | Los módulos parsean y Agent V2 diagnostica; la capacidad está intencionalmente bloqueada/no wired. |
| PortfolioManager | OPEN | No existe una implementación canónica con ownership de portfolio. |
| Risk Engine completo | PARTIALLY_CLOSED | Existen contratos/riesgo dispersos; falta engine y ledger de portfolio integrados. |
| Compliance gate | OPEN | Checks parciales no equivalen a una capa de compliance canónica. |
| Validation Lab local | OPEN | Hay backtests y QC research; no existe certificación local reproducible completa R14. |
| Paper trading integral | OPEN | Conectores y observabilidad existen; no hay soak integrado de 30 días certificado. |
| LiveTradingGate deshabilitado | OPEN | Live permanece deshabilitado correctamente, pero la clase/gate técnico R16 no existe. |
| Microservicios amplios | SUPERSEDED | Sustituido por modular monolith primero y extracción selectiva condicionada R17. |
| Producto/UX | PARTIALLY_CLOSED | Chat, dashboard y trace UI existen; faltan certificación operativa, accesibilidad y restore/support bundle. |

## 13.5 Scorecard factual

El score base R0 es **49/100**, con resiliencia **0/1** y certificación **no emitida**. Se aplica el cap de 69 por bloqueadores críticos funcionales abiertos. No se aplica como hallazgo nuevo un cap por bypass de governance: R0 no encontró evidencia suficiente para afirmar un bypass activo, pero R2 aún debe ejecutar la auditoría adversarial completa.

El detalle machine-readable está en `docs/roadmap/BRAIN_101_SCORECARD.json`.

## 13.6 Backlog no ocultable inicial

| Deuda | Severidad | Owner propuesto | Disposición |
|---|---|---|---|
| `session.py` y `main.py` sobre target | High | R4 | Reducir por boundaries internos, sin extracción distribuida prematura. |
| `agent/tools.py` y `agent/loop.py` legacy | High | R4/R5 | Migrar o deprecar con parity y rollback. |
| Ownership distribuido de semantic/FAISS | Critical | R6 | Crear `MemoryService`; cero writer externo. |
| Provider/Ollama distribuido | High | R8 | Centralizar en ProviderGateway interno. |
| Financial runtime incompleto | Critical | R11-R16 | Mantener paper-only y avanzar en orden constitucional. |
| Duplicación `brain/` vs `tmp_agent/brain_v9/brain/` | Medium | R4/R6 | Inventariar y resolver ownership. |
| Artefactos históricos/top-level/archives | Medium | R3/R18 | Clasificar, retener o retirar con evidencia. |
| Cobertura E2E transversal insuficiente | High | R3 | Construir gap matrix y contratos Windows/Ubuntu. |

## 13.7 Issues propuestos después de adopción

No se crean Issues R1+ dentro de R0. Tras el merge humano de este Draft PR, crear en este orden:

1. `[BRAIN-101][R1.1] Add roadmap manifest validation to Agent Loop`
2. `[BRAIN-101][R1.2] Add roadmap-doc and test-only profiles`
3. `[BRAIN-101][R2.1] Reaudit constitutional security blockers`
4. `[BRAIN-101][R3.1] Build current contract/E2E gap matrix`

Cada Issue debe declarar roadmap/version, phase/item, dependencies, base SHA, paths permitidos/prohibidos, gates, rollback, autoridad humana y prohibiciones de auto-merge/canonical sync/live trading.

## 13.8 Gate de adopción

```text
STATUS: READY_FOR_BRAIN_101_ROADMAP_ADOPTION
R0_STATUS: READY_FOR_HUMAN_ADOPTION
LIVE_TRADING_ENABLED: false
AUTO_MERGE: false
CANONICAL_LOCAL_SYNC: false
HUMAN_FINAL_AUTHORITY: true
NEXT_GATE: Human review and merge of the R0 documentation Draft PR
```
