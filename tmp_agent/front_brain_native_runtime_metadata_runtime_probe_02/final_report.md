# Final Report: FRONT-BRAIN-NATIVE-RUNTIME-METADATA-RUNTIME-PROBE-02

**Branch:** `codex/own-capital-sustainable-return`  
**Baseline:** `3c01aa64`  
**Date:** 2026-06-29  
**Status:** ✅ Verified

## Objective

Runtime-probe `POST /v2/chat/agent` to prove that:

1. `capability_metadata` is returned in the live API path (not only via the static helper).
2. `NativeAgentRuntimeV2` remains the active backend.
3. LangGraph is **not** activated.
4. Governance and security are **not** weakened.

## Artifacts produced

- `tests/smoke/test_brain_native_runtime_metadata_runtime_probe_02.py`
- `tmp_agent/front_brain_native_runtime_metadata_runtime_probe_02/runtime_probe.json`
- `tmp_agent/front_brain_native_runtime_metadata_runtime_probe_02/runtime_probe.md`
- `tmp_agent/front_brain_native_runtime_metadata_runtime_probe_02/final_report.json`
- `tmp_agent/front_brain_native_runtime_metadata_runtime_probe_02/final_report.md`

No source runtime files (`native_runtime.py`, `runtime.py`, `main.py`, governance, memory, FAISS, trading, `.env`) were modified.

## Validation results

```
tests/smoke/test_brain_native_runtime_metadata_runtime_probe_02.py
15 passed, 0 failed
```

All 14 required metadata keys were observed in live responses:

`memory_used`, `retrieval_attempted`, `retrieval_no_results`, `retrieval_skipped`, `planner_used`, `evidence_routed`, `evidence_sources_count`, `tools_considered`, `tools_executed`, `tools_blocked`, `governance_checked`, `trace_events_count`, `intent_route`, `classification`.

## Runtime observations

| Check | Result |
|-------|--------|
| Active backend | `native_runtime` |
| Active runtime class | `NativeAgentRuntimeV2` |
| LangGraph active | No |
| Route `/v2/chat/agent` exists | Yes |
| `capability_metadata` in live response | Yes |
| `trace_events_count` included | Yes |
| Governance enforced for write intent in `read_only` | Yes |
| Sensitive paths staged | No (`SAFE`) |
| `native_runtime.py` untouched | Confirmed |

## Security / safety controls

- Strict-operator access was overridden **only in the test sandbox** by patching `brain_v9.api_security.require_strict_operator_access.__code__` before importing `app`.
- `finalize_agent_run` was monkeypatched to avoid live LLM calls.
- No memory writes, FAISS mutations, trading actions, broker calls, or source edits occurred.
- The write-intent probe confirmed that `file_patch_apply_approval_required` is blocked in `read_only` mode and `governance_checked=True` is reported.

## Conclusion

The runtime probe confirms the prior implementation front exposed `capability_metadata` through the live `/v2/chat/agent` path with `NativeAgentRuntimeV2` as the active backend, without weakening governance or activating LangGraph.
