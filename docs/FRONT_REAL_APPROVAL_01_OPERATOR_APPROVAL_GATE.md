# FRONT-REAL-APPROVAL-01: Operator Approval Gate for Controlled Write

**Status:** APPROVAL GATE ONLY — This document does NOT execute or authorize a real write by itself.

**Branch:** codex/own-capital-sustainable-return
**Date:** 2026-06-08
**Relates to:** [FRONT-REAL-PLAN-01](FRONT_REAL_PLAN_01_CONTROLLED_E2E_WRITE_PLAN.md)

---

## 1. Objetivo

Formalizar la compuerta de aprobacion humana que debe pasarse antes de cualquier escritura real controlada en `memory/semantic/semantic_memory.jsonl`.

Este documento **no autoriza ejecucion por si mismo**. Solo define la compuerta.

## 2. Alcance

- Documentar la variable de entorno de aprobacion requerida.
- Documentar el comportamiento fail-closed.
- Documentar la doble confirmacion requerida.
- Documentar las acciones bloqueadas implicitamente.
- Referenciar los modulos de infraestructura existentes que ya implementan este gate.

## 3. Out of Scope

- NO ejecutar escritura real.
- NO modificar `memory/semantic/`.
- NO tocar FAISS.
- NO modificar `tmp_agent/brain_v9/main.py`.
- NO modificar `tmp_agent/brain_v9/core/session.py`.
- NO modificar `brain/curated_runtime_lookup.py`.
- NO modificar adapters reales de escritura.
- NO activar trading.
- NO tocar B8.
- NO aplicar patches.
- NO promover conocimiento.

## 4. Relacion con FRONT-REAL-PLAN-01

FRONT-REAL-PLAN-01 definio el ciclo controlado de escritura:
- Target: `memory/semantic/semantic_memory.jsonl`
- Backup y rollback requeridos
- 1 record exacto
- Retrieval verification

FRONT-REAL-APPROVAL-01 formaliza la compuerta que bloquea la ejecucion de ese plan hasta que un operador humano apruebe explicitamente.

## 5. Variables de Entorno Requeridas

### `BRAIN_APPROVAL_4D_DRY_GATE_TOKEN`

- **Ubicacion:** Variable de entorno (no hardcoded).
- **Valor:** Token secreto definido por operador humano.
- **Requerido:** Si.
- **Fallo:** BLOCKED (fail-closed).
- **No revelar:** Este token no debe aparecer en codigo, logs, ni evidence.
- **Placeholder en .env.example:** Vacio (correcto).

## 6. Aprobacion Humana Requerida

El sistema requiere **dos confirmaciones explicitas** de un operador humano:

### Confirmacion 1 — Intento de Approval
- El operador declara intencion de ejecutar escritura controlada.
- El operador proporciona token de aprobacion.
- El sistema valida token y precondiciones.

### Confirmacion 2 — Ejecucion Inmediata Antes de Write
- Inmediatamente antes del `append` al archivo.
- El operador confirma nuevamente:
  - Target store es correcto.
  - Backup esta creado y verificado.
  - Runtime esta detenido.
  - Git working tree esta limpio.
  - Solo 1 record sera escrito.

Sin ambas confirmaciones: **BLOCKED**.

## 7. Doble Confirmacion Requerida

Ambas confirmaciones deben ser explicitas y documentadas en evidence.

La infraestructura ya existente (`brain/semantic_memory_final_pre_execution_gate.py`) codifica esto:
- `requires_second_confirmation: True`
- `second_confirmation_contract` en reporte

## 8. Fail-Closed Behavior

El sistema falla cerrado por defecto. Todas estas condiciones resultan en BLOCKED:

| Condicion | Estado | Accion |
|---|---|---|
| Token ausente | `BRAIN_APPROVAL_4D_DRY_GATE_TOKEN` no definida | BLOCKED |
| Token vacio | Variable vacia | BLOCKED |
| Token invalido | No coincide con `compare_digest` | BLOCKED |
| Solo 1 confirmacion | Falta segunda confirmacion | BLOCKED |
| Dirty git | Staged/modified files no autorizados | BLOCKED |
| Runtime activo | Puerto 8090 responde cuando debe estar detenido | BLOCKED |
| FAISS write solicitado | Write pide tocar FAISS | BLOCKED |
| Trading/B8 solicitado | Write pide activar trading o B8 | BLOCKED |
| Patch application solicitado | Write pide aplicar patches | BLOCKED |
| Preflight no aprobado | Snapshot no pasa | BLOCKED |

La implementacion existente en `brain/semantic_memory_real_write_readiness_gate.py`:
- `validate_user_approval_token()` usa `hmac.compare_digest` (timing-attack safe).
- Sin token: `REAL_WRITE_BLOCKED`
- Con token valido pero sin demas precondiciones: `READY_BLOCKED` (nunca `READY`).

## 9. Token Handling sin Revelar Secretos

- Token se lee de variable de entorno.
- Token no se loguea ni se imprime.
- Token no se guarda en archivos.
- Comparacion es timing-safe (`hmac.compare_digest`).
- `.env.example` solo tiene placeholder vacio.

## 10. Evidence Requirements

Antes de que un future front (FRONT-REAL-CANARY-PLAN-01 o similar) pueda ejecutar, debe producir evidence de:
1. Token configurado (sin mostrar valor).
2. Primera confirmacion registrada.
3. Backup creado y verificado.
4. Preflight snapshot pasado.
5. Go/No-Go checklist aprobado.
6. Authorization packet generado.
7. Segunda confirmacion registrada.
8. Retrieval verification pasada.
9. Rollback verification pasada.

## 11. Stop Conditions

- Token no configurado.
- Primera confirmacion faltante.
- Backup no creado.
- Preflight snapshot con blockers.
- Go/No-Go checklist con blockers.
- Runtime activo.
- Git working tree dirty.
- Operador cancela.
- FAISS/trading/B8/patch solicitado.

## 12. Safety Flags

- `materialization_allowed_now: false`
- `patch_file_creation_allowed_now: false`
- `git_apply_allowed_now: false`
- `target_file_modification_allowed_now: false`
- `patch_application_allowed_now: false`
- `real_patch_application_allowed_now: false`
- `memory_write_allowed: false`
- `faiss_write_allowed: false`
- `real_write_allowed: false`
- `promotion_allowed: false`
- `must_not_create_patch_files: true`
- `must_not_run_git_apply: true`
- `must_not_modify_target_files: true`

## 13. Que NO Autoriza Este Frente

Este frente (FRONT-REAL-APPROVAL-01):
- **No ejecuta ninguna escritura.**
- **No modifica memoria semantica.**
- **No toca FAISS.**
- **No activa trading.**
- **No toca B8.**
- **No aplica patches.**
- **No promueve conocimiento.**

Este frente solo documenta la compuerta que **bloquea** estas acciones hasta que el operador humano apruebe explicitamente en un frente futuro.

## 14. Que Frente Futuro Podria Ejecutar

- **FRONT-REAL-CANARY-PLAN-01** — Single-record canary execution plan.
- **FRONT-REAL-EXEC-PLAN-01** — Formal execution plan con backup real.
- **FRONT-INFRA-03** — Startup/runbook reproducibility (sin escritura real).

Estos frentes futuros, si se aprueban, requeriran:
1. Todas las precondiciones de este documento.
2. Backup creado y verificado.
3. Runtime detenido.
4. Git working tree limpio.
5. Doble confirmacion humana.
6. Retrieval verification.
7. Rollback verification.

## 15. Declaracion Explicita

> **This approval gate does not execute or authorize a real write by itself.**
>
u003e Execution of any real write requires:
> 1. A separate future front (FRONT-REAL-CANARY-PLAN-01 or similar)
003e 2. Human operator approval at two distinct gates
003e 3. Runtime stopped
003e 4. Clean git working tree
003e 5. Real backup created and verified
003e 6. All preflight tests passing
003e 7. Retrieval verification post-write
003e 8. Rollback verification demonstrated
003e
003e Until a future front is explicitly approved, **no real write is permitted**.
