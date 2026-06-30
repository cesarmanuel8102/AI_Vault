## Phase 1 — Current Live-Chat Gap Diagnosis

### Service status at baseline `0df9508`

| Endpoint | Status | Notes |
|---|---|---|
| `/health` | 200 OK | healthy |
| `/v2/agent/status` | 200 OK | `backend=langgraph_parity`, `langgraph_default_active=true`, `rollback_backend=native_runtime` |
| `/v2/chat/agent` | 200 OK | response uses `provider_used="deterministic_parity_finalizer"`, `model_used="parity_v1_full"` |
| `/v2/agent/capabilities` | **500** | `LangGraphParityRuntimeV2` has no `list_capabilities` |
| `/ui/` | 200 OK | served |
| Trace URL | 200 OK | exists but only 2 events (run_created, run_completed) |

### Critical gaps

1. **Deterministic finalizer is primary.** `LangGraphParityRuntimeV2._finalizer_node` always calls `_deterministic_finalizer`, producing generic parity text. Real LLM (`finalize_agent_run`) is never invoked.
2. **Capabilities endpoint returns 500.** Missing `list_capabilities` on the default runtime blocks the required capability matrix.
3. **Intent classification is coarse.** `AgentV2IntentAdapter` returns legacy intents (`QUERY`, `CONVERSATION`, `COMMAND`) and routes (`direct_assistant`, `brain_evidence`, `operational_agent`). It does not classify the required semantic intents (e.g., `explain_capabilities`, `dashboard_diagnosis`, `code_change_request`, `trading_broker_live`).
4. **Governance lacks explicit policy table.** Write-tool blocking works, but there is no explicit decision engine for trading/IBKR, delete, memory-write, autonomy, self-improvement.
5. **Trace lacks required metadata.** Trace events do not carry `intent_detected`, `route_selected`, `governance_decision`, `tools_considered`, `tools_executed`, `fallback_reason` in a structured way.
6. **Dashboard shows fallback only partially.** It displays `latest_provider_used` but not a full capability/truthful metadata panel.

### Why this blocks real Brain Agent V2 usage

The user can chat, but every answer is a deterministic parity stub. The agent cannot explain capabilities truthfully, cannot route nuanced Spanish/English intents, and cannot demonstrate real LLM reasoning. Unsafe actions are not consistently classified and escalated. The capabilities endpoint, required by the acceptance contract, is broken.
