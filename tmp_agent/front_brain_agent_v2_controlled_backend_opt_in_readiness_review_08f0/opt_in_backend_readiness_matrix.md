# Opt-In Backend Readiness Matrix

**Front**: FRONT-BRAIN-AGENT-V2-CONTROLLED-BACKEND-OPT-IN-READINESS-REVIEW-08F0  
**Source head**: 883df0a  
**Default backend**: NativeAgentRuntimeV2  
**Candidate backend**: LangGraphParityRuntimeV2 (opt-in only)

## Matrix

| # | Category | Status | Evidence | Blocking Gaps | Required 08F1 Work | Risk |
|---|----------|--------|----------|---------------|--------------------|------|
| 1 | Runtime interface parity | **FAIL** | `langgraph_parity_runtime.py` | Missing `create_run`, `execute_run`, `plan_run`, `list_runs` | Add production-runtime wrapper methods matching Native signatures | CRITICAL |
| 2 | Response normalization parity | **PARTIAL** | `api_adapter.py`, `response_normalizer.py` | LangGraph returns graph state, not Native run dict | Translate graph state before normalization | HIGH |
| 3 | Trace contract parity | **PASS** | Both use `TraceStore` | None | Ensure run_root layout matches Native | LOW |
| 4 | Run lifecycle parity | **FAIL** | `/v2/agent/runs/{id}/{plan,execute,pause,resume,cancel}` | Missing lifecycle methods in LangGraph class | Implement no-op or graph-aware lifecycle methods | MEDIUM |
| 5 | Dashboard compatibility | **PASS** | `dashboard_routes.py` (R3 fix) | None | No dashboard changes needed | LOW |
| 6 | Security / token compatibility | **PASS** | `api_adapter.py` + `require_strict_operator_access` | None | No security changes needed | LOW |
| 7 | Governance / read_only enforcement | **PARTIAL** | `governance_gate` node in LangGraph graph | Need proof graph blocks writes like Native | Add read_only write-blocking tests | MEDIUM |
| 8 | Fallback-to-native behavior | **PASS** | `runtime.py` selector | None | Preserve fallback guard | LOW |
| 9 | Test coverage | **FAIL** | No LangGraph backend contract smoke test | Missing opt-in backend test | Add `test_brain_agent_v2_langgraph_backend_contract_08f1.py` | HIGH |
| 10 | CI coverage | **PASS** | phase1-ci and nontrading-smoke-regression run smoke tests | None | New tests auto-discovered | LOW |
| 11 | No memory/FAISS mutation risk | **PASS** | 08F0 reports-only; LangGraph uses read memory path | None | 08F1 must not add FAISS writes | LOW |
| 12 | No trading/broker mutation risk | **PASS** | 08F0 did not touch trading files | None | 08F1 must not touch trading/IBKR | LOW |
| 13 | Observability / debug metadata | **PARTIAL** | LangGraph sets parity keys; needs backend metadata | Missing `backend_selected`/`backend_fallback_*` | Set backend metadata on wrapper | MEDIUM |
| 14 | Rollback safety | **PASS** | Native default; env opt-in only | None | Keep default unchanged | LOW |
| 15 | Canary readiness | **FAIL** | LangGraph cannot be selected today | Missing wrapper, translation, tests | Complete 08F1 implementation | CRITICAL |

## Summary

- **PASS**: 6 categories
- **PARTIAL**: 3 categories
- **FAIL**: 5 categories (including 2 CRITICAL)
- **Overall readiness**: **NOT READY** for LangGraph opt-in activation.
- **Recommendation**: Proceed to 08F1 to address CRITICAL/HIGH gaps while keeping Native as default.
