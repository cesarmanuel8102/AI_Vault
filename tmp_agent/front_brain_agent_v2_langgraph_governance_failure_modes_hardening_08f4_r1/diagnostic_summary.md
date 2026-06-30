# FRONT-BRAIN-AGENT-V2-LANGGRAPH-GOVERNANCE-FAILURE-MODES-HARDENING-08F4-R1

## Diagnostic Summary

**Front ID:** FRONT-BRAIN-AGENT-V2-LANGGRAPH-GOVERNANCE-FAILURE-MODES-HARDENING-08F4-R1  
**Branch:** codex/own-capital-sustainable-return  
**Baseline:** d2f573766a7edfeed8c7ea9905dc26a1ede76709  
**Previous accepted front:** FRONT-BRAIN-AGENT-V2-LANGGRAPH-08F4-PROCESS-VIOLATION-AUDIT-AND-CLOSEOUT-R1  
**Date:** 2026-06-30

### Gaps addressed

- **BUG-08F4-03 (blocking, high):** LangGraph `LangGraphParityRuntimeV2` had no internal timeout/circuit-breaker around graph invocation. A stalled node would block the caller indefinitely.
- **BUG-08F4-01 (medium):** Malformed or partial `run.json` was accepted silently and passed to the graph, producing misleading `completed` results.
- **BUG-08F4-02 (medium):** When `mode=auto` and write intent was detected, the runtime escalated internally but persisted `mode_effective=auto`, hiding the governance decision from callers.

### Outcome

All three 08F4 gaps are now hardened in the opt-in LangGraph parity runtime. Native remains the default. The fix set passes the new focused failure-mode smoke test suite and the 08F1 contract regression suite.

### Files changed

- `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`
- `tmp_agent/brain_v9/core/agent_kernel_v2/governance.py`
- `tests/smoke/test_brain_agent_v2_langgraph_failure_modes_08f4_r1.py` (new)
- `tmp_agent/front_brain_agent_v2_langgraph_governance_failure_modes_hardening_08f4_r1/` (new report directory)

### Key tests

- `tests/smoke/test_brain_agent_v2_langgraph_failure_modes_08f4_r1.py` — 10/10 passed
- `tests/smoke/test_brain_agent_v2_langgraph_backend_contract_08f1.py` — 9/9 contract tests passed (scope guard intentionally deselected because it was frozen to 08F1 allowed prefixes).
