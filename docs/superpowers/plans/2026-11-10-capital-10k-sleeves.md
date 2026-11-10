# Capital de USD 10,000 por sleeve — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aportar USD 9,500 a cada sleeve y autorizar USD 10,000 por sleeve sin resetear P&L, epoch ni reloj.

**Architecture:** Eventos append-only de aporte y enmienda de autoridad, aplicados atómicamente. La autoridad efectiva mantiene linaje verificable hasta el target existente y debe coincidir con el ledger.

**Tech Stack:** Python 3, Pydantic, SQLite append-only, pytest, PowerShell de despliegue.

**Spec:** `docs/superpowers/specs/2026-11-10-capital-10k-sleeves-design.md`

## Global Constraints

- PAPER únicamente; nunca conectar a 4001.
- USD 10,000 por sleeve mediante aporte USD 9,500.
- Preservar P&L, epoch y reloj.
- Mutación atómica, idempotente y fail-closed.
- Cero órdenes durante migración.

## Review Focus

- Repetición idéntica de la migración debe ser idempotente.
- Repetición con importe distinto debe bloquearse.
- Autoridad enmendada sin linaje al target debe bloquear nueva responsabilidad.
- Aporte no debe alterar P&L, fees ni reloj.
- Estado no plano o responsabilidad reservada debe impedir la migración.

---

### Task 1: Ledger de aportes

**Files:**
- Modify: `ibkr_paper_30d/sleeve_ledger.py`
- Test: `tests/ibkr_paper_30d/test_sleeve_ledger.py`

**Interfaces:**
- Produces: `SleeveLedgerStore.contribute_capital_in_transaction(...)` y proyección de `CAPITAL_CONTRIBUTION`.

- [ ] Escribir tests RED de aporte, preservación de P&L, idempotencia y conflicto.
- [ ] Ejecutar los tests y confirmar el fallo esperado.
- [ ] Implementar el evento y su proyección.
- [ ] Ejecutar tests GREEN.

### Task 2: Enmienda y linaje de autoridad

**Files:**
- Modify: `ibkr_paper_30d/multi_universe_models.py`
- Modify: `ibkr_paper_30d/multi_universe_authority.py`
- Modify: `ibkr_paper_30d/risk.py`
- Test: `tests/ibkr_paper_30d/test_multi_universe_models.py`
- Test: `tests/ibkr_paper_30d/test_multi_universe_authority.py`
- Test: `tests/ibkr_paper_30d/test_capital_boundary_risk.py`

**Interfaces:**
- Consumes: aporte de Task 1.
- Produces: autoridades positivas de importe variable, enmienda append-only y raíz de linaje.

- [ ] Escribir tests RED para USD 10,000, linaje, atomicidad e inconsistencias.
- [ ] Confirmar RED.
- [ ] Implementar modelos y store de enmienda.
- [ ] Confirmar GREEN.

### Task 3: Validación runtime y mandato económico

**Files:**
- Modify: `ibkr_paper_30d/production_continuity_runtime.py`
- Modify: `ibkr_paper_30d/autonomous_research.py`
- Test: `tests/ibkr_paper_30d/test_production_continuity_runtime.py`
- Test: `tests/ibkr_paper_30d/test_mandate_hardening.py`

**Interfaces:**
- Consumes: autoridad efectiva y raíz de Task 2.
- Produces: validación target→linaje→autoridad→ledger y benchmark USD 20,000 por sleeve.

- [ ] Escribir tests RED de coincidencia y bloqueo.
- [ ] Confirmar RED.
- [ ] Implementar validación y contexto dinámico.
- [ ] Confirmar GREEN.

### Task 4: Migración de producción

**Files:**
- Create: `tools/amend_sleeve_capital.py`
- Test: `tests/ibkr_paper_30d/test_amend_sleeve_capital.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: dry-run y `--apply` atómico/idempotente con comprobante JSON.

- [ ] Escribir tests RED del preflight, apply, idempotencia y reloj/P&L preservados.
- [ ] Confirmar RED.
- [ ] Implementar CLI.
- [ ] Confirmar GREEN.

### Task 5: Verificación y despliegue

**Files:**
- Modify: artefactos de despliegue sólo si el flujo canónico lo exige.

- [ ] Ejecutar suite completa, kernel/provenance y `git diff --check`.
- [ ] Revisar el diff completo una vez.
- [ ] Detener runtime canónico sin tocar IBKR orders/positions.
- [ ] Crear backup SQLite, desplegar HEAD aprobado y ejecutar migración una vez.
- [ ] Rebind/relaunch con el flujo canónico.
- [ ] Verificar PAPER 4002, lock/watchdog, ambos ledgers USD 10,000, P&L/reloj preservados y primer ciclo aceptado.
