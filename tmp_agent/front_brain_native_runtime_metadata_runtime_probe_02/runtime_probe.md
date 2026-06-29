# Runtime Probe: Front Brain Native Runtime Capability Metadata (02)

**Date:** 2026-06-29
**Branch:** `codex/own-capital-sustainable-return`
**Baseline:** `3c01aa64`
**Endpoint:** `POST /v2/chat/agent`
**Runtime backend probed:** `NativeAgentRuntimeV2`

## Summary

Live TestClient probes against `/v2/chat/agent` confirm that `capability_metadata` is returned in the actual API response path, not only through the static helper. `NativeAgentRuntimeV2` remains the active backend, LangGraph is not activated, and governance/security behavior is preserved.

## Runtime selector verification

| Property | Observed value |
|----------|----------------|
| `rt.backend` | `native_runtime` |
| `type(rt).__name__` | `NativeAgentRuntimeV2` |

## Probe cases

### 1. Brain evidence query (read_only)

**Request body:** `{"message": "What is the status of the brain gate approve endpoint?", "mode": "read_only"}`

**Result:** `200 OK`

| `capability_metadata` key | Observed value |
|---------------------------|----------------|
| `memory_used` | `false` |
| `retrieval_attempted` | `false` |
| `retrieval_no_results` | `false` |
| `retrieval_skipped` | `true` |
| `planner_used` | `true` |
| `evidence_routed` | `true` |
| `evidence_sources_count` | `2` |
| `tools_considered` | `12` |
| `tools_executed` | `12` |
| `tools_blocked` | `0` |
| `governance_checked` | `false` |
| `trace_events_count` | `28` |
| `intent_route` | `brain_evidence` |
| `classification` | `brain_evidence` |

All 14 required metadata keys are present in the live response.

### 2. Direct assistant greeting (read_only)

**Request body:** `{"message": "hi", "mode": "read_only"}`

**Result:** `200 OK`

- `intent_route`: `direct_assistant`
- `planner_used`: `false`
- `retrieval_skipped`: `false` (direct-assistant routes are exempt from the skip rule)
- `trace_events_count`: `4`

### 3. Write intent in read_only mode (governance probe)

**Request body:** `{"message": "apply patch to README.md", "mode": "read_only"}`

**Result:** `200 OK`

- `intent_route`: `operational_agent`
- `classification`: `approval_required_write`
- `mode_escalation_required`: `true`
- `blocked_tools`: `["file_patch_apply_approval_required"]`
- `capability_metadata.governance_checked`: `true`
- `capability_metadata.tools_blocked`: `1`

The write tool was scheduled, correctly blocked, and the response reflects active governance enforcement. No file was modified.

## Security / governance observations

- Strict-operator access was overridden **only inside the test/probe sandbox** by patching `brain_v9.api_security.require_strict_operator_access.__code__` before importing `app`.
- Live LLM calls were avoided by monkeypatching `brain_v9.core.agent_kernel_v2.finalizer.finalize_agent_run`.
- No memory writes, FAISS mutations, trading actions, broker calls, or source-file edits occurred.
- `native_runtime.py` does **not** contain `capability_metadata`; the field is added in `api_adapter.py` and derived via `_build_capability_metadata`.
- The staging guard script reports `SAFE` for the current working tree.

## Conclusion

The runtime probe confirms the previous implementation front exposed `capability_metadata` through the live `/v2/chat/agent` path with `NativeAgentRuntimeV2` as the active backend, without weakening governance or activating LangGraph.

See `runtime_probe.json` for the full raw response payloads.
