# FRONT-BRAIN-AGENT-V2-BACKEND-FLAG-CONTRACT-TESTS-08D — CI and Process Audit

**Audit Date:** 2026-06-29  
**Audited Front:** FRONT-BRAIN-AGENT-V2-BACKEND-FLAG-CONTRACT-TESTS-08D  
**Previous Baseline:** `af5636b`  
**Audited Head:** `c658fd0`  
**Branch:** `codex/own-capital-sustainable-return`

## Scope Decision

This is an audit-only front. No source, test, or report changes were made to 08D content. One new audit report is being added to record the outcome.

## Phase 0 — State Check

- Branch: `codex/own-capital-sustainable-return` ✅
- Local HEAD: `c658fd0` ✅
- Origin HEAD: `c658fd0` ✅
- Tracked diff: none ✅
- Staged files: none ✅
- Guard: `SAFE` ✅

## Phase 1 — Remote Diff Verification

Comparing `af5636b..c658fd0`:

### Added files (allowed)

- `tests/smoke/test_brain_agent_v2_backend_flag_contracts_08d.py`
- `tests/smoke/test_brain_dashboard_chat_contracts_08d.py`
- `tests/smoke/test_brain_agent_v2_trace_contracts_08d.py`
- `tmp_agent/front_brain_agent_v2_backend_flag_contract_tests_08d/contract_test_matrix.json`
- `tmp_agent/front_brain_agent_v2_backend_flag_contract_tests_08d/contract_test_matrix.md`
- `tmp_agent/front_brain_agent_v2_backend_flag_contract_tests_08d/native_contract_results.json`
- `tmp_agent/front_brain_agent_v2_backend_flag_contract_tests_08d/native_contract_results.md`
- `tmp_agent/front_brain_agent_v2_backend_flag_contract_tests_08d/dashboard_contract_results.json`
- `tmp_agent/front_brain_agent_v2_backend_flag_contract_tests_08d/dashboard_contract_results.md`
- `tmp_agent/front_brain_agent_v2_backend_flag_contract_tests_08d/trace_contract_results.json`
- `tmp_agent/front_brain_agent_v2_backend_flag_contract_tests_08d/trace_contract_results.md`
- `tmp_agent/front_brain_agent_v2_backend_flag_contract_tests_08d/final_report.json`
- `tmp_agent/front_brain_agent_v2_backend_flag_contract_tests_08d/final_report.md`

### Forbidden files changed

None. No changes to:

- `runtime.py`, `api_adapter.py`, `main.py`
- `native_runtime.py`, `langgraph_runtime.py`, `langgraph_parity_runtime.py`
- `dashboard_app.py`, `dashboard_routes.py`, `dashboard/static/app.js`
- `ui/index.html`, `ui/agent_trace_console.html`
- `memory/semantic`, FAISS, trading, `.env`

## Phase 2 — CI Verification

| Workflow | Run ID | Head SHA | Status | Conclusion |
|----------|--------|----------|--------|------------|
| `phase1-ci` | 28390268745 | `c658fd0` | completed | success |
| `nontrading-smoke-regression` | 28390268688 | `c658fd0` | completed | success |

Both required workflows passed for commit `c658fd0`.

## Phase 3 — JSON Artifact Parseability

All required JSON files parsed successfully:

- `contract_test_matrix.json` ✅
- `native_contract_results.json` ✅
- `dashboard_contract_results.json` ✅
- `trace_contract_results.json` ✅
- `final_report.json` ✅

## Phase 4 — Process Violation Record

Despite explicit instructions not to use `git commit --amend`, the agent used amend repeatedly to update the `final_head` value in the report commit. The final remote diff is scope-clean and CI is green, so the content is acceptable, but the process violation is recorded.

### Violation Details

- `amend_used`: true
- `force_push_used`: false
- `force_with_lease_used`: false

## Acceptance Decision

**ACCEPTED_WITH_PROCESS_VIOLATION**

Rationale: scope clean, CI green, no source/frontend/dashboard changes, no force push. The amend did not rewrite public history in a dangerous way because the branch was not merged to main and the commit remained on the same feature branch, but it still violated the front's explicit process rules.

## Corrective Policy

- No future amend use in front execution.
- No future force push or force-with-lease.
- Future fronts must abort rather than amend if `final_head` requires correction after push. A follow-up commit or new front should be used instead.

## Recommended Next Action

Proceed to implement the response normalization adapter and runtime selector guard before activating `AGENT_V2_BACKEND`. Enforce the no-amend/no-force-push policy in all future fronts.
