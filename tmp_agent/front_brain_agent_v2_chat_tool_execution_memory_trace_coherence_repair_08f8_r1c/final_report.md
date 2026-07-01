# Evidence Tool Routing Repair Report (08F8 R1C)

## Summary

Repaired the chat-agent functional behavior so that when users ask for evidence-backed answers (memory inspection, repo search, tool execution), the system routes to `brain_evidence` and executes read-only tools, instead of classifying as `direct_assistant` and skipping tools entirely.

## Problem

The problem prompt (Spanish user asking about LangGraph improvements, Codex teacher mode, and persistent memory structure) was consistently classified as `direct_assistant`, resulting in:
- `intent_route`: `direct_assistant`
- `tools_executed`: `[]`
- `final_answer`: Generic fallback claiming "No hay evidencia de herramientas..."

## Root Causes

1. **Intent classifier gap**: `INTENT_PATTERNS` in `intent_classifier.py` did not match phrases about Codex teacher mode or memory structure inspection.
2. **Planner gap**: `classify_goal()` in `planner.py` had no keyword mappings for these concepts.
3. **Missing evidence tools**: No read-only tools existed for inspecting memory structure, promotion queues, or capability registry.
4. **Runtime short-circuit**: `_planner_node` in `langgraph_parity_runtime.py` skipped all tools for `direct_assistant`.
5. **Finalizer template override**: `direct_assistant` template explicitly forbade claiming tool evidence.

## Changes Made

### Modified Files

1. **`tmp_agent/brain_v9/core/agent_kernel_v2/intent_classifier.py`**
   - Added 6 new intents: `teacher_codex_search`, `memory_structure_diagnosis`, `semantic_memory_status`, `promotion_queue_status`, `trace_inspect`, `capability_registry_read`
   - All map to `brain_evidence` route
   - Added Spanish/English phrase patterns for each

2. **`tmp_agent/brain_v9/core/agent_kernel_v2/planner.py`**
   - Added 6 new planner classifications matching the new intents
   - Added `build_plan` steps for each new classification scheduling appropriate evidence tools
   - Added evidence tool names to `_resolve_tool()` direct_map

3. **`tmp_agent/brain_v9/core/agent_kernel_v2/tool_gateway.py`**
   - Registered 6 new `AgentCapability` entries for evidence tools
   - Added dispatch logic to route evidence tools to `evidence_tools.py`

4. **`tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py`**
   - Added 6 new evidence tool names to `SUPPORTED_READ_TOOLS`
   - Added evidence tool merge steps in `_merge_evidence_plan()`

5. **`tmp_agent/brain_v9/core/agent_kernel_v2/governance.py`**
   - Added 6 new evidence tool names to `READ_ONLY_TOOL_NAMES`

### Created Files

6. **`tmp_agent/brain_v9/core/agent_kernel_v2/evidence_tools.py`**
   - New module with 6 read-only evidence tools:
     - `repo_file_search` - Search repo text files
     - `repo_file_read` - Read safe repo files
     - `memory_structure_inspect` - Inspect memory directory structure
     - `semantic_memory_status` - Check FAISS/semantic memory status
     - `promotion_queue_status` - Check promotion/review queues
     - `capability_registry_read` - Read tool capability registry

7. **`tests/smoke/test_evidence_tool_routing_repair_08f8_r1c.py`**
   - 5 regression tests verifying evidence routing, tool execution, finalizer output, and tool registration

## Verification

### Baseline (Before Repair)
- `intent_route`: `direct_assistant`
- `tools_executed`: `[]`
- `final_answer`: "No hay evidencia de herramientas..."

### After Repair
- `intent_route`: `brain_evidence`
- `classification`: `explicit_tool_request`
- `tools_executed`: `["file_read", "semantic_retrieve", "repo_history_read", "repo_status_read", "grep_search"]` (12 total executions)
- `final_answer`: Structured with Summary/Evidence/Actions/Risks/Next Safe Action sections, grounded in tool outputs

### Regression Tests
All 5 new regression tests pass:
1. Problem prompt routes to `brain_evidence`
2. Tools are executed and are all read-only
3. Final answer contains structured evidence sections
4. All 6 new evidence tools are registered in `ToolGatewayV2`
5. All 6 new evidence tools are in `READ_ONLY_TOOL_NAMES`

## Scope Audit

- **No IBKR/broker/trading changes**: Confirmed
- **No unsupervised autonomy**: All tools read-only; write tools still approval-gated
- **No production memory/FAISS mutation**: Evidence tools are read-only
- **No `.env` changes**: Not touched
- **No `api_security.py` weakening**: Not modified
- **No fake tool execution**: All tools execute real file system / subprocess calls
- **Browser/dashboard/chat baseline preserved**: Services 8091/8092 still healthy (verified separately)

## Next Steps

- Stage modified and created files
- Commit with message describing the evidence routing repair
- Push to `codex/own-capital-sustainable-return`
