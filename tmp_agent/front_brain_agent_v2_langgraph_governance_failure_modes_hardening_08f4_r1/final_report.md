# Final Report — FRONT-BRAIN-AGENT-V2-LANGGRAPH-GOVERNANCE-FAILURE-MODES-HARDENING-08F4-R1

## Decision

**ACCEPTED_08F4_R1**

## Rationale

- BUG-08F4-03 (blocking) is fixed: `LangGraphParityRuntimeV2` now enforces an internal timeout around graph invocation and returns a safe failed Native-style state on timeout. Tests confirm execution is bounded to well under the timeout.
- BUG-08F4-01 is fixed: malformed run state (missing required fields or invalid JSON) is rejected with `status=failed`, `error=malformed_run_state`, and a persisted run.json.
- BUG-08F4-02 is fixed: `mode=auto` with write intent now reflects `mode_effective=approval_required` while preserving `mode_requested=auto`.
- Native default is preserved; LangGraph remains opt-in (`AGENT_V2_BACKEND=langgraph`).
- Scope is clean: only allowed source files were modified.
- Local validation passes (compile, focused smoke tests, 08F1 regression tests, hygiene guard).

## Baseline and head

- Starting baseline: `d2f573766a7edfeed8c7ea9905dc26a1ede76709`
- New baseline after commit: `<to be recorded after push>`

## Validation summary

| Check | Result |
|---|---|
| py_compile (modified files + new test) | PASS |
| 08F4-R1 focused smoke tests (10 tests) | PASS |
| 08F1 regression contract tests (9 selected) | PASS |
| Hygiene guard | SAFE |
| Scope audit | No forbidden files modified |
| CI | Pending push verification |

## Scope audit

- Modified source files:
  - `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`
  - `tmp_agent/brain_v9/core/agent_kernel_v2/governance.py`
- New test file:
  - `tests/smoke/test_brain_agent_v2_langgraph_failure_modes_08f4_r1.py`
- New report directory:
  - `tmp_agent/front_brain_agent_v2_langgraph_governance_failure_modes_hardening_08f4_r1/`

No forbidden paths or production wiring changes.

## Process compliance

- No amend.
- No force push / force-with-lease / reset.
- No history rewrite.
- Staged explicit files only.
- Hygiene guard passed before commit.

## Next steps

1. Stage explicit files and commit.
2. Push normally.
3. Verify CI for `phase1-ci` and `nontrading-smoke-regression`.
4. Record final head in report JSONs.

## Sign-off

Prepared by opencode on 2026-06-30.
