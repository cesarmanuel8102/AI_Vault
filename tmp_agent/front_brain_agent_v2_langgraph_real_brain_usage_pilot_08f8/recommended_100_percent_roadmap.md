# Recommended 100% Roadmap — 08F8

| Priority | Front | Goal |
|---|---|---|
| 1 | FRONT-BRAIN-AGENT-V2-GOVERNANCE-HARDENING-08F8-R1 | Surface approval_required, blocked_tools, and required_permission in /v2/chat/agent for unsafe actions |
| 2 | FRONT-BRAIN-AGENT-V2-INTENT-ROUTER-NL-GOVERNANCE-08F8-R2 | Implement fine-grained Spanish/English intent classification with read-only/build/trading/memory labels |
| 3 | FRONT-BRAIN-AGENT-V2-TOOLS-EXECUTION-08F8-R3 | Wire repo/file/safe-shell tool execution into operational_agent route |
| 4 | FRONT-BRAIN-AGENT-V2-LANGGRAPH-STATE-PERSISTENCE-08F8-R4 | Implement real pause/resume/cancel with checkpoint persistence |
| 5 | FRONT-BRAIN-AGENT-V2-AUTONOMY-DRYRUN-LOOP-08F8-R5 | Enable dry-run autonomy loop with journal, max steps, and human approval gates |
| 6 | FRONT-BRAIN-AGENT-V2-MEMORY-RETRIEVAL-READONLY-PILOT-08F8-R6 | Activate read-only memory/retrieval in chat route |
| 7 | FRONT-BRAIN-AGENT-V2-MODEL-ROUTING-COST-POLICY-08F8-R7 | Expose actual model provider, model name, and cost/latency metadata |
| 8 | FRONT-BRAIN-AGENT-V2-DASHBOARD-TRACE-OBSERVABILITY-08F8-R8 | Fix roadmap governance warning and enrich dashboard run/fallback views |
| 9 | FRONT-BRAIN-AGENT-V2-CAPABILITIES-ENDPOINT-08F8-R9 | Add list_capabilities to LangGraphParityRuntimeV2 |
| 10 | FRONT-BRAIN-AGENT-V2-SELF-IMPROVEMENT-REPORTONLY-LOOP-08F8-R10 | Implement report-only self-improvement critique loop |
| 11 | FRONT-BRAIN-AGENT-V2-PRODUCTION-READINESS-GATES-08F8-R11 | End-to-end real LLM integration test and cost cap policy |

## Production readiness gates
- All P0 gaps closed
- Governance blocks trading/broker/memory writes without approval
- Autonomy runs only dry-run unless explicitly approved
- Self-improvement never edits files without approval
- Fallback to Native works with a single env var
- Dashboard exposes backend, fallback, and trace
- CI green on phase1 + nontrading-smoke-regression

