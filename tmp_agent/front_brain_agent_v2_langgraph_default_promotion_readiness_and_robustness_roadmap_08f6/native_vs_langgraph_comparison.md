# Native vs LangGraph Comparison — 08F6

## Scope

Evidence-driven comparison of `NativeAgentRuntimeV2` vs `LangGraphParityRuntimeV2` across 18 dimensions relevant to default promotion.

## Summary

| Outcome | Count |
|---|---|
| Native stronger | 5 |
| LangGraph stronger | 8 |
| Equivalent | 5 |
| Blockers for default promotion | 2 |

## Overall assessment

LangGraph is structurally better aligned with Brain's long-term agentic orchestration goals, but it is not yet a production-complete replacement for Native. Two blocking gaps must be closed before default promotion can be considered:

1. Runtime contract completeness: LangGraph is missing `plan_run`, `pause_run`, `resume_run`, and `cancel_run`.
2. Checkpoint/resume readiness: no pause/resume methods, and the resume path is unverified.

## Comparison table

| ID | Dimension | Native | LangGraph | Classification | Blocker |
|---|---|---|---|---|---|
| C-01 | Runtime contract completeness | Full 9-method interface | Missing plan/pause/resume/cancel | Native stronger | YES |
| C-02 | State persistence | run.json + CheckpointStore + TraceStore under RUN_ROOT | Same stores under caller-provided run_root | Equivalent | NO |
| C-03 | Trace quality | Step events, provider metadata, mode escalation | Graph-node events, node_path, capability metadata | LangGraph stronger | NO |
| C-04 | Checkpoint/resume readiness | pause_run/resume_run exist | No pause/resume methods | Native stronger | YES |
| C-05 | Human-in-the-loop suitability | Governance inside execute_run | Governance gate node, mode_effective escalation | Equivalent | NO |
| C-06 | Failure containment | Try/except around load/execute | Graph timeout, malformed state handling | LangGraph stronger | NO |
| C-07 | Timeout/circuit-breaker | No explicit timeout | 30s ThreadPoolExecutor wrapper | LangGraph stronger | NO |
| C-08 | Malformed run handling | KeyError/may raise | Validated required fields, failed stub | LangGraph stronger | NO |
| C-09 | Write-intent escalation | validate_mode + infer_auto_decision | escalate_auto_mode_effective node | Equivalent | NO |
| C-10 | Fallback to Native | Already default | runtime.py safe fallback | Equivalent | NO |
| C-11 | Dashboard compatibility | Status shows native_runtime | backend metadata exposed; fallback_reason not in dashboard | Native stronger | NO |
| C-12 | Test coverage | 17 tests across selector + dashboard | 20 tests across contract + failure modes | Equivalent | NO |
| C-13 | CI coverage | Green with Native default | Green with env opt-in; no separate CI matrix | Equivalent | NO |
| C-14 | Maintainability | ~505 lines, linear | ~1334 lines + graph wiring | Native stronger | NO |
| C-15 | Fit with long-term goal | Stable but harder to extend | Designed for durable execution, HITL, sub-agents | LangGraph stronger | NO |
| C-16 | Fit with multi-agent orchestration | No sub-agent harness | Graph nodes can host sub-agent roles | LangGraph stronger | NO |
| C-17 | Fit with memory/knowledge evolution | MemoryGatewayV2 direct | memory_retrieval + evidence_routing nodes | LangGraph stronger | NO |
| C-18 | Fit with tool governance | Governance inside execute_run | Explicit governance gate node | LangGraph stronger | NO |

## Phase result

PHASE 2 — Native vs LangGraph comparison: **COMPLETED**

## Recorded

`2026-06-30T18:15:00+00:00`
