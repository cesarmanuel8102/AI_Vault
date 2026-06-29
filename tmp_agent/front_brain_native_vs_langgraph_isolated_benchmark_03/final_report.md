# Final Report: FRONT-BRAIN-NATIVE-VS-LANGGRAPH-ISOLATED-BENCHMARK-03

**Branch:** `codex/own-capital-sustainable-return`  
**Starting head:** `c58e2a6`  
**Date:** 2026-06-29

## Goal

Determine whether LangGraph is worth wiring into Brain later by comparing it against the current `NativeAgentRuntimeV2` path in an isolated benchmark, without modifying production runtime wiring.

## What was done

1. **State lock** — verified branch and HEAD match remote, no tracked diff, guard SAFE.
2. **Static inventory** — inspected runtime selector, native runtime, and langgraph runtime files.
3. **Smoke test** — created deterministic benchmark in `tests/smoke/test_brain_native_vs_langgraph_isolated_benchmark_03.py`.
4. **Native probe** — used FastAPI TestClient against `/v2/chat/agent` with strict-operator override and finalizer monkeypatch; confirmed `capability_metadata`, native backend, and governance.
5. **LangGraph probe** — imported `LangGraphAgentRuntimeV2`, instantiated it, and ran isolated `graph_probe()` safely.
6. **Scorecard** — scored both runtimes across 13 dimensions.
7. **Reports** — wrote native/langgraph probes, scorecard, and final report.

## Source files modified

None.

## Files created

- `tests/smoke/test_brain_native_vs_langgraph_isolated_benchmark_03.py`
- `tmp_agent/front_brain_native_vs_langgraph_isolated_benchmark_03/static_inventory.json`
- `tmp_agent/front_brain_native_vs_langgraph_isolated_benchmark_03/native_probe.json`
- `tmp_agent/front_brain_native_vs_langgraph_isolated_benchmark_03/langgraph_probe.json`
- `tmp_agent/front_brain_native_vs_langgraph_isolated_benchmark_03/comparison_scorecard.json`
- `tmp_agent/front_brain_native_vs_langgraph_isolated_benchmark_03/comparison_scorecard.md`
- `tmp_agent/front_brain_native_vs_langgraph_isolated_benchmark_03/final_report.json`
- `tmp_agent/front_brain_native_vs_langgraph_isolated_benchmark_03/final_report.md`

## Native V2 probe summary

- Endpoint: `POST /v2/chat/agent`
- Status: `200 OK`
- Backend: `native_runtime`
- Runtime class: `NativeAgentRuntimeV2`
- `capability_metadata`: present with all 14 required keys
- Governance: write intent blocked in `read_only` mode
- Source modified: no

## LangGraph probe summary

- File exists: yes
- Importable: yes
- Instantiable: yes
- `graph_probe()` executed: yes (toy StateGraph ran plan → retrieve → tools → final)
- Production wired: no
- MemoryGatewayV2 / ToolGatewayV2 / governance / trace / checkpointer: none wired
- Classification: `LANGGRAPH_EXECUTABLE_ISOLATED`

## Scorecard summary

| Runtime | Normalized Score | Classification | Decision |
|---------|------------------|----------------|----------|
| Native V2 | 80 / 100 | `PRODUCTION_CANONICAL` | **KEEP_NATIVE_V2_AND_IMPROVE** |
| LangGraph | 19 / 100 | `LANGGRAPH_EXECUTABLE_ISOLATED` | Not production-ready |

## Decision

**`KEEP_NATIVE_V2_AND_IMPROVE`**

LangGraph executes in isolation but has no production integration, no measurable advantage over Native V2, and lacks governance/memory/tool/trace wiring. Wiring it now would introduce risk without proven benefit.

## Recommended next action

**A. Continue improving Native V2 with capability-driven patches**

## Governance / safety status

- Governance preserved.
- Memory, FAISS, trading, broker, QC, QuantConnect, and `.env` untouched.
- LangGraph not activated as default runtime.
- `/v2/chat/agent` remains routed to NativeAgentRuntimeV2.
