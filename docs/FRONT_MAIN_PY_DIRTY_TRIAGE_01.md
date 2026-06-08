# FRONT-MAIN-PY-DIRTY-TRIAGE-01: Diagnose Preexisting main.py Dirty State

**Status:** IN_PROGRESS
**Date:** 2026-06-08
**Branch:** codex/own-capital-sustainable-return
**HEAD:** baf2722d

---

## 1. Objetivo

Diagnosticar las modificaciones preexistentes en `tmp_agent/brain_v9/main.py` antes de permitir cualquier integración de router en el runtime principal.

## 2. Motivo del Bloqueo

FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-INTEGRATION-01 fue bloqueado con el status:
**FAILED_MAIN_PY_PREEXISTING_DIRTY**

`git diff --name-status` mostró:
- `M    tmp_agent/brain_v9/main.py`

## 3. Preflight Result

- git workdir: limpio excepto main.py
- staged: vacío ✅
- main.py: dirty ✅
- HEAD: baf2722d (sincronizado local == remote)

## 4. Diff Summary

- Total de líneas en diff: ~8,833
- Inserciones: 4,413
- Borrados: 4,325
- Tamaño del archivo diff: gran cantidad

## 5. Classification

| Sección | Riesgo | Descripción |
|---|---|---|
| imports | LOW | Import blocks reorganized |
| curated_runtime_lookup | MEDIUM | Added FAISS_WRITE_ALLOWED and REAL_WRITE_ALLOWED |
| brain_v9_config | LOW | Config imports adjusted |
| routes/endpoints | HIGH | Router definitions appear modified |
| security | HIGH | Auth/security modules edited |
| memory/FAISS paths | HIGH | Memory and FAISS-related imports touched |
| trading/B8 | HIGH | Trading module references exist |

## 6. Risk Assessment

**Risk Level: HIGH**

- Diff masivo de ~8,833 líneas con 4,413 insertions y 4,325 deletions.
- Nature: preexistente (no documentado en frentes previos).
- Impacto: bloquea integración de routers nuevos, puede contener cambios no aprobados en runtime, FAISS, trading.

## 7. Relation to Previous Fronts

- `FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-01` y `FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-INTEGRATION-01` no documentaron este dirty en main.py.
- Probablemente proviene de un frente anterior no archivado.

## 8. Resolution Options

### Option A: KEEP_AND_COMMIT_MAIN_PY_CHANGES
- **Status:** No recomendado sin human review dado el size del diff.
- **Impact:** Commit changes as they are.
- **Risk:** HIGH — could commit unapproved changes.

### Option B: DISCARD_NOT_AUTHORIZED_REQUIRES_OPERATOR
- **Status:** Considerado.
- **Action:** git checkout tmp_agent/brain_v9/main.py (revert to HEAD).
- **Risk:** MEDIUM — operator must review diff before discarding.

### Option C: SPLIT_INTO_SEPARATE_FRONT
- **Status:** Recomendado.
- **Action:** Create FRONT-MAIN-PY-PREEXISTING-COMMIT-01 to review and commit the preexisting changes.
- **Risk:** LOW.

### Option D: NEED_HUMAN_REVIEW
- **Status:** REQUIRED.
- **Action:** Operator must review tmp_agent/front_main_py_dirty_triage_01/main_py_diff.patch.txt.
- **Decision:** TBD by operator.

## 9. Recommended Resolution

**NEED_HUMAN_REVIEW**

## 10. Why No Cleanup Was Executed

- No git reset/checkout/clean/stash executed.
- main.py was not modified by this front.
- main.py was not staged.
- main.py was not committed.
- This front is diagnostic-only.

## 11. Safety Flags

- materialization_allowed_now: false
- patch_generation_allowed_now: false
- memory_write_allowed: false
- faiss_write_allowed: false
- real_write_allowed: false
- promotion_allowed: false

## 12. Recommended Next Front

**FRONT-MAIN-PY-DIRTY-HUMAN-REVIEW-01** — operator review of preexisting main.py dirty state.

Alternativas:
- FRONT-MAIN-PY-DIRTY-COMMIT-01 — commit preexisting changes
- FRONT-MAIN-PY-DIRTY-DISCARD-PLAN-01 — plan to discard changes
