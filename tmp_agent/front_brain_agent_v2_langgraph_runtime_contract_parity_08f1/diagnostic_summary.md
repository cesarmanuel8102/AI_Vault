# Diagnostic Summary — FRONT-BRAIN-AGENT-V2-LANGGRAPH-RUNTIME-CONTRACT-PARITY-08F1

**Front**: FRONT-BRAIN-AGENT-V2-LANGGRAPH-RUNTIME-CONTRACT-PARITY-08F1  
**Branch**: codex/own-capital-sustainable-return  
**Starting baseline**: 81c6122  
**Previous accepted front**: FRONT-BRAIN-AGENT-V2-CONTROLLED-BACKEND-OPT-IN-READINESS-REVIEW-08F0

## Purpose

Implement controlled LangGraph runtime contract parity for Agent V2 so `LangGraphParityRuntimeV2` can be selected **only** as an opt-in backend through `AGENT_V2_BACKEND=langgraph`.

This is **not** a LangGraph canary, **not** a default activation, and **not** a dashboard/frontend/trading/memory change.

## Scope confirmation

- Native default preserved: yes
- LangGraph default activation: no
- LangGraph canary started: no
- Source files modified: yes (only allowed files)
- Dashboard/frontend/api_security/main/api_adapter/native_runtime/response_normalizer: unchanged
- Memory/FAISS/trading/env: untouched
- Guard result: SAFE

## Files modified

- `tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`
- `tests/smoke/test_brain_agent_v2_backend_response_normalization_08e.py` (minimal scope guard update, justified by 08F1)
- `tests/smoke/test_brain_agent_v2_langgraph_backend_contract_08f1.py` (new)

## Older test update note

The 08E response normalization test had an outdated scope guard that listed `langgraph_parity_runtime.py` as a forbidden modification target. Because 08F1 is explicitly authorized to modify that file, the guard was updated minimally to remove the now-incorrect prohibition.

## Recommended next front

**FRONT-BRAIN-AGENT-V2-LANGGRAPH-OPT-IN-CANARY-SMOKE-08F2**

Run controlled local/live canary smoke with `AGENT_V2_BACKEND=langgraph`. Keep Native default. Do not start production canary yet.
