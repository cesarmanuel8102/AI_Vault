# FASE-0-SEGURIDAD — Resumen ejecutivo

**Branch:** `codex/own-capital-sustainable-return`
**HEAD:** `248e41c5` (== origin, sin commits nuevos)
**Estado:** 4 patches preparadas, validadas, **NO commiteadas, NO pusheadas**.

## Riesgos mitigados

| ID | Riesgo critico (audit 2026-06-02) | Mitigacion |
|----|-----------------------------------|------------|
| 0A | `.dev_auth/credentials.enc` y `god_audit.jsonl` aun tracked en index pese a WT-HYGIENE-02. `.gitignore` solo cubria `master.key`. | `.gitignore` reforzado (`.dev_auth/**`). Script `phase0A_untrack_sensitive_files_plan.ps1` materializa el untrack (sin commit, sin delete fisico, allowlist explicita). |
| 0B | GOD mode auto-aprobaba TODO incluido P3 destructivo. | `gate.check()` intercepta P3 dentro del bloque GOD: devuelve `allowed=false`, `pending_id`, `requires_human_approval=true`. P0/P1/P2 siguen funcionando bajo GOD. |
| 0C | `BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS` por defecto `"true"`; `/dev` y `/godmode` devolvian JSON 200 con `success=false` (mascara la exposicion). | Default `"false"`, parser estricto `{1,true,yes,on}`, `log.warning` cuando se activa, endpoints lanzan `HTTPException(403)`. |
| 0D | R27 selfdev_bypass + GOD podian editar `execution_gate.py`, `ethics_kernel`, `api_security`, `trace_redactor`, etc. | Denylist `_PROTECTED_SELFDEV_PATH_PREFIXES/_FILE_TOKENS/_EXACT_BASENAMES` chequeada al INICIO de `gate.check()`, antes de GOD y antes de selfdev_bypass. Devuelve `action=blocked`. |

## Artefactos en `tmp_agent/security_phase0_evidence/`

- `phase0_preflight.json`
- `phase0_secret_exposure_report.json`
- `phase0A_gitignore_dev_auth.patch` (+4 lineas en `.gitignore`)
- `phase0A_untrack_sensitive_files_plan.ps1` (untrack-only, no commit)
- `phase0B_god_p3_guardrail.patch` (+29 lineas en `execution_gate.py`)
- `phase0C_dev_endpoints_default_off.patch` (config.py + main.py)
- `phase0D_selfdev_protected_paths.patch` (+109 lineas en `execution_gate.py`)
- `_phase0_BD_combined_execution_gate.patch` (B+D combinado, referencia)
- `phase0_patch_manifest.json`
- `phase0_validation_report.json`
- `phase0_security_summary.md` (este archivo)

## Tests creados (todos PASS — 14 casos)

- `tests/unit/test_execution_gate_god_p3.py` — 3 casos
- `tests/unit/test_dev_endpoints_default_off.py` — 6 casos (incluye AST guard contra dead-code `return` antes de `raise HTTPException`)
- `tests/unit/test_selfdev_protected_paths.py` — 5 casos

## Hardening adicional Patch 0C (post-revisión)

Tras revision: inspeccionado el bloque `if not BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS:` en
`main.py:3831-3836` (/dev) y `main.py:3913-3918` (/godmode). Confirmado que NO existe
`return {...}` antes de `raise HTTPException(...)`; el bloque entero fue reemplazado.
Se anadio test AST `test_no_dead_code_return_before_raise_in_unsafe_gate` que falla si
una futura edicion reintroduce el patron. Adicional `test_at_least_two_raise_403_in_main`
asegura >=2 `raise HTTPException(status_code=403)` en main.py.

## Orden de aplicacion recomendado

`0A → 0B → 0C → 0D` (B y D ambos tocan `execution_gate.py`; B primero).

## Lo que NO se hizo (por diseno)

- No commit, no push, no `git add -A`, no reset, no clean.
- No se imprimio contenido de credenciales (solo presencia/tracking).
- No se toco `tmp_agent/strategies/`, `memory/semantic/`, B7/ChatMetrics, `core/session.py`, `core/session_chat_metrics.py`, `ROADMAP_STATUS.json`, `MIGRATION_CONTROL_LEDGER.md`, ni UI.
- No se revirtio WT-HYGIENE-02.

## Proximo paso sugerido

Revisar las 4 patches individualmente. Cuando se decida aplicar:

1. Confirmar `git status` limpio de cambios fuera de scope.
2. Aplicar en orden A→B→C→D (las patches ya estan en working tree).
3. Ejecutar el plan PowerShell de 0A para untrack `.dev_auth/credentials.enc` y `god_audit.jsonl` del index (no borra archivos fisicos).
4. Re-correr los 3 tests unit.
5. Commit por patch (4 commits separados) y push.
