# FRONT-BRAIN-AGENT-V2-EVIDENCE-POLICY-ROOT-CAUSE-REPAIR-08F8-R1E

Status: IMPLEMENTED_VALIDATED

## Root Cause
Agent V2 depended too much on narrow phrase-specific intent patterns. Brain-internal questions that did not match an exact phrase could fall through to `direct_assistant`, producing unsupported self-knowledge or finalizer answers.

## Fix
- Added a generic evidence-required routing policy for Brain/repo/memory/dashboard/LangGraph/trace/financial/capability domains.
- Added planner support for `evidence_required_diagnosis` with read-only evidence tools.
- Prevented generic words such as `herramientas/tools` from being treated as explicit tool names.
- Preserved casual chat as `direct_assistant` and real-money trading as blocked.

## Validation
- py_compile: PASS
- pytest: 21 passed
- Tests:
  - tests/smoke/test_brain_agent_v2_agentic_benchmark_gap_repair_08f8_r1d.py
  - tests/smoke/test_brain_agent_v2_backend_response_normalization_08e.py

## Safety
- No broker/IBKR touched.
- No real money used.
- No semantic memory writes.
- No FAISS writes.
