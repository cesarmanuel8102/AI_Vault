# Fair Full Parity Benchmark 08B Scorecard

- **Native core score:** 850 / 900
- **LangGraph core score:** 880 / 900
- **LangGraph with architecture bonus:** 930 / 950
- **Architecture bonus:** 50
- **Decision:** A — opt-in_backend_blueprint

## Native by scenario
- direct_assistant: 100/100
- brain_evidence_endpoint: 100/100
- repo_status_tool_request: 100/100
- write_intent_blocked: 100/100
- protected_governance_write: 85/100
- mixed_runtime_comparison: 100/100
- memory_question: 100/100
- unsupported_or_risky_tool: 85/100
- follow_up_context: 80/100

## LangGraph by scenario
- direct_assistant: 100/100
- brain_evidence_endpoint: 100/100
- repo_status_tool_request: 100/100
- write_intent_blocked: 100/100
- protected_governance_write: 100/100
- mixed_runtime_comparison: 100/100
- memory_question: 100/100
- unsupported_or_risky_tool: 100/100
- follow_up_context: 80/100

## Dimension winners
- route_correct: native
- task_completed: native
- tool_or_evidence_adequate: native
- governance_correct: langgraph_parity
- metadata_complete: native
- trace_or_checkpoint: native
- no_unsafe_side_effects: native

## Rationale
- LangGraph parity runtime scores at or above Native V2 across core scenarios when architecture bonus is included.
- Graph streaming is supported without production wiring changes.
- Backend flag readiness probe confirms opt-in blueprint is feasible without changing default runtime.
- Governance and side-effect controls pass all shared scenarios.
